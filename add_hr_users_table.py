"""One-time migration: create hr_users table."""
import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://postgres:team12@localhost:5432/jd_analyser")

    exists = await conn.fetchval(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='hr_users'"
    )
    if exists:
        print("Table hr_users already exists — skipping.")
        await conn.close()
        return

    await conn.execute("""
        CREATE TABLE hr_users (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email       VARCHAR(255) NOT NULL UNIQUE,
            full_name   VARCHAR(255) NOT NULL,
            hashed_password TEXT NOT NULL,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            password_reset_token    VARCHAR(255),
            password_reset_expires  TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX ix_hr_users_email ON hr_users(email);
    """)
    print("Created hr_users table.")
    await conn.close()


asyncio.run(main())
