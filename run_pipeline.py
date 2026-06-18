"""Full end-to-end pipeline test script."""
import httpx
import time
import sys

BASE = "http://127.0.0.1:8000/api/v1"
RESUME_PATH = "uploads/resumes/sample_resume.txt"
JD_TEXT = (
    "We are looking for a Senior Python Engineer with 5+ years experience. "
    "Required skills: Python, FastAPI, PostgreSQL, Docker, AWS, Redis, SQLAlchemy, "
    "REST APIs, Git, Kubernetes, CI/CD, Linux. Must have experience with microservices "
    "architecture, async programming, and system design. "
    "Bachelor degree in Computer Science or equivalent."
)


def create_jd():
    r = httpx.post(
        f"{BASE}/jobs",
        data={"title": "Senior Python Engineer", "company_name": "TechCorp", "description_text": JD_TEXT},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    print(f"[1] JD created: {d['id']}  status={d['status']}")
    return d["id"]


def upload_resume(jd_id):
    with open(RESUME_PATH, "rb") as f:
        r = httpx.post(
            f"{BASE}/resumes/{jd_id}/upload",
            files=[("files", ("sample_resume.txt", f, "text/plain"))],
            timeout=15,
        )
    r.raise_for_status()
    d = r.json()
    uploaded = d.get("uploaded", [])
    resume_id = uploaded[0]["id"] if uploaded else "?"
    print(f"[2] Resume uploaded: {resume_id}  total={d.get('total_uploaded')}")
    return resume_id


def run_pipeline(jd_id):
    r = httpx.post(f"{BASE}/jobs/{jd_id}/process", timeout=15)
    r.raise_for_status()
    d = r.json()
    print(f"[3] Pipeline started: {d.get('message', d)}")


def poll_status(jd_id, timeout=300):
    print("[4] Polling pipeline status...")
    for i in range(timeout // 5):
        r = httpx.get(f"{BASE}/dashboard/{jd_id}/status", timeout=10)
        d = r.json()
        status = d.get("status")
        progress = d.get("progress_percentage", 0)
        print(f"    [{i*5:3d}s] status={status}  progress={progress}%  profiled={d.get('profiled')}  matched={d.get('matched')}  rec={d.get('recommended')}")
        if status in ("completed", "failed"):
            return d
        time.sleep(5)
    print("TIMEOUT waiting for pipeline")
    return {}


def show_results(jd_id):
    r = httpx.get(f"{BASE}/dashboard/{jd_id}", timeout=10)
    d = r.json()
    print()
    print("=== PIPELINE OVERVIEW ===")
    print(f"Status         : {d['status']}")
    print(f"Total Resumes  : {d['total_resumes']} | Processed: {d['processed_resumes']} | Failed: {d['failed_resumes']}")
    print(f"Avg Score      : {d['avg_overall_score']}")

    r2 = httpx.get(f"{BASE}/dashboard/{jd_id}/candidates", timeout=10)
    candidates = r2.json()
    print()
    print(f"=== RANKED CANDIDATES ({len(candidates)}) ===")

    for c in candidates:
        cp  = c.get("candidate_profile") or {}
        mr  = c.get("match_result") or {}
        rec = c.get("recommendation") or {}
        print()
        print(f"  Rank #{c.get('rank')} - {cp.get('full_name')}  [{(rec.get('level') or '?').upper()}]")
        print(f"  Email       : {cp.get('email')} | Exp: {cp.get('total_years_experience')} yrs")
        print(f"  Overall     : {c.get('overall_score')}/100")
        print(f"  Skill:{mr.get('skill_match_score')}  Exp:{mr.get('experience_score')}  Edu:{mr.get('education_score')}  Sem:{mr.get('semantic_similarity_score')}")
        print(f"  Skills      : {cp.get('skills')}")
        print(f"  Matched     : {mr.get('matched_skills')}")
        print(f"  Missing     : {mr.get('missing_skills')}")
        print(f"  Strengths   : {mr.get('strengths')}")
        print(f"  Weaknesses  : {mr.get('weaknesses')}")
        print(f"  Summary     : {mr.get('analysis_summary')}")
        if rec:
            print(f"  Rec Level   : {rec.get('level')}")
            print(f"  Highlights  : {rec.get('highlight_points')}")
            print(f"  Red Flags   : {rec.get('red_flags')}")
            print(f"  Int. Stages : {rec.get('suggested_interview_stages')}")
            qs = rec.get("interview_questions") or []
            print(f"  Questions ({len(qs)}):")
            for q in qs:
                print(f"    - {q}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        jd_id = sys.argv[1]
        show_results(jd_id)
    else:
        jd_id = create_jd()
        upload_resume(jd_id)
        run_pipeline(jd_id)
        poll_status(jd_id)
        show_results(jd_id)
