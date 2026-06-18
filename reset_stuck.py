"""Reset stuck pipelines back to failed status so they don't pollute the dashboard."""
import asyncio
import asyncpg

STUCK_JD_IDS = [
    "fed43e0b-1cff-4fd5-a878-8ed0a587b50a",
    "74627793-117a-492f-ab9b-ecaf3e8c2f7d",
]

async def main():
    conn = await asyncpg.connect("postgresql://postgres:team12@localhost:5432/jd_analyser")
    for jd_id in STUCK_JD_IDS:
        await conn.execute(
            "UPDATE job_descriptions SET status='failed', error_message='Pipeline killed by server reload during DeepSeek API slowdown' WHERE id=$1 AND status='analyzing'",
            jd_id
        )
        print(f"Reset {jd_id}")
    await conn.close()
    print("Done")

asyncio.run(main())
