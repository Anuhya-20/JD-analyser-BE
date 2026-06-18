"""
LangGraph Workflow — assembles all 6 agent nodes into a directed graph.

Flow:
  START → jd_analysis → resume_parser → profile_builder
        → matching → ranking → recommendation → END
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END, START
from loguru import logger

from app.agents.state import RecruitmentState
from app.agents.jd_analysis_agent import jd_analysis_node
from app.agents.resume_parser_agent import resume_parser_node
from app.agents.profile_builder_agent import profile_builder_node
from app.agents.matching_agent import matching_node
from app.agents.ranking_agent import ranking_node
from app.agents.recommendation_agent import recommendation_node


def _should_continue_after_jd_analysis(state: RecruitmentState) -> str:
    """Route: skip pipeline if JD analysis failed."""
    if state.get("jd_analysis") is None:
        logger.error("[Workflow] JD analysis failed — aborting pipeline")
        return "end"
    if not state.get("resume_file_infos"):
        logger.warning("[Workflow] No resumes to process")
        return "end"
    return "continue"


def _build_workflow() -> StateGraph:
    graph = StateGraph(RecruitmentState)

    # Register all agent nodes
    graph.add_node("analyze_jd", jd_analysis_node)
    graph.add_node("resume_parser", resume_parser_node)
    graph.add_node("profile_builder", profile_builder_node)
    graph.add_node("matching", matching_node)
    graph.add_node("ranking", ranking_node)
    graph.add_node("recommendation", recommendation_node)

    # Entry point
    graph.add_edge(START, "analyze_jd")

    # Conditional routing after JD analysis
    graph.add_conditional_edges(
        "analyze_jd",
        _should_continue_after_jd_analysis,
        {"continue": "resume_parser", "end": END},
    )

    # Linear pipeline
    graph.add_edge("resume_parser", "profile_builder")
    graph.add_edge("profile_builder", "matching")
    graph.add_edge("matching", "ranking")
    graph.add_edge("ranking", "recommendation")
    graph.add_edge("recommendation", END)

    return graph


# Compiled workflow — singleton, import and call .invoke() or .ainvoke()
recruitment_workflow = _build_workflow().compile()


async def run_recruitment_pipeline(
    job_description_id: str,
    job_description_text: str,
    resume_file_infos: list,
    jd_analysis: Optional[dict] = None,
    jd_embedding: Optional[list] = None,
) -> RecruitmentState:
    """
    Execute the full recruitment pipeline asynchronously.

    Pass jd_analysis + jd_embedding to skip the LLM-based JD analysis node
    (use when the JD was already analyzed at creation time via analyze_jd_only).
    """
    initial_state: RecruitmentState = {
        "job_description_id": job_description_id,
        "job_description_text": job_description_text,
        "jd_analysis": jd_analysis,
        "jd_embedding": jd_embedding,
        "resume_file_infos": resume_file_infos,
        "parsed_resumes": [],
        "candidate_profiles": [],
        "match_scores": [],
        "ranked_candidates": [],
        "recommendations": [],
        "errors": [],
        "processing_stats": {},
    }

    logger.info(
        f"[Workflow] Starting pipeline for JD={job_description_id} "
        f"with {len(resume_file_infos)} resumes"
    )

    final_state = await recruitment_workflow.ainvoke(initial_state)

    logger.info(
        f"[Workflow] Pipeline complete. Stats: {final_state.get('processing_stats', {})}"
    )
    return final_state
