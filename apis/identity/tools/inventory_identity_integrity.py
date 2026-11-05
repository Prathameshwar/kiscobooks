"""Read-only pre-migration inventory. Prints IDs and field names, never personal values.

Run with IDENTITY_DATABASE_URL set to the target database. No remediation is automatic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_QUERIES = {
    "duplicate_affiliations": (
        "SELECT HEX(m.user_id) user_id, HEX(m.company_id) company_id, HEX(m.department_id) "
        "department_id, COUNT(*) n FROM membership m GROUP BY m.user_id, m.company_id, "
        "m.department_id HAVING COUNT(*) > 1"
    ),
    "multiple_active_primaries": (
        "SELECT HEX(m.user_id) user_id, COUNT(*) n FROM membership m WHERE is_active = 1 AND "
        "is_primary = 1 GROUP BY m.user_id HAVING COUNT(*) > 1"
    ),
    "foreign_default_company": (
        "SELECT HEX(u.id) id FROM user u JOIN company c ON c.id=u.default_company_id "
        "WHERE u.tenant_id<>c.tenant_id"
    ),
    "foreign_default_department": (
        "SELECT HEX(u.id) id FROM user u JOIN department d ON "
        "d.id=u.default_department_id WHERE u.tenant_id<>d.tenant_id OR "
        "u.default_company_id IS NULL OR u.default_company_id<>d.company_id"
    ),
    "foreign_manager": (
        "SELECT HEX(u.id) id FROM user u JOIN user m ON m.id=u.reporting_manager_id WHERE "
        "u.tenant_id<>m.tenant_id"
    ),
    "foreign_department_head": (
        "SELECT HEX(d.id) id FROM department d JOIN user u ON u.id=d.head_user_id WHERE "
        "d.tenant_id<>u.tenant_id"
    ),
    "foreign_department_company": (
        "SELECT HEX(d.id) id FROM department d JOIN company c ON c.id=d.company_id WHERE "
        "d.tenant_id<>c.tenant_id"
    ),
    "foreign_department_parent": (
        "SELECT HEX(d.id) id FROM department d JOIN department p ON p.id=d.parent_id "
        "WHERE d.tenant_id<>p.tenant_id OR d.company_id<>p.company_id"
    ),
    "foreign_registration_address": (
        "SELECT HEX(r.id) id FROM company_tax_registration r JOIN company_address a ON "
        "a.id=r.registered_address_id WHERE r.tenant_id<>a.tenant_id OR "
        "r.company_id<>a.company_id"
    ),
    "foreign_membership": (
        "SELECT HEX(m.id) id FROM membership m JOIN user u ON u.id=m.user_id JOIN company "
        "c ON c.id=m.company_id LEFT JOIN department d ON d.id=m.department_id WHERE "
        "m.tenant_id<>u.tenant_id OR m.tenant_id<>c.tenant_id OR m.tenant_id<>d.tenant_id "
        "OR m.company_id<>d.company_id"
    ),
    "personal_audit_candidates": (
        "SELECT HEX(id) id, event_type, JSON_KEYS(JSON_EXTRACT(payload, '$.changes')) "
        "changed_fields FROM outbox WHERE JSON_UNQUOTE(JSON_EXTRACT(payload, "
        "'$.entity_type')) IN ('user','tenant') AND JSON_LENGTH(JSON_EXTRACT(payload, "
        "'$.changes')) > 0"
    ),
}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    engine = create_async_engine(os.environ["IDENTITY_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            results = {}
            for name, sql in _QUERIES.items():
                rows = (await connection.execute(text(sql))).mappings().all()
                results[name] = [dict(row) for row in rows]
            report = json.dumps(results, indent=2, default=str)
            if args.output:
                args.output.write_text(report + "\n", encoding="utf-8")
            else:
                print(report)
            await connection.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
