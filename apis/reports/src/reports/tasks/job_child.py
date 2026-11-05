"""Private job entry point; terminate stalled threads even if the parent disappears."""

import asyncio
import os
import sys
import threading
import uuid


def main() -> int:
    try:
        tenant, company, identity = (uuid.UUID(value) for value in sys.argv[1:4])
        seconds = float(sys.argv[4])
        if not 0 < seconds <= 7260 or any(key.int == 0 for key in (tenant, company, identity)):
            return 2
        # The parent is the primary deadline. This independent watchdog also bounds
        # asyncio executor shutdown and survives a lost/killed Celery parent.
        watchdog = threading.Timer(seconds, lambda: os._exit(124))
        watchdog.daemon = True
        watchdog.start()
        from billing_platform.process_limits import memory_limit

        memory_limit(512 * 1024 * 1024)
        from reports.config import Settings
        from reports.tasks.framework_worker import execute

        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return 2
        settings = Settings.model_validate_json(raw)
        asyncio.run(execute(settings, tenant, company, identity))
        return 0
    except Exception:
        # Business details, credentials, SQL and exception text stay inside the child.
        return 2


if __name__ == "__main__":
    os._exit(main())
