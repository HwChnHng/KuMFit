import time
import os
import sys
import getpass
import re
from datetime import datetime

from broker.event_broker import EventBroker
from common import crud
from common.database import SessionLocal

try:
    import wein_crawler as crawler
except ImportError:
    import importlib
    crawler = importlib.import_module("wein-crawler")

def get_user_credentials():
    """환경변수에서 먼저 찾고, 없으면 사용자에게 입력받는 함수"""
    user_id = os.getenv("WEIN_ID")
    user_pw = os.getenv("WEIN_PW")

    if not user_id:
        try:
            print("\n [Input] 환경변수에 WEIN_ID가 없습니다.")
            user_id = input(" ▶ 위인전 아이디를 입력하세요: ")
        except EOFError:
            print(" [!] Error: Docker 백그라운드 모드에서는 입력을 받을 수 없습니다.")
            return None, None

    if not user_pw:
        try:
            if not user_id: return None, None
            user_pw = getpass.getpass(" ▶ 위인전 비밀번호를 입력하세요: ")
        except EOFError:
            print(" [!] Error: Docker 백그라운드 모드에서는 입력을 받을 수 없습니다.")
            return None, None
            
    return user_id, user_pw

# [추가됨] 날짜 문자열 파싱 함수 ("2025.09.01 ~ 2025.09.30" -> datetime 객체 변환)
def parse_date_range(date_str):
    if not date_str:
        return None, None
    try:
        # 정규식으로 날짜 추출 (YYYY.MM.DD 형식)
        dates = re.findall(r"(\d{4})\.(\d{2})\.(\d{2})", date_str)
        if len(dates) >= 2:
            start_str = f"{dates[0][0]}-{dates[0][1]}-{dates[0][2]}"
            end_str = f"{dates[1][0]}-{dates[1][1]}-{dates[1][2]}"
            # 문자열을 datetime 객체로 변환
            start_dt = datetime.strptime(start_str, "%Y-%m-%d")
            end_dt = datetime.strptime(end_str, "%Y-%m-%d")
            return start_dt, end_dt
    except Exception as e:
        print(f"[Warn] 날짜 파싱 실패 ({date_str}): {e}")
    return None, None

def main():
    user_id, user_pw = get_user_credentials()
    
    if not user_id or not user_pw:
        print(" [!] 인증 정보가 없어 프로그램을 종료합니다.")
        return

    done_queue = os.getenv("WEIN_DONE_QUEUE", "wein_updates_done")
    print(f" [*] RabbitMQ 브로커에 연결 중... (User: {user_id})")
    broker = EventBroker(queue_name=done_queue)

    while True:
        print(f"\n [Cycle] 크롤링 시작... ({time.strftime('%H:%M:%S')})")
        
        try:
            # 1. 크롤러 실행 (여기서 'category', 'apply_period' 등의 키로 받아옴)
            raw_results = crawler.crawl_weinzon(user_id, user_pw)
            
            if raw_results:
                print(f" [Crawling] {len(raw_results)}건 수집 성공. 데이터 변환 및 전송 준비...")
                
                # 2. [핵심 수정] DB 스키마에 맞게 데이터 변환 (Mapping)
                db_data = []
                for item in raw_results:
                    # 날짜 파싱
                    start_dt, end_dt = parse_date_range(item.get("apply_period", ""))
                    
                    mapped_item = {
                        "title": item.get("title"),
                        "topic": item.get("category"),          # category -> topic 변환
                        "apply_start": start_dt,                # 문자열 -> datetime 변환
                        "apply_end": end_dt,                    # 문자열 -> datetime 변환
                        "run_time_text": item.get("run_period"),# run_period -> run_time_text 변환
                        "location": "",                         # 크롤러에 없으면 빈값
                        "target_audience": "",                  # 크롤러에 없으면 빈값
                        "mileage": 0,
                        "detail_url": ""
                    }
                    db_data.append(mapped_item)

                # 3. DB 저장 (변환된 데이터 사용)
                with SessionLocal() as db:
                    crud.save_programs(db, db_data)
                
                # 4. 완료 이벤트 발행
                broker.publish({
                    "event_type": "CRAWLING_COMPLETE",
                    "timestamp": time.time(),
                    "count": len(db_data),
                })
            else:
                print(" [Crawling] 수집된 데이터가 없습니다.")

        except Exception as e:
            print(f" [Error] 크롤링/전송 중 오류 발생: {e}")

        print(" [Sleep] 1시간 대기합니다...")
        time.sleep(3600)

if __name__ == "__main__":
    main()