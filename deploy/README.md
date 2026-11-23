# 배포

서버 한 대에 Docker Compose로 전부 띄운다. 코드 실행 샌드박스가 Docker로 컨테이너를 만들기 때문에 Docker를 쓸 수 있는 VM이어야 한다.

```
인터넷 ─ 80/443 ─ web (Caddy: HTTPS, 화면 파일, /api → backend)
                    └ backend ─ db (PostgreSQL), redis
                                 worker ─ 작업마다 bridge-sandbox 컨테이너
```

## 1. 서버 준비

- Ubuntu 22.04 또는 24.04, 메모리 2GB 이상 (4GB 권장), 디스크 20GB 이상
- 방화벽(보안 그룹)에서 **TCP 22, 80, 443** 열기
- 고정(예약) 공인 IP를 붙이기. IP가 바뀌면 주소가 바뀐다

## 2. 처음 한 번

```bash
git clone https://github.com/bridge-knu/bridge.git
cd bridge
sh deploy/setup.sh          # Docker 설치 + 스왑 2GB
exit                        # 다시 접속해야 docker 권한이 적용된다
```

다시 접속한 뒤:

```bash
cd bridge/deploy
cp .env.example .env
nano .env                   # 주석 안내대로 SITE_ADDRESS, 비밀번호, JWT_SECRET 채우기
docker compose up -d --build
```

처음 빌드는 5~10분 걸린다. 끝나면 `https://<SITE_ADDRESS>` 로 접속한다.

- 주소: 공인 IP가 `34.64.12.34`면 `SITE_ADDRESS=34-64-12-34.sslip.io`. 도메인 없이 HTTPS 인증서를 받을 수 있다
- 인증서는 Caddy가 자동으로 받는다. 처음 접속이 안 되면 `docker compose logs web`에서 인증서 오류를 확인한다 (80, 443 포트가 열려 있어야 함)

## 3. 업데이트 (main에 merge된 뒤)

```bash
cd bridge && git pull
cd deploy && docker compose up -d --build
docker compose restart backend
```

- `content/`는 컨테이너에 연결만 되어 있고 backend가 시작할 때 한 번 읽어 두기 때문에, 콘텐츠만 바뀐 업데이트는 `up -d --build`로는 반영되지 않는다. 그래서 마지막에 backend를 재시작한다.

DB 마이그레이션은 backend가 시작할 때 자동으로 적용된다. 업데이트 후에는 데모 계정(`demo` / `0000`)으로 데모 시나리오를 한 번 끝까지 돌려 본다.

## DB 백업

데모 데이터라도 서버가 망가지면 복구할 수 있게 하루 한 번 백업한다. 서버에서 한 번만 실행:

```bash
mkdir -p ~/backups
(crontab -l 2>/dev/null; echo '0 4 * * * cd ~/bridge/deploy && docker compose exec -T db pg_dump -U bridge bridge | gzip > ~/backups/bridge-$(date +\%F).sql.gz && find ~/backups -mtime +7 -delete') | crontab -
```

매일 새벽 4시에 백업하고 7일 지난 파일은 지운다. 복구: `gunzip -c ~/backups/파일.sql.gz | docker compose exec -T db psql -U bridge bridge`

## 보안 설정 요약

- 열린 포트는 80·443뿐 (db, redis, backend는 서버 안에서만 접근)
- HTTPS 강제(HSTS), iframe 삽입 금지, 요청 크기 512KB 제한, API 문서 끔
- 로그인: 아이디별 5회 실패 시 1분 잠금 + IP별 1분 60번·새 계정 1시간 30개
- 코드 실행: 네트워크 차단·128MB·5초·출력 64KB, 사용자별 1분 20번
- 비밀값은 서버의 `deploy/.env`에만 있다 (`chmod 600`). 서버 열쇠는 레포 읽기 전용 deploy key

## 확인·문제 해결

```bash
docker compose ps                    # 모두 Up인지 (sandbox는 Exited(0)이 정상)
docker compose logs -f backend       # API 오류
docker compose logs -f worker        # 코드 실행 오류
curl -s https://<SITE_ADDRESS>/api/health
```

- DB 비밀번호를 바꿨다면 `DATABASE_URL`도 같이 바꾼다. 이미 만든 DB의 비밀번호는 `.env`를 바꿔도 안 바뀌므로, 처음부터 다시 하려면 `docker compose down -v` (데이터가 모두 지워진다)
- 메모리가 부족하면 `free -h`로 스왑이 켜져 있는지 확인한다
