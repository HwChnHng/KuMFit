import getpass
import os
import signal
import sys
import threading
import time

from crawler_service import fetch_programs
from publisher import Publisher
from repository import save_programs


def _get_user_credentials():
    """환경변수 우선, 없으면 입력받기 (도커 백그라운드 모드 대응)"""
    user_id = os.getenv("WEIN_ID")
    user_pw = os.getenv("WEIN_PW")

    if not user_id:
        try:
            print("\n [Input] 환경변수에 WEIN_ID가 없습니다.")
            user_id = input(" ▶ 위인전 아이디를 입력하세요: ")
        except EOFError:
            print(" [!] Error: Docker 백그라운드 모드에서는 입력을 받을 수 없습니다.")
            return None, None

    if not user_pw:
        try:
            if not user_id:
                return None, None
            user_pw = getpass.getpass(" ▶ 위인전 비밀번호를 입력하세요: ")
        except EOFError:
            print(" [!] Error: Docker 백그라운드 모드에서는 입력을 받을 수 없습니다.")
            return None, None

    return user_id, user_pw


def run_forever(base_interval: int = 3600, backoff_initial: int = 60, backoff_max: int = 600):
    """성공 시 base_interval, 실패 시 지수 백오프 대기. SIGINT/SIGTERM graceful 종료."""
    user_id, user_pw = _get_user_credentials()
    if not user_id or not user_pw:
        print(" [!] 인증 정보가 없어 프로그램을 종료합니다.")
        return

    stop_event = threading.Event()

    def _handle_signal(signum, frame):
        print(f"\n [Signal] 종료 신호 수신({signum}), 현재 사이클 종료 후 정지합니다.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass  # 일부 플랫폼/스레드 환경에서 설정 불가 시 무시

    publisher = Publisher()
    backoff = backoff_initial

    while not stop_event.is_set():
        print(f"\n [Cycle] 크롤링 시작... ({time.strftime('%H:%M:%S')})")
        try:
            programs = fetch_programs(user_id, user_pw)
            if programs:
                print(f" [Crawling] {len(programs)}건 수집 성공. DB 저장 및 이벤트 발행...")
                save_programs(programs)
                publisher.publish_done(len(programs))
            else:
                print(" [Crawling] 수집된 데이터가 없습니다.")

            # 성공 시 백오프 리셋
            backoff = backoff_initial
            sleep_seconds = base_interval
        except Exception as e:
            print(f" [Error] 크롤링/저장/발행 중 오류 발생: {e}")
            sleep_seconds = backoff
            backoff = min(backoff * 2, backoff_max)

        print(f" [Sleep] {sleep_seconds}초 대기합니다... (Ctrl+C로 종료)")
        stop_event.wait(sleep_seconds)

    print(" [Exit] 프로듀서 종료")
