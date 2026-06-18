import asyncio, asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres:team12@localhost:5432/jd_analyser")
    rows = await conn.fetch("SELECT id, title, status, created_at FROM job_descriptions ORDER BY created_at DESC LIMIT 10")
    print(f"Total JDs in DB: {len(rows)}")
    for r in rows:
        print(f"  {r['id']} | {r['status']} | {r['title'][:50]}")

    # Check resumes for the specific JD
    JD_ID = "97cdc24c-40da-4841-81a5-1a78d9d4ad65"
    res = await conn.fetch("SELECT id, status, original_filename FROM resumes WHERE job_description_id=$1", JD_ID)
    print(f"\nResumes for JD {JD_ID}: {len(res)}")
    for r in res:
        print(f"  {r['id']} | {r['status']} | {r['original_filename']}")

    await conn.close()

asyncio.run(main())
