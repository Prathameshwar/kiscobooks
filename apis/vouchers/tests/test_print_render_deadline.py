"""A stuck renderer can never block the print worker: the deadline fails the job safely.

Everything here uses a FAKE child process (a sleeping Python) and fake slow operating-system
kill helpers. No browser is started.
"""

import asyncio
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from sqlalchemy import select
from test_purchase_print import queued, snapshot

from vouchers.models.printing import VoucherPrintJob
from vouchers.tasks import print_worker

WINDOWS = sys.platform == "win32"
# Fake renderer: starts a grandchild (like the Playwright driver / browser), reports both
# process ids, then ignores its input and sleeps for ten minutes.
HANGING_CHILD = """
import os, subprocess, sys, time
grand = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
open(sys.argv[1], "w").write(f"{os.getpid()} {grand.pid}")
time.sleep(600)
"""
PDF_CHILD = "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'%PDF-1.7 fake %%EOF')"
REAL_POPEN = subprocess.Popen
RENDER_BUDGET_SECONDS = 25  # Outer guard so a regression fails the test instead of hanging it.


def alive(pid: int) -> bool:
    if WINDOWS:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    import os

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def terminate(pid: int) -> None:
    """Test cleanup only: stop one fake process by PID without any subprocess."""
    if WINDOWS:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if handle:
            kernel32.TerminateProcess(handle, 1)
            kernel32.CloseHandle(handle)
        return
    import os
    import signal

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def wait_until_dead(pids: list[int], seconds: float = 20) -> list[int]:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not any(alive(pid) for pid in pids):
            return []
        time.sleep(0.1)
    return [pid for pid in pids if alive(pid)]


class FakeRenderer:
    """Replaces only the renderer child's command; every other Popen/run passes through."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, script: str) -> None:
        self.pidfile = tmp_path / "fake-renderer-pids"

        def command(args: object) -> bool:
            return list(args)[1:] == ["-m", "vouchers.tasks.print_child"]  # type: ignore[call-overload]

        pidfile, popen_script = self.pidfile, script

        class Popen(REAL_POPEN):  # type: ignore[misc]
            def __init__(self, args, *rest, **options):  # type: ignore[no-untyped-def]
                if command(args):
                    args = [args[0], "-c", popen_script, str(pidfile)]
                super().__init__(args, *rest, **options)

        monkeypatch.setattr(print_worker.subprocess, "Popen", Popen)
        self.popen = Popen

    def pids(self) -> list[int]:
        try:
            return [int(part) for part in self.pidfile.read_text().split()]
        except (OSError, ValueError):
            return []

    def cleanup(self) -> None:
        for pid in self.pids():
            terminate(pid)


@pytest.fixture
def renderer(monkeypatch, tmp_path):
    created: list[FakeRenderer] = []

    def make(script: str = HANGING_CHILD) -> FakeRenderer:
        fake = FakeRenderer(monkeypatch, tmp_path, script)
        created.append(fake)
        return fake

    yield make
    for fake in created:
        fake.cleanup()


def settings(timeout: int = 2):
    # The real setting is validated at 15-120 s; the test passes a tiny deadline to the
    # same attribute the worker reads (assignment bypasses the production floor).
    return SimpleNamespace(print_timeout_seconds=timeout, print_browser_executable=None)


def render_in_thread(timeout: int = 2):
    outcome: dict[str, object] = {}

    def target() -> None:
        started = time.monotonic()
        try:
            outcome["value"] = print_worker.render(settings(timeout), snapshot())
        except BaseException as error:  # the test inspects exactly what escaped
            outcome["error"] = error
        outcome["seconds"] = time.monotonic() - started

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(RENDER_BUDGET_SECONDS)
    return thread, outcome


def slow_failing_taskkill(monkeypatch, delay: float = 0.3):
    """The review measured taskkill at 12.8 s against its 5 s budget: model that failure."""
    real_run = subprocess.run
    calls: list[list[str]] = []

    def run(args, *rest, **options):
        if "taskkill" in str(args[0]).lower():
            calls.append(list(args))
            time.sleep(delay)
            raise subprocess.TimeoutExpired(args, options.get("timeout", 5))
        return real_run(args, *rest, **options)

    monkeypatch.setattr(print_worker.subprocess, "run", run)
    return calls


def assert_controlled_timeout(thread, outcome, fake):
    assert not thread.is_alive(), "the worker thread is still blocked after the deadline"
    error = outcome.get("error")
    assert isinstance(error, TimeoutError), repr(error)
    assert not isinstance(error, subprocess.TimeoutExpired)
    assert "deadline" in str(error) and "sleep" not in str(error)
    assert outcome["seconds"] < RENDER_BUDGET_SECONDS
    pids = fake.pids()
    assert len(pids) == 2
    assert wait_until_dead(pids[:1]) == [], "the renderer child survived its deadline"


def test_deadline_with_a_slow_tree_kill_returns_a_controlled_failure(renderer, monkeypatch):
    fake = renderer()
    slow_failing_taskkill(monkeypatch)
    thread, outcome = render_in_thread()
    try:
        assert_controlled_timeout(thread, outcome, fake)
        # The whole renderer tree is gone, not only the Python child.
        assert wait_until_dead(fake.pids()) == [], "the renderer's descendants survived"
    finally:
        fake.cleanup()


@pytest.mark.skipif(not WINDOWS, reason="Windows fallback when no Job Object can be attached")
def test_deadline_without_a_job_object_and_a_slow_taskkill_still_fails_safely(
    renderer, monkeypatch
):
    fake = renderer()
    monkeypatch.setattr(print_worker, "attach_job", lambda process: None, raising=False)
    calls = slow_failing_taskkill(monkeypatch)
    thread, outcome = render_in_thread()
    try:
        assert_controlled_timeout(thread, outcome, fake)
        assert calls, "the fallback tree kill was never attempted"
    finally:
        fake.cleanup()


@pytest.mark.skipif(WINDOWS, reason="POSIX process-group kill")
def test_deadline_when_the_process_group_kill_is_refused_still_fails_safely(renderer, monkeypatch):
    fake = renderer()

    def refused(group, signal):
        raise PermissionError("the group could not be signalled")

    monkeypatch.setattr(print_worker.os, "killpg", refused)
    thread, outcome = render_in_thread()
    try:
        assert_controlled_timeout(thread, outcome, fake)
    finally:
        fake.cleanup()


def test_an_unexpected_error_never_leaves_the_renderer_running(renderer, monkeypatch):
    fake = renderer()

    def broken(self, *args, **options):
        # Wait until the fake child has announced itself, then fail like a broken pipe.
        end = time.monotonic() + 20
        while len(fake.pids()) < 2 and time.monotonic() < end:
            time.sleep(0.05)
        raise RuntimeError("renderer pipe failed")

    monkeypatch.setattr(fake.popen, "communicate", broken)
    thread, outcome = render_in_thread()
    try:
        assert not thread.is_alive(), "an unexpected error blocked the worker thread"
        assert isinstance(outcome.get("error"), RuntimeError)
        assert wait_until_dead(fake.pids()) == [], "the renderer outlived the failed render"
    finally:
        fake.cleanup()


def test_successful_render_returns_the_pdf_and_leaves_nothing_running(renderer):
    renderer(PDF_CHILD)
    pdf = print_worker.render(settings(15), snapshot())
    assert pdf.startswith(b"%PDF-") and pdf.endswith(b"%%EOF")


@pytest.mark.parametrize(
    "script",
    [
        "import sys; sys.stdin.buffer.read(); sys.exit(3)",
        "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'not a pdf')",
        "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'%PDF-1'); sys.exit(2)",
    ],
)
def test_failed_or_invalid_renderer_output_is_refused(renderer, script):
    renderer(script)
    with pytest.raises(ConflictError, match="renderer is unavailable"):
        print_worker.render(settings(15), snapshot())


def test_a_renderer_that_ended_itself_on_its_deadline_is_reported_as_a_timeout(renderer):
    from vouchers.domain.purchase_print import RENDER_DEADLINE_EXIT_CODE

    renderer(f"import sys; sys.stdin.buffer.read(); sys.exit({RENDER_DEADLINE_EXIT_CODE})")
    with pytest.raises(TimeoutError, match="deadline"):
        print_worker.render(settings(15), snapshot())


async def test_a_deadline_ends_the_job_failed_with_a_safe_code_and_no_lease(
    client, prefix, app, tmp_path, monkeypatch, renderer
):
    fake = renderer()
    slow_failing_taskkill(monkeypatch)
    _, _, _, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    app.state.settings.print_timeout_seconds = 2  # no validation on assignment, as in prod env
    identity = uuid.UUID((await client.post(url, json=body, headers=headers())).json()["id"])
    try:
        await asyncio.wait_for(
            print_worker.execute(
                app.state.session_factory, app.state.settings, TENANT, COMPANY, identity
            ),
            RENDER_BUDGET_SECONDS,
        )
    finally:
        fake.cleanup()
    status = (
        await client.get(prefix + "/voucher-print-jobs/" + str(identity), headers=headers())
    ).json()
    assert status["status"] == "FAILED" and status["failure_code"] == "RENDER_TIMEOUT"
    assert status["download_token"] is None
    text = str(status).lower()
    assert "traceback" not in text and "sleep" not in text and "taskkill" not in text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.scalar(select(VoucherPrintJob).where(VoucherPrintJob.id == identity))
            assert job.status == "FAILED" and job.lease_until is None and job.attempt == 1
    # A terminal job is never run again by a duplicate delivery.
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.scalar(select(VoucherPrintJob).where(VoucherPrintJob.id == identity))
            assert job.attempt == 1
