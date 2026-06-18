import asyncio
import asyncpg

JD_ID = "919f480a-63df-4021-a59a-cb1957de7f1b"

async def main():
    conn = await asyncpg.connect("postgresql://postgres:team12@localhost:5432/jd_analyser")

    rows = await conn.fetch(
        "SELECT overall_score, strengths, weaknesses, matched_skills, missing_skills, analysis_summary, rank FROM match_results WHERE job_description_id = $1",
        JD_ID
    )
    print("=== MATCH RESULTS ===")
    for r in rows:
        print("Score:", r["overall_score"], "Rank:", r["rank"])
        print("Strengths:", r["strengths"])
        print("Weaknesses:", r["weaknesses"])
        print("Summary:", r["analysis_summary"])
        print("Matched:", r["matched_skills"])
        print("Missing:", r["missing_skills"])

    rows2 = await conn.fetch(
        """SELECT r.level, r.suggested_interview_stages, r.highlight_points, r.red_flags
           FROM recommendations r
           JOIN match_results mr ON r.match_result_id = mr.id
           WHERE mr.job_description_id = $1""",
        JD_ID
    )
    print()
    print("=== RECOMMENDATIONS ===")
    for r in rows2:
        print("Level:", r["level"])
        print("Stages:", r["suggested_interview_stages"])
        print("Highlights:", r["highlight_points"])
        print("RedFlags:", r["red_flags"])

    await conn.close()

asyncio.run(main())
