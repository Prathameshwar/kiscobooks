"""Bounded PDF execution with a leased claim and content-addressed private storage."""

import asyncio
import ctypes
import datetime as dt
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vouchers.config import PrintRuntime, chromium_sandbox
from vouchers.domain.purchase_print import (
    RENDER_DEADLINE_EXIT_CODE,
    RENDERER_VERSION,
    snapshot_hash,
)
from vouchers.domain.supporting_files import MAX_BYTES, location, object_key, store
from vouchers.models.printing import VoucherPrintJob

DISPATCH_EVENT = "vouchers.print_job.execute"
log = logging.getLogger("vouchers.print")


def sandbox_enabled(settings: PrintRuntime) -> bool:
    """The browser sandbox decision, announced loudly whenever it is off (local development)."""
    enabled = chromium_sandbox(settings)
    if not enabled:
        log.warning(
            "Chromium sandbox is DISABLED for Purchase PDF rendering "
            "(VOUCHERS_ENVIRONMENT=development, VOUCHERS_PRINT_CHROMIUM_SANDBOX is off). "
            "Local development only; production keeps the sandbox on."
        )
    return enabled


def dispatch(db: AsyncSession, job: VoucherPrintJob) -> None:
    emit(
        db,
        aggregate_type="vouchers.print_job",
        aggregate_id=job.id,
        event_type=DISPATCH_EVENT,
        tenant_id=job.tenant_id,
        payload={"version": 1, "company_id": str(job.company_id), "job_id": str(job.id)},
    )


def lifecycle(db: AsyncSession, job: VoucherPrintJob, action: str) -> None:
    event = "vouchers.print_job." + action
    emit(
        db,
        aggregate_type="vouchers.print_job",
        aggregate_id=job.id,
        event_type=event,
        tenant_id=job.tenant_id,
        payload=audit_payload(
            action=event,
            entity_type="vouchers.print_job",
            entity_id=job.id,
            actor_user_id=None,
            company_id=job.company_id,
            category="system",
        )
        | {"actor_type": "system"},
    )


def child_deadline(timeout: int) -> int:
    """The renderer child ends itself shortly before the parent's own deadline."""
    return timeout - min(10, max(2, timeout // 4))


# Stopping a renderer is bounded step by step. A `taskkill` on a busy Windows host was
# measured at 12.8 s (5.6 s even for an unknown PID), so its budget is generous, but it is
# only a fallback: the Job Object below ends a whole tree synchronously.
TREE_KILL_SECONDS = 15
REAP_SECONDS = 5
# Job Object constants (winnt.h).
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
PROCESS_SET_QUOTA_AND_TERMINATE = 0x0100 | 0x0001


class BasicLimits(ctypes.Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    )


class IoCounters(ctypes.Structure):
    _fields_ = tuple(
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    )


class ExtendedLimits(ctypes.Structure):
    _fields_ = (
        ("BasicLimitInformation", BasicLimits),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


class RendererJob:
    """A kill-on-close Windows Job Object holding the renderer, its driver and its browser.

    Members are inherited by every descendant, so terminating (or closing) the job ends the
    whole tree at once, without enumerating processes or starting a helper executable.
    """

    def __init__(self, kernel32: Any, handle: Any) -> None:
        self.kernel32 = kernel32
        self.handle = handle

    def terminate(self) -> None:
        if self.handle:
            self.kernel32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        # Closing the last handle also ends any process still inside (KILL_ON_JOB_CLOSE).
        handle, self.handle = self.handle, None
        if handle:
            self.kernel32.CloseHandle(handle)


def attach_job(process: subprocess.Popen[bytes]) -> RendererJob | None:
    """Return a job holding `process`, or None where unavailable (never raises)."""
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        member = kernel32.OpenProcess(PROCESS_SET_QUOTA_AND_TERMINATE, False, process.pid)
        attached = bool(member) and bool(
            kernel32.SetInformationJobObject(
                job,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            )
            and kernel32.AssignProcessToJobObject(job, member)
        )
        if member:
            kernel32.CloseHandle(member)
        if not attached:
            kernel32.CloseHandle(job)
            return None
        return RendererJob(kernel32, job)
    except Exception:
        # A missing Job Object only selects the bounded taskkill fallback below.
        return None


def taskkill(pid: int) -> None:
    """Fallback Windows tree kill. Must run while the root is alive: with the root gone,
    `taskkill /T` finds nothing and its descendants are orphaned. Raises on timeout."""
    root = Path(os.environ.get("SYSTEMROOT", "C:/Windows"))
    subprocess.run(  # noqa: S603 -- OS executable, our own numeric child PID only.
        [str(root / "System32/taskkill.exe"), "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=TREE_KILL_SECONDS,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def stop_renderer(process: subprocess.Popen[bytes], job: RendererJob | None) -> None:
    """Stop the renderer's whole tree. Every step is bounded and none can raise, so a slow
    or failing OS helper can never keep the worker from recording the failure."""
    try:
        if job is not None:
            job.terminate()
        elif sys.platform == "win32":
            taskkill(process.pid)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass  # A slow or refused tree kill still falls through to the direct kill.
    try:
        if process.poll() is None:
            process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=REAP_SECONDS)
    except subprocess.TimeoutExpired:
        pass  # Unkillable child: give up on it rather than block this worker.


def render(settings: PrintRuntime, snapshot: dict[str, Any]) -> bytes:
    # A pure renderer needs operating-system paths, not database/broker/API secrets.
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOME",
        "PLAYWRIGHT_BROWSERS_PATH",
        "LANG",
        "LC_ALL",
        "TZ",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    sandbox = sandbox_enabled(settings)
    executable = sys.executable
    if sys.platform == "win32":
        executable = str(getattr(sys, "_base_executable", sys.executable))
        environment["__PYVENV_LAUNCHER__"] = sys.executable
    payload = json.dumps(
        {
            "snapshot": snapshot,
            "executable": str(settings.print_browser_executable)
            if settings.print_browser_executable
            else None,
            # The child must exit by itself well inside this parent's own deadline.
            "deadline_seconds": child_deadline(settings.print_timeout_seconds),
            "chromium_sandbox": sandbox,
        }
    ).encode()
    process = subprocess.Popen(  # noqa: S603 -- fixed module, no shell or user command.
        [executable, "-m", "vouchers.tasks.print_child"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
        shell=False,
        start_new_session=sys.platform != "win32",
        creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        if sys.platform == "win32"
        else 0,
    )
    job = attach_job(process)
    try:
        try:
            output, _ = process.communicate(payload, timeout=settings.print_timeout_seconds)
        except subprocess.TimeoutExpired as error:
            # Celery's solo pool has no effective hard time limit on Windows, so this is
            # the only deadline. Stopping the renderer can never raise or wait unboundedly.
            stop_renderer(process, job)
            raise TimeoutError("Purchase PDF exceeded its deadline") from error
    finally:
        # Any other exit (broken pipe, interrupt, ...) must not leave a live renderer, and
        # nothing here waits on a still-running child the way a `with Popen` block would.
        if process.poll() is None:
            stop_renderer(process, job)
        if job is not None:
            job.close()
    if process.returncode == RENDER_DEADLINE_EXIT_CODE:
        # The child ended itself on its own, earlier, deadline: still a timeout to the job.
        raise TimeoutError("Purchase PDF exceeded its deadline")
    if (
        process.returncode != 0
        or not output.startswith(b"%PDF-")
        or not 0 < len(output) <= MAX_BYTES
    ):
        raise ConflictError("Purchase PDF renderer is unavailable")
    return output


def store_pdf(root: Path | None, key: str, pdf: bytes, digest: str) -> None:
    """Publish a private PDF while allowing the Vouchers API group to read it."""
    store(root, key, pdf, digest)
    target = location(root, key)
    assert root is not None
    for directory in (target.parent, *target.parent.parents):
        if directory == root:
            break
        directory.chmod(0o2750)
    target.chmod(0o640)


async def execute(
    factory: async_sessionmaker[AsyncSession],
    settings: PrintRuntime,
    tenant: uuid.UUID,
    company: uuid.UUID,
    identity: uuid.UUID,
) -> None:
    if not any(
        scope.tenant_id == tenant and scope.company_id == company for scope in settings.print_scopes
    ):
        raise PermissionError("Purchase print worker company is not allowed")
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            job = await db.scalar(
                select(VoucherPrintJob)
                .where(
                    VoucherPrintJob.company_id == company,
                    VoucherPrintJob.id == identity,
                )
                .with_for_update()
            )
            if job is None or job.status in {"READY", "FAILED"}:
                return
            if job.status == "RUNNING" and job.lease_until and job.lease_until > utcnow():
                return
            if job.attempt >= 3:
                job.status, job.failure_code = "FAILED", "ATTEMPTS_EXHAUSTED"
                job.row_version += 1
                lifecycle(db, job, "failed")
                return
            snapshot = job.snapshot
            if (
                snapshot_hash(snapshot) != job.request_hash
                or snapshot.get("renderer_version") != RENDERER_VERSION
            ):
                job.status, job.failure_code = "FAILED", "SOURCE_INTEGRITY"
                job.row_version += 1
                lifecycle(db, job, "failed")
                return
            job.status = "RUNNING"
            job.attempt += 1
            job.row_version += 1
            job.lease_until = utcnow() + dt.timedelta(seconds=settings.print_timeout_seconds + 30)
            attempt, voucher = job.attempt, job.voucher_id
            lifecycle(db, job, "started")
        failure = None
        digest, size = None, None
        try:
            pdf = await asyncio.to_thread(render, settings, snapshot)
            digest, size = hashlib.sha256(pdf).hexdigest(), len(pdf)
            key = object_key(tenant, company, voucher, digest)
            await asyncio.to_thread(store_pdf, settings.print_file_root, key, pdf, digest)
        except TimeoutError:
            failure = "RENDER_TIMEOUT"
        except Exception:
            # No invoice, SQL parameters, tokens or renderer output enter broker logs.
            failure = "RENDER_UNAVAILABLE"
        async with factory() as db, db.begin():
            job = await db.scalar(
                select(VoucherPrintJob)
                .where(
                    VoucherPrintJob.company_id == company,
                    VoucherPrintJob.id == identity,
                )
                .with_for_update()
            )
            if job is None or job.status != "RUNNING" or job.attempt != attempt:
                return
            job.lease_until = None
            job.row_version += 1
            job.failure_code = failure
            if failure:
                job.status = "FAILED"
                lifecycle(db, job, "failed")
            else:
                job.status, job.content_hash, job.size_bytes = "READY", digest, size
                lifecycle(db, job, "ready")


def run(settings: PrintRuntime, tenant: str, company: str, identity: str) -> None:
    async def work() -> None:
        engine = create_engine(settings.database_url)
        try:
            await execute(
                create_session_factory(engine, guarded=True),
                settings,
                uuid.UUID(tenant),
                uuid.UUID(company),
                uuid.UUID(identity),
            )
        finally:
            await engine.dispose()

    asyncio.run(work())
