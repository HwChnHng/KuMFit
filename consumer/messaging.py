import json
import os
import time
from typing import Optional

import pika

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")


def _connection():
    return pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))


def publish(queue_name: str, payload: dict):
    conn = _connection()
    channel = conn.channel()
    dlq_name = f"{queue_name}.dlq"
    _declare_with_dlq(channel, queue_name, dlq_name)
    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=json.dumps(payload, ensure_ascii=False),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    conn.close()


def _declare_with_dlq(channel, queue_name: str, dlq_name: Optional[str] = None):
    args = {}
    if dlq_name:
        args = {"x-dead-letter-exchange": "", "x-dead-letter-routing-key": dlq_name}
        channel.queue_declare(queue=dlq_name, durable=True)
    channel.queue_declare(queue=queue_name, durable=True, arguments=args)


def consume(queue_name: str, callback, dlq_name: Optional[str] = None, prefetch: int = 1):
    """재시도 루프 + DLQ 적용"""
    while True:
        try:
            conn = _connection()
            channel = conn.channel()
            _declare_with_dlq(channel, queue_name, dlq_name)
            channel.basic_qos(prefetch_count=prefetch)
            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            channel.start_consuming()
        except Exception as e:
            print(f" [Retry] {queue_name} 연결 재시도: {e}")
            time.sleep(5)
