from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, blocks, code, diagnosis, health, plan, profile, run
from app.db import SessionLocal
from app.security import jwt_secret
from app.seed import ensure_demo_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    jwt_secret()  # JWT_SECRET이 안전하지 않으면 여기서 서버 시작을 멈춘다
    with SessionLocal() as db:
        ensure_demo_user(db)
    yield


app = FastAPI(title="Bridge API", lifespan=lifespan)

for module in (health, auth, profile, diagnosis, plan, blocks, code, run):
    app.include_router(module.router)
