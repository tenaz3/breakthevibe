"""Test execution engine using pytest subprocess."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


@dataclass
class StepCapture:
    """Captured data for a single test step."""

    name: str
    screenshot_path: str | None = None
    network_calls: list[dict[str, Any]] = field(default_factory=list)
    console_logs: list[str] = field(default_factory=list)
    diff_result: dict[str, Any] | None = None
    heal_info: dict[str, Any] | None = None


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

    def __init__(self, output_dir: Path, timeout: int = 300, max_reruns: int = 1) -> None:
        self._output_dir = output_dir
        self._timeout = timeout
        self._max_reruns = max_reruns
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
            cmd=" ".join(cmd),
        )

        start = time.monotonic()
        exec_result: ExecutionResult
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

            stdout_str = stdout_bytes.decode(errors="replace")
            stderr_str = stderr_bytes.decode(errors="replace")

            if proc.returncode != 0:
                logger.warning(
                    "pytest_nonzero_exit",
                    suite=suite_name,
                    exit_code=proc.returncode,
                    stdout=stdout_str[-2000:],
                    stderr=stderr_str[-2000:],
                )

            exec_result = ExecutionResult(
                suite_name=suite_name,
                success=proc.returncode == 0,
                exit_code=proc.returncode or 0,
                stdout=stdout_str,
                stderr=stderr_str,
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
            exec_result = ExecutionResult(
                suite_name=suite_name,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Test timed out after {self._timeout}s",
                timed_out=True,
                test_file=test_file,
                duration_seconds=duration,
            )
        finally:
            self._cleanup_test_files(suite_name, test_file)
        return exec_result

    def _write_test_file(self, suite_name: str, test_code: str) -> Path:
        """Write test code to a temporary file."""
        test_file = self._output_dir / f"{suite_name}.py"
        test_file.write_text(test_code)
        logger.debug("test_file_written", suite=suite_name, path=str(test_file))
        return test_file

    def _write_capture_conftest(self, suite_name: str) -> None:
        """Write a conftest.py that captures per-step screenshots, network, and console."""
        captures_dir = self._output_dir / f"{suite_name}_captures"
        captures_dir.mkdir(exist_ok=True)

        # Escape backslashes for Windows paths
        captures_dir_str = str(captures_dir).replace("\\", "\\\\")

        # Write pytest config to ensure asyncio_mode=auto for generated tests
        pytest_ini = self._output_dir / "pytest.ini"
        if not pytest_ini.exists():
            pytest_ini.write_text("[pytest]\nasyncio_mode = auto\n")

        conftest = self._output_dir / "conftest.py"
        conftest.write_text(f"""\
\"\"\"Auto-generated conftest for per-step capture.\"\"\"
import json
from pathlib import Path

import pytest_asyncio
from playwright.async_api import async_playwright

CAPTURES_DIR = Path("{captures_dir_str}")


@pytest_asyncio.fixture()
async def page(request):
    \"\"\"Create an async page with capture of network, console, and screenshot.\"\"\"
    network_calls = []
    console_logs = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(record_video_dir=str(CAPTURES_DIR))
        pg = await context.new_page()

        def _on_request(req):
            if req.resource_type in ("xhr", "fetch"):
                network_calls.append({{"url": req.url, "method": req.method}})

        def _on_response(resp):
            for call in network_calls:
                if call["url"] == resp.url:
                    call["status"] = resp.status
                    break

        def _on_console(msg):
            console_logs.append(f"[{{msg.type}}] {{msg.text}}")

        pg.on("request", _on_request)
        pg.on("response", _on_response)
        pg.on("console", _on_console)

        yield pg

        # Take post-test screenshot
        screenshot_path = None
        try:
            ss_path = CAPTURES_DIR / f"{{request.node.name}}.png"
            await pg.screenshot(path=str(ss_path))
            screenshot_path = str(ss_path)
        except Exception:
            pass

        # Write captures
        step = {{
            "name": request.node.name,
            "screenshot_path": screenshot_path,
            "network_calls": network_calls,
            "console": console_logs,
        }}
        out = CAPTURES_DIR / f"{{request.node.name}}.json"
        out.write_text(json.dumps(step, default=str))

        await context.close()
        await browser.close()
""")

    def _load_captures(self, suite_name: str) -> list[StepCapture]:
        """Load per-step capture data written by the test subprocess."""
        captures_dir = self._output_dir / f"{suite_name}_captures"
        captures: list[StepCapture] = []
        if not captures_dir.exists():
            return captures

        # Load heal log if present (written by generated fallback code)
        heal_entries: list[dict[str, Any]] = []
        heal_log = self._output_dir / "_heal_log.jsonl"
        if heal_log.exists():
            with contextlib.suppress(OSError):
                for line in heal_log.read_text().splitlines():
                    with contextlib.suppress(json.JSONDecodeError):
                        heal_entries.append(json.loads(line))

        for capture_file in sorted(captures_dir.glob("*.json")):
            if capture_file.stem.endswith("_diff"):
                continue  # Diff files are merged into the main capture below
            try:
                data = json.loads(capture_file.read_text())
                # Check for a companion diff result file
                diff_file = captures_dir / f"{capture_file.stem}_diff.json"
                diff_data = None
                if diff_file.exists():
                    with contextlib.suppress(json.JSONDecodeError, OSError):
                        diff_data = json.loads(diff_file.read_text())
                captures.append(
                    StepCapture(
                        name=data.get("name", capture_file.stem),
                        screenshot_path=data.get("screenshot_path"),
                        network_calls=data.get("network_calls", []),
                        console_logs=data.get("console", []),
                        diff_result=diff_data or data.get("diff_result"),
                        heal_info=data.get("heal_info"),
                    )
                )
            except (json.JSONDecodeError, OSError):
                continue
        # Attach heal info from the heal log to the first capture (or create one)
        if heal_entries:
            if captures:
                captures[0].heal_info = heal_entries[0]
            else:
                captures.append(StepCapture(name="healed_selectors", heal_info=heal_entries[0]))
            # Add remaining entries as additional heal_info captures
            for entry in heal_entries[1:]:
                captures.append(StepCapture(name="healed_selectors", heal_info=entry))
        return captures

    def _cleanup_test_files(self, suite_name: str, test_file: Path | None) -> None:
        """Remove generated test/config files. Keep captures dir for screenshots."""
        if test_file is not None:
            with contextlib.suppress(OSError):
                test_file.unlink(missing_ok=True)
        # Keep captures dir — screenshots and JSON are needed for the report.
        # Only clean up JSON captures (data already loaded), keep PNGs/videos.
        captures_dir = self._output_dir / f"{suite_name}_captures"
        if captures_dir.exists():
            for f in captures_dir.glob("*.json"):
                with contextlib.suppress(OSError):
                    f.unlink()
        # Remove conftest and heal log written for this suite run
        conftest = self._output_dir / "conftest.py"
        with contextlib.suppress(OSError):
            conftest.unlink(missing_ok=True)
        heal_log = self._output_dir / "_heal_log.jsonl"
        with contextlib.suppress(OSError):
            heal_log.unlink(missing_ok=True)
        pytest_ini = self._output_dir / "pytest.ini"
        with contextlib.suppress(OSError):
            pytest_ini.unlink(missing_ok=True)
        logger.debug("test_files_cleaned_up", suite=suite_name)

    def _build_command(self, test_file: Path, workers: int) -> list[str]:
        """Build the pytest command with retry and parallel support."""
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-v",
            "--tb=short",
        ]
        # Only add rerun flags if pytest-rerunfailures is installed
        try:
            import pytest_rerunfailures  # noqa: F401

            cmd.extend([f"--reruns={self._max_reruns}", "--reruns-delay=2"])
        except ImportError:
            pass
        if workers > 1:
            cmd.extend(["-n", str(workers)])
        return cmd
