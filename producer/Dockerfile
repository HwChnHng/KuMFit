# 1. 베이스 이미지
FROM python:3.9-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. Chromium 및 필수 패키지 설치
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 4. 라이브러리 설치
# (docker-compose context가 루트이므로 경로 명시)
COPY producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. [수정됨] Broker 모듈 복사 (broker 폴더 -> 컨테이너 안으로)
COPY broker /app/broker

COPY common /app/common

# 6. 프로듀서 소스 코드 복사
COPY producer .

# 7. 실행
CMD ["python", "-u", "main.py"]