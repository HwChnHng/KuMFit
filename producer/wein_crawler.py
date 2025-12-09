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
    results = []
    print(f"\n --- [{category_name}] 접속 시작 ---")
    driver.get(list_url)
    time.sleep(1) # 페이지 로딩 대기
    
    for page in range(1, max_pages + 1):
        print(f" [Page] {page}페이지 스캔 중...")

        if page > 1:
            try:
                # [수정됨] 페이지 이동 함수 호출 (위인전 사이트 방식)
                driver.execute_script(f"fn_egov_link_page({page});") 
                time.sleep(2) # 이동 대기
            except Exception as e:
                print(f" [Skip] 페이지 이동 실패: {e}")
                break

        try:
            # 카드 로딩 대기 (최대 5초)
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.tab_wrap div.ul_list_wrap ul.ul_box li"))
            )
            cards = driver.find_elements(By.CSS_SELECTOR, "div.tab_wrap div.ul_list_wrap ul.ul_box > li")
            
            if not cards:
                print(" [End] 카드가 없어 종료합니다.")
                break
                
            for card in cards:
                try:
                    title = card.find_element(By.CSS_SELECTOR, "div.text_box div.title a").text.strip()
                    
                    # 1. 신청 기간
                    try:
                        date_apply_el = card.find_element(By.CSS_SELECTOR, "p.date span.date01")
                        apply_period = date_apply_el.text.strip()
                    except:
                        apply_period = ""

                    # 2. [팀원 업데이트 반영] 진행 기간
                    try:
                        date_run_el = card.find_element(By.CSS_SELECTOR, "p.date span.date02")
                        run_period = date_run_el.text.strip()
                    except:
                        run_period = ""

                    # 3. 상태 확인
                    status = extract_status_from_card(card)
                    
                    if status in ["신청", "대기신청"]:
                        results.append({
                            "category": category_name,
                            "title": title,
                            "apply_period": apply_period,
                            "run_period": run_period,
                            "site_status": status
                        })
                except:
                    continue
        except:
            print(f" [End] {page}페이지에서 로딩 실패 또는 끝")
            break
            
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