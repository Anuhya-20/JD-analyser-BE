You are a Principal AI Architect, Staff Python Engineer, LangGraph Expert, and System Designer.

I want you to build a complete enterprise-grade AI Recruitment sk-7ee92d7795fd4a0797eddc1eaccb6a2a
  Platform that performs Job Description analysis, Resume Parsing, Candidate Matching, Ranking, and Recruiter Recommendations.

Generate the complete production-ready source code.

BUSINESS REQUIREMENT

The system should allow recruiters to:

Upload a Job Description (JD)
Upload thousands of resumes
Extract structured information from resumes
Match resumes against the JD
Rank candidates
Generate strengths and weaknesses
Suggest interview questions
Display recruiter dashboard results
Store all data in PostgreSQL
Support future scaling to millions of resumes
ARCHITECTURE

Implement the following Agentic AI workflow using LangGraph.

Job Description
      |
      V
JD Analysis Agent
      |
      V
Resume Parser Agent
      |
      V
Profile Builder Agent
      |
      V
Matching Agent
      |
      V
Ranking Agent
      |
      V
Recommendation Agent
      |
      V
PostgreSQL + Dashboard API

Each agent must be an independent LangGraph node.

Agents must communicate through a shared state object.

TECH STACK

Backend:

Python 3.12
FastAPI
LangGraph
LangChain
PostgreSQL
SQLAlchemy
Alembic
Pydantic v2

AI:

OpenAI GPT-4o
or
Gemini 2.5 Pro

Embeddings:

BAAI/bge-base-en-v1.5

Vector Database:

PGVector

Resume Processing:







How JD Analyser Ranks Candidates — HR Guide
The Big Picture: 4 Scores, 1 Final Score
Every candidate gets scored on 4 dimensions. Those 4 scores are combined into one Overall Score (0–100). The higher the overall score, the higher the rank.


┌─────────────────────────────────────────────────────────┐
│                   OVERALL SCORE (0–100)                  │
│                                                          │
│  Skill Match  +  Experience  +  Education  +  Semantic  │
│     Score           Score        Score        Fit Score  │
└─────────────────────────────────────────────────────────┘
The 4 Dimensions Explained
1. Skill Match Score
"Does this candidate have the skills we asked for?"

Compares the candidate's listed skills against the required skills in the job description.


JD Required Skills: Python, FastAPI, PostgreSQL, Docker, AWS  (5 skills)

Candidate A skills: Python ✓  FastAPI ✓  PostgreSQL ✓  Docker ✗  AWS ✗
Skill Match = 3 out of 5 = 60%

Candidate B skills: Python ✓  FastAPI ✓  PostgreSQL ✓  Docker ✓  AWS ✓
Skill Match = 5 out of 5 = 100%
2. Experience Score
"Does this candidate have the right number of years?"


JD asks for: 3–6 years

Candidate has 4 years  → Perfect range   → 100%
Candidate has 3 years  → Perfect range   →  98%
Candidate has 7 years  → Slightly over   →  96%
Candidate has 1 year   → Under by 2 yrs  →  33%
Candidate has 0 years  → Fresher         →  see below
3. Education Score
"Does this candidate meet the education requirement?"

The system understands education levels in order:


PhD / Doctorate    → Level 6  (highest)
Master's / MBA     → Level 5
Bachelor's / B.Tech→ Level 4
Diploma / Associate→ Level 3
Bootcamp / Cert    → Level 2
High School        → Level 1

JD requires: Bachelor's (Level 4)

Candidate has Master's (Level 5) → Exceeds  → 100%
Candidate has Bachelor's (Level 4)→ Meets    → 100%
Candidate has Diploma (Level 3)  → Below    →  75%
Candidate has nothing on record  → Unknown  →  80% (neutral)
4. Semantic Fit Score
"Does this candidate's overall profile 'feel' like the right role?"

This is the AI dimension. The system converts both the job description and the candidate's resume into mathematical vectors (embeddings), then measures how similar they are.


Think of it as:
  JD says "microservices, distributed systems, cloud-native"
  Candidate's resume says "designed scalable architecture,
  Kubernetes deployments, multi-service APIs"

  → They never used the exact same words
  → But semantically they are very similar → High score

This catches candidates who are a great fit but use
different terminology than the JD.
Freshers vs Seniors — Different Rules
This is the most important part. The weights change based on who the candidate is and what the JD asks for.

When the JD is for a Fresher / Entry-Level role:

┌──────────────────────────────────────────────────────┐
│         FRESHER / ENTRY-LEVEL JD WEIGHTS             │
│                                                      │
│  Skill Match     ████████████  30%                   │
│  Education       ████████████  30%  ← equally important│
│  Semantic Fit    ██████████    25%                   │
│  Experience      ██████        15%  ← less important  │
│                                                      │
│  WHY: A fresher cannot have 5 years of experience.   │
│  Their degree, skills, and projects matter more.     │
└──────────────────────────────────────────────────────┘
When the JD is for a Senior / Experienced role:

┌──────────────────────────────────────────────────────┐
│         SENIOR / EXPERIENCED JD WEIGHTS              │
│                                                      │
│  Skill Match     ██████████████  35%  ← most critical│
│  Experience      ██████████      25%  ← second most  │
│  Semantic Fit    ██████████      25%                  │
│  Education       ██████          15%  ← least critical│
│                                                      │
│  WHY: A senior candidate proves value through        │
│  real work experience, not just their degree.        │
└──────────────────────────────────────────────────────┘
How a Fresher is Scored on Experience
Freshers are never penalised for not having years of experience. Instead the system checks what the JD actually expects:

JD Requirement	Fresher Experience Score	Reason
Entry-level / 0 yrs	90%	JD was designed for freshers — no penalty
0–1 year	85%	Very low bar — close enough
1–2 years	60% (with internship) / 45%	Some work history helps
2–3 years	35%	Notable gap, but not disqualified
5+ years	15%	Clear mismatch — still ranked, just low
Internships count: A fresher with 6 months of internship experience is treated better than one with zero. The system counts every month of internship and gives partial credit.

GPA Bonus for Freshers: If a fresher has a high GPA (e.g., 3.8/4.0), up to +10 points is added to their education score. This rewards academic excellence when work experience is absent.

Full Example: Same JD, Two Candidates
JD: Senior Python Engineer — 5–8 years required


                        CANDIDATE A             CANDIDATE B
                        (Senior, 6 yrs)         (Fresher, 0 yrs)
─────────────────────────────────────────────────────────────────
Skill Match         Python,FastAPI,Docker    Python,FastAPI only
                    8/10 skills = 80%        3/10 skills = 30%

Experience          6 yrs (in 5–8 range)     0 yrs (fresher)
                    100%                     15% (JD needs 5yrs)

Education           Bachelor's               Master's (!)
                    meets req = 100%         exceeds req = 100%

Semantic Fit        Resume matches JD well   Partial match
                    85%                      40%
─────────────────────────────────────────────────────────────────
WEIGHTS             skill 35%, exp 25%,      skill 35%, exp 25%,
(senior JD)         sem 25%, edu 15%         sem 25%, edu 15%
─────────────────────────────────────────────────────────────────
OVERALL SCORE       80×0.35 + 100×0.25       30×0.35 + 15×0.25
                    + 85×0.25 + 100×0.15     + 40×0.25 + 100×0.15
                  = 28+25+21.25+15           = 10.5+3.75+10+15
                  = 89.25                    = 39.25
─────────────────────────────────────────────────────────────────
RANK                #1                       #8 (or lower)
RECOMMENDATION      STRONG HIRE              NOT RECOMMENDED
Tie-Breaking (When Two Candidates Score the Same)
If two candidates have identical overall scores, the system breaks the tie in this exact order:


Step 1 → Who matched more required skills?       (higher wins)
Step 2 → Whose profile is semantically closer?   (higher wins)
Step 3 → Who has a better experience score?      (higher wins)
Step 4 → Who has better education?               (higher wins)
Step 5 → Who has more total matched skills?      (higher wins)
Step 6 → Who is missing fewer skills?            (lower missing wins)

Still tied after all 6 steps?
→ Both candidates get the SAME rank (co-ranked)
→ Next candidate skips a rank number
→ HR interviews both — they are genuinely equivalent
What HR Sees in the Dashboard

Rank  Candidate          Score   Skill   Exp   Edu   Semantic  Verdict
───────────────────────────────────────────────────────────────────────
 #1   Rahul Sharma         89     80%    100%  100%    85%    STRONG HIRE
 #2   Priya Nair           84     75%     95%  100%    80%    HIRE
 #3   Arun Mehta           78     70%     88%   80%    74%    CONSIDER
 #3   Deepa Rao            78     70%     88%   80%    74%    CONSIDER  ← co-ranked
 #5   Vikram Rao           61     50%     72%   80%    55%    MAYBE
 #6   Anjali Patel (F)     58     45%     90%  100%    60%    MAYBE     ← fresher, edu helps
 #7   Kiran Bose           39     30%     15%  100%    40%    NOT REC   ← fresher on senior JD
The (F) tag means the AI detected the candidate as a fresher and applied the fresher-adjusted weights automatically. HR does not need to configure this — the system detects it from the resume.



pdfplumber
pymupdf
python-docx

Storage:

Local file storage
