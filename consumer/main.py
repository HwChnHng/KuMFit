import json
import os
import threading
import time
import re
import pika
from datetime import datetime

# 공통 모듈 및 크롤러
from broker.event_broker import EventBroker
from common import crud
from common.database import get_db, init_db

try:
    import everytime_crawler
except ImportError:
    everytime_crawler = None

# --- 설정 ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
EVERYTIME_QUEUE = os.getenv("EVERYTIME_QUEUE", "everytime_sync")
CRAWL_DONE_QUEUE = os.getenv("CRAWL_DONE_QUEUE", "crawl_done")
EVERYTIME_URL_DEFAULT = os.getenv("EVERYTIME_URL")


# -------------------------------
# [핵심] 시간 충돌 판별 로직
# -------------------------------
def parse_korean_time(time_str):
    """ '14:00' 문자열을 분(minute) 단위 정수로 변환 """
    try:
        if not time_str: return None
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except:
        return None

def is_time_overlap(start1, end1, start2, end2):
    """ 두 시간 범위가 겹치는지 확인 (교집합이 있으면 True) """
    return max(start1, start2) < min(end1, end2)

def check_conflict(program, user_timetable):
    """
    프로그램 시간(텍스트)과 사용자 시간표(DB데이터)를 비교하여 겹치면 True 반환
    """
    # 1. 프로그램 시간 정보가 없으면 '충돌 없음'으로 간주 (상시 활동 등)
    if not program.run_time_text:
        return False
        
    text = program.run_time_text
    
    # 2. 프로그램 텍스트에서 '요일'과 '시간' 추출 (정규식 활용)
    # 예: "9/10(수) 14:00~16:00" -> 요일:수, 시작:14:00, 끝:16:00
    # 요일 패턴: (월) or 월요일 or 그냥 월
    days_found = re.findall(r"([월화수목금토일])", text)
    
    # 시간 패턴: 14:00~16:00 or 14:00-16:00
    time_match = re.search(r"(\d{1,2}:\d{2})\s*[~-]\s*(\d{1,2}:\d{2})", text)
    
    # 요일이나 시간이 명시되지 않았으면 충돌 판단 불가 -> '충돌 없음'으로 간주 (추천)
    if not days_found or not time_match:
        return False
        
    prog_start = parse_korean_time(time_match.group(1))
    prog_end = parse_korean_time(time_match.group(2))
    
    if prog_start is None or prog_end is None:
        return False

    # 3. 사용자 시간표와 비교
    for tt in user_timetable:
        # 요일이 같은 수업만 비교
        if tt.day in days_found: 
            class_start = parse_korean_time(tt.start_time)
            class_end = parse_korean_time(tt.end_time)
            
            if class_start is not None and class_end is not None:
                # 겹치면 충돌!
                if is_time_overlap(prog_start, prog_end, class_start, class_end):
                    return True
                    
    return False # 모든 수업과 비교했는데 안 겹침


# -------------------------------
# 추천 생성 (필터링 방식)
# -------------------------------
def generate_recommendations(student_id: str):
    recommendations = []
    
    with get_db() as db:
        # 1. 데이터 가져오기
        all_programs = crud.get_all_programs(db)
        user_timetable = crud.get_timetables(db, student_id)
        
        # 2. 필터링: 시간 충돌이 없는 프로그램만 추천
        for prog in all_programs:
            if not check_conflict(prog, user_timetable):
                recommendations.append({
                    "title": prog.title,
                    "category": prog.topic or "일반",
                    "status": "추천 (공강)",  # '신청가능' 대신 추천 사유 표시
                    "program_id": prog.id    # 정렬을 위해 ID 저장
                })
        
        # 3. 최신순 정렬 (ID 역순)
        recommendations.sort(key=lambda x: x['program_id'], reverse=True)

    # 결과가 없으면 안내 메시지
    if not recommendations:
        recommendations.append({
            "title": "공강 시간에 맞는 프로그램이 없습니다.",
            "category": "-",
            "status": ""
        })
        
    return recommendations


# -------------------------------
# 기존 로직 유지 (RabbitMQ 핸들러)
# -------------------------------
def publish(queue_name: str, payload: dict):
    broker = EventBroker(queue_name=queue_name)
    broker.publish(payload)
    broker.close()

def handle_everytime(ch, method, properties, body):
    # (이전 코드와 동일하므로 생략 가능하지만, 전체 파일 교체를 위해 포함)
    try:
        msg = json.loads(body.decode("utf-8"))
        student_id = msg.get("studentId")
        timetable_url = msg.get("timetableUrl") or EVERYTIME_URL_DEFAULT
        
        if not student_id: return

        print(f" [everytime] sync 요청 수신: {student_id}")
        
        if everytime_crawler:
            raw_tt = everytime_crawler.crawl_shared_timetable(timetable_url)
        else:
            raw_tt = []

        # DB 저장용 데이터 변환
        timetable = []
        for item in raw_tt:
            timetable.append({
                "day": item.get("day", ""),
                "start_time": item.get("start", ""),
                "end_time": item.get("end", ""),
                "subject_name": item.get("subject_name") or item.get("title", ""),
                "classroom": item.get("classroom", "")
            })

        with get_db() as db:
            if timetable:
                crud.save_timetables(db, student_id, timetable)
                print(f" [everytime] 저장 완료: {len(timetable)}건")

        # 크롤링 완료 알림 -> handle_crawl_done 실행 유도
        publish(CRAWL_DONE_QUEUE, {"type": "crawl_done", "studentId": student_id})
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f" [Error] everytime handle: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def handle_crawl_done(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        student_id = msg.get("studentId")
        
        print(f" [recommend] 추천 생성 시작: {student_id}")
        
        # ★ 위에서 만든 필터링 함수 호출
        recs = generate_recommendations(student_id)

        with get_db() as db:
            crud.save_recommendation(db, student_id, recs)
            
        print(f" [recommend] 추천 완료: {len(recs)}건 저장")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f" [Error] recommend handle: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def consume(queue_name, callback):
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            channel.start_consuming()
        except Exception as e:
            print(f" [Retry] {queue_name} 연결 재시도: {e}")
            time.sleep(5)

def main():
    print(" [*] Consumer 시작 (공강 시간 추천 모드)")
    init_db()

    t1 = threading.Thread(target=consume, args=(EVERYTIME_QUEUE, handle_everytime), daemon=True)
    t2 = threading.Thread(target=consume, args=(CRAWL_DONE_QUEUE, handle_crawl_done), daemon=True)
    
    t1.start()
    t2.start()
    t1.join()
    t2.join()

if __name__ == "__main__":
    main()