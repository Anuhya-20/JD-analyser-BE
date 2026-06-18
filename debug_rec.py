"""Debug: test the recommendation LLM call directly."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.agents.recommendation_agent import RecommendationOutput, RECOMMENDATION_PROMPT, _simple_rec, _experienced_stages
from app.agents.llm_factory import get_llm
from app.utils.token_utils import trim_list

score = {
    "resume_id": "test-123",
    "overall_score": 79.0,
    "skill_match_score": 50.0,
    "experience_score": 100.0,
    "education_score": 100.0,
    "semantic_similarity_score": 86.0,
    "candidate_tier": "experienced",
    "matched_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "missing_skills": ["Microservices", "System Design"],
    "strengths": ["Strong FastAPI expertise", "AWS production experience"],
    "weaknesses": ["No explicit microservices architecture mentioned"],
    "rank": 1,
}

profile = {
    "full_name": "Rahul Sharma",
    "total_years_experience": 6.0,
    "internship_months": 0,
    "gpa": 3.36,
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "Redis"],
    "work_experience": [
        {"title": "Senior Backend Engineer", "company": "DataSync Technologies", "duration_months": 30},
    ],
    "internships": [],
    "academic_projects": [],
    "projects": [],
    "education": [{"degree": "B.Tech", "field_of_study": "Computer Science", "institution": "JNTU"}],
    "certifications": [{"name": "AWS Certified Solutions Architect"}],
}

jd = {
    "title": "Senior Python Engineer",
    "company_name": "TechCorp",
    "is_entry_level": False,
    "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
    "experience_level": "Senior",
    "min_years_experience": 5,
    "max_years_experience": 10,
}

print("Testing recommendation LLM call...")
try:
    llm = get_llm(temperature=0.3, max_tokens=650)
    chain = RECOMMENDATION_PROMPT | llm.with_structured_output(RecommendationOutput)

    result = chain.invoke({
        "jd_title": jd["title"],
        "company_name": jd["company_name"],
        "is_entry_level": jd["is_entry_level"],
        "required_skills": trim_list(jd["required_skills"], 10),
        "experience_level": jd["experience_level"],
        "min_exp": jd["min_years_experience"],
        "max_exp": jd["max_years_experience"],
        "candidate_name": profile["full_name"],
        "candidate_tier": "EXPERIENCED",
        "overall_score": score["overall_score"],
        "skill_score": score["skill_match_score"],
        "exp_score": score["experience_score"],
        "edu_score": score["education_score"],
        "total_exp": profile["total_years_experience"],
        "internship_months": profile["internship_months"],
        "gpa": profile["gpa"],
        "education_summary": "B.Tech Computer Science JNTU",
        "all_skills": trim_list(profile["skills"], 15),
        "work_summary": "Senior Backend Engineer@DataSync 30mo",
        "projects_summary": "None",
        "certifications": "AWS Certified Solutions Architect",
        "matched_skills": trim_list(score["matched_skills"], 10),
        "missing_skills": trim_list(score["missing_skills"], 8),
        "strengths": trim_list(score["strengths"], 4, " | "),
        "weaknesses": trim_list(score["weaknesses"], 4, " | "),
    })

    print("SUCCESS!")
    print(f"Level: {result.recommendation_level}")
    print(f"Questions ({len(result.interview_questions)}):")
    for q in result.interview_questions:
        print(f"  - {q}")
    print(f"Stages: {result.suggested_interview_stages}")
    print(f"Highlights: {result.highlight_points}")
    print(f"Red Flags: {result.red_flags}")

except Exception as e:
    import traceback
    print(f"FAILED: {e}")
    traceback.print_exc()
