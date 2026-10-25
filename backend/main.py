"""
Acehill Repair API
Run:   uvicorn main:app --reload
Docs:  http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from database import init_db
from routers import auth, billing, reports, shop, users


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Acehill Repair", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(shop.router)
app.include_router(billing.router)
app.include_router(reports.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
