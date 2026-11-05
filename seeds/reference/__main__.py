"""Seed `currency`, `country` and `state` into one service database.

    IDENTITY_DATABASE_URL=... python -m seeds.reference identity --dry-run
    IDENTITY_DATABASE_URL=... python -m seeds.reference identity

Run **after** `alembic upgrade head` creates the three tables and **before** any
migration that adds a foreign key pointing at them, so a fresh environment never
has a composite `(country_code, state_code)` key with nothing to reference.

Deliberately a shim. The mechanism lives in `billing_platform.reference.seed`
because all seven service databases carry these tables and each needs the identical
seed — duplicating it per service is how two copies drift (CLAUDE.md §3). Keeping
this file empty of logic also keeps it testable: everything it calls is covered by
`libs/platform/tests/test_reference_seed.py`.
"""

import sys

from billing_platform.reference.seed import main

# Identity owns its cache-generation policy. Register it for this legacy seed
# entry point as well as identity.install; other services keep their own model set.
if len(sys.argv) > 1 and sys.argv[1] == "identity":
    from identity import models as _identity_models  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
