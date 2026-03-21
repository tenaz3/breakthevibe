"""Symmetric encryption for sensitive values at rest."""

from __future__ import annotations

import base64
import hashlib

import structlog
from cryptography.fernet import Fernet, InvalidToken

from breakthevibe.config.settings import get_settings

logger = structlog.get_logger(__name__)


def _get_fernet() -> Fernet:
    """Get Fernet instance using the app's secret key (derived to 32 bytes)."""
    key = get_settings().secret_key.encode()
    derived = hashlib.sha256(key).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value, return base64-encoded ciphertext.

    Args:
        plaintext: The value to encrypt.

    Returns:
        Fernet-encrypted ciphertext as a UTF-8 string.
    """
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext back to plaintext.

    Falls back to returning the raw value for unencrypted legacy entries so
    existing plaintext keys continue to work after the migration.

    Args:
        ciphertext: The encrypted value to decrypt.

    Returns:
        Decrypted plaintext, or the original string if decryption fails.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.warning("decrypt_failed_returning_raw")
        return ciphertext
