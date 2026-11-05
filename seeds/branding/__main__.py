"""Deployment-only brand seed, with dry-run support; no schema migrations are run.

Run using the Identity virtualenv and the intended private environment configuration.
The normal Identity installer also invokes this seed through seed_installation.
"""

from identity.seeds.branding import main

if __name__ == "__main__":
    raise SystemExit(main())
