"""Private renderer entry point. No network, database, credentials or caller templates."""

import json
import sys
import time
from pathlib import Path

from billing_platform.process_limits import memory_limit


def main() -> int:
    started = time.monotonic()
    try:
        source, output = (Path(arg) for arg in sys.argv[1:])
        if output.exists() or source.stat().st_size > 64 * 1024 * 1024:
            return 2
        with source.open(encoding="utf-8") as stream:
            header = stream.readline(65537)
            if len(header) > 65536:
                return 2
            settings = json.loads(header)
            memory_limit(min(1073741824, settings["memory_bytes"]))
            if "gstr1" in settings:
                from reports.rendering.gstr1_pdf import render
            elif "gstr3b" in settings:
                from reports.rendering.gstr3b_pdf import render
            else:
                from reports.rendering.pdf_layout import render

            metrics = render(stream, output, settings)
            from billing_platform.process_memory import peak_rss

            with source.with_name("render-metrics.json").open("x", encoding="utf-8") as report:
                json.dump(
                    metrics | {"peak_rss_bytes": peak_rss(), "seconds": time.monotonic() - started},
                    report,
                )
        return 0
    except Exception as exc:
        # Parent receives only a stable failure category; no business data or stack trace.
        return 3 if isinstance(exc, MemoryError) else 4 if isinstance(exc, OSError) else 2


if __name__ == "__main__":
    raise SystemExit(main())
