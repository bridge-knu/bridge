#!/bin/sh
# 새 Ubuntu 서버에서 한 번만 실행한다: Docker 설치 + 메모리 부족 대비 스왑 2GB.
#   sh deploy/setup.sh
set -e

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Docker 설치 완료. 로그아웃 후 다시 접속해야 sudo 없이 docker를 쓸 수 있습니다."
fi

if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
  echo "스왑 2GB 추가 완료"
fi

docker --version || sudo docker --version
