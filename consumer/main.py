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
# [핵심] 시간 충돌 판별 로직 (요일 자동 계산 추가)
# -------------------------------
def is_time_overlap(start1, end1, start2, end2):
    """ 두 시간 범위(분 단위)가 겹치는지 확인 """
    return max(start1, start2) < min(end1, end2)

def parse_time_str(time_str):
    """ '14:00' -> 840 (분) """
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except:
        return None

def get_korean_weekday(date_obj):
    """ 날짜 객체 -> '월', '화' 변환 """
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[date_obj.weekday()]

# 에브리타임 결과 보정: +9시간, 끝시간은 2분 줄임
TIME_OFFSET_MIN = 9 * 60
END_TRIM_MIN = 2


def minutes_to_str(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def adjust_time_range(start_str: str, end_str: str):
    start_min = parse_time_str(start_str)
    end_min = parse_time_str(end_str)
    if start_min is None or end_min is None:
        return start_str, end_str

    start_adj = start_min + TIME_OFFSET_MIN
    end_adj = end_min + TIME_OFFSET_MIN - END_TRIM_MIN

    # 음수 방지 및 24시간 래핑
    start_adj = start_adj % (24 * 60)
    end_adj = end_adj % (24 * 60)

    return minutes_to_str(start_adj), minutes_to_str(end_adj)


def check_conflict(program, user_timetable):
    if not program.run_time_text:
        return False
        
    text = program.run_time_text
    
    # 정규식으로 날짜와 시간 추출
    # 예: "2025.12.30 10:00 ~ 2025.12.30 17:30"
    # 패턴: YYYY.MM.DD HH:MM
    pattern = r"(\d{4}\.\d{2}\.\d{2})\s+(\d{1,2}:\d{2})"
    matches = re.findall(pattern, text)
    
    if len(matches) < 2:
        # 날짜 형식이 아니거나 정보 부족하면 통과 (상시 활동 등)
        return False
        
    start_date_str, start_time_str = matches[0]
    end_date_str, end_time_str = matches[1]
    
    try:
        # 날짜 객체로 변환
        start_dt = datetime.strptime(start_date_str, "%Y.%m.%d")
        end_dt = datetime.strptime(end_date_str, "%Y.%m.%d")
        
        # [판단 1] 기간이 다른 날짜에 걸쳐 있다면? (장기 프로그램)
        # -> 보통 이런건 수업 시간이랑 1:1 비교가 무의미하므로 '충돌 없음'으로 간주
        if start_dt.date() != end_dt.date():
            return False 

        # [판단 2] 하루짜리 행사라면? -> 요일 계산해서 충돌 체크!
        target_day = get_korean_weekday(start_dt) # 예: "화"
        
        prog_start_min = parse_time_str(start_time_str)
        prog_end_min = parse_time_str(end_time_str)
        
        if prog_start_min is None or prog_end_min is None:
            return False

        # 사용자 시간표 루프
        for tt in user_timetable:
            if tt.day == target_day: # 요일 일치!
                class_start = parse_time_str(tt.start_time)
                class_end = parse_time_str(tt.end_time)
                
                if class_start and class_end:
                    # 시간 겹치는지 확인
                    if is_time_overlap(prog_start_min, prog_end_min, class_start, class_end):
                        print(f" [Conflict] '{program.title}'({target_day} {start_time_str}) 겹침 -> 수업: {tt.subject_name}")
                        return True # 충돌!

    except Exception as e:
        print(f" [Error] 날짜 파싱 실패 ({text}): {e}")
        return False
                    
    return False # 모든 검사 통과


# -------------------------------
# 추천 생성 (필터링 방식)
# -------------------------------
def generate_recommendations(student_id: str):
    recommendations = []
    
    with get_db() as db:
        all_programs = crud.get_all_programs(db)
        user_timetable = crud.get_timetables(db, student_id)
        
        print(f" [Debug] 추천 계산 시작: 프로그램 {len(all_programs)}개")

        for prog in all_programs:
            # 충돌이 '없는' 것만 추천
            if not check_conflict(prog, user_timetable):
                recommendations.append({
                    "title": prog.title,
                    "category": prog.topic or "일반",
                    "status": "추천 (공강)",
                    "program_id": prog.id
                })
        
        recommendations.sort(key=lambda x: x['program_id'], reverse=True)

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
            start_time = item.get("start", "")
            end_time = item.get("end", "")
            start_time, end_time = adjust_time_range(start_time, end_time)
            timetable.append({
                "day": item.get("day", ""),
                "start_time": start_time,
                "end_time": end_time,
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
