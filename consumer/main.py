from handlers import handle_crawl_done, handle_everytime
from runner import run


def main():
    print(" [*] Consumer 시작 (공강 시간 추천 모드)")
    run(handle_everytime, handle_crawl_done)


if __name__ == "__main__":
    main()
