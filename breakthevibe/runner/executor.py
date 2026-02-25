"""Test execution engine using pytest subprocess."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


@dataclass
class StepCapture:
    """Captured data for a single test step."""

    name: str
    screenshot_path: str | None = None
    network_calls: list[dict] = field(default_factory=list)
    console_logs: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of a test execution run."""

    suite_name: str
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    test_file: Path | None = None
    duration_seconds: float = 0.0
    step_captures: list[StepCapture] = field(default_factory=list)


class TestExecutor:
    """Runs generated pytest code via subprocess."""

    def __init__(self, output_dir: Path, timeout: int = 300) -> None:
        self._output_dir = output_dir
        self._timeout = timeout
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        suite_name: str,
        test_code: str,
        workers: int = 1,
    ) -> ExecutionResult:
        """Write test code to file and run via pytest subprocess."""
        test_file = self._write_test_file(suite_name, test_code)
        # Write a conftest that enables per-step capture
        self._write_capture_conftest(suite_name)
        cmd = self._build_command(test_file, workers)

        logger.info(
            "running_tests",
            suite=suite_name,
            workers=workers,
            file=str(test_file),
        )

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._output_dir),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            duration = time.monotonic() - start

            # Load captured step data if available
            captures = self._load_captures(suite_name)

            return ExecutionResult(
                suite_name=suite_name,
                success=proc.returncode == 0,
                exit_code=proc.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                test_file=test_file,
                duration_seconds=duration,
                step_captures=captures,
            )
        except TimeoutError:
            duration = time.monotonic() - start
            logger.warning(
                "test_timeout",
                suite=suite_name,
                timeout=self._timeout,
            )
            proc.kill()
            await proc.wait()
            return ExecutionResult(
                suite_name=suite_name,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Test timed out after {self._timeout}s",
                timed_out=True,
                test_file=test_file,
                duration_seconds=duration,
            )

    def _write_test_file(self, suite_name: str, test_code: str) -> Path:
        """Write test code to a temporary file."""
        test_file = self._output_dir / f"{suite_name}.py"
        test_file.write_text(test_code)
        return test_file

    def _write_capture_conftest(self, suite_name: str) -> None:
        """Write a conftest.py that captures per-step screenshots and logs."""
        captures_dir = self._output_dir / f"{suite_name}_captures"
        captures_dir.mkdir(exist_ok=True)

        conftest = self._output_dir / "conftest.py"
        conftest.write_text(f"""\
\"\"\"Auto-generated conftest for per-step capture.\"\"\"
import json
from pathlib import Path

import pytest

CAPTURES_DIR = Path("{captures_dir}")
_step_data = []


@pytest.fixture(autouse=True)
def _capture_step_data(request):
    \"\"\"Capture per-test metadata.\"\"\"
    step = {{"name": request.node.name, "screenshots": [], "console": []}}
    _step_data.append(step)
    yield
    # Write captures after each test
    out = CAPTURES_DIR / f"{{request.node.name}}.json"
    out.write_text(json.dumps(step, default=str))
""")

    def _load_captures(self, suite_name: str) -> list[StepCapture]:
        """Load per-step capture data written by the test subprocess."""
        captures_dir = self._output_dir / f"{suite_name}_captures"
        captures: list[StepCapture] = []
        if not captures_dir.exists():
            return captures

        for capture_file in sorted(captures_dir.glob("*.json")):
            try:
                data = json.loads(capture_file.read_text())
                captures.append(
                    StepCapture(
                        name=data.get("name", capture_file.stem),
                        screenshot_path=data.get("screenshot_path"),
                        network_calls=data.get("network_calls", []),
                        console_logs=data.get("console", []),
                    )
                )
            except (json.JSONDecodeError, OSError):
                continue
        return captures

    def _build_command(self, test_file: Path, workers: int) -> list[str]:
        """Build the pytest command."""
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-v",
            "--tb=short",
        ]
        if workers > 1:
            cmd.extend(["-n", str(workers)])
        return cmd
