"""One-time migration: add is_active column to job_descriptions."""
import asyncio, asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres:team12@localhost:5432/jd_analyser")

    # Check if column already exists
    exists = await conn.fetchval(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='job_descriptions' AND column_name='is_active'"
    )
    if exists:
        print("Column is_active already exists — skipping.")
    else:
        await conn.execute(
            "ALTER TABLE job_descriptions ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
        )
        print("Added is_active column (default TRUE for all existing JDs).")

    # Verify
    count = await conn.fetchval("SELECT COUNT(*) FROM job_descriptions WHERE is_active = TRUE")
    print(f"Active JDs: {count}")
    await conn.close()

asyncio.run(main())
