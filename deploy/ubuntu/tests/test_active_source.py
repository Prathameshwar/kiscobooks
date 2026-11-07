"""A copied venv must execute application code from the selected release."""

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
import venv

INSTALLER = pathlib.Path(__file__).resolve().parents[1] / "install-runtime.sh"


@unittest.skipUnless(os.name == "posix", "Requires the Ubuntu runtime")
class ActiveSource(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.install = INSTALLER.read_text()
        self.old = self.root / "old"
        self.old.mkdir()
        (self.old / "reports.py").write_text("SOURCE = 'old'\n")
        (self.old / "uvicorn.py").write_text(
            "import importlib,sys\nprint(importlib.import_module(sys.argv[1].split('.')[0]).SOURCE)\n"
        )
        for name in ("release_a", "release_b"):
            app = self.root / name / "apis/reports"
            package = app / "src/reports/tasks"
            package.mkdir(parents=True)
            (package.parent / "__init__.py").write_text(f"SOURCE = '{name}'\n")
            (package / "__init__.py").write_text("")
            (package / "source_worker.py").write_text(
                "from reports import SOURCE\nprint(SOURCE)\n"
            )
            (package / "job_dispatcher.py").write_text(
                "from reports import SOURCE\nprint(SOURCE)\n"
            )
            venv.EnvBuilder(with_pip=False).create(app / ".venv")
            site = next((app / ".venv/lib").glob("python*/site-packages"))
            (site / "copied-source.pth").write_text(str(self.old) + "\n")
        self.current = self.root / "current"
        self.current.symlink_to(self.root / "release_a")

    def switch(self):
        self.current.unlink()
        self.current.symlink_to(self.root / "release_b")

    def test_api_follows_the_current_release_despite_stale_editable_path(self):
        launcher = re.search(
            r"cat >/usr/local/libexec/kiscobooks-api <<'EOF'\n(.*?)\nEOF",
            self.install,
            re.S,
        ).group(1)
        script = self.root / "api.sh"
        script.write_text(
            launcher.replace("/opt/kiscobooks/current", str(self.current))
        )
        for expected in ("release_a", "release_b"):
            result = subprocess.run(
                ["bash", str(script), "reports"], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
            if expected == "release_a":
                self.switch()
        result = subprocess.run(
            ["bash", str(script), "unknown"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 64)

    def test_report_worker_follows_the_current_release(self):
        block = re.search(
            r"for worker in accounting-report-snapshots reports-sources; do\n.*?\ndone",
            self.install,
            re.S,
        ).group()
        units = self.root / "units"
        units.mkdir()
        block = block.replace("/etc/systemd/system", str(units)).replace(
            "/opt/kiscobooks/current", str(self.current)
        )
        subprocess.run(["bash", "-c", block], check=True)
        unit = (units / "kiscobooks-reports-sources.service").read_text()
        env = dict(os.environ)
        for line in unit.splitlines():
            if line.startswith("Environment="):
                key, value = line.removeprefix("Environment=").split("=", 1)
                env[key] = value
        command = next(
            line.removeprefix("ExecStart=").split()
            for line in unit.splitlines()
            if line.startswith("ExecStart=")
        )
        for expected in ("release_a", "release_b"):
            result = subprocess.run(
                command, cwd=self.current, env=env, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
            if expected == "release_a":
                self.switch()

    def test_every_report_lane_follows_the_current_release(self):
        block = re.search(
            r"for lane in dispatcher short bulk render; do\n.*?\ndone",
            self.install,
            re.S,
        ).group()
        units = self.root / "lanes"
        units.mkdir()
        block = block.replace("/etc/systemd/system", str(units)).replace(
            "/opt/kiscobooks/current", str(self.current)
        )
        subprocess.run(["bash", "-c", block], check=True)
        for expected in ("release_a", "release_b"):
            for lane in ("dispatcher", "short", "bulk", "render"):
                lines = (
                    (units / f"kiscobooks-reports-{lane}.service")
                    .read_text()
                    .splitlines()
                )
                env = dict(os.environ)
                for line in lines:
                    if line.startswith("Environment="):
                        key, value = line.removeprefix("Environment=").split("=", 1)
                        env[key] = value
                command = next(
                    line.removeprefix("ExecStart=").split()
                    for line in lines
                    if line.startswith("ExecStart=")
                )
                result = subprocess.run(
                    command, cwd=self.current, env=env, capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected, lane)
            if expected == "release_a":
                self.switch()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        INSTALLER = pathlib.Path(sys.argv[1])
    unittest.main(argv=[sys.argv[0]])
