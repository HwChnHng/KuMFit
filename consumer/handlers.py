import json
import os
from datetime import datetime

from domain import adjust_time_range, generate_recommendations
from messaging import publish
from repository import (
    get_all_programs,
    get_timetables,
    save_recommendation,
    save_timetables,
)
from schemas import CRAWL_DONE_SCHEMA, EVERYTIME_SCHEMA, validate_message

try:
    import everytime_crawler
except ImportError:
    everytime_crawler = None

EVERYTIME_URL_DEFAULT = os.getenv("EVERYTIME_URL")
CRAWL_DONE_QUEUE = os.getenv("CRAWL_DONE_QUEUE", "crawl_done")


def handle_everytime(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        if not validate_message(msg, EVERYTIME_SCHEMA):
            raise ValueError("invalid payload")

        student_id = msg.get("studentId")
        timetable_url = msg.get("timetableUrl") or EVERYTIME_URL_DEFAULT
        print(f" [everytime] sync 요청 수신: {student_id}")

        raw_tt = []
        if everytime_crawler:
            raw_tt = everytime_crawler.crawl_shared_timetable(timetable_url)

        timetable = []
        for item in raw_tt:
            start_time = item.get("start", "")
            end_time = item.get("end", "")
            start_time, end_time = adjust_time_range(start_time, end_time)
            timetable.append(
                {
                    "day": item.get("day", ""),
                    "start_time": start_time,
                    "end_time": end_time,
                    "subject_name": item.get("subject_name") or item.get("title", ""),
                    "classroom": item.get("classroom", ""),
                }
            )

        save_timetables(student_id, timetable)
        print(f" [everytime] 저장 완료: {len(timetable)}건")

        publish(CRAWL_DONE_QUEUE, {"type": "crawl_done", "studentId": student_id})
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f" [Error] everytime handle: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def handle_crawl_done(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        if not validate_message(msg, CRAWL_DONE_SCHEMA):
            raise ValueError("invalid payload")

        student_id = msg.get("studentId")
        print(f" [recommend] 추천 생성 시작: {student_id}")

        programs = get_all_programs()
        user_timetable = get_timetables(student_id)
        recs = generate_recommendations(programs, user_timetable, now=datetime.now())

        save_recommendation(student_id, recs)
        print(f" [recommend] 추천 완료: {len(recs)}건 저장")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f" [Error] recommend handle: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
