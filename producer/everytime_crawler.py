import os
import re
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
# 왼쪽 시간축(div.times > div.time)에서
#   - base_hour : 가장 위에 있는 시간(예: 9)
#   - base_top  : 그 시간의 top px
#   - px_per_hour : 1시간당 몇 px인지
# 를 계산
# ----------------------------------------------------------------------
def compute_time_mapping(soup: BeautifulSoup, subject_divs):
    """
    - 시간축(div.times)의 텍스트에서 base_hour(예: 9시)를 얻고
    - 과목 블록들의 top px 차이로 1 slot(30분)당 px를 추정해서
      base_top, px_per_hour를 계산한다.
    """
    # 1) 시간축 텍스트로부터 base_hour 계산
    time_divs = soup.select("div.times > div.time")
    hours = []

    for d in time_divs:
        label = d.get_text(strip=True)  # "오전 9시", "오후 1시" 등
        h = parse_korean_hour(label)
        if h is not None:
            hours.append(h)

    if hours:
        base_hour = min(hours)
    else:
        # 혹시 못 찾으면 기본 9시로 가정
        base_hour = 9

    # 2) 과목 블록들의 top px 수집
    tops = []
    for div in subject_divs:
        style = div.get("style", "")
        top_px = parse_style_value(style, "top")
        if top_px is not None:
            tops.append(top_px)

    if not tops:
        raise RuntimeError("과목 블록의 top 정보를 찾지 못했습니다.")

    tops.sort()
    # 인접한 top 차이들 중 양수인 최소값 → 1 slot(30분) px 근사
    diffs = [b - a for a, b in zip(tops, tops[1:]) if b > a]
    if diffs:
        slot_px = min(diffs)
    else:
        slot_px = 50.0  # fallback

    # 1시간 = 30분*2 slot
    px_per_hour = slot_px * 2
    base_top = tops[0]  # 가장 위에 있는 수업의 top을 기준으로 사용

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

    start_str = hour_float_to_str(start_hour)
    end_str = hour_float_to_str(end_hour)

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

        # 1) 과목 블록 먼저 찾기
        subject_divs = soup.select("div.subject")
        if not subject_divs:
            print("[WARN] 과목 블록(div.subject)을 찾지 못했습니다.")
            return []

        # 2) 왼쪽 시간축 + 과목 top으로 px → 시간 매핑 계산
        base_hour, base_top, px_per_hour = compute_time_mapping(soup, subject_divs)
        print(f"[DEBUG] base_hour={base_hour}, base_top={base_top}, "
            f"px_per_hour={px_per_hour}")


        # 2) 요일 기준 td 리스트
        td_list = soup.select("table.tablebody tbody tr td")

        # 3) 과목 블록들
        subject_divs = soup.select("div.subject")
        if not subject_divs:
            print("[WARN] 과목 블록(div.subject)을 찾지 못했습니다.")
            return []

        timetable = []

        for div in subject_divs:
            # (1) 요일 계산: 자신이 속한 td가 몇 번째인지
            parent_td = div.find_parent("td")
            day_idx = td_list.index(parent_td)
            day = DAYS[day_idx]

            # (2) 시간 계산
            style = div.get("style", "")
            top_px = parse_style_value(style, "top")
            height_px = parse_style_value(style, "height")

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
