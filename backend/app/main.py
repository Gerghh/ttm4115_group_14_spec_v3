import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .db.database import engine, Base, SessionLocal
from .models import drone, diagnostic  # noqa: F401 — ensure tables are registered
from .api import health, drones
from .db.seed import seed_drones, reseed_drones

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend_optional")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_drones(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Drone Readiness API",
    description="Monitor drone availability and readiness via Pi agent diagnostics.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(drones.router)


@app.post("/seed", tags=["admin"], summary="Wipe and re-seed demo drones")
def manual_seed():
    db = SessionLocal()
    try:
        reseed_drones(db)
    finally:
        db.close()
    return {"message": "Database re-seeded with demo drones."}


# Serve the optional frontend dashboard if the directory exists
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
