import time
import os
import sys
import getpass  # 비밀번호 입력 시 화면에 안 보이게 하는 라이브러리

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

    # 1. 환경변수에 없으면 입력 요청
    if not user_id:
        try:
            print("\n [Input] 환경변수에 WEIN_ID가 없습니다.")
            user_id = input(" ▶ 위인전 아이디를 입력하세요: ")
        except EOFError:
            # Docker 백그라운드 실행 시 입력 불가하므로 에러 처리
            print(" [!] Error: Docker 백그라운드 모드에서는 입력을 받을 수 없습니다. 환경변수를 설정해주세요.")
            return None, None

    if not user_pw:
        try:
            if not user_id: return None, None # ID 입력하다 취소했을 경우
            # 비밀번호는 입력할 때 화면에 안 보이게 처리 (getpass)
            user_pw = getpass.getpass(" ▶ 위인전 비밀번호를 입력하세요: ")
        except EOFError:
            print(" [!] Error: Docker 백그라운드 모드에서는 입력을 받을 수 없습니다.")
            return None, None
            
    return user_id, user_pw

def main():
    # --- [설정 가져오기 (수정됨)] ---
    user_id, user_pw = get_user_credentials()
    
    if not user_id or not user_pw:
        print(" [!] 인증 정보가 없어 프로그램을 종료합니다.")
        return

    done_queue = os.getenv("WEIN_DONE_QUEUE", "wein_updates_done")

    # --- [브로커 연결] ---
    print(f" [*] RabbitMQ 브로커에 연결 중... (User: {user_id})")
    broker = EventBroker(queue_name=done_queue)

    while True:
        print(f"\n [Cycle] 크롤링 시작... ({time.strftime('%H:%M:%S')})")
        
        try:
            # 1. 크롤러 실행
            results = crawler.crawl_weinzon(user_id, user_pw)
            
            if results:
                print(f" [Crawling] {len(results)}건 수집 성공. 전송 준비...")
                # DB 직접 저장
                with SessionLocal() as db:
                    crud.save_programs(db, results)
                # 완료 이벤트만 발행 (데이터 미포함)
                broker.publish(
                    {
                        "event_type": "CRAWLING_COMPLETE",
                        "timestamp": time.time(),
                        "count": len(results),
                    }
                )
            else:
                print(" [Crawling] 수집된 데이터가 없습니다.")

        except Exception as e:
            print(f" [Error] 크롤링/전송 중 오류 발생: {e}")

        print(" [Sleep] 1시간 대기합니다...")
        time.sleep(3600)

if __name__ == "__main__":
    main()
