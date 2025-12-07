import pika
import json
import os
import time
import sys

# 공통 모듈 가져오기 (DB 접속 및 저장 함수)
from common.database import get_db,init_db
from common import crud

# --- [설정] ---
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
QUEUE_NAME = 'weinjeon_updates'

def get_rabbitmq_connection():
    """RabbitMQ 연결 (실패 시 재시도 로직 포함)"""
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            return connection
        except pika.exceptions.AMQPConnectionError:
            print(" [!] RabbitMQ 연결 실패. 5초 후 재시도...")
            time.sleep(5)

def callback(ch, method, properties, body):
    """메시지 수신 시 실행되는 함수"""
    print(" [x] 메시지 수신됨")
    
    db = next(get_db()) # DB 세션 생성
    try:
        # 1. JSON 디코딩
        message = json.loads(body)
        
        # 2. 데이터 추출 (Producer가 보낸 형식에 맞춤)
        # 예: {"event_type": "CRAWLING_COMPLETE", "data": [...]}
        programs_data = message.get('data', [])
        
        if not programs_data:
            print(" [!] 데이터가 비어있습니다.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 3. DB에 저장 (common/crud.py 활용)
        crud.save_programs(db, programs_data)
        print(f" [DB] 비교과 프로그램 {len(programs_data)}건 저장 완료!")
        
        # 4. 처리 완료 통보 (Ack)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f" [Error] 데이터 처리 중 오류 발생: {e}")
        # 에러 나면 Ack를 안 보내서 나중에 다시 처리하게 할 수도 있음 (여기선 생략)
    finally:
        db.close() # 세션 닫기

def main():
    print(" [*] Consumer가 시작되었습니다. 메시지를 기다리는 중...")
    
    init_db()
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    
    # 큐 선언 (Producer랑 같은 이름이어야 함)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    
    # 한 번에 하나씩만 처리 (부하 방지)
    channel.basic_qos(prefetch_count=1)
    
    # 구독 시작
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        connection.close()

if __name__ == "__main__":
    main()
