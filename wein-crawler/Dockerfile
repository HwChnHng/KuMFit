FROM python:3.11-slim

# 출력 버퍼링 끄기 (print가 바로바로 보이게)
ENV PYTHONUNBUFFERED=1

# 작업 폴더 설정
WORKDIR /app

# 시스템 패키지 설치 (wget, gpg 등)
RUN apt-get update && \
    apt-get install -y wget gnupg ca-certificates && \
    # 구글 크롬 저장소 추가
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    # 구글 크롬 설치
    apt-get install -y google-chrome-stable fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

# 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사 (현재 폴더 전체 -> 컨테이너 /app)
COPY . .

# 크롬 경로 환경변수 (옵션)
ENV CHROME_BIN=/usr/bin/google-chrome

# 컨테이너 시작 시 실행할 명령
CMD ["python", "wein-crawler.py"]