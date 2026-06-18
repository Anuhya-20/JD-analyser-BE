"""Create the J2EE/MicroServices/GCP Technical Architect JD."""
import httpx

BASE = "http://127.0.0.1:8000/api/v1"

JD_TEXT = """
Job Opening: J2EE/MicroServices/GCP – Technical Architect
Job Code: BT0188 | Department: IT | Location: Hyderabad | Full Time | 10 to 15 Years Experience

We are seeking a seasoned Technical Architect with deep expertise in J2EE, Microservices, and
Google Cloud Platform (GCP) to lead architectural design and implementation of enterprise-grade systems.

Required Skills:
- Java, J2EE, Spring Boot, Spring Cloud, Spring MVC
- Microservices architecture, service mesh, API Gateway
- Google Cloud Platform (GCP): GKE, Cloud Run, Cloud Functions, Pub/Sub, BigQuery, Spanner, GCS
- Docker, Kubernetes, Helm
- REST APIs, gRPC, Event-driven architecture
- CI/CD pipelines (Jenkins, Cloud Build, GitLab CI)
- Git, Maven, Gradle
- Apigee API management

Preferred Skills:
- Kafka, RabbitMQ for messaging
- CQRS, Event Sourcing patterns
- Service mesh (Istio, Linkerd)
- Terraform or other IaC tools
- Security best practices (OAuth2, JWT, Zero Trust)

Responsibilities:
- Design and lead implementation of scalable microservices-based solutions using Java/J2EE on GCP
- Define technical architecture, design patterns, and coding standards for the team
- Drive cloud-native transformation and migration from monolithic to microservices architecture
- Conduct architecture reviews, code reviews, and ensure high-quality delivery
- Collaborate with product managers and business stakeholders to translate requirements into technical solutions
- Mentor senior, mid-level, and junior engineers; conduct knowledge-sharing sessions
- Own NFRs (performance, scalability, reliability, security, observability)
- Evaluate emerging technologies and recommend adoption

Experience: 10 to 15 years in Java/J2EE application development with at least 3+ years in
Technical Architect or Lead Architect role. Strong hands-on experience with GCP and microservices.

Education: Bachelor's or Master's degree in Computer Science, Engineering, or related field.
"""

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
print(f"JD Created!")
print(f"  ID     : {d['id']}")
print(f"  Title  : {d['title']}")
print(f"  Status : {d['status']}")
print()
print(f"Upload resumes with:")
print(f"  POST /api/v1/resumes/{d['id']}/upload")
print(f"Trigger pipeline with:")
print(f"  POST /api/v1/jobs/{d['id']}/process")
