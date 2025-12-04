FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y default-libmysqlclient-dev gcc

COPY api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY broker /app/broker

COPY common /app/common

COPY api-gateway .

EXPOSE 5000

CMD ["python", "app.py"]