"""Test execution engine using pytest subprocess."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


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
        cmd = self._build_command(test_file, workers)

        logger.info(
            "running_tests",
            suite=suite_name,
            workers=workers,
            file=str(test_file),
        )

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
            return ExecutionResult(
                suite_name=suite_name,
                success=proc.returncode == 0,
                exit_code=proc.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                test_file=test_file,
            )
        except TimeoutError:
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
            )

    def _write_test_file(self, suite_name: str, test_code: str) -> Path:
        """Write test code to a temporary file."""
        test_file = self._output_dir / f"{suite_name}.py"
        test_file.write_text(test_code)
        return test_file

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
