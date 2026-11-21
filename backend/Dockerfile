FROM python:3.11-slim

WORKDIR /app

# 워커가 샌드박스 컨테이너를 띄울 때 쓰는 docker 명령
COPY --from=docker:27.3.1-cli /usr/local/bin/docker /usr/local/bin/docker

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000
# 시작할 때 DB 마이그레이션을 먼저 적용한다.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
