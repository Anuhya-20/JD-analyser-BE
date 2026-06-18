"""
Ranking Agent — Node 5 in the LangGraph workflow.

Sorts candidates by their overall match score and assigns rank numbers.
Pure computation — no LLM call needed here.
"""
from __future__ import annotations
from loguru import logger

from app.agents.state import RecruitmentState, MatchScore


def ranking_node(state: RecruitmentState) -> RecruitmentState:
    """
    LangGraph node: Rank candidates by overall score descending.
    Reads: match_scores
    Writes: ranked_candidates
    """
    scores = state.get("match_scores", [])

    if not scores:
        logger.warning("[Ranking] No match scores to rank")
        return {**state, "ranked_candidates": []}

    # Tie-breaking cascade (all descending):
    #  1. overall_score           — primary weighted score
    #  2. skill_match_score       — more required skills matched wins
    #  3. semantic_similarity     — closer semantic fit to JD wins
    #  4. experience_score        — more relevant experience wins
    #  5. education_score         — higher education wins
    #  6. matched_skills count    — absolute number of JD skills present (not just %)
    #  7. missing_skills count    — fewer gaps is better (negated → ascending)
    #
    # If ALL 7 are equal → co-rank (same rank number, next rank is skipped)
    ranked = sorted(
        scores,
        key=lambda s: (
            s.get("overall_score") or 0.0,
            s.get("skill_match_score") or 0.0,
            s.get("semantic_similarity_score") or 0.0,
            s.get("experience_score") or 0.0,
            s.get("education_score") or 0.0,
            len(s.get("matched_skills") or []),
            -(len(s.get("missing_skills") or [])),
        ),
        reverse=True,
    )

    def _rank_key(s: MatchScore) -> tuple:
        return (
            round(s.get("overall_score") or 0.0, 2),
            round(s.get("skill_match_score") or 0.0, 2),
            round(s.get("semantic_similarity_score") or 0.0, 2),
            round(s.get("experience_score") or 0.0, 2),
            round(s.get("education_score") or 0.0, 2),
            len(s.get("matched_skills") or []),
            len(s.get("missing_skills") or []),
        )

    # Co-rank: candidates with identical keys on all 7 dimensions share the same rank.
    # The next rank after a group of N tied candidates skips N-1 positions.
    # Example: two candidates tied at rank 3 → both get rank 3, next is rank 5.
    current_rank = 1
    for i, score in enumerate(ranked):
        if i == 0:
            ranked[i] = {**score, "rank": current_rank}
        else:
            if _rank_key(ranked[i]) == _rank_key(ranked[i - 1]):
                # True tie — share the same rank
                ranked[i] = {**score, "rank": ranked[i - 1]["rank"]}
            else:
                current_rank = i + 1
                ranked[i] = {**score, "rank": current_rank}

    # Log true ties so they are visible in server logs
    true_ties = [r for r in ranked if sum(1 for x in ranked if x["rank"] == r["rank"]) > 1]
    if true_ties:
        tied_ranks = sorted({r["rank"] for r in true_ties})
        logger.warning(
            f"[Ranking] {len(true_ties)} candidates share ranks {tied_ranks} — "
            "all scoring dimensions are identical. Co-ranked."
        )

    top3 = [(r["rank"], r.get("overall_score", 0), r.get("skill_match_score", 0)) for r in ranked[:3]]
    logger.info(f"[Ranking] Ranked {len(ranked)} candidates. Top 3 (rank, overall, skill): {top3}")

    return {
        **state,
        "ranked_candidates": ranked,
        "processing_stats": {
            **state.get("processing_stats", {}),
            "candidates_ranked": len(ranked),
        },
    }
