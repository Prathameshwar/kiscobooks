"""Exercise worker lifecycle with private test configuration and separate PID records."""

import asyncio
import json
import os
import subprocess
from pathlib import Path


async def verify_workers(
    root: Path, runtime: Path, env_files: dict[str, dict[str, object]], on_started
) -> None:
    config = runtime / "worker-env"
    state = runtime / "worker-state"
    config.mkdir()
    for name, values in env_files.items():
        # Values are generated test credentials, never copied into source or tool output.
        lines = []
        for key, value in values.items():
            rendered = (
                json.dumps(value, separators=(",", ":")) if isinstance(value, dict) else str(value)
            )
            if "\n" in rendered or "'" in rendered:
                raise ValueError("unsupported private test configuration value")
            lines.append(key + "='" + rendered + "'")
        (config / name).write_text("\n".join(lines), encoding="utf-8")
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root / "start/win/audit-workers.ps1"),
        "-EnvDirectory",
        str(config),
        "-RuntimeDirectory",
        str(state),
    ]

    workers = {
        "accounting.env": "accounting-publisher",
        "catalog.env": "catalog-publisher",
        "audit.env": "audit-consumer",
        "audit-publisher.env": "audit-publisher",
    }

    async def command(action: str) -> str:
        if len(env_files) == 4:
            return await invoke(action, "all")
        return "".join([await invoke(action, workers[name]) for name in env_files])

    async def invoke(action: str, worker: str) -> str:
        output, error = (
            runtime / ("worker-" + action + ".out"),
            runtime / ("worker-" + action + ".err"),
        )
        # Worker descendants inherit Windows handles. Files avoid waiting for pipe EOF from
        # long-lived descendants after the short-lived PowerShell launcher has exited.
        with output.open("w") as out, error.open("w") as err:
            result = await asyncio.to_thread(
                subprocess.run,
                [*args, "-Action", action, "-Worker", worker],
                stdout=out,
                stderr=err,
                text=True,
                timeout=90,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        assert result.returncode == 0, "worker lifecycle failed: " + error.read_text()[-1200:]
        return output.read_text()

    try:
        await command("start")
        await asyncio.sleep(3)
        original = {p.name: json.loads(p.read_text()) for p in state.glob("*.json")}
        assert len(original) == len(env_files)
        assert (await command("start")).count("Already running") == len(env_files)
        assert original == {p.name: json.loads(p.read_text()) for p in state.glob("*.json")}
        assert (await command("status")).count("True") == len(env_files)
        await on_started()
    finally:
        try:
            await command("stop")
            await command("stop")
        finally:
            for name in env_files:
                (config / name).unlink(missing_ok=True)
    assert not list(state.glob("*.json"))
    print("Worker start/restart/status/stop passed", flush=True)
