import pytest

from breakthevibe.utils.retry import retry
from breakthevibe.utils.sanitize import is_safe_url, sanitize_url


@pytest.mark.unit
class TestSanitize:
    def test_sanitize_url_strips_whitespace(self) -> None:
        assert sanitize_url("  https://example.com  ") == "https://example.com"

    def test_sanitize_url_removes_fragment(self) -> None:
        assert sanitize_url("https://example.com/page#section") == "https://example.com/page"

    def test_is_safe_url_blocks_localhost(self) -> None:
        assert is_safe_url("http://localhost:3000") is False
        assert is_safe_url("http://127.0.0.1") is False

    def test_is_safe_url_blocks_private_ips(self) -> None:
        assert is_safe_url("http://192.168.1.1") is False
        assert is_safe_url("http://10.0.0.1") is False

    def test_is_safe_url_allows_public(self) -> None:
        assert is_safe_url("https://example.com") is True
        assert is_safe_url("https://google.com") is True


@pytest.mark.unit
class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_succeeds_on_first_try(self) -> None:
        call_count = 0

        @retry(max_attempts=3, delay_ms=10)
        async def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failure(self) -> None:
        call_count = 0

        @retry(max_attempts=3, delay_ms=10)
        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self) -> None:
        @retry(max_attempts=2, delay_ms=10)
        async def always_fail() -> str:
            raise ValueError("fail")

        with pytest.raises(ValueError, match="fail"):
            await always_fail()
