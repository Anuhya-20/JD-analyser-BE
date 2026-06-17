You are a Principal AI Architect, Staff Python Engineer, LangGraph Expert, and System Designer.

I want you to build a complete enterprise-grade AI Recruitment Platform that performs Job Description analysis, Resume Parsing, Candidate Matching, Ranking, and Recruiter Recommendations.

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

pdfplumber
pymupdf
python-docx

Storage:

Local file storage
