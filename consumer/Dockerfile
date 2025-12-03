# 1. 파이썬 3.9 슬림 버전 사용
FROM python:3.9-slim

# 2. 작업 폴더 설정
WORKDIR /app

# 3. 시스템 패키지 설치 (MySQL/MariaDB 접속 라이브러리, 수치계산용 라이브러리 등)
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 4. 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 코드 복사
COPY . .

# 6. 실행 명령어 (main.py가 있다고 가정)
CMD ["python", "-u", "main.py"]