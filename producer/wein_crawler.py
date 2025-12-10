from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import os

# 로그인 페이지
LOGIN_URL = "https://wein.konkuk.ac.kr/common/user/login.do"

# 비교과 목록 URL
GENL_URL = "https://wein.konkuk.ac.kr/redirect?url=/ptfol/imng/comprSbjtMngt/icmpNsbjtApl/genl/findTotPcondList.do"
EMPLYM_URL = "https://wein.konkuk.ac.kr/redirect?url=/ptfol/imng/comprSbjtMngt/icmpNsbjtApl/emplym/findTotPcondList.do"
GRUPDPT_URL = "https://wein.konkuk.ac.kr/redirect?url=/ptfol/imng/comprSbjtMngt/icmpNsbjtApl/grupDpt/findTotPcondList.do"

MAX_PAGES = 10

def extract_status_from_card(card):
    try:
        raw_text = ""
        try:
            btn_span = card.find_element(By.CSS_SELECTOR, "div.bottom a span")
            raw_text = btn_span.text.strip()
        except:
            try:
                bottom = card.find_element(By.CSS_SELECTOR, "div.bottom")
                raw_text = bottom.text.strip()
            except:
                return ""

        norm = re.sub(r"\s+", "", raw_text)
        if "신청완료" in norm: return "신청완료"
        if "대기신청" in norm or ("대기" in norm and "신청" in norm): return "대기신청"
        if "신청마감" in norm or "마감" in norm: return "신청마감"
        if "신청" in norm or "접수" in norm: return "신청"
        return ""
    except:
        return ""
def crawl_category(driver, list_url, category_name, max_pages=10):
    """
    이미 로그인된 driver를 받아서,
    해당 비교과 목록 페이지를 1페이지 ~ max_pages 페이지까지 크롤링한다.
    리턴: [{category, title, apply_period, run_period, site_status}, ...]
    """
    results = []

    print("\n==============================")
    print(f"[{category_name}] 크롤링 시작")
    print(f"목록 URL: {list_url}")
    print("==============================")

    # 1페이지 진입
    driver.get(list_url)
    time.sleep(2)
    print(" → 1페이지 접속 완료, 현재 URL:", driver.current_url)

    for page in range(1, max_pages + 1):
        print(f"\n--- {category_name} : {page} 페이지 ---")

        if page > 1:
            #  로컬에서 잘 되는 방식 그대로 사용: global.page(page)
            try:
                print(f"  → {page}페이지로 이동 (global.page 사용)")
                driver.execute_script("return global.page(arguments[0]);", page)
                time.sleep(2)  # 페이지 전환 대기
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
            # 1. 제목
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "div.text_box div.title a")
                title = title_el.text.strip()
            except Exception:
                title = ""

            # 2. 신청기간
            try:
                date_apply_el = card.find_element(By.CSS_SELECTOR, "p.date span.date01")
                apply_period = date_apply_el.text.strip()
            except Exception:
                apply_period = ""

            # 3. 진행기간
            try:
                date_run_el = card.find_element(By.CSS_SELECTOR, "p.date span.date02")
                run_period = date_run_el.text.strip()
            except Exception:
                run_period = ""

            # 4. 상태 (버튼 텍스트)
            status = extract_status_from_card(card)

            # "신청" / "대기신청"만 수집
            if status not in ("신청", "대기신청"):
                continue

            results.append(
                {
                    "category": category_name,
                    "title": title,
                    "apply_period": apply_period,
                    "run_period": run_period,
                    "site_status": status,
                }
            )

    print(f"\n[{category_name}] 크롤링 종료. 총 {len(results)}개 수집.")
    return results



def crawl_weinzon(user_id, user_pw):
    # [중요] Docker 환경설정
    options = Options()
    options.add_argument("--headless=new")  # [수정] 최신 헤드리스 모드 사용
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Docker 내부 경로 지정
    options.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver")
    
    # 드라이버 실행
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f" [Error] 드라이버 실행 실패: {e}")
        return []

    all_results = []
    try:
        print(" [Login] 로그인 페이지 접속...")
        driver.get(LOGIN_URL)
        
        # [수정] 입력창이 뜰 때까지 최대 10초 대기 (안전장치)
        wait = WebDriverWait(driver, 10)
        id_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.input_id")))
        pw_input = driver.find_element(By.CSS_SELECTOR, "input.input_pw")
        login_btn = driver.find_element(By.CSS_SELECTOR, "#loginBtn")

        print(" [Login] 아이디/비번 입력 중...")
        id_input.clear()
        id_input.send_keys(str(user_id))
        pw_input.clear()
        pw_input.send_keys(str(user_pw))
        
        login_btn.click()
        time.sleep(2) # 로그인 처리 대기
        
        # 로그인 성공 체크
        if "login.do" in driver.current_url:
            print(" [Fail] 로그인 실패 (아이디/비번 확인 필요)")
            return []

        print(" [Login] 성공! 크롤링 시작...")
        
        all_results += crawl_category(driver, GENL_URL, "일반비교과", MAX_PAGES)
        all_results += crawl_category(driver, EMPLYM_URL, "취창업비교과", MAX_PAGES)
        all_results += crawl_category(driver, GRUPDPT_URL, "단과대비교과", MAX_PAGES)
        
        return all_results

    except Exception as e:
        print(f" [Error] 크롤링 도중 상세 에러: {e}")
        return []
        
    finally:
        if driver:
            driver.quit()