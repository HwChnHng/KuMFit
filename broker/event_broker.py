import pika
import json
import os
import time

class EventBroker:
    def __init__(self, queue_name='weinjeon_updates'):
        """
        초기화: RabbitMQ 연결 설정
        """
        # 도커 환경변수에서 호스트 가져오기 (기본값: localhost)
        self.mq_host = os.getenv('RABBITMQ_HOST', 'localhost')
        self.queue_name = queue_name
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        """
        RabbitMQ 연결 시도 (실패 시 5초마다 재시도)
        도커가 켜질 때 RabbitMQ보다 파이썬이 먼저 켜지면 에러가 나기 때문에 재시도 로직 필수
        """
        while True:
            try:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(host=self.mq_host)
                )
                self.channel = self.connection.channel()
                # 큐 선언 (durable=True: RabbitMQ가 꺼져도 메시지 보존)
                self.channel.queue_declare(queue=self.queue_name, durable=True)
                print(f" [Broker] RabbitMQ({self.mq_host}) 연결 성공!")
                return
            except pika.exceptions.AMQPConnectionError:
                print(f" [Broker] 연결 실패. 5초 후 재시도합니다... ({self.mq_host})")
                time.sleep(5)

    def publish(self, data):
        """
        데이터를 JSON으로 변환하여 발행 (Publish)
        """
        try:
            # 딕셔너리 -> JSON 문자열 변환 (한글 깨짐 방지 ensure_ascii=False)
            message_body = json.dumps(data, ensure_ascii=False)
            
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 메시지를 디스크에 영구 저장 (안전성 확보)
                )
            )
            print(f" [>>>] Event Published: {data.get('title', 'No Title')}")
            
        except Exception as e:
            print(f" [Error] 메시지 전송 실패: {e}")
            # 연결이 끊어졌을 경우 재연결 로직을 여기에 추가할 수도 있음

    def close(self):
        if self.connection and not self.connection.is_closed:
            self.connection.close()