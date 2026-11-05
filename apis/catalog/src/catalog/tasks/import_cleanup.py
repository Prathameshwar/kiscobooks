"""python -m catalog.tasks.import_cleanup --tenant UUID --company UUID."""

from billing_platform.import_cleanup_cli import main

if __name__ == "__main__":
    main("catalog")
