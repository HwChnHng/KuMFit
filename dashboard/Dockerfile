FROM python:3.11-slim

WORKDIR /app

# 필요한 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 대시보드 소스 복사 (app.py, templates, static 등)
COPY . .

# Flask 앱 실행
CMD ["python", "app.py"]