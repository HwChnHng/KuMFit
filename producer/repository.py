from typing import Dict, List

from common import crud
from common.database import get_db


def save_programs(programs: List[Dict]):
    if not programs:
        return
    with get_db() as db:
        crud.save_programs(db, programs)
