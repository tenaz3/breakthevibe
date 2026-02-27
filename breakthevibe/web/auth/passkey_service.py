"""WebAuthn passkey service — registration and authentication ceremonies."""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Any

import structlog
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from breakthevibe.models.database import WebAuthnCredential, _utc_now
from breakthevibe.web.auth.challenge_store import InMemoryChallengeStore

if TYPE_CHECKING:
    from breakthevibe.storage.repositories.users import DatabaseUserRepository
    from breakthevibe.storage.repositories.webauthn import DatabaseWebAuthnCredentialRepository

logger = structlog.get_logger(__name__)


class PasskeyService:
    """Orchestrates WebAuthn registration and authentication ceremonies."""

    def __init__(
        self,
        credential_repo: DatabaseWebAuthnCredentialRepository,
        user_repo: DatabaseUserRepository,
        rp_id: str,
        rp_name: str,
        origin: str,
    ) -> None:
        self._credential_repo = credential_repo
        self._user_repo = user_repo
        self._rp_id = rp_id
        self._rp_name = rp_name
        self._origin = origin
        self._challenges = InMemoryChallengeStore()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def begin_registration(
        self, user_id: str, user_email: str, webauthn_user_id: bytes | None = None
    ) -> dict[str, Any]:
        """Generate registration options for a user.

        Returns a JSON-serializable dict of PublicKeyCredentialCreationOptions
        plus a ``challenge_key`` for the client to echo back.
        """
        existing = await self._credential_repo.list_for_user(user_id)
        exclude_credentials = [PublicKeyCredentialDescriptor(id=c.credential_id) for c in existing]

        options = generate_registration_options(
            rp_id=self._rp_id,
            rp_name=self._rp_name,
            user_id=webauthn_user_id,
            user_name=user_email,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=exclude_credentials,
        )

        challenge_key = secrets.token_urlsafe(16)
        self._challenges.set(challenge_key, options.challenge)

        options_json = json.loads(options_to_json(options))
        return {
            "options": options_json,
            "challenge_key": challenge_key,
            "webauthn_user_id": options.user.id.hex() if options.user else None,
        }

    async def complete_registration(
        self,
        user_id: str,
        credential_json: str,
        challenge_key: str,
        webauthn_user_id_hex: str | None = None,
    ) -> WebAuthnCredential:
        """Verify attestation and persist the new credential."""
        expected_challenge = self._challenges.pop(challenge_key)
        if expected_challenge is None:
            msg = "Challenge expired or already used"
            raise ValueError(msg)

        verified = verify_registration_response(
            credential=credential_json,
            expected_challenge=expected_challenge,
            expected_rp_id=self._rp_id,
            expected_origin=self._origin,
        )

        webauthn_user_id_bytes: bytes | None = None
        if webauthn_user_id_hex:
            webauthn_user_id_bytes = bytes.fromhex(webauthn_user_id_hex)

        credential = WebAuthnCredential(
            user_id=user_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            aaguid=str(verified.aaguid) if verified.aaguid else "",
            transports=(
                json.dumps([t.value for t in verified.credential_device_type_transports])
                if hasattr(verified, "credential_device_type_transports")
                else "[]"
            ),
            device_type=verified.credential_device_type or "single_device",
            backed_up=verified.credential_backed_up or False,
            webauthn_user_id=webauthn_user_id_bytes,
        )

        await self._credential_repo.create(credential)
        logger.info("passkey_registered", user_id=user_id)
        return credential

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def begin_authentication(self, email: str | None = None) -> dict[str, Any]:
        """Generate authentication options.

        If email is provided, returns allow_credentials scoped to that user.
        Otherwise, allows any discoverable credential (resident key).
        """
        allow_credentials: list[PublicKeyCredentialDescriptor] = []

        if email:
            user = await self._user_repo.get_by_email(email)
            if user:
                creds = await self._credential_repo.list_for_user(user.id)
                allow_credentials = [
                    PublicKeyCredentialDescriptor(
                        id=c.credential_id,
                        transports=_parse_transports(c.transports),
                    )
                    for c in creds
                ]

        options = generate_authentication_options(
            rp_id=self._rp_id,
            allow_credentials=allow_credentials if allow_credentials else None,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        challenge_key = secrets.token_urlsafe(16)
        self._challenges.set(challenge_key, options.challenge)

        options_json = json.loads(options_to_json(options))
        return {
            "options": options_json,
            "challenge_key": challenge_key,
        }

    async def complete_authentication(
        self,
        credential_json: str,
        challenge_key: str,
    ) -> str:
        """Verify assertion, update sign count, return authenticated user_id."""
        expected_challenge = self._challenges.pop(challenge_key)
        if expected_challenge is None:
            msg = "Challenge expired or already used"
            raise ValueError(msg)

        # Parse the credential to get the credential_id for lookup
        cred_data = json.loads(credential_json)
        raw_id_b64 = cred_data.get("rawId", cred_data.get("id", ""))

        # Look up stored credential by raw ID
        from webauthn.helpers import base64url_to_bytes

        credential_id_bytes = base64url_to_bytes(raw_id_b64)
        stored = await self._credential_repo.get_by_credential_id(credential_id_bytes)
        if not stored:
            msg = "Credential not found"
            raise ValueError(msg)

        verified = verify_authentication_response(
            credential=credential_json,
            expected_challenge=expected_challenge,
            expected_rp_id=self._rp_id,
            expected_origin=self._origin,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
        )

        # Update sign count for clone detection
        await self._credential_repo.update_sign_count(
            credential_id=stored.credential_id,
            new_count=verified.new_sign_count,
            last_used_at=_utc_now(),
        )

        logger.info("passkey_authenticated", user_id=stored.user_id)
        return stored.user_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def has_any_credentials(self) -> bool:
        """Check if any passkey credentials exist (for bootstrap detection)."""
        return await self._credential_repo.has_any()

    async def get_webauthn_user_id(self, user_id: str) -> bytes | None:
        """Return the WebAuthn user handle for an existing user, if any."""
        creds = await self._credential_repo.list_for_user(user_id)
        if creds and creds[0].webauthn_user_id:
            return creds[0].webauthn_user_id
        return None


def _parse_transports(transports_json: str) -> list[AuthenticatorTransport]:
    """Parse JSON transport strings into AuthenticatorTransport enums."""
    if not transports_json or transports_json == "[]":
        return []
    raw = json.loads(transports_json)
    result: list[AuthenticatorTransport] = []
    for t in raw:
        try:
            result.append(AuthenticatorTransport(t))
        except ValueError:
            continue
    return result
