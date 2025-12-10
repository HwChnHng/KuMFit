from typing import Dict, List

from common import crud
from common.database import get_db


def save_timetables(student_id: str, timetable: List[Dict]):
    with get_db() as db:
        if timetable:
            crud.save_timetables(db, student_id, timetable)


def get_timetables(student_id: str):
    with get_db() as db:
        return crud.get_timetables(db, student_id)


def get_all_programs():
    with get_db() as db:
        return crud.get_all_programs(db)


def save_recommendation(student_id: str, results: List[Dict]):
    with get_db() as db:
        crud.save_recommendation(db, student_id, results)
