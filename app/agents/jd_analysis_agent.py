"""
JD Analysis Agent â€” Node 1.
1 LLM call per pipeline run (negligible cost).
Optimisation: JD text capped at 2500 chars; system prompt compressed; max_tokens=600.
"""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from app.agents.state import RecruitmentState
from app.agents.llm_factory import get_llm
from app.services.embedding_service import embedding_service
from app.utils.token_utils import trim_text, estimate_tokens


class SalaryRange(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: str = "USD"
    period: str = "annual"


class JDStructuredOutput(BaseModel):
    title: str
    company_name: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    experience_level: Optional[str] = None       # Intern/Fresher/Junior/Mid/Senior/Lead/Principal
    min_years_experience: Optional[float] = None
    max_years_experience: Optional[float] = None
    education_requirements: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    company_context: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    salary_range: Optional[SalaryRange] = None
    industry: Optional[str] = None
    key_technologies: List[str] = Field(default_factory=list)
    is_entry_level: bool = False
    accepts_freshers: bool = False
    is_internship: bool = False

    @field_validator(
        "required_skills", "preferred_skills", "education_requirements",
        "responsibilities", "key_technologies",
        mode="before",
    )
    @classmethod
    def null_to_empty_list(cls, v):
        return v if v is not None else []


JD_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert technical recruiter extracting structured data from job descriptions.\n\n"
        "EXPERIENCE EXTRACTION RULES (critical â€” follow exactly):\n"
        "- Read the EXACT numbers written in the JD. Never infer or guess.\n"
        "- '1-2 years' â†’ min_years_experience=1, max_years_experience=2\n"
        "- '2+ years' â†’ min_years_experience=2, max_years_experience=null\n"
        "- '3 years' â†’ min_years_experience=3, max_years_experience=3\n"
        "- 'fresher/entry/0 years' â†’ min_years_experience=0, max_years_experience=1\n"
        "- If no years mentioned â†’ leave both as null\n"
        "- DO NOT set 5 years just because the tech stack looks senior.\n\n"
        "LEVEL: Intern|Fresher|Junior|Mid|Senior|Lead|Principal â€” pick from JD wording.\n"
        "SKILLS: Normalize (JSâ†’JavaScript, k8sâ†’Kubernetes).\n"
        "FLAGS: is_entry_level=true if min_years<=1 or role says fresher/entry/new-grad. "
        "accepts_freshers=true if JD welcomes freshers or min_years=0.",
    ),
    (
        "human",
        "Extract all structured information from this job description:\n\n{jd_text}",
    ),
])


def jd_analysis_node(state: RecruitmentState) -> RecruitmentState:
    if state.get("jd_analysis") is not None:
        logger.info(f"[JD Analysis] Pre-loaded from DB â€” skipping LLM call")
        return state

    logger.info(f"[JD Analysis] JD={state['job_description_id']}")

    try:
        # Cap JD text â€” 2500 chars covers virtually all JDs fully
        jd_text = trim_text(state["job_description_text"], max_chars=2500)
        est = estimate_tokens(jd_text)
        logger.debug(f"[JD Analysis] Input ~{est} tokens after trim")

        llm = get_llm(temperature=0.0, max_tokens=1500)
        chain = JD_ANALYSIS_PROMPT | llm.with_structured_output(JDStructuredOutput, method="function_calling")
        result: JDStructuredOutput = chain.invoke({"jd_text": jd_text})

        jd_analysis = result.model_dump()

        # Normalise fresher flags
        if (jd_analysis.get("min_years_experience") or 0) == 0:
            jd_analysis["accepts_freshers"] = True
            jd_analysis["is_entry_level"] = True

        logger.info(
            f"[JD Analysis] '{jd_analysis['title']}' | "
            f"entry={jd_analysis['is_entry_level']} freshers={jd_analysis['accepts_freshers']} | "
            f"{len(jd_analysis['required_skills'])} req skills"
        )

        try:
            embedding_text = _jd_embedding_text(jd_analysis, state["job_description_text"])
            jd_embedding = embedding_service.embed_document(embedding_text)
        except Exception as emb_err:
            logger.warning(f"[JD Analysis] Embedding skipped (non-critical): {emb_err}")
            jd_embedding = None

        return {
            **state,
            "jd_analysis": jd_analysis,
            "jd_embedding": jd_embedding,
            "processing_stats": {
                **state.get("processing_stats", {}),
                "jd_analysis_done": True,
                "jd_is_entry_level": jd_analysis["is_entry_level"],
            },
        }

    except Exception as e:
        logger.error(f"[JD Analysis] Failed: {e}")
        return {
            **state,
            "errors": state.get("errors", []) + [f"JD Analysis failed: {str(e)}"],
            "jd_analysis": None,
            "jd_embedding": None,
        }


def _jd_embedding_text(jd: dict, raw: str) -> str:
    parts = []
    if jd.get("title"):            parts.append(f"Title: {jd['title']}")
    if jd.get("experience_level"): parts.append(f"Level: {jd['experience_level']}")
    if jd.get("industry"):         parts.append(f"Industry: {jd['industry']}")
    if jd.get("required_skills"):  parts.append("Required: " + ", ".join(jd["required_skills"]))
    if jd.get("key_technologies"): parts.append("Tech: " + ", ".join(jd["key_technologies"]))
    if jd.get("responsibilities"):
        parts.append("Responsibilities: " + ". ".join(jd["responsibilities"][:4]))
    if jd.get("is_entry_level"):   parts.append("Entry-level / fresher role")
    parts.append(raw[:800])
    return "\n".join(parts)

