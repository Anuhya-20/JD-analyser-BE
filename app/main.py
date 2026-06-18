from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from app.config import settings
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"AI Provider: {settings.AI_PROVIDER.upper()}")
    logger.info(f"Embedding model: {settings.EMBEDDING_MODEL}")

    # Pre-load embedding model to warm up at startup
    try:
        from app.services.embedding_service import embedding_service
        embedding_service._load_model()
        logger.info("Embedding model loaded at startup")
    except Exception as e:
        logger.warning(f"Could not pre-load embedding model: {e}")

    yield
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## AI Recruitment Platform

Enterprise-grade platform for Job Description analysis, Resume Parsing,
Candidate Matching, Ranking, and Recruiter Recommendations using LangGraph.

### Workflow
1. **Upload JD** — POST `/api/v1/jobs`
2. **Upload Resumes** — POST `/api/v1/resumes/{jd_id}/upload`
3. **Trigger Pipeline** — POST `/api/v1/jobs/{jd_id}/process`
4. **View Dashboard** — GET `/api/v1/dashboard/{jd_id}`
5. **Ranked Candidates** — GET `/api/v1/dashboard/{jd_id}/candidates`
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — adjust origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Register API routes
app.include_router(api_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ai_provider": settings.AI_PROVIDER,
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "health": "/health",
    }
