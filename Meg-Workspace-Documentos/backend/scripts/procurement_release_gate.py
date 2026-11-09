"""Release gate for Procurement production deployments.

This gate intentionally uses real infrastructure; it never swaps in mocks.
Run it inside the production/staging image after Alembic migration and before traffic.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.base import engine


async def main() -> int:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        checks = [
            ("procurement_jobs", "SELECT 1 FROM procurement_jobs LIMIT 1"),
            ("procurement_idempotency", "SELECT 1 FROM procurement_idempotency LIMIT 1"),
            ("procurement_storage_intents", "SELECT 1 FROM procurement_storage_intents LIMIT 1"),
            ("jurisdiction_inheritance", "SELECT 1 FROM jurisdiction_inheritance LIMIT 1"),
        ]
        for name, sql in checks:
            await conn.execute(text(sql))
            print(f"PASS schema:{name}")

        # DB-driven procurement configuration must be present after migration.
        # Empty configuration would make a fresh deployment look healthy while
        # silently breaking procedure selection and catalog-driven UI.
        data_checks = [
            ("jurisdiction_profiles", "SELECT count(*) FROM jurisdiction_profiles WHERE active = true"),
            ("procedure_thresholds", "SELECT count(*) FROM procedure_thresholds WHERE active = true"),
            ("catalog_terms", "SELECT count(*) FROM catalog_terms WHERE active = true"),
        ]
        for name, sql in data_checks:
            count = int((await conn.execute(text(sql))).scalar_one())
            if count <= 0:
                print(f"FAIL data:{name}: no active DB-driven records")
                return 1
            print(f"PASS data:{name}:{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
