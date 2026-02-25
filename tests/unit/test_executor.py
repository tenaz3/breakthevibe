from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from breakthevibe.runner.executor import ExecutionResult, TestExecutor


@pytest.mark.unit
class TestTestExecutor:
    @pytest.fixture()
    def executor(self, tmp_path: Path) -> TestExecutor:
        return TestExecutor(output_dir=tmp_path, timeout=60)

    @pytest.fixture()
    def sample_test_code(self) -> str:
        return (
            'import pytest\n\n'
            '@pytest.mark.asyncio\n'
            'async def test_example(page):\n'
            '    """Simple test."""\n'
            '    await page.goto("https://example.com")\n'
            '    assert page.url == "https://example.com/"\n'
        )

    def test_writes_test_file(
        self,
        executor: TestExecutor,
        sample_test_code: str,
        tmp_path: Path,
    ) -> None:
        test_file = executor._write_test_file("test_example_suite", sample_test_code)
        assert test_file.exists()
        assert test_file.name == "test_example_suite.py"
        assert test_file.read_text() == sample_test_code

    def test_builds_pytest_command(
        self, executor: TestExecutor, tmp_path: Path
    ) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("# test")
        cmd = executor._build_command(test_file, workers=1)
        assert any("pytest" in c for c in cmd)
        assert str(test_file) in cmd
        assert "-v" in cmd

    def test_builds_parallel_command(
        self, executor: TestExecutor, tmp_path: Path
    ) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("# test")
        cmd = executor._build_command(test_file, workers=4)
        assert "-n" in cmd
        assert "4" in cmd

    @pytest.mark.asyncio
    @patch("breakthevibe.runner.executor.asyncio.create_subprocess_exec")
    async def test_run_returns_result(
        self,
        mock_subprocess: MagicMock,
        executor: TestExecutor,
        sample_test_code: str,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"1 passed", b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        result = await executor.run("test_suite", sample_test_code, workers=1)
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.exit_code == 0
        assert "1 passed" in result.stdout

    @pytest.mark.asyncio
    @patch("breakthevibe.runner.executor.asyncio.create_subprocess_exec")
    async def test_run_captures_failure(
        self,
        mock_subprocess: MagicMock,
        executor: TestExecutor,
        sample_test_code: str,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"1 failed", b"ERRORS")
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        result = await executor.run("test_fail", sample_test_code, workers=1)
        assert result.success is False
        assert result.exit_code == 1
        assert "1 failed" in result.stdout

    @pytest.mark.asyncio
    @patch("breakthevibe.runner.executor.asyncio.create_subprocess_exec")
    async def test_run_handles_timeout(
        self,
        mock_subprocess: MagicMock,
        executor: TestExecutor,
        sample_test_code: str,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = TimeoutError()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_subprocess.return_value = mock_proc

        result = await executor.run("test_timeout", sample_test_code, workers=1)
        assert result.success is False
        assert result.timed_out is True
