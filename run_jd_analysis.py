"""Run JD analysis directly for a given JD ID, bypassing the background task."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.agents.jd_analysis_agent import jd_analysis_node
from app.agents.state import RecruitmentState
from app.services.embedding_service import embedding_service
import asyncpg

JD_ID = sys.argv[1] if len(sys.argv) > 1 else "d3516cfe-c688-4cf6-a1d7-94e0e48821a1"
DB_URL = "postgresql://postgres:team12@localhost:5432/jd_analyser"


async def main():
    conn = await asyncpg.connect(DB_URL)

    row = await conn.fetchrow("SELECT id, title, description_text FROM job_descriptions WHERE id=$1", JD_ID)
    if not row:
        print(f"JD {JD_ID} not found")
        return

    print(f"Analyzing JD: {row['title']}")
    print(f"ID: {JD_ID}")
    print("Calling DeepSeek (please wait)...")

    state: RecruitmentState = {
        "job_description_id": JD_ID,
        "job_description_text": row["description_text"],
        "jd_analysis": None, "jd_embedding": None,
        "resume_file_infos": [], "parsed_resumes": [],
        "candidate_profiles": [], "match_scores": [],
        "ranked_candidates": [], "recommendations": [],
        "errors": [], "processing_stats": {},
    }

    result = jd_analysis_node(state)
    analysis = result.get("jd_analysis")

    if not analysis:
        print("ERROR: JD analysis returned nothing")
        errors = result.get("errors", [])
        if errors:
            print("Errors:", errors)
        return

    print("\n=== EXTRACTED FIELDS ===")
    print(f"Title            : {analysis.get('title')}")
    print(f"Experience Level : {analysis.get('experience_level')}")
    print(f"Min Years Exp    : {analysis.get('min_years_experience')}")
    print(f"Max Years Exp    : {analysis.get('max_years_experience')}")
    print(f"Location         : {analysis.get('location')}")
    print(f"Employment Type  : {analysis.get('employment_type')}")
    print(f"Industry         : {analysis.get('industry')}")
    print(f"Is Entry Level   : {analysis.get('is_entry_level')}")
    print(f"Accepts Freshers : {analysis.get('accepts_freshers')}")
    print(f"Required Skills  : {analysis.get('required_skills')}")
    print(f"Preferred Skills : {analysis.get('preferred_skills')}")
    print(f"Education Req    : {analysis.get('education_requirements')}")
    print(f"Responsibilities :")
    for r in analysis.get("responsibilities", []):
        print(f"  - {r}")

    print("\nSaving to database...")

    salary = analysis.get("salary_range")
    import json
    salary_json = json.dumps(salary) if isinstance(salary, dict) else None

    await conn.execute("""
        UPDATE job_descriptions SET
            required_skills = $2::json,
            preferred_skills = $3::json,
            experience_level = $4,
            min_years_experience = $5,
            max_years_experience = $6,
            education_requirements = $7::json,
            responsibilities = $8::json,
            company_context = $9,
            location = $10,
            employment_type = $11,
            salary_range = $12::json,
            industry = $13
        WHERE id = $1
    """,
        JD_ID,
        json.dumps(analysis.get("required_skills", [])),
        json.dumps(analysis.get("preferred_skills", [])),
        analysis.get("experience_level"),
        analysis.get("min_years_experience"),
        analysis.get("max_years_experience"),
        json.dumps(analysis.get("education_requirements", [])),
        json.dumps(analysis.get("responsibilities", [])),
        analysis.get("company_context"),
        analysis.get("location"),
        analysis.get("employment_type"),
        salary_json,
        analysis.get("industry"),
    )

    print("Done! All fields saved to database.")
    await conn.close()


asyncio.run(main())
