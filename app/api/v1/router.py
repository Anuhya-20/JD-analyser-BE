from fastapi import APIRouter
from app.api.v1 import jobs, resumes, dashboard, auth, ratings, analytics, compare

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router,      prefix="/auth",      tags=["Authentication"])
api_router.include_router(jobs.router,      prefix="/jobs",      tags=["Job Descriptions"])
api_router.include_router(resumes.router,   prefix="/resumes",   tags=["Resumes"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(ratings.router,   prefix="/ratings",   tags=["Ratings"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(compare.router,   prefix="/compare",   tags=["Candidate Comparison"])
