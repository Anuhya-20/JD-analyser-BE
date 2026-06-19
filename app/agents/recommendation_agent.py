"""
Recommendation Agent â€” Node 6 (final).

Token optimisations:
  - Interview questions removed entirely (biggest single saving)
  - max_tokens=600 output cap (was 1200)
  - Compressed system prompt (~80 tokens)
  - All input lists capped via trim_list()
  - work/projects summaries capped at 100 chars
  - Rule-based path for rank>20 (zero LLM cost)
"""
from __future__ import annotations
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel, Field, model_validator
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from app.agents.state import RecruitmentState, MatchScore, CandidateRecommendation
from app.agents.llm_factory import get_llm
from app.utils.token_utils import trim_list, coerce_llm_output
from app.config import settings

TOP_N_FULL_ANALYSIS = 30


class RecommendationOutput(BaseModel):
    recommendation_level: str = "maybe"
    recruiter_notes: str = ""
    suggested_interview_stages: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    highlight_points: List[str] = Field(default_factory=list)
    culture_fit_notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v):
        return coerce_llm_output(cls, v)


# Compressed prompt â€” ~100 token system message
RECOMMENDATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Senior technical recruiter. Write a CONCISE candidate brief. "
        "KEEP EVERY STRING SHORT: red flags â‰¤10 words, highlights â‰¤12 words, stages â‰¤5 words. "
        "FRESHER stages: Aptitudeâ†’Phone Screenâ†’Assignmentâ†’HR. "
        "EXPERIENCED stages: Phone Screenâ†’Codingâ†’System Designâ†’HMâ†’Ref Check. "
        "Provide 3-4 red flags, 3-4 highlights, recruiter notes in 2 sentences.",
    ),
    (
        "human",
        """Role: {jd_title} @ {company_name} | Entry-level: {is_entry_level}
Required: {required_skills} | Exp: {experience_level} {min_exp}-{max_exp}yrs

Candidate: {candidate_name} [{candidate_tier}]
Score: {overall_score}/100 | Skill:{skill_score} Exp:{exp_score} Edu:{edu_score}
Exp: {total_exp}yrs | Intern: {internship_months}mo | GPA: {gpa}
Education: {education_summary}
Skills: {all_skills}
Work/Intern: {work_summary}
Projects: {projects_summary}
Certs: {certifications}
Matched: {matched_skills} | Missing: {missing_skills}
Strengths: {strengths} | Weaknesses: {weaknesses}""",
    ),
])


def _level(score: float) -> str:
    if score >= 80: return "strongly_recommended"
    if score >= 65: return "recommended"
    if score >= 45: return "maybe"
    return "not_recommended"


def _fresher_stages() -> List[str]:
    return ["Online Aptitude/Coding Test", "Technical Phone Screen", "Take-home Assignment", "Technical Interview", "HR Round"]


def _experienced_stages() -> List[str]:
    return ["Technical Phone Screen", "Coding Interview", "System Design Round", "Hiring Manager Interview", "Reference Check"]


def _simple_rec(score: MatchScore, profile_lookup: dict) -> CandidateRecommendation:
    is_fresher = score.get("candidate_tier") == "fresher"
    profile    = profile_lookup.get(score["resume_id"], {})

    if is_fresher:
        stages = _fresher_stages()
        notes  = (
            f"Fresher with {profile.get('internship_months',0)} months internship. "
            f"Score: {score['overall_score']:.1f}/100. Matched: {trim_list(score['matched_skills'],5)}."
        )
    else:
        stages = _experienced_stages()
        notes  = (
            f"Experienced candidate ({profile.get('total_years_experience',0)} yrs). "
            f"Score: {score['overall_score']:.1f}/100. Missing: {trim_list(score['missing_skills'],5)}."
        )

    return CandidateRecommendation(
        resume_id=score["resume_id"],
        recommendation_level=_level(score["overall_score"]),
        recruiter_notes=notes,
        interview_questions=[],
        suggested_interview_stages=stages,
        red_flags=[w for w in score.get("weaknesses", [])[:3]],
        highlight_points=[s for s in score.get("strengths", [])[:3]],
        culture_fit_notes="Evaluate during interview.",
    )


def _full_rec(score: MatchScore, profile_lookup: dict, jd: dict) -> CandidateRecommendation:
    profile    = profile_lookup.get(score["resume_id"], {})
    is_fresher = score.get("candidate_tier") == "fresher"

    try:
        # Compact summaries â€” cap at 100 chars each
        work_parts = []
        for j in profile.get("work_experience", [])[:2]:
            if isinstance(j, dict):
                work_parts.append(f"{j.get('title','')}@{j.get('company','')} {j.get('duration_months','?')}mo")
        for i in profile.get("internships", [])[:1]:
            if isinstance(i, dict):
                work_parts.append(f"Intern:{i.get('title','')}@{i.get('company','')} {i.get('duration_months','?')}mo")
        work_summary = ("; ".join(work_parts) or "None")[:100]

        proj_parts = []
        for p in (profile.get("academic_projects", []) + profile.get("projects", []))[:3]:
            if isinstance(p, dict):
                techs = ",".join(p.get("technologies", [])[:3])
                proj_parts.append(f"{p.get('name','')}({techs})")
        projects_summary = ("; ".join(proj_parts) or "None")[:100]

        edu_summary = ""
        for e in profile.get("education", [])[:1]:
            if isinstance(e, dict):
                edu_summary = f"{e.get('degree','')} {e.get('field_of_study','')} {e.get('institution','')}"

        certs = trim_list(
            [c.get("name","") for c in profile.get("certifications",[])[:4] if isinstance(c,dict) and c.get("name")],
            4,
        ) or "None"

        llm = get_llm(temperature=0.3, max_tokens=600)
        chain = RECOMMENDATION_PROMPT | llm.with_structured_output(RecommendationOutput, method="function_calling")

        result: RecommendationOutput = chain.invoke({
            "jd_title":          jd.get("title", ""),
            "company_name":      jd.get("company_name", "the company"),
            "is_entry_level":    jd.get("is_entry_level", False),
            "required_skills":   trim_list(jd.get("required_skills", []), 10),
            "experience_level":  jd.get("experience_level", ""),
            "min_exp":           jd.get("min_years_experience", "N/A"),
            "max_exp":           jd.get("max_years_experience", "N/A"),
            "candidate_name":    profile.get("full_name", "Candidate"),
            "candidate_tier":    "FRESHER" if is_fresher else "EXPERIENCED",
            "overall_score":     score["overall_score"],
            "skill_score":       score["skill_match_score"],
            "exp_score":         score["experience_score"],
            "edu_score":         score["education_score"],
            "total_exp":         profile.get("total_years_experience", 0),
            "internship_months": profile.get("internship_months", 0),
            "gpa":               profile.get("gpa") or "N/A",
            "education_summary": edu_summary or "N/A",
            "all_skills":        trim_list(profile.get("skills", []), 15),
            "work_summary":      work_summary,
            "projects_summary":  projects_summary,
            "certifications":    certs,
            "matched_skills":    trim_list(score["matched_skills"], 10),
            "missing_skills":    trim_list(score["missing_skills"], 8),
            "strengths":         trim_list(score.get("strengths", []), 4, " | "),
            "weaknesses":        trim_list(score.get("weaknesses", []), 4, " | "),
        })

        return CandidateRecommendation(
            resume_id=score["resume_id"],
            recommendation_level=result.recommendation_level,
            recruiter_notes=result.recruiter_notes,
            interview_questions=[],
            suggested_interview_stages=result.suggested_interview_stages,
            red_flags=result.red_flags,
            highlight_points=result.highlight_points,
            culture_fit_notes=result.culture_fit_notes,
        )

    except Exception as e:
        logger.warning("[Recommendation] LLM failed for {}: {}", score["resume_id"], str(e))
        return _simple_rec(score, profile_lookup)


def recommendation_node(state: RecruitmentState) -> RecruitmentState:
    ranked      = state.get("ranked_candidates", [])
    profiles    = state.get("candidate_profiles", [])
    jd          = state.get("jd_analysis") or {}
    profile_map = {p["resume_id"]: p for p in profiles}

    logger.info(f"[Recommendation] {len(ranked)} candidates | top-{TOP_N_FULL_ANALYSIS} get full LLM")

    top  = [s for s in ranked if (s.get("rank") or 999) <= TOP_N_FULL_ANALYSIS]
    rest = [s for s in ranked if (s.get("rank") or 999) > TOP_N_FULL_ANALYSIS]

    recs = [_simple_rec(s, profile_map) for s in rest]

    if top:
        max_w = min(settings.MAX_RESUME_PROCESSING_WORKERS, len(top))
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            futures = {executor.submit(_full_rec, s, profile_map, jd): s for s in top}
            for f in as_completed(futures):
                recs.append(f.result())

    rank_order = {s["resume_id"]: s.get("rank", 999) for s in ranked}
    recs.sort(key=lambda r: rank_order.get(r["resume_id"], 999))

    strongly = sum(1 for r in recs if r["recommendation_level"] == "strongly_recommended")
    logger.info(f"[Recommendation] Done | {strongly} strongly recommended | {len(top)} LLM calls | {len(rest)} rule-based")

    return {
        **state,
        "recommendations": recs,
        "processing_stats": {
            **state.get("processing_stats", {}),
            "recommendations_generated": len(recs),
            "recommendation_llm_calls": len(top),
            "recommendation_rule_based": len(rest),
            "strongly_recommended": strongly,
        },
    }
