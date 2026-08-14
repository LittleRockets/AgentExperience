"""Bounded local/HTTPS package resolution with a content-addressed cache."""

from __future__ import annotations

import hashlib
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .model import MountPolicy


@dataclass(frozen=True, slots=True)
class ResolvedPackage:
    path: Path
    source: str
    sha256: str
    from_cache: bool = False


class PackageSource(Protocol):
    def resolve(
        self,
        reference: str | os.PathLike[str],
        *,
        policy: MountPolicy,
        expected_sha256: str = "",
    ) -> ResolvedPackage: ...


class DefaultPackageSource:
    def __init__(self, cache_path: str | Path) -> None:
        self.cache_path = Path(cache_path)

    def resolve(
        self,
        reference: str | os.PathLike[str],
        *,
        policy: MountPolicy,
        expected_sha256: str = "",
    ) -> ResolvedPackage:
        value = os.fspath(reference)
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme in ("http", "https"):
            if parsed.scheme != "https":
                raise ValueError("remote experience packages require HTTPS")
            if parsed.username or parsed.password or parsed.query:
                raise ValueError("package URL cannot contain credentials or query parameters")
            return self._remote(value, policy, expected_sha256)
        path = Path(value).expanduser().resolve()
        digest = _file_sha256(path, policy.maximum_package_bytes)
        _verify_expected(digest, expected_sha256)
        return ResolvedPackage(path, str(path), digest)

    def _remote(self, url: str, policy: MountPolicy, expected_sha256: str) -> ResolvedPackage:
        if expected_sha256:
            cached = self.cache_path / f"{expected_sha256.lower()}.exp"
            if cached.exists():
                digest = _file_sha256(cached, policy.maximum_package_bytes)
                _verify_expected(digest, expected_sha256)
                return ResolvedPackage(cached, url, digest, True)
        if policy.offline:
            raise FileNotFoundError("verified package is not available in the offline cache")
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/octet-stream, application/zip"},
        )
        opener = urllib.request.build_opener(_BoundedRedirect(policy.maximum_redirects))
        with opener.open(request, timeout=policy.network_timeout_seconds) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https":
                raise ValueError("package download redirected away from HTTPS")
            content = response.read(policy.maximum_package_bytes + 1)
        if len(content) > policy.maximum_package_bytes:
            raise ValueError("remote package exceeds configured size limit")
        digest = hashlib.sha256(content).hexdigest()
        _verify_expected(digest, expected_sha256)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        destination = self.cache_path / f"{digest}.exp"
        if not destination.exists():
            temporary = self.cache_path / f".{digest}.{os.getpid()}.tmp"
            temporary.write_bytes(content)
            temporary.replace(destination)
        return ResolvedPackage(destination, url, digest)


class _BoundedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        count = int(req.headers.get("X-Agent-Experience-Redirects", "0"))
        if count >= self.maximum:
            raise ValueError("package download exceeded redirect limit")
        target = super().redirect_request(req, fp, code, msg, headers, newurl)
        if target is not None:
            target.add_header("X-Agent-Experience-Redirects", str(count + 1))
        return target


def _file_sha256(path: Path, maximum: int) -> str:
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("package file is missing or exceeds configured size limit")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_expected(actual: str, expected: str) -> None:
    if expected and actual.lower() != expected.lower():
        raise ValueError("package source SHA-256 does not match the pinned digest")
