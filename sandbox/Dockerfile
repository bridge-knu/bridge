# 학생 코드를 실행하는 이미지. 워커가 작업마다 새 컨테이너로 띄우고 끝나면 지운다.
FROM alpine:3.20

RUN apk add --no-cache gcc musl-dev python3

COPY runner.py /runner.py

USER 1000:1000
ENTRYPOINT ["python3", "/runner.py"]
