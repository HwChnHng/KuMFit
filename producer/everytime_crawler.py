import os
import re
import math
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# 요일 리스트 (td 인덱스랑 매핑)
DAYS = ["월", "화", "수", "목", "금", "토", "일"]


# ----------------------------------------------------------------------
# style="top: 450px; height: 151px;" 에서 숫자(px)만 뽑는 함수
# ----------------------------------------------------------------------
def parse_style_value(style: str, key: str, default=None):
    m = re.search(rf"{key}\s*:\s*([0-9\.]+)px", style)
    return float(m.group(1)) if m else default


# ----------------------------------------------------------------------
# "오전 9시", "오후 1시" → 24시간제 정수 (9, 13, ...)
# ----------------------------------------------------------------------
def parse_korean_hour(label: str):
    # 예: label = "오전 9시", "오후 1시", "오후 12시"
    m = re.search(r"(오전|오후)\s*(\d+)시", label)
    if not m:
        return None
    ampm, h = m.group(1), int(m.group(2))
    if ampm == "오전":
        if h == 12:
            h = 0
    else:  # 오후
        if h != 12:
            h += 12
    return h


# ----------------------------------------------------------------------
# 브라우저 실좌표 기반 시간 매핑 계산
# ----------------------------------------------------------------------
def compute_time_mapping_from_metrics(metrics):
    """
    metrics = {
      "tableHeight": ...,
      "times": [{label, top}, ...],
      "subjects": [{top, height, dayIndex}, ...]
    }
    """
    times = metrics.get("times") or []
    table_height = metrics.get("tableHeight")

    # 1) 유효 좌표만 추출 (table 높이 안에 있는 라벨 우선)
    def valid_times(src):
        if not table_height:
            return src
        return [t for t in src if t.get("top") is not None and 0 <= t["top"] <= table_height]

    times_filtered = valid_times(times)
    if not times_filtered:
        times_filtered = [t for t in times if t.get("top") is not None]

    hours = []
    tops = []
    for t in times_filtered:
        h = parse_korean_hour(t.get("label", ""))
        top = t.get("top")
        if h is not None and top is not None:
            hours.append(h)
            tops.append(top)

    base_hour = min(hours) if hours else 9
    base_top = min(tops) if tops else 0

    px_per_hour = None
    if len(hours) >= 2 and tops:
        # 인접 라벨 간 최소 양수 간격 사용 (스냅 안정화)
        pairs = sorted(zip(hours, tops), key=lambda x: x[0])
        deltas = []
        for (h1, t1), (h2, t2) in zip(pairs, pairs[1:]):
            dh = h2 - h1
            dt = t2 - t1
            if dh > 0 and dt > 0:
                deltas.append(dt / dh)
        if deltas:
            px_per_hour = min(deltas)

    # times가 충분치 않으면 table height를 사용 (라벨 개수 - 1 기준)
    if px_per_hour is None and table_height and len(hours) >= 2:
        hour_span = max(hours) - min(hours)
        if hour_span > 0:
            px_per_hour = table_height / hour_span
    elif px_per_hour is None and table_height:
        px_per_hour = table_height / 24

    if px_per_hour is not None:
        px_per_hour = max(20.0, min(px_per_hour, 200.0))

    return base_hour, base_top, px_per_hour


# ----------------------------------------------------------------------
# 왼쪽 시간축(div.times > div.time)에서
#   - base_hour : 가장 위에 있는 시간(예: 9)
#   - base_top  : 그 시간의 top px
#   - px_per_hour : 1시간당 몇 px인지
# 를 계산
# ----------------------------------------------------------------------
def compute_time_mapping(soup: BeautifulSoup, subject_divs):
    """
    - 시간축(div.times)의 텍스트에서 base_hour(예: 9시)를 얻고
    - div.time의 실제 위치(top) 차이로 1시간당 px를 우선 계산하고,
      부족하면 과목 블록 간격으로 보정해 base_top, px_per_hour를 계산한다.
    """
    # 1) 시간축 텍스트/위치 → base_hour, px_per_hour 후보 계산
    time_divs = soup.select("div.times > div.time")
    hours = []
    time_positions = []

    for d in time_divs:
        label = d.get_text(strip=True)  # "오전 9시", "오후 1시" 등
        h = parse_korean_hour(label)
        if h is not None:
            hours.append(h)
            top_px = parse_style_value(d.get("style", ""), "top")
            if top_px is not None:
                time_positions.append((h, top_px))

    base_hour = min(hours) if hours else 9

    px_per_hour = None
    base_top = None
    if len(time_positions) >= 2:
        # 시간 오름차순으로 정렬 후 인접 라벨 간 간격을 사용
        time_positions.sort(key=lambda x: x[0])
        deltas = []
        for (h1, t1), (h2, t2) in zip(time_positions, time_positions[1:]):
            dh = h2 - h1
            dt = t2 - t1
            if dh > 0 and dt > 0:
                deltas.append(dt / dh)
        if deltas:
            px_per_hour = min(deltas)  # 가장 작은 양수 간격을 사용해 과대 추정을 방지
            # base_top은 가장 이른 시간 라벨의 top으로 맞춘다
            for h, t in time_positions:
                if h == base_hour:
                    base_top = t
                    break

    # 2) 과목 블록들의 top/height px 수집 (fallback용)
    tops = []
    heights = []
    for div in subject_divs:
        style = div.get("style", "")
        top_px = parse_style_value(style, "top")
        height_px = parse_style_value(style, "height")
        if top_px is not None:
            tops.append(top_px)
        if height_px is not None:
            heights.append(height_px)

    if not tops and px_per_hour is None:
        raise RuntimeError("과목 블록의 top 정보를 찾지 못했습니다.")

    # 3) 시간축 정보만으로 px_per_hour를 얻지 못했다면 과목 간격으로 보정
    if px_per_hour is None:
        slot_px = None

        # 3-1) 과목 블록 height들의 최대공약수로 슬롯(30분) px 추정
        height_ints = [int(round(h)) for h in heights if h and h > 0]
        if height_ints:
            slot_px = height_ints[0]
            for h in height_ints[1:]:
                slot_px = math.gcd(slot_px, h)
            if slot_px < 10:  # 너무 작은 값이면 무시
                slot_px = None

        # 3-2) 실패 시 top 간격의 최소 양수값 사용
        if slot_px is None:
            tops.sort()
            diffs = [b - a for a, b in zip(tops, tops[1:]) if b > a]
            if diffs:
                slot_px = min(diffs)

        # 3-3) 그래도 없으면 기본값
        if slot_px is None or slot_px <= 0:
            slot_px = 50.0  # 안전 기본값

        # 1시간 = 30분*2 slot
        px_per_hour = slot_px * 2

        # 비정상적으로 큰 값이면 40~200 사이로 클램프
        px_per_hour = max(40.0, min(px_per_hour, 200.0))

    # 4) base_top 미지정 시 보정: 시간축 좌표 → 과목 좌표 순
    if base_top is None:
        if time_positions:
            # base_hour와 매칭되는 좌표가 없으면 가장 위에 있는 라벨 사용
            base_top = min(time_positions, key=lambda x: x[1])[1]
        elif tops:
            base_top = tops[0]

    return base_hour, base_top, px_per_hour


# ----------------------------------------------------------------------
# float 시간(예: 9.5) → "09:30" 문자열
# ----------------------------------------------------------------------
def hour_float_to_str(h: float) -> str:
    hour = int(h)
    minute = int(round((h - hour) * 60))
    if minute == 60:
        hour += 1
        minute = 0
    return f"{hour:02d}:{minute:02d}"


# ----------------------------------------------------------------------
# 슬롯(30분 단위) → "HH:MM" 문자열
# ----------------------------------------------------------------------
def slot_to_time_str(base_hour: float, slot_idx: int) -> str:
    return hour_float_to_str(base_hour + slot_idx * 0.5)


# ----------------------------------------------------------------------
# 브라우저에서 실제 좌표 정보를 수집
# ----------------------------------------------------------------------
def collect_layout_metrics(driver):
    script = """
    const table = document.querySelector('table.tablebody');
    const tableRect = table ? table.getBoundingClientRect() : null;

    const times = Array.from(document.querySelectorAll('div.times > div.time')).map(el => {
      const rect = el.getBoundingClientRect();
      return {
        label: el.textContent.trim(),
        top: tableRect ? rect.top - tableRect.top : rect.top
      };
    });

    const subjects = Array.from(document.querySelectorAll('div.subject')).map(el => {
      const rect = el.getBoundingClientRect();
      const parentTd = el.closest('td');
      let dayIndex = -1;
      if (parentTd && parentTd.parentElement) {
        const tds = Array.from(parentTd.parentElement.querySelectorAll('td'));
        dayIndex = tds.indexOf(parentTd);
      }
      return {
        top: tableRect ? rect.top - tableRect.top : rect.top,
        height: rect.height,
        dayIndex: dayIndex
      };
    });

    return {
      tableHeight: tableRect ? tableRect.height : null,
      times: times,
      subjects: subjects
    };
    """
    try:
        return driver.execute_script(script)
    except Exception:
        return {}


# ----------------------------------------------------------------------
# 과목 블록 top/height → 실제 시작/끝 시각 + 30분 슬롯(start_slot, end_slot)
#   - base_hour   : 시간축 기준 시작 시간 (예: 9)
#   - base_top    : 그 시간의 top px
#   - px_per_hour : 1시간당 px
#   - 1 slot = 30분
# ----------------------------------------------------------------------
def px_to_time_and_slots(top_px, height_px, base_hour, base_top, px_per_hour):
    # 픽셀 기준 상대 시간(시간 단위)
    start_rel_hour = (top_px - base_top) / px_per_hour
    start_hour = base_hour + start_rel_hour

    dur_hour = height_px / px_per_hour
    end_hour = start_hour + dur_hour

    # 1 slot = 30분 = 0.5시간
    start_slot = int(round((start_hour - base_hour) * 2))  # base_hour 기준
    end_slot = int(round((end_hour - base_hour) * 2))

    # 슬롯 인덱스를 시간으로 변환해 30분 단위로 스냅
    start_str = slot_to_time_str(base_hour, start_slot)
    end_str = slot_to_time_str(base_hour, end_slot)

    return start_str, end_str, start_slot, end_slot


# ----------------------------------------------------------------------
# 메인 크롤링 함수
#   입력 : 에브리타임 시간표 공유 URL
#   출력 : 시간표 리스트
#          [
#             { "day": "월", "day_index": 0,
#               "start": "09:00", "end": "10:30",
#               "start_slot": 0, "end_slot": 3 },
#             ...
#          ]
# ----------------------------------------------------------------------
# 공통 헤드리스 옵션을 환경변수로 고정
CHROME_WINDOW_SIZE = os.getenv("CHROME_WINDOW_SIZE", "1920,1080")
CHROME_DEVICE_SCALE_FACTOR = os.getenv("CHROME_DEVICE_SCALE_FACTOR", "1")


def crawl_shared_timetable(url: str):
    if url.startswith("everytime.kr"):
        url = "https://" + url

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--force-device-scale-factor={CHROME_DEVICE_SCALE_FACTOR}")
    options.add_argument(f"--window-size={CHROME_WINDOW_SIZE}")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    )
    options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(
        service=Service("/usr/bin/chromedriver"),
        options=options,
    )

    try:
        print(f"[INFO] 요청 URL: {url}")
        driver.get(url)

        # 시간표 테이블이 로드될 때까지 대기 (최대 20초)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.tablebody"))
            )
        except TimeoutException:
            print("[WARN] 시간표 테이블(table.tablebody)을 찾지 못했습니다.")
            print(f"[DEBUG] page title: {driver.title}")
            try:
                snippet = driver.page_source[:1000]
                print(f"[DEBUG] page source snippet: {snippet}")
            except Exception:
                pass
            return []

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # 실좌표 메트릭 수집 (table height, div.time 위치, 과목 위치)
        layout_metrics = collect_layout_metrics(driver)

        # 1) 과목 블록 먼저 찾기
        subject_divs = soup.select("div.subject")
        if not subject_divs:
            print("[WARN] 과목 블록(div.subject)을 찾지 못했습니다.")
            return []

        # 2) 왼쪽 시간축 + 과목 top으로 px → 시간 매핑 계산
        base_hour = base_top = px_per_hour = None

        if layout_metrics:
            base_hour, base_top, px_per_hour = compute_time_mapping_from_metrics(layout_metrics)

        if px_per_hour is None:
            base_hour, base_top, px_per_hour = compute_time_mapping(soup, subject_divs)

        print(f"[DEBUG] base_hour={base_hour}, base_top={base_top}, px_per_hour={px_per_hour}")


        # 2) 요일 기준 td 리스트
        td_list = soup.select("table.tablebody tbody tr td")

        # 3) 과목 블록들
        subject_divs = soup.select("div.subject")
        if not subject_divs:
            print("[WARN] 과목 블록(div.subject)을 찾지 못했습니다.")
            return []

        timetable = []
        metrics_subjects = layout_metrics.get("subjects") if layout_metrics else []
        metrics_idx = 0

        for div in subject_divs:
            # (1) 요일 계산: metrics dayIndex 우선 → soup fallback
            day_idx = None
            if metrics_subjects and metrics_idx < len(metrics_subjects):
                m = metrics_subjects[metrics_idx]
                if m.get("dayIndex", -1) >= 0:
                    day_idx = m["dayIndex"]

            if day_idx is None:
                parent_td = div.find_parent("td")
                day_idx = td_list.index(parent_td)

            day = DAYS[day_idx]

            # (2) 시간 계산
            style = div.get("style", "")
            top_px = parse_style_value(style, "top")
            height_px = parse_style_value(style, "height")

            if metrics_subjects and metrics_idx < len(metrics_subjects):
                m = metrics_subjects[metrics_idx]
                top_px = m.get("top", top_px)
                height_px = m.get("height", height_px)
                metrics_idx += 1

            start_time, end_time, start_slot, end_slot = px_to_time_and_slots(
                top_px, height_px, base_hour, base_top, px_per_hour
            )

            timetable.append({
                "day": day,               # 요일 한글 ('월' 등)
                "day_index": day_idx,     # 0=월,1=화,...
                "start": start_time,      # "09:00"
                "end": end_time,          # "10:30"
                "start_slot": start_slot, # base_hour 기준 30분 단위 슬롯
                "end_slot": end_slot,
            })

        print("=== 최종 시간표 ===")
        for t in timetable:
            print(t)

        return timetable

    finally:
        driver.quit()


if __name__ == "__main__":
    shared_url = input("에브리타임 시간표 공유 URL: ").strip()
    crawl_shared_timetable(shared_url)
