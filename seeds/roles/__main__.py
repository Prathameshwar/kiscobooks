"""Seed the fourteen system roles and their permissions into `identity`.

    IDENTITY_DATABASE_URL=... python -m seeds.roles --dry-run
    IDENTITY_DATABASE_URL=... python -m seeds.roles

No service argument, unlike `seeds.reference`: `role` and `role_permission` exist
only in `identity`, and naming a service would invite pointing this at a database
that has no such table.

Runs under `apis/identity`'s virtualenv — it imports `identity.domain.system_roles`,
which is where the fourteen roles are defined:

    cd apis/identity && IDENTITY_DATABASE_URL=... python -m uv run python -m seeds.roles

Run **after** `alembic upgrade head` reaches revision 0016, which creates both tables.
Re-run on every deploy: adding a permission to a shipped role is applied by exactly
this, and `--dry-run` first reports what it would change.

Deliberately a shim. The mechanism lives in `identity.seeds.roles`, where it can be
imported and tested — `apis/identity/tests/test_role_seed.py` covers everything this
file calls.
"""

from identity.seeds.roles import main

if __name__ == "__main__":
    raise SystemExit(main())
