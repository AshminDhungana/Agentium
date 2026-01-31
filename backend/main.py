from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from backend.api.routes import tasks, auth, agents, council
from backend.core.config import settings
from backend.models.database import engine, Base
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agentium API",
    description="AI Governance Platform API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(tasks.router)
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(council.router, prefix="/council", tags=["council"])

@app.on_event("startup")
async def startup():
    logger.info("Starting Agentium API...")
    async with engine.begin() as conn:
        # Create tables (simple auto-migration for dev)
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down...")
