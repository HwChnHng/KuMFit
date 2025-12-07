import json
import os
import threading
import time

import pika

from broker.event_broker import EventBroker
from common import crud
from common.database import get_db, init_db

# 에브리타임 크롤러 (producer 폴더의 파일을 컨테이너에 복사)
try:
    import everytime_crawler
except ImportError:
    everytime_crawler = None

# --- 설정 ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
EVERYTIME_QUEUE = os.getenv("EVERYTIME_QUEUE", "everytime_sync")
CRAWL_DONE_QUEUE = os.getenv("CRAWL_DONE_QUEUE", "crawl_done")
EVERYTIME_URL_DEFAULT = os.getenv("EVERYTIME_URL")


def publish(queue_name: str, payload: dict):
    broker = EventBroker(queue_name=queue_name)
    broker.publish(payload)
    broker.close()


# -------------------------------
# 에브리타임 동기화 처리
# -------------------------------
def crawl_everytime(student_id: str):
    if everytime_crawler is None:
        raise RuntimeError("everytime_crawler 모듈을 불러오지 못했습니다.")
    # student_id로 URL을 알 수 없으므로, 메시지에 timetableUrl을 포함하거나
    # 환경변수 EVERYTIME_URL을 사용하도록 합니다.
    raise NotImplementedError("timetableUrl 또는 EVERYTIME_URL이 필요합니다.")


def handle_everytime(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        student_id = msg.get("studentId")
        timetable_url = msg.get("timetableUrl") or EVERYTIME_URL_DEFAULT
        if not student_id:
            raise ValueError("studentId missing")
        if not timetable_url:
            print(" [everytime] timetableUrl/EVERYTIME_URL 없음. 메시지 건너뜀")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        print(f" [everytime] sync 요청 수신: {student_id}")

        # 실제 크롤링
        try:
            raw_tt = everytime_crawler.crawl_shared_timetable(timetable_url)
        except Exception as e:
            print(f" [everytime] 크롤링 실패: {e}")
            raw_tt = []

        # 크롤러 결과 → DB 스키마에 맞게 매핑
        timetable = []

        def to_min(tstr: str):
            try:
                h, m = tstr.split(":")
                return int(h) * 60 + int(m)
            except Exception:
                return None

        def fmt_min(total_min: int):
            total_min = total_min % (24 * 60)
            h = total_min // 60
            m = total_min % 60
            return f"{h:02d}:{m:02d}"

        START_OFFSET = 9 * 60  # +9시간
        END_ADJUST = -2  # 종료 시간에서 2분 감소

        for idx, item in enumerate(raw_tt, start=1):
            start_raw = item.get("start") or item.get("start_time") or ""
            end_raw = item.get("end") or item.get("end_time") or ""
            start_min = to_min(start_raw)
            end_min = to_min(end_raw)

            if start_min is not None:
                start_min = start_min + START_OFFSET
            if end_min is not None:
                end_min = end_min + START_OFFSET + END_ADJUST

            timetable.append(
                {
                    "day": item.get("day", ""),
                    "start_time": fmt_min(start_min) if start_min is not None else "",
                    "end_time": fmt_min(end_min) if end_min is not None else "",
                    "subject_name": item.get("subject_name")
                    or item.get("title")
                    or f"Everytime 과목{idx}",
                    "classroom": item.get("classroom", ""),
                }
            )

        with get_db() as db:
            if timetable:
                crud.save_timetables(db, student_id, timetable)
                print(
                    f" [everytime] 시간표 저장 완료: {student_id}, {len(timetable)}건"
                )
            else:
                print(" [everytime] 저장할 시간표가 없습니다.")

        publish(
            CRAWL_DONE_QUEUE,
            {"type": "crawl_done", "source": "everytime", "studentId": student_id},
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f" [everytime] 처리 실패: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


# -------------------------------
# 추천 더미 생성
# -------------------------------
def generate_recommendations(student_id: str):
    with get_db() as db:
        programs = crud.get_all_programs(db)
    recs = []
    for prog in programs[:5]:
        recs.append(
            {
                "title": prog.title,
                "category": prog.topic or "비교과",
                "status": "추천",
            }
        )
    if not recs:
        recs.append(
            {
                "title": "샘플 추천 프로그램",
                "category": "기본",
                "status": "추천",
            }
        )
    return recs


def handle_crawl_done(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        student_id = msg.get("studentId")
        if not student_id:
            raise ValueError("studentId missing")

        print(f" [recommend] crawl_done 수신: {student_id}")
        recs = generate_recommendations(student_id)

        with get_db() as db:
            crud.save_recommendation(db, student_id, recs)
        print(f" [recommend] 추천 저장 완료: {student_id}, {len(recs)}건")

        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f" [recommend] 처리 실패: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


# -------------------------------
# 소비 루프
# -------------------------------
def consume(queue_name, callback):
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST)
            )
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            print(f" [consumer] 큐 소비 시작: {queue_name}")
            channel.start_consuming()
        except Exception as e:
            print(f" [consumer] 연결/처리 오류, 5초 후 재시도 ({queue_name}): {e}")
            time.sleep(5)


def main():
    print(" [*] Consumer 시작")
    init_db()

    threads = [
        threading.Thread(
            target=consume, args=(EVERYTIME_QUEUE, handle_everytime), daemon=True
        ),
        threading.Thread(
            target=consume, args=(CRAWL_DONE_QUEUE, handle_crawl_done), daemon=True
        ),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
