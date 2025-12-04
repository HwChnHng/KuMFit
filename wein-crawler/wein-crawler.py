from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import os

# 로그인 페이지
LOGIN_URL = "https://wein.konkuk.ac.kr/common/user/login.do"

# 비교과 목록 URL들 (메뉴에 있는 redirect 형태로 맞춤)
GENL_URL = "https://wein.konkuk.ac.kr/redirect?url=/ptfol/imng/comprSbjtMngt/icmpNsbjtApl/genl/findTotPcondList.do"       # 일반비교과
EMPLYM_URL = "https://wein.konkuk.ac.kr/redirect?url=/ptfol/imng/comprSbjtMngt/icmpNsbjtApl/emplym/findTotPcondList.do"    # 취창업비교과
GRUPDPT_URL = "https://wein.konkuk.ac.kr/redirect?url=/ptfol/imng/comprSbjtMngt/icmpNsbjtApl/grupDpt/findTotPcondList.do"  # 단과대비교과

# 각 분류별로 최대 몇 페이지까지 돌지
MAX_PAGES = 10


def extract_status_from_card(card):
    """
    카드 하단 버튼에서 상태를 최대한 정확히 판별.
    가능한 값: '신청', '대기신청', '신청마감', '신청완료'
    못 찾으면 "" 리턴.
    """
    raw_text = ""

    # 1) div.bottom 안의 버튼(span)에서 직접 텍스트 가져오기
    try:
        btn_span = card.find_element(By.CSS_SELECTOR, "div.bottom a span")
        raw_text = btn_span.text.strip()
    except Exception:
        # fallback: bottom 전체 텍스트
        try:
            bottom = card.find_element(By.CSS_SELECTOR, "div.bottom")
            raw_text = bottom.text.strip()
        except Exception:
            return ""

    # 공백/줄바꿈 제거
    norm = re.sub(r"\s+", "", raw_text)

    # 우선순위: 더 구체적인 문자열부터
    if "신청완료" in norm:
        return "신청완료"
    if "대기신청" in norm or ("대기" in norm and "신청" in norm):
        return "대기신청"
    if "신청마감" in norm or "마감" in norm:
        return "신청마감"
    # '신청' 또는 '접수'가 들어가면 신청으로 간주 (취창업/단과대 쪽 방어용)
    if "신청" in norm or "접수" in norm:
        return "신청"

    return ""


def crawl_category(driver, list_url: str, category_name: str, max_pages: int = 10):
    """
    이미 로그인된 driver를 받아서,
    해당 비교과 목록 페이지를 1페이지 ~ max_pages 페이지까지 크롤링한다.
    리턴: [{category, title, apply_period, site_status}, ...]
    """
    results = []

    print("\n==============================")
    print(f"[{category_name}] 크롤링 시작")
    print(f"목록 URL: {list_url}")
    print("==============================")

    # 1페이지로 진입
    driver.get(list_url)
    time.sleep(2)
    print(" → 1페이지 접속 완료, 현재 URL:", driver.current_url)

    for page in range(1, max_pages + 1):
        print(f"\n--- {category_name} : {page} 페이지 ---")

        if page > 1:
            # 2페이지 이상부터는 global.page(페이지번호) 호출해서 이동
            try:
                driver.execute_script("return global.page(arguments[0]);", page)
                time.sleep(2)
                print(f" → global.page({page}) 호출 완료")
            except Exception as e:
                print(f" → {page} 페이지로 이동 실패. 여기까지 크롤링하고 이 분류는 종료. ({e})")
                break

        # 카드(li)가 로딩될 때까지 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.tab_wrap div.ul_list_wrap ul.ul_box li")
                )
            )
        except Exception as e:
            print(" → 카드 로딩 대기 중 에러, 이 분류는 여기까지.:", e)
            break

        cards = driver.find_elements(
            By.CSS_SELECTOR,
            "div.tab_wrap div.ul_list_wrap ul.ul_box > li"
        )
        print(f" → 카드 {len(cards)}개 발견")

        for idx, card in enumerate(cards, start=1):
            # 제목
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "div.text_box div.title a")
                title = title_el.text.strip()
            except Exception:
                title = ""

            # 신청기간 (예: "신청기간 2025.09.04 ~ 2025.12.31")
            try:
                date_apply_el = card.find_element(By.CSS_SELECTOR, "p.date span.date01")
                apply_period = date_apply_el.text.strip()
            except Exception:
                apply_period = ""

            # 상태 (버튼에 적혀있는 텍스트: 신청 / 대기신청 / 신청마감 / 신청완료 등)
            site_status = extract_status_from_card(card)

            #  확인용
            # print(f"    [DEBUG] {title} → '{site_status}'")

            # 최종적으로 "신청" / "대기신청"만 수집 (신청마감/신청완료는 버림)
            if site_status not in ("신청", "대기신청"):
                continue

           

            results.append(
                {
                    "category": category_name,
                    "title": title,
                    "apply_period": apply_period,
                    "site_status": site_status,
                }
            )

    print(f"\n[{category_name}] 크롤링 종료. 총 {len(results)}개 수집.")
    return results


def crawl_weinzon(user_id: str, user_pw: str):
    # 크롬 옵션 설정
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # 크롬 드라이버 자동 설치
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    all_results = []

    try:
        # 1) 로그인
        print("[1] 로그인 페이지 접속")
        driver.get(LOGIN_URL)

        print("[2] 아이디 / 비밀번호 입력")
        driver.find_element(By.CSS_SELECTOR, "input.input_id").send_keys(user_id)
        driver.find_element(By.CSS_SELECTOR, "input.input_pw").send_keys(user_pw)

        print("[3] 로그인 버튼 클릭")
        driver.find_element(By.CSS_SELECTOR, "#loginBtn").click()
        time.sleep(2)
        print(" → 로그인 후 2초 대기 완료, 현재 URL:", driver.current_url)

        # 2) 각 비교과 유형별 크롤링
        all_results += crawl_category(driver, GENL_URL,   "일반비교과",   MAX_PAGES)
        all_results += crawl_category(driver, EMPLYM_URL, "취창업비교과", MAX_PAGES)
        all_results += crawl_category(driver, GRUPDPT_URL,"단과대비교과", MAX_PAGES)

        # 3) 전체 결과 출력 (신청 / 대기신청만)
        print("\n================ 신청 / 대기신청 최종 결과 ================")
        for r in all_results:
            print(f"[{r['category']}] {r['title']}")
            print(f"  신청기간 : {r['apply_period']}")
            print(f"  상태     : {r['site_status']}")
            print()

        print(f"총 {len(all_results)}개 프로그램 수집 완료 (신청/대기신청만 포함)")

        return all_results

    finally:
        driver.quit()

if __name__ == "__main__":
    # 1순위: 환경변수에서 아이디 / 비번 가져오기 (도커/서버용)
    WEIN_ID = os.getenv("WEIN_ID")
    WEIN_PW = os.getenv("WEIN_PW")

    # 로컬에서 직접 실행할 때는 입력 받기
    if not WEIN_ID:
        WEIN_ID = input("위인전 아이디를 입력하세요: ")
    if not WEIN_PW:
        WEIN_PW = input("위인전 비밀번호를 입력하세요: ")

    while True:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n===== {now} : 위인전 크롤링 1회 시작 =====")

        try:
            crawl_weinzon(WEIN_ID, WEIN_PW)
        except Exception as e:
            print("[에러] 크롤링 중 오류 발생:", e)

        now_end = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"===== {now_end} : 크롤링 1회 종료, 1시간 대기 =====\n")

        # 1시간(3600초) 대기
        time.sleep(3600)