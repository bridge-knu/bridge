from fastapi import FastAPI

from app.api import health

app = FastAPI(title="Bridge API")

app.include_router(health.router)
