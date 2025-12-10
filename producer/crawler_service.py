import re
from datetime import datetime, timedelta, timezone

try:
    import wein_crawler as crawler
except ImportError:
    import importlib

    crawler = importlib.import_module("wein-crawler")


def _parse_date_range(date_str: str):
    """예: '2025.09.01 ~ 2025.09.30' -> (datetime, datetime)"""
    if not date_str:
        return None, None
    try:
        kst = timezone(timedelta(hours=9))
        dates = re.findall(r"(\d{4})\.(\d{2})\.(\d{2})", date_str)
        if len(dates) >= 2:
            start_str = f"{dates[0][0]}-{dates[0][1]}-{dates[0][2]}"
            end_str = f"{dates[1][0]}-{dates[1][1]}-{dates[1][2]}"
            # 파싱된 날짜를 KST 기준으로 저장(naive로 떨어뜨리기 전에 KST tzinfo 적용)
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=kst).astimezone(kst).replace(tzinfo=None)
            end_dt = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=kst).astimezone(kst).replace(tzinfo=None)
            return start_dt, end_dt
    except Exception as e:
        print(f"[Warn] 날짜 파싱 실패 ({date_str}): {e}")
    return None, None


def fetch_programs(user_id: str, user_pw: str):
    """크롤러 호출 후 DB 저장 스키마에 맞춰 맵핑된 리스트 반환"""
    raw_results = crawler.crawl_weinzon(user_id, user_pw)
    if not raw_results:
        return []

    mapped = []
    for item in raw_results:
        start_dt, end_dt = _parse_date_range(item.get("apply_period", ""))
        mapped.append(
            {
                "title": item.get("title"),
                "topic": item.get("category"),
                "apply_start": start_dt,
                "apply_end": end_dt,
                "run_time_text": item.get("run_period"),
                "location": "",
                "target_audience": "",
                "mileage": 0,
                "detail_url": "",
            }
        )
    return mapped
