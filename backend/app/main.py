import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, blocks, code, diagnosis, errors, health, plan, profile, run
from app.content import get_graph
from app.db import SessionLocal
from app.security import jwt_secret
from app.seed import ensure_demo_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    jwt_secret()  # JWT_SECRET이 안전하지 않으면 여기서 서버 시작을 멈춘다
    get_graph()  # content/*.json 형식이 틀리면 여기서 서버 시작을 멈춘다
    with SessionLocal() as db:
        ensure_demo_user(db)
    yield


# 배포에서는 API 문서(/docs, /openapi.json)를 끈다 (DISABLE_DOCS=1)
docs_off = os.environ.get("DISABLE_DOCS") == "1"
app = FastAPI(
    title="Bridge API",
    lifespan=lifespan,
    docs_url=None if docs_off else "/docs",
    redoc_url=None if docs_off else "/redoc",
    openapi_url=None if docs_off else "/openapi.json",
)
errors.install(app)

for module in (health, auth, profile, diagnosis, plan, blocks, code, run):
    app.include_router(module.router)
