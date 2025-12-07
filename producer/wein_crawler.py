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
    time.sleep(2)
    
    for page in range(1, max_pages + 1):
        print(f" [Page] {page}페이지 스캔 중...")

        if page > 1:
            try:
                # [수정됨] global.page -> window.fn_egov_link_page 또는 그냥 페이지 이동 함수 호출
                # 위인전 사이트는 보통 fn_egov_link_page(pageIndex) 또는 linkPage(pageIndex)를 씁니다.
                # 안전하게 'a' 태그를 눌러서 이동하거나, js를 수정합니다.
                
                # 시도 1: 일반적인 전자정부 프레임워크 페이징 함수 호출
                driver.execute_script(f"fn_egov_link_page({page});") 
                time.sleep(2)
            except Exception as e:
                print(f" [Skip] 페이지 이동 실패 (더 이상 페이지가 없거나 함수명 다름): {e}")
                break

        try:
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
                    period_el = card.find_element(By.CSS_SELECTOR, "p.date span.date01")
                    period = period_el.text.strip()
                    status = extract_status_from_card(card)
                    
                    if status in ["신청", "대기신청"]:
                        results.append({
                            "category": category_name,
                            "title": title,
                            "apply_period": period,
                            "site_status": status
                        })
                except:
                    continue
        except:
            print(f" [End] {page}페이지에서 로딩 실패 또는 끝")
            break
            
    return results

def crawl_weinzon(user_id, user_pw):
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"

    service = Service("/usr/bin/chromedriver")
    
    # 드라이버 실행
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f" [Error] 드라이버 실행 실패: {e}")
        return []

    all_results = []
    try:
        print(" [Login] 로그인 시도...")
        driver.get(LOGIN_URL)
        
        # ID/PW 입력 (SendKeys 에러 방지 위해 문자열 변환)
        driver.find_element(By.CSS_SELECTOR, "input.input_id").send_keys(str(user_id))
        driver.find_element(By.CSS_SELECTOR, "input.input_pw").send_keys(str(user_pw))
        driver.find_element(By.CSS_SELECTOR, "#loginBtn").click()
        
        time.sleep(2)
        
        # 로그인 성공 체크 (URL이 바뀌었는지)
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
        driver.quit()