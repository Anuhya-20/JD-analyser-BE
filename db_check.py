import asyncio, asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres:team12@localhost:5432/jd_analyser")
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    print("Tables:", [r["tablename"] for r in tables])
    jds    = await conn.fetchval("SELECT COUNT(*) FROM job_descriptions")
    res    = await conn.fetchval("SELECT COUNT(*) FROM resumes")
    cp     = await conn.fetchval("SELECT COUNT(*) FROM candidate_profiles")
    mr     = await conn.fetchval("SELECT COUNT(*) FROM match_results")
    print(f"job_descriptions  : {jds}")
    print(f"resumes           : {res}")
    print(f"candidate_profiles: {cp}")
    print(f"match_results     : {mr}")
    await conn.close()

asyncio.run(main())
