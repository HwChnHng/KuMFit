import os
import threading

from messaging import consume

EVERYTIME_QUEUE = os.getenv("EVERYTIME_QUEUE", "everytime_sync")
CRAWL_DONE_QUEUE = os.getenv("CRAWL_DONE_QUEUE", "crawl_done")


def run(everytime_handler, crawl_done_handler):
    t1 = threading.Thread(
        target=consume,
        args=(EVERYTIME_QUEUE, everytime_handler, f"{EVERYTIME_QUEUE}.dlq"),
        daemon=True,
    )
    t2 = threading.Thread(
        target=consume,
        args=(CRAWL_DONE_QUEUE, crawl_done_handler, f"{CRAWL_DONE_QUEUE}.dlq"),
        daemon=True,
    )
    t1.start()
    t2.start()
    t1.join()
    t2.join()
