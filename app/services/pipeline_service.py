"""
Pipeline Service — orchestrates database I/O before and after the LangGraph workflow.

Responsibilities:
  1. Load JD and resume records from the database
  2. Invoke the LangGraph pipeline
  3. Persist all agent outputs back to the database

Session policy: both public entry points (analyze_jd_only, execute_pipeline) create
their own AsyncSession so they can be safely run as BackgroundTasks without holding
the web-request session open for the entire duration.
"""
from __future__ import annotations
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from loguru import logger

from app.database import AsyncSessionLocal
from app.models.job_description import JobDescription, JDStatus
from app.models.resume import Resume, ResumeStatus
from app.models.candidate_profile import CandidateProfile as CandidateProfileModel
from app.models.match_result import MatchResult, MatchStatus
from app.models.recommendation import Recommendation, RecommendationLevel
from app.agents.workflow import run_recruitment_pipeline
from app.agents.jd_analysis_agent import jd_analysis_node
from app.agents.state import RecruitmentState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_pre_analysis(jd: JobDescription) -> Optional[dict]:
    """
    Reconstruct the jd_analysis dict from already-persisted DB fields.
    Returns None if JD hasn't been analyzed yet (required_skills is empty).
    Avoids a duplicate LLM call when the pipeline runs after analyze_jd_only.
    """
    if not jd.required_skills:
        return None

    min_exp = jd.min_years_experience or 0
    return {
        "title": jd.title or "",
        "company_name": jd.company_name,
        "required_skills": jd.required_skills or [],
        "preferred_skills": jd.preferred_skills or [],
        "experience_level": jd.experience_level,
        "min_years_experience": jd.min_years_experience,
        "max_years_experience": jd.max_years_experience,
        "education_requirements": jd.education_requirements or [],
        "responsibilities": jd.responsibilities or [],
        "company_context": jd.company_context,
        "location": jd.location,
        "employment_type": jd.employment_type,
        "salary_range": jd.salary_range,
        "industry": jd.industry,
        # Derived fields (not stored separately in DB)
        "key_technologies": [],
        "is_entry_level": min_exp <= 1,
        "accepts_freshers": min_exp == 0,
        "is_internship": False,
    }


# ── Public entry points ───────────────────────────────────────────────────────

async def analyze_jd_only(
    job_description_id: uuid.UUID,
) -> None:
    """
    Run ONLY the JD analysis node (no resumes needed).
    Called as a background task on JD creation so that structured fields
    (required_skills, experience_level, etc.) are populated immediately.
    Creates its own session — safe to run as a BackgroundTask.
    """
    jd_id_str = str(job_description_id)
    logger.info(f"[JD Analysis] Auto-analyzing JD={jd_id_str}")

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(JobDescription).where(JobDescription.id == job_description_id)
            )
            jd = result.scalar_one_or_none()
            if not jd:
                logger.error(f"[JD Analysis] JD {jd_id_str} not found")
                return

            # Skip if already analyzed (idempotent)
            if jd.required_skills:
                logger.info(f"[JD Analysis] Already analyzed — skipping")
                return

            import asyncio
            state: RecruitmentState = {
                "job_description_id": jd_id_str,
                "job_description_text": jd.description_text,
                "jd_analysis": None,
                "jd_embedding": None,
                "resume_file_infos": [],
                "parsed_resumes": [],
                "candidate_profiles": [],
                "match_scores": [],
                "ranked_candidates": [],
                "recommendations": [],
                "errors": [],
                "processing_stats": {},
            }

            loop = asyncio.get_event_loop()
            result_state = await loop.run_in_executor(None, jd_analysis_node, state)

            analysis = result_state.get("jd_analysis")
            if not analysis:
                logger.warning(f"[JD Analysis] No analysis returned for JD={jd_id_str}")
                return

            salary = analysis.get("salary_range")
            salary_dict = salary if isinstance(salary, dict) else (
                salary.model_dump() if hasattr(salary, "model_dump") else None
            )

            await db.execute(
                update(JobDescription)
                .where(JobDescription.id == job_description_id)
                .values(
                    required_skills=analysis.get("required_skills", []),
                    preferred_skills=analysis.get("preferred_skills", []),
                    experience_level=analysis.get("experience_level"),
                    min_years_experience=analysis.get("min_years_experience"),
                    max_years_experience=analysis.get("max_years_experience"),
                    education_requirements=analysis.get("education_requirements", []),
                    responsibilities=analysis.get("responsibilities", []),
                    company_context=analysis.get("company_context"),
                    location=analysis.get("location"),
                    employment_type=analysis.get("employment_type"),
                    salary_range=salary_dict,
                    industry=analysis.get("industry"),
                    embedding=result_state.get("jd_embedding"),
                )
            )
            await db.commit()
            logger.info(
                f"[JD Analysis] Done for JD={jd_id_str} | "
                f"{len(analysis.get('required_skills', []))} required skills | "
                f"level={analysis.get('experience_level')}"
            )

        except Exception as e:
            logger.error(f"[JD Analysis] Failed for JD={jd_id_str}: {e}", exc_info=True)


async def execute_pipeline(
    job_description_id: uuid.UUID,
) -> None:
    """
    Main entry point. Runs the full recruitment pipeline for a JD.
    Called as a background task from the API.
    Creates its own session — safe to run as a BackgroundTask.
    """
    jd_id_str = str(job_description_id)
    logger.info(f"[Pipeline] Starting for JD={jd_id_str}")

    async with AsyncSessionLocal() as db:
        # Mark JD as analyzing
        await db.execute(
            update(JobDescription)
            .where(JobDescription.id == job_description_id)
            .values(status=JDStatus.ANALYZING)
        )
        await db.commit()

        try:
            # Load JD
            result = await db.execute(
                select(JobDescription).where(JobDescription.id == job_description_id)
            )
            jd = result.scalar_one_or_none()
            if not jd:
                raise ValueError(f"JobDescription {jd_id_str} not found")

            # Load all pending resumes for this JD
            result = await db.execute(
                select(Resume).where(
                    Resume.job_description_id == job_description_id,
                    Resume.status == ResumeStatus.PENDING,
                )
            )
            resumes = result.scalars().all()

            if not resumes:
                logger.warning(f"[Pipeline] No pending resumes for JD={jd_id_str}")
                await _mark_jd_complete(db, job_description_id)
                return

            resume_file_infos = [
                {
                    "resume_id": str(r.id),
                    "file_path": r.file_path,
                    "filename": r.original_filename,
                    "file_type": r.file_type or "pdf",
                }
                for r in resumes
            ]

            # Mark resumes as parsing
            resume_ids = [r.id for r in resumes]
            await db.execute(
                update(Resume)
                .where(Resume.id.in_(resume_ids))
                .values(status=ResumeStatus.PARSING)
            )
            await db.commit()

            # Reuse existing JD analysis from DB to skip the duplicate LLM call (~7s saved)
            pre_analysis = _build_pre_analysis(jd)
            pre_embedding = jd.embedding if pre_analysis else None
            if pre_analysis:
                logger.info(f"[Pipeline] Using pre-loaded JD analysis — skipping LLM call")

            # Run LangGraph pipeline
            final_state: RecruitmentState = await run_recruitment_pipeline(
                job_description_id=jd_id_str,
                job_description_text=jd.description_text,
                resume_file_infos=resume_file_infos,
                jd_analysis=pre_analysis,
                jd_embedding=pre_embedding,
            )

            # Persist results
            if not pre_analysis:
                # JD wasn't pre-analyzed — persist the fresh analysis from the pipeline
                await _persist_jd_analysis(db, job_description_id, final_state)
            await _persist_parsed_resumes(db, final_state)
            await _persist_candidate_profiles(db, job_description_id, final_state)
            await _persist_match_results(db, job_description_id, final_state)
            await _persist_recommendations(db, final_state)

            await _mark_jd_complete(db, job_description_id)
            logger.info(f"[Pipeline] Completed successfully for JD={jd_id_str}")

        except Exception as e:
            logger.error(f"[Pipeline] Failed for JD={jd_id_str}: {e}", exc_info=True)
            await db.rollback()
            await db.execute(
                update(JobDescription)
                .where(JobDescription.id == job_description_id)
                .values(status=JDStatus.FAILED, error_message=str(e)[:1000])
            )
            await db.commit()


# ── Persistence helpers ───────────────────────────────────────────────────────

async def _persist_jd_analysis(
    db: AsyncSession,
    jd_id: uuid.UUID,
    state: RecruitmentState,
) -> None:
    analysis = state.get("jd_analysis") or {}
    if not analysis:
        return

    salary = analysis.get("salary_range")
    salary_dict = salary if isinstance(salary, dict) else (salary.model_dump() if hasattr(salary, "model_dump") else None)

    await db.execute(
        update(JobDescription)
        .where(JobDescription.id == jd_id)
        .values(
            required_skills=analysis.get("required_skills", []),
            preferred_skills=analysis.get("preferred_skills", []),
            experience_level=analysis.get("experience_level"),
            min_years_experience=analysis.get("min_years_experience"),
            max_years_experience=analysis.get("max_years_experience"),
            education_requirements=analysis.get("education_requirements", []),
            responsibilities=analysis.get("responsibilities", []),
            company_context=analysis.get("company_context"),
            location=analysis.get("location"),
            employment_type=analysis.get("employment_type"),
            salary_range=salary_dict,
            industry=analysis.get("industry"),
            embedding=state.get("jd_embedding"),
        )
    )
    await db.commit()
    logger.debug(f"[Pipeline] Persisted JD analysis for {jd_id}")


async def _persist_parsed_resumes(
    db: AsyncSession,
    state: RecruitmentState,
) -> None:
    parsed = state.get("parsed_resumes", [])
    for r in parsed:
        resume_id = uuid.UUID(r["resume_id"])
        if r.get("error"):
            await db.execute(
                update(Resume)
                .where(Resume.id == resume_id)
                .values(
                    status=ResumeStatus.FAILED,
                    error_message=r["error"][:500],
                    raw_text=r.get("raw_text", ""),
                    page_count=r.get("page_count", 0),
                )
            )
        else:
            await db.execute(
                update(Resume)
                .where(Resume.id == resume_id)
                .values(
                    raw_text=r.get("raw_text", ""),
                    page_count=r.get("page_count", 0),
                    status=ResumeStatus.PROFILING,
                )
            )
    await db.commit()


async def _persist_candidate_profiles(
    db: AsyncSession,
    jd_id: uuid.UUID,
    state: RecruitmentState,
) -> None:
    profiles = state.get("candidate_profiles", [])
    for p in profiles:
        resume_id = uuid.UUID(p["resume_id"])

        if p.get("error"):
            await db.execute(
                update(Resume)
                .where(Resume.id == resume_id)
                .values(status=ResumeStatus.FAILED, error_message=p["error"][:500])
            )
            continue

        profile_record = CandidateProfileModel(
            resume_id=resume_id,
            job_description_id=jd_id,
            full_name=p.get("full_name"),
            email=p.get("email"),
            phone=p.get("phone"),
            location=p.get("location"),
            linkedin_url=p.get("linkedin_url"),
            github_url=p.get("github_url"),
            portfolio_url=p.get("portfolio_url"),
            summary=p.get("summary"),
            skills=p.get("skills", []),
            work_experience=p.get("work_experience", []) + p.get("internships", []),
            education=p.get("education", []),
            certifications=p.get("certifications", []),
            projects=p.get("projects", []) + p.get("academic_projects", []),
            languages=p.get("languages", []),
            total_years_experience=p.get("total_years_experience", 0.0),
            internship_months=p.get("internship_months", 0),
            gpa=p.get("gpa"),
            is_fresher=p.get("is_fresher", False),
            highest_education_level=p.get("highest_education_level"),
            embedding=p.get("embedding"),
        )
        db.add(profile_record)
        await db.execute(
            update(Resume)
            .where(Resume.id == resume_id)
            .values(status=ResumeStatus.COMPLETED)
        )

    await db.commit()
    logger.debug(f"[Pipeline] Persisted {len(profiles)} candidate profiles")


async def _persist_match_results(
    db: AsyncSession,
    jd_id: uuid.UUID,
    state: RecruitmentState,
) -> None:
    result = await db.execute(
        select(CandidateProfileModel).where(
            CandidateProfileModel.job_description_id == jd_id
        )
    )
    profiles = result.scalars().all()
    profile_by_resume = {str(p.resume_id): p for p in profiles}

    ranked = state.get("ranked_candidates", [])
    for score in ranked:
        profile = profile_by_resume.get(score["resume_id"])
        if not profile:
            continue

        mr = MatchResult(
            job_description_id=jd_id,
            candidate_profile_id=profile.id,
            overall_score=score.get("overall_score"),
            skill_match_score=score.get("skill_match_score"),
            experience_score=score.get("experience_score"),
            education_score=score.get("education_score"),
            semantic_similarity_score=score.get("semantic_similarity_score"),
            keyword_match_score=score.get("keyword_match_score"),
            strengths=score.get("strengths", []),
            weaknesses=score.get("weaknesses", []),
            matched_skills=score.get("matched_skills", []),
            missing_skills=score.get("missing_skills", []),
            analysis_summary=score.get("analysis_summary", ""),
            candidate_tier=score.get("candidate_tier", "experienced"),
            rank=score.get("rank"),
            status=MatchStatus.COMPLETED,
        )
        db.add(mr)

    await db.commit()
    logger.debug(f"[Pipeline] Persisted {len(ranked)} match results")


async def _persist_recommendations(
    db: AsyncSession,
    state: RecruitmentState,
) -> None:
    recs = state.get("recommendations", [])
    if not recs:
        return

    resume_ids = [uuid.UUID(r["resume_id"]) for r in recs]

    # Load all candidate profiles for these resumes in ONE query (was N+1)
    cp_result = await db.execute(
        select(CandidateProfileModel).where(
            CandidateProfileModel.resume_id.in_(resume_ids)
        )
    )
    cp_by_resume = {str(cp.resume_id): cp for cp in cp_result.scalars().all()}

    # Load all relevant match results in ONE query (was N+1)
    profile_ids = [cp.id for cp in cp_by_resume.values()]
    mr_result = await db.execute(
        select(MatchResult).where(
            MatchResult.candidate_profile_id.in_(profile_ids)
        )
    )
    mr_by_profile = {str(mr.candidate_profile_id): mr for mr in mr_result.scalars().all()}

    level_map = {
        "strongly_recommended": RecommendationLevel.STRONGLY_RECOMMENDED,
        "strong_yes":           RecommendationLevel.STRONGLY_RECOMMENDED,
        "strongly recommended": RecommendationLevel.STRONGLY_RECOMMENDED,
        "recommended":          RecommendationLevel.RECOMMENDED,
        "yes":                  RecommendationLevel.RECOMMENDED,
        "maybe":                RecommendationLevel.MAYBE,
        "maybe_recommended":    RecommendationLevel.MAYBE,
        "not_recommended":      RecommendationLevel.NOT_RECOMMENDED,
        "no":                   RecommendationLevel.NOT_RECOMMENDED,
    }

    for rec in recs:
        cp = cp_by_resume.get(rec["resume_id"])
        if not cp:
            continue
        mr = mr_by_profile.get(str(cp.id))
        if not mr:
            continue

        level_str = rec.get("recommendation_level", "maybe").lower().strip().replace(" ", "_")
        level = level_map.get(level_str, RecommendationLevel.MAYBE)

        recommendation = Recommendation(
            match_result_id=mr.id,
            level=level,
            recruiter_notes=rec.get("recruiter_notes", ""),
            interview_questions=rec.get("interview_questions", []),
            suggested_interview_stages=rec.get("suggested_interview_stages", []),
            red_flags=rec.get("red_flags", []),
            highlight_points=rec.get("highlight_points", []),
            culture_fit_notes=rec.get("culture_fit_notes", ""),
        )
        db.add(recommendation)

    await db.commit()
    logger.debug(f"[Pipeline] Persisted {len(recs)} recommendations")


async def _mark_jd_complete(db: AsyncSession, jd_id: uuid.UUID) -> None:
    await db.execute(
        update(JobDescription)
        .where(JobDescription.id == jd_id)
        .values(status=JDStatus.COMPLETED)
    )
    await db.commit()
