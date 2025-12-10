import re
from datetime import datetime

TIME_OFFSET_MIN = 9 * 60
END_TRIM_MIN = 2


def is_time_overlap(start1, end1, start2, end2):
    """두 시간 범위(분 단위)가 겹치는지 확인"""
    return max(start1, start2) < min(end1, end2)


def parse_time_str(time_str):
    """'14:00' -> 840 (분)"""
    try:
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    except Exception:
        return None


def get_korean_weekday(date_obj):
    """날짜 객체 -> '월', '화'"""
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[date_obj.weekday()]


def minutes_to_str(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def adjust_time_range(start_str: str, end_str: str):
    """에브리타임 시간 보정(+9h, 종료 2분 트림)"""
    start_min = parse_time_str(start_str)
    end_min = parse_time_str(end_str)
    if start_min is None or end_min is None:
        return start_str, end_str

    start_adj = start_min + TIME_OFFSET_MIN
    end_adj = end_min + TIME_OFFSET_MIN - END_TRIM_MIN

    start_adj %= 24 * 60
    end_adj %= 24 * 60

    return minutes_to_str(start_adj), minutes_to_str(end_adj)


def check_conflict(program, user_timetable):
    """프로그램 일정과 사용자 시간표가 겹치는지 검사"""
    if not program.run_time_text:
        return False

    text = program.run_time_text
    pattern = r"(\d{4}\.\d{2}\.\d{2})\s+(\d{1,2}:\d{2})"
    matches = re.findall(pattern, text)
    if len(matches) < 2:
        return False

    start_date_str, start_time_str = matches[0]
    end_date_str, end_time_str = matches[1]

    try:
        start_dt = datetime.strptime(start_date_str, "%Y.%m.%d")
        end_dt = datetime.strptime(end_date_str, "%Y.%m.%d")
        if start_dt.date() != end_dt.date():
            return False

        target_day = get_korean_weekday(start_dt)
        prog_start_min = parse_time_str(start_time_str)
        prog_end_min = parse_time_str(end_time_str)
        if prog_start_min is None or prog_end_min is None:
            return False

        for tt in user_timetable:
            if tt.day == target_day:
                class_start = parse_time_str(tt.start_time)
                class_end = parse_time_str(tt.end_time)
                if class_start and class_end:
                    if is_time_overlap(
                        prog_start_min, prog_end_min, class_start, class_end
                    ):
                        print(
                            f" [Conflict] '{program.title}'({target_day} {start_time_str}) 겹침 -> 수업: {tt.subject_name}"
                        )
                        return True
    except Exception as e:
        print(f" [Error] 날짜 파싱 실패 ({text}): {e}")
        return False

    return False


def generate_recommendations(programs, user_timetable, now=None):
    """추천 결과 생성 (충돌 제거 + 마감 임박 정렬)"""
    recommendations = []
    now = now or datetime.now()

    candidates = []
    for prog in programs:
        if check_conflict(prog, user_timetable):
            continue

        deadline = prog.apply_end
        sort_key = deadline if deadline else datetime(9999, 12, 31)
        status_text = "추천 (공강)"

        if deadline:
            if deadline < now:
                continue

            days_left = (deadline - now).days
            if days_left <= 3:
                status_text = f"마감임박 ⏰ (D-{days_left})"
            elif days_left <= 7:
                status_text = f"서두르세요 🏃 (D-{days_left})"
            else:
                status_text = f"접수중 (D-{days_left})"

        candidates.append(
            {
                "title": prog.title,
                "category": prog.topic or "일반",
                "status": status_text,
                "sort_key": sort_key,
            }
        )

    candidates.sort(key=lambda x: x["sort_key"])

    for item in candidates:
        recommendations.append(
            {
                "title": item["title"],
                "category": item["category"],
                "status": item["status"],
            }
        )

    if not recommendations:
        recommendations.append(
            {"title": "현재 신청 가능한 공강 프로그램이 없습니다.", "category": "-", "status": ""}
        )

    return recommendations
