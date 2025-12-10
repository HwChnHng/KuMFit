EVERYTIME_SCHEMA = {
    "required": ["studentId"],
    "optional": ["timetableUrl"],
}

CRAWL_DONE_SCHEMA = {
    "required": ["studentId"],
    "optional": [],
}


def validate_message(msg: dict, schema: dict) -> bool:
    """필수 키가 존재하는지 최소한으로 검증"""
    if not isinstance(msg, dict):
        return False
    required = schema.get("required", [])
    return all(k in msg and msg[k] is not None for k in required)
