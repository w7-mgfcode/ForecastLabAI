#!/usr/bin/env python
"""Check database connectivity.

Usage:
    uv run python scripts/check_db.py
"""

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


async def check_database():
    """Verify database connection and basic operations."""
    settings = get_settings()

    print("ForecastLabAI - Database Connectivity Check")
    print("=" * 45)
    print(f"Database URL: {settings.database_url.split('@')[1]}")  # Hide credentials
    print()

    engine = create_async_engine(settings.database_url)

    try:
        async with engine.connect() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
            print("[OK] Basic connectivity")

            # Check PostgreSQL version
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"[OK] PostgreSQL version: {version[:50]}...")

            # Check pgvector extension
            result = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            if result.scalar():
                print("[OK] pgvector extension installed")
            else:
                print("[WARN] pgvector extension not installed")
                print("       Run: CREATE EXTENSION vector;")

        print()
        print("Database check completed successfully!")
        return 0

    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Ensure Docker is running: docker-compose up -d")
        print("  2. Check DATABASE_URL in .env file")
        print("  3. Verify PostgreSQL container is healthy: docker-compose ps")
        return 1

    finally:
        await engine.dispose()


def main():
    sys.exit(asyncio.run(check_database()))


if __name__ == "__main__":
    main()
