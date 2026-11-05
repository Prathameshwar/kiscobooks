"""Catalog defaults entrypoint; run with the Catalog virtualenv."""
from catalog.seeds.classification import main

if __name__ == "__main__":
    raise SystemExit(main())
