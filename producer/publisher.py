import os
import time
from typing import Optional

from broker.event_broker import EventBroker


class Publisher:
    def __init__(self, queue_name: Optional[str] = None):
        self.queue_name = queue_name or os.getenv("WEIN_DONE_QUEUE", "wein_updates_done")

    def publish_done(self, count: int):
        payload = {
            "event_type": "CRAWLING_COMPLETE",
            "timestamp": time.time(),
            "count": count,
        }
        broker = EventBroker(queue_name=self.queue_name)
        try:
            broker.publish(payload)
        finally:
            broker.close()
