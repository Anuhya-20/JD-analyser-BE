import httpx, time

BASE = "http://127.0.0.1:8000/api/v1"

JD_TEXT = """Job Opening
J2EE/MicroServices/GCP – Technical Architect
BT0188 | IT | Hyderabad | Full Time | 10 to 15 Years Experience

Job Description: J2EE/MicroServices/GCP – Technical Architect

We are seeking a highly accomplished Architect to lead the design and implementation of enterprise-scale digital platforms and cloud-native solutions. The ideal candidate will be responsible for defining architectural vision, establishing technology standards, driving modernization initiatives, and ensuring scalable, secure, and resilient systems across the organization.

The role requires strong expertise in Java-based enterprise platforms, microservices architecture, cloud-native development on GCP, distributed systems, and enterprise integration patterns. The Architect will work closely with business stakeholders, product leadership, engineering teams, and delivery managers to align technology solutions with strategic business objectives.

Requirements:
- 10–15 years of experience in designing and delivering large-scale enterprise applications using Java (8/11/17/21), Spring Boot, and Microservices Architecture.
- Proven expertise in Solution Architecture, Enterprise Architecture, and Cloud-Native Architecture for mission-critical applications.
- Strong experience architecting solutions on Google Cloud Platform (GCP) utilizing services such as GKE, Cloud Run, Pub/Sub, Cloud SQL, Cloud Storage, Secret Manager, IAM, VPC, Load Balancing, Cloud Monitoring, and Cloud Logging.
- Deep understanding of Distributed Systems, Event-Driven Architecture, Domain-Driven Design (DDD), and API-First Design Principles.
- Experience designing high-throughput, low-latency systems using Kafka, Pub/Sub, and asynchronous messaging patterns.
- Expertise in designing secure applications using OAuth 2.0, OpenID Connect, JWT, IAM, and API Security standards.
- Work with relational and NoSQL databases including PostgreSQL, MySQL, Cloud SQL, MongoDB.
- Ability to define architecture standards, technology roadmaps, governance frameworks, and engineering best practices across multiple teams.
- Strong stakeholder management skills with experience working with business leaders, product owners, engineering teams, and executive leadership.
- Define non-functional requirements including scalability, availability, performance, security, observability, and disaster recovery.
- Drive modernization initiatives including cloud migration, microservices adoption, API transformation.
- Familiarity with Observability platforms such as Grafana, Prometheus, ELK, Splunk, and OpenTelemetry.
- Experience deploying and managing containerized applications in cloud-native environments.
- Understanding of OAuth 2.0, JWT, OpenID Connect, and secure API development practices.
- Good oral and written communication skills. Good team player. Proactive and adaptive."""

print("Creating JD...")
r = httpx.post(
    f"{BASE}/jobs",
    data={
        "title": "J2EE/MicroServices/GCP – Technical Architect",
        "company_name": "Bilvantis Technologies",
        "description_text": JD_TEXT.strip(),
    },
    timeout=15,
)
r.raise_for_status()
d = r.json()
JD_ID = d["id"]
print(f"  ID     : {JD_ID}")
print(f"  Status : {d['status']}")
print()
print("Waiting for background JD analysis (DeepSeek is extracting structured fields)...")

for attempt in range(1, 13):
    time.sleep(10)
    r2 = httpx.get(f"{BASE}/jobs/{JD_ID}", timeout=15)
    d2 = r2.json()
    req = d2.get("required_skills")
    if req:
        print(f"  [+] Fields populated after {attempt*10}s!")
        break
    print(f"  [{attempt*10}s] Still waiting... (required_skills still null)")
else:
    print("  [!] Timed out — DeepSeek may be slow. Run: python check_jd.py " + JD_ID)

print()
print("=== EXTRACTED JD FIELDS ===")
r3 = httpx.get(f"{BASE}/jobs/{JD_ID}", timeout=15)
d3 = r3.json()
print(f"JD ID            : {JD_ID}")
print(f"Title            : {d3.get('title')}")
print(f"Status           : {d3.get('status')}")
print(f"Experience Level : {d3.get('experience_level')}")
print(f"Min Exp (years)  : {d3.get('min_years_experience')}")
print(f"Max Exp (years)  : {d3.get('max_years_experience')}")
print(f"Location         : {d3.get('location')}")
print(f"Employment Type  : {d3.get('employment_type')}")
print(f"Industry         : {d3.get('industry')}")
print(f"Required Skills  : {d3.get('required_skills')}")
print(f"Preferred Skills : {d3.get('preferred_skills')}")
print(f"Education Req    : {d3.get('education_requirements')}")
print(f"Responsibilities : {d3.get('responsibilities')}")
