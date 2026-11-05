"""Preview or apply company-fenced projection recovery; never edits stock history.

Run as an authorized service operator with Accounting's existing environment.
Preview is the default. Apply needs the preview digest, company generation and a
reason. A fresh operation or drift invalidates that preview. No credentials or
financial balances are printed. Structural/history loss requires reviewed repair.
"""

import argparse
import asyncio
import json
import uuid

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.errors import ConflictError

from accounting.config import Settings
from accounting.tasks.stock_repair import apply, preview


async def run(args: argparse.Namespace) -> None:
    settings = Settings(_env_file=args.env_file)  # type: ignore[call-arg] # BaseSettings loads existing service credentials.
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    try:
        with tenant_scope(args.tenant):
            async with factory.begin() as db:
                if args.apply:
                    plan = await apply(
                        db,
                        args.tenant,
                        args.company,
                        expected_generation=args.expected_generation,
                        expected_digest=args.expected_digest,
                        reason=args.reason,
                    )
                else:
                    plan = await preview(db, args.tenant, args.company)
                result = {
                    "mode": "APPLIED" if args.apply else "PREVIEW",
                    "company_id": str(args.company),
                    "generation": plan.setup.generation,
                    "digest": plan.digest,
                    "changed_rows": len(plan.changes),
                    "examined_rows": plan.examined,
                }
        # Print success only after commit; a failed reconciliation emits no success.
        print(json.dumps(result, sort_keys=True))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--tenant", type=uuid.UUID, required=True)
    parser.add_argument("--company", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-generation", type=int)
    parser.add_argument("--expected-digest")
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.apply and (
        args.expected_generation is None or not args.expected_digest or not args.reason
    ):
        parser.error("apply requires expected-generation, expected-digest and reason from review")
    try:
        asyncio.run(run(args))
    except ConflictError as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
