"""Envelope encryption for state blobs (ADR 004 decision 3).

Terraform state holds provider secrets in plaintext. A database dump must not be a
secret dump, so each stored blob is sealed with a per-write data key (DEK) that is
itself wrapped by a key-encryption key (KEK) from the environment.

Layout, little-endian:

    magic       8   b"RPVSTE01"
    kid_len     2   uint16
    kid         n   utf-8 key id
    dek_nonce  12   AES-GCM nonce for the wrapped DEK
    wrapped_len 2   uint16
    wrapped_dek n   KEK-sealed DEK
    nonce      12   AES-GCM nonce for the payload
    ciphertext  *   DEK-sealed state bytes

Binary rather than base64 JSON: state documents reach megabytes and a 33% inflation
on every version is a real storage cost.
"""

from __future__ import annotations

import base64
import binascii
import os
import struct
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

STATE_KEK_ENV: Final = "REPAVE_STATE_KEK"
STATE_KEK_ID_ENV: Final = "REPAVE_STATE_KEK_ID"

ENCRYPTION_NONE: Final = "none"
ENCRYPTION_AESGCM: Final = "aes-256-gcm"

_MAGIC: Final = b"RPVSTE01"
_NONCE_BYTES: Final = 12
_KEY_BYTES: Final = 32
_DEFAULT_KEY_ID: Final = "default"


class StateCryptoError(RuntimeError):
    """Sealing or opening a state blob failed."""


@dataclass(frozen=True)
class StateCrypto:
    """A configured KEK. Absent means the store writes plaintext (local dev only)."""

    key: bytes
    key_id: str

    def seal(self, plaintext: bytes) -> bytes:
        dek = AESGCM.generate_key(bit_length=256)
        dek_nonce = os.urandom(_NONCE_BYTES)
        wrapped = AESGCM(self.key).encrypt(dek_nonce, dek, None)

        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext, None)

        kid = self.key_id.encode("utf-8")
        return b"".join(
            (
                _MAGIC,
                struct.pack("<H", len(kid)),
                kid,
                dek_nonce,
                struct.pack("<H", len(wrapped)),
                wrapped,
                nonce,
                ciphertext,
            )
        )

    def open(self, sealed: bytes) -> bytes:
        kid, dek_nonce, wrapped, nonce, ciphertext = _unpack(sealed)
        if kid != self.key_id:
            raise StateCryptoError(
                f"state blob was sealed with key id {kid!r} but {STATE_KEK_ID_ENV} is "
                f"{self.key_id!r}; set the matching key to read this state"
            )
        try:
            dek = AESGCM(self.key).decrypt(dek_nonce, wrapped, None)
            return AESGCM(dek).decrypt(nonce, ciphertext, None)
        except InvalidTag as exc:
            raise StateCryptoError(
                f"state blob failed authentication; {STATE_KEK_ENV} does not match the "
                "key used to write it, or the row is corrupt"
            ) from exc


def _unpack(sealed: bytes) -> tuple[str, bytes, bytes, bytes, bytes]:
    if not sealed.startswith(_MAGIC):
        raise StateCryptoError("state blob is not a repave envelope (bad magic)")
    offset = len(_MAGIC)
    try:
        (kid_len,) = struct.unpack_from("<H", sealed, offset)
        offset += 2
        kid = sealed[offset : offset + kid_len].decode("utf-8")
        offset += kid_len

        dek_nonce = sealed[offset : offset + _NONCE_BYTES]
        offset += _NONCE_BYTES

        (wrapped_len,) = struct.unpack_from("<H", sealed, offset)
        offset += 2
        wrapped = sealed[offset : offset + wrapped_len]
        offset += wrapped_len

        nonce = sealed[offset : offset + _NONCE_BYTES]
        offset += _NONCE_BYTES
    except struct.error as exc:
        raise StateCryptoError("state blob envelope is truncated") from exc

    ciphertext = sealed[offset:]
    if len(dek_nonce) != _NONCE_BYTES or len(nonce) != _NONCE_BYTES or not ciphertext:
        raise StateCryptoError("state blob envelope is truncated")
    return kid, dek_nonce, wrapped, nonce, ciphertext


def load_state_crypto() -> StateCrypto | None:
    """Read the KEK from the environment. None when unset (plaintext, local dev only)."""
    raw = os.environ.get(STATE_KEK_ENV, "").strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise StateCryptoError(
            f"{STATE_KEK_ENV} must be base64-encoded 32 bytes; generate one with "
            '`python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`'
        ) from exc
    if len(key) != _KEY_BYTES:
        raise StateCryptoError(
            f"{STATE_KEK_ENV} must decode to exactly {_KEY_BYTES} bytes (got {len(key)})"
        )
    key_id = os.environ.get(STATE_KEK_ID_ENV, "").strip() or _DEFAULT_KEY_ID
    return StateCrypto(key=key, key_id=key_id)


def seal_blob(plaintext: bytes, crypto: StateCrypto | None) -> tuple[bytes, str, str | None]:
    """Return (stored_bytes, encryption_label, key_id)."""
    if crypto is None:
        return plaintext, ENCRYPTION_NONE, None
    return crypto.seal(plaintext), ENCRYPTION_AESGCM, crypto.key_id


def open_blob(stored: bytes, encryption: str, crypto: StateCrypto | None) -> bytes:
    """Inverse of `seal_blob`, keyed on the label recorded with the row."""
    if encryption == ENCRYPTION_NONE:
        return stored
    if encryption != ENCRYPTION_AESGCM:
        raise StateCryptoError(f"unknown state blob encryption {encryption!r}")
    if crypto is None:
        raise StateCryptoError(
            f"state blob is encrypted but {STATE_KEK_ENV} is not set; export and reads "
            "require the key that wrote it"
        )
    return crypto.open(stored)
