from typing import Dict, List

from common import crud
from common.database import SessionLocal


def save_programs(programs: List[Dict]):
    if not programs:
        return
    with SessionLocal() as db:
        crud.save_programs(db, programs)
