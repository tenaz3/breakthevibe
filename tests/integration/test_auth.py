import pytest

from breakthevibe.web.auth.session import SessionAuth


@pytest.mark.integration
class TestSessionAuth:
    async def test_create_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = await auth.create_session(username="admin")
        assert token is not None
        assert len(token) > 20

    async def test_validate_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = await auth.create_session(username="admin")
        user = await auth.validate_session(token)
        assert user is not None
        assert user["username"] == "admin"

    async def test_invalid_token(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        user = await auth.validate_session("invalid-token")
        assert user is None

    async def test_destroy_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = await auth.create_session(username="admin")
        await auth.destroy_session(token)
        user = await auth.validate_session(token)
        assert user is None

    async def test_different_secrets(self) -> None:
        auth1 = SessionAuth(secret_key="secret-1")
        auth2 = SessionAuth(secret_key="secret-2")
        token = await auth1.create_session(username="admin")
        user = await auth2.validate_session(token)
        assert user is None
