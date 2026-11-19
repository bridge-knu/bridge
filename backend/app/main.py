from fastapi import FastAPI

from app.api import auth, blocks, code, diagnosis, health, plan, profile, run

app = FastAPI(title="Bridge API")

for module in (health, auth, profile, diagnosis, plan, blocks, code, run):
    app.include_router(module.router)
