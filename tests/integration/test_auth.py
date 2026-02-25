import pytest

from breakthevibe.web.auth.session import SessionAuth


@pytest.mark.integration
class TestSessionAuth:
    def test_create_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = auth.create_session(username="admin")
        assert token is not None
        assert len(token) > 20

    def test_validate_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = auth.create_session(username="admin")
        user = auth.validate_session(token)
        assert user is not None
        assert user["username"] == "admin"

    def test_invalid_token(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        user = auth.validate_session("invalid-token")
        assert user is None

    def test_destroy_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = auth.create_session(username="admin")
        auth.destroy_session(token)
        user = auth.validate_session(token)
        assert user is None

    def test_different_secrets(self) -> None:
        auth1 = SessionAuth(secret_key="secret-1")
        auth2 = SessionAuth(secret_key="secret-2")
        token = auth1.create_session(username="admin")
        user = auth2.validate_session(token)
        assert user is None
