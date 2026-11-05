"""Pure offline PDF process. Input is frozen JSON on stdin, output is PDF on stdout.

Every browser step has a bound of its own and a watchdog ends the whole process by itself
before the parent's deadline, so a wedged browser never depends on the parent to stop it.
"""

import asyncio
import contextlib
import json
import math
import os
import sys
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from vouchers.domain.canvas_print import roll_width
from vouchers.domain.purchase_print import RENDER_DEADLINE_EXIT_CODE, page_templates, render_html

# Bound for each of launch / context / page / content / PDF. Playwright's own timeouts do
# not cover page creation or PDF output, so each step is also wrapped in `asyncio.wait_for`.
STEP_SECONDS = 25.0
CLOSE_SECONDS = 5.0
# After the PDF has been handed over, the driver teardown may take this long; then the
# process ends with success anyway, so a hung teardown can never cost a finished render.
TEARDOWN_SECONDS = 10.0
DEFAULT_DEADLINE_SECONDS = 60.0
# Distinct non-zero status shared with the parent: a step bound or the watchdog fired.
EXIT_DEADLINE = RENDER_DEADLINE_EXIT_CODE


#: CSS pixels per millimetre (96 per inch), the unit Chromium measures layout in.
PX_PER_MM = 96 / 25.4
#: The longest roll page a PDF carries (Chromium's own ceiling is 200 inches).
ROLL_MAX_MM = 5000.0


async def bounded[T](step: Awaitable[T], seconds: float) -> T:
    return await asyncio.wait_for(step, seconds)


def roll_length(height_px: float) -> float:
    """A measured roll's page length in whole millimetres, or a refusal past the ceiling."""
    length = float(math.ceil(height_px / PX_PER_MM)) + 1
    if not 1 < length <= ROLL_MAX_MM:
        raise ValueError("this roll print is longer than a roll page can be")
    return length


def sandbox_requested(payload: dict[str, Any]) -> bool:
    """The sandbox stays on unless the parent sent an explicit boolean `false`."""
    return payload.get("chromium_sandbox") is not False


async def render(
    snapshot: dict[str, Any],
    executable: Path | None = None,
    deliver: Callable[[bytes], None] | None = None,
    sandbox: bool = True,
) -> bytes:
    """Return the PDF. `deliver` receives it the moment it exists, before browser or driver
    teardown, which cannot be bounded from here (`async with` exit)."""
    step = STEP_SECONDS
    html = render_html(snapshot)  # Validates the frozen source before any browser starts.
    header, footer = page_templates(snapshot)
    async with async_playwright() as runtime:
        browser = await bounded(
            runtime.chromium.launch(
                headless=True,
                chromium_sandbox=sandbox,
                executable_path=str(executable) if executable else None,
                timeout=step * 1000,
            ),
            step,
        )
        try:
            context = await bounded(
                browser.new_context(java_script_enabled=False, service_workers="block"), step
            )
            await bounded(context.route("**/*", lambda route: route.abort()), step)
            page = await bounded(context.new_page(), step)
            page.set_default_timeout(step * 1000)
            width = roll_width(snapshot["layout"])
            if width is not None:
                # A roll is laid out at its own width, in print media, then measured: its one
                # page is exactly as long as what is printed on it.
                await bounded(
                    page.set_viewport_size({"width": round(width * PX_PER_MM), "height": 800}),
                    step,
                )
                await bounded(page.emulate_media(media="print"), step)
            await bounded(page.set_content(html, wait_until="load"), step)
            if width is not None:
                box = await bounded(page.locator("main").bounding_box(), step)
                length = roll_length(box["height"] if box else 0.0)
                data = await bounded(
                    page.pdf(
                        width=f"{width:g}mm",
                        height=f"{length:g}mm",
                        print_background=True,
                        prefer_css_page_size=False,
                        tagged=True,
                        outline=True,
                    ),
                    step,
                )
            else:
                data = await bounded(
                    page.pdf(
                        format="A4",
                        print_background=True,
                        prefer_css_page_size=True,
                        display_header_footer=True,
                        header_template=header,
                        footer_template=footer,
                        tagged=True,
                        outline=True,
                    ),
                    step,
                )
            if deliver is not None:
                deliver(data)
            return data
        finally:
            # A browser that will not close must neither hide the real error nor lose a
            # finished PDF; the watchdog and the parent's process-tree kill remain behind it.
            with contextlib.suppress(Exception):
                await bounded(browser.close(), CLOSE_SECONDS)


class Watchdog:
    """Ends this process from a separate thread, even if the event loop is wedged.

    `disarm` and expiry are mutually exclusive under one lock: once a finished render has
    disarmed it, the deadline can no longer replace its outcome, even mid-write.
    """

    def __init__(self, seconds: float, exit_process: Callable[[int], object], code: int) -> None:
        self.exit_process = exit_process
        self.code = code
        self.lock = threading.Lock()
        self.disarmed = False
        self.timer = threading.Timer(seconds, self.expire)
        self.timer.daemon = True
        self.timer.start()

    def expire(self) -> None:
        with self.lock:
            if not self.disarmed:
                self.exit_process(self.code)

    def disarm(self) -> None:
        with self.lock:
            self.disarmed = True
        self.timer.cancel()


def arm_watchdog(
    seconds: float,
    exit_process: Callable[[int], object] = os._exit,
    code: int = EXIT_DEADLINE,
) -> Watchdog:
    return Watchdog(seconds, exit_process, code)


def main(exit_process: Callable[[int], object] = os._exit) -> None:
    payload = json.loads(sys.stdin.buffer.read(5_242_881))
    executable = Path(payload["executable"]) if payload.get("executable") else None
    deadline = min(max(float(payload.get("deadline_seconds") or DEFAULT_DEADLINE_SECONDS), 1), 300)
    watchdog = arm_watchdog(deadline, exit_process)
    delivered = False

    def deliver(pdf: bytes) -> None:
        # The finished PDF wins over any later deadline: disarm first (atomic with expiry),
        # emit it, then give the teardown a short bound that ends in success, not failure.
        nonlocal delivered
        watchdog.disarm()
        try:
            sys.stdout.buffer.write(pdf)
            sys.stdout.buffer.flush()
        except BaseException:
            arm_watchdog(TEARDOWN_SECONDS, exit_process, 1)  # Failed hand-over, still bounded.
            raise
        delivered = True
        arm_watchdog(TEARDOWN_SECONDS, exit_process, 0)

    try:
        # The default (sandboxed) call is unchanged; only an explicit `false` adds an argument.
        unsandboxed = {} if sandbox_requested(payload) else {"sandbox": False}
        asyncio.run(render(payload["snapshot"], executable, deliver, **unsandboxed))
    except (TimeoutError, PlaywrightTimeoutError):
        if not delivered:
            exit_process(EXIT_DEADLINE)  # A step bound fired: report it like the watchdog does.
            return
    except Exception:
        if not delivered:
            raise  # No PDF was handed over: a plain failure.
    # Either clean, or a driver error after the PDF was already flushed to the parent.
    exit_process(0)


if __name__ == "__main__":
    main()
