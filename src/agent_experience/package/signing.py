"""Ed25519 package signing and a repository-local public-key trust store."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def key_id(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class PackageSigner:
    """In-memory Ed25519 signer; private bytes are never serialized into packages."""

    _private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> PackageSigner:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_private_bytes(cls, value: bytes) -> PackageSigner:
        return cls(Ed25519PrivateKey.from_private_bytes(value))

    @classmethod
    def load(cls, path: str | Path) -> PackageSigner:
        value = Path(path).read_bytes()
        key = serialization.load_pem_private_key(value, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("signing key must be Ed25519")
        return cls(key)

    @property
    def public_key_bytes(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    @property
    def key_id(self) -> str:
        return key_id(self.public_key_bytes)

    def sign(self, value: bytes) -> bytes:
        return self._private_key.sign(value)

    def save_private_key(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self._private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(destination, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        return destination


def verify_signature(public_key: bytes, signature: bytes, value: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, value)
    except (InvalidSignature, ValueError):
        return False
    return True


def load_public_key(path: str | Path) -> bytes:
    value = Path(path).read_bytes()
    if len(value) == 32:
        Ed25519PublicKey.from_public_bytes(value)
        return value
    key = serialization.load_pem_public_key(value)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("trusted key must be Ed25519")
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class TrustStore:
    """Small atomic JSON store containing trusted public keys and revocations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def add(self, public_key: bytes, *, alias: str = "") -> str:
        values = self._read()
        identifier = key_id(public_key)
        values["keys"][identifier] = {
            "public_key": base64.b64encode(public_key).decode("ascii"),
            "alias": alias,
            "revoked": False,
        }
        self._write(values)
        return identifier

    def revoke(self, identifier: str) -> None:
        values = self._read()
        if identifier not in values["keys"]:
            raise KeyError(identifier)
        values["keys"][identifier]["revoked"] = True
        self._write(values)

    def is_trusted(self, identifier: str, public_key: bytes) -> bool:
        value = self._read()["keys"].get(identifier)
        return bool(
            value
            and not value.get("revoked", False)
            and value.get("public_key") == base64.b64encode(public_key).decode("ascii")
        )

    def entries(self) -> dict[str, dict[str, object]]:
        return dict(self._read()["keys"])

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"keys": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("keys"), dict):
            raise ValueError("invalid trust store")
        return value

    def _write(self, value: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)
