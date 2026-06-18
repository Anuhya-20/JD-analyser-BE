import httpx, json, sys

JD_ID = sys.argv[1]

r = httpx.get(f"http://127.0.0.1:8000/api/v1/dashboard/{JD_ID}", timeout=10)
d = r.json()
print("=== PIPELINE OVERVIEW ===")
print(f"Status         : {d['status']}")
print(f"Total Resumes  : {d['total_resumes']} | Processed: {d['processed_resumes']} | Failed: {d['failed_resumes']}")
print(f"Avg Score      : {d['avg_overall_score']}")
print()

r2 = httpx.get(f"http://127.0.0.1:8000/api/v1/dashboard/{JD_ID}/candidates", timeout=10)
candidates = r2.json()   # returns a list directly, not {"candidates": [...]}

if isinstance(candidates, dict) and "detail" in candidates:
    print(f"ERROR: {candidates['detail']}")
    sys.exit(1)

print(f"=== RANKED CANDIDATES ({len(candidates)}) ===")

for c in candidates:
    cp  = c.get("candidate_profile") or {}
    mr  = c.get("match_result") or {}
    rec = c.get("recommendation") or {}

    tier = (rec.get("level") or "?").upper()
    print()
    print(f"  Rank #{c.get('rank')} - {cp.get('full_name')}  [{tier}]")
    print(f"  Email       : {cp.get('email')} | Exp: {cp.get('total_years_experience')} yrs")
    print(f"  Overall     : {c.get('overall_score')}/100")
    print(f"  Skill       : {mr.get('skill_match_score')}")
    print(f"  Experience  : {mr.get('experience_score')}")
    print(f"  Education   : {mr.get('education_score')}")
    print(f"  Semantic    : {mr.get('semantic_similarity_score')}")
    print(f"  Skills      : {cp.get('skills')}")
    print(f"  Matched     : {mr.get('matched_skills')}")
    print(f"  Missing     : {mr.get('missing_skills')}")
    print(f"  Strengths   : {mr.get('strengths')}")
    print(f"  Weaknesses  : {mr.get('weaknesses')}")
    print(f"  Summary     : {mr.get('analysis_summary')}")
    if rec:
        print(f"  Rec Level   : {rec.get('level')}")
        print(f"  Int. Stages : {rec.get('suggested_interview_stages')}")
        qs = rec.get("interview_questions") or []
        print(f"  Questions ({len(qs)}):")
        for q in qs:
            print(f"    - {q}")
        flags = rec.get("red_flags") or []
        if flags:
            print(f"  Red Flags   : {flags}")
        pts = rec.get("highlight_points") or []
        if pts:
            print(f"  Highlights  : {pts}")
