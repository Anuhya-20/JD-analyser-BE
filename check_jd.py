import asyncio, asyncpg, sys

JD_ID = sys.argv[1] if len(sys.argv) > 1 else "d3516cfe-c688-4cf6-a1d7-94e0e48821a1"

async def main():
    conn = await asyncpg.connect("postgresql://postgres:team12@localhost:5432/jd_analyser")
    row = await conn.fetchrow(
        "SELECT id, title, status, required_skills, experience_level, min_years_experience, max_years_experience, location, employment_type, industry, error_message, updated_at FROM job_descriptions WHERE id=$1",
        JD_ID
    )
    if not row:
        print("JD not found")
    else:
        print(f"ID              : {row['id']}")
        print(f"Title           : {row['title']}")
        print(f"Status          : {row['status']}")
        print(f"required_skills : {row['required_skills']}")
        print(f"experience_level: {row['experience_level']}")
        print(f"min_years_exp   : {row['min_years_experience']}")
        print(f"max_years_exp   : {row['max_years_experience']}")
        print(f"location        : {row['location']}")
        print(f"employment_type : {row['employment_type']}")
        print(f"industry        : {row['industry']}")
        print(f"error_message   : {row['error_message']}")
        print(f"updated_at      : {row['updated_at']}")
    await conn.close()

asyncio.run(main())
