from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, blocks, code, diagnosis, health, plan, profile, run
from app.db import SessionLocal
from app.seed import ensure_demo_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_demo_user(db)
    yield


app = FastAPI(title="Bridge API", lifespan=lifespan)

for module in (health, auth, profile, diagnosis, plan, blocks, code, run):
    app.include_router(module.router)
