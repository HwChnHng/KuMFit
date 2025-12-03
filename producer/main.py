import pika
import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# --- [설정] ---
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
QUEUE_NAME = 'weinjeon_updates'

def get_rabbitmq_connection():
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            return connection
        except pika.exceptions.AMQPConnectionError:
            print(" [!] RabbitMQ 연결 실패. 5초 후 재시도...")
            time.sleep(5)

# --- [수정된 부분: Chromium 설정] ---
def get_driver():
    chrome_options = Options()
    # Docker 환경 필수 옵션
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Chromium 바이너리 위치 지정 (Docker 내 설치 위치)
    chrome_options.binary_location = "/usr/bin/chromium"
    
    # 크롬 드라이버 서비스 생성 (/usr/bin/chromedriver 사용)
    service = Service("/usr/bin/chromedriver")
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME)
    print(f" [*] Connected to RabbitMQ at {RABBITMQ_HOST}")

    print(" [*] Starting Chromium Browser...")
    try:
        driver = get_driver()
        
        while True:
            # 테스트: 구글 접속
            driver.get("https://www.google.com")
            title = driver.title
            print(f" [Crawling] 현재 페이지 제목: {title}")

            data = {
                "event": "CRAWLING_SUCCESS",
                "title": title,
                "timestamp": time.time()
            }
            
            channel.basic_publish(exchange='', routing_key=QUEUE_NAME, body=json.dumps(data))
            print(f" [x] Sent data to RabbitMQ")

            time.sleep(10)

    except Exception as e:
        print(f" [Error] {e}")
        # 에러 발생 시 드라이버가 켜져있다면 끄기
        if 'driver' in locals():
            driver.quit()
    finally:
        if 'connection' in locals() and connection.is_open:
            connection.close()

if __name__ == "__main__":
    main()
