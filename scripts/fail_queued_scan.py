"""Validate runner configuration or fail only an unclaimed queued scan.

This helper deliberately needs no installed project dependencies or .env file.
It is used only for setup failures before the worker starts, not worker errors.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
import sys
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import UUID


SAFE_SETUP_ERROR = "The scan could not start because runner setup failed. Check configuration before starting a new scan."
HTTP_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 65536


class ConfigurationError(ValueError):
    """Required configuration is absent or unsafe; values are never included."""


class FinalizationError(RuntimeError):
    """A conditional update could not be confirmed safely."""


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward privileged headers to a Location destination.
        return None


@dataclass(frozen=True)
class Settings:
    scan_id: str
    owner_id: str
    url: str
    secret_key: str
    legacy_jwt: bool


def _required_uuid(value: str) -> str:
    try:
        cleaned = value.strip()
        normalized = str(UUID(cleaned))
        if cleaned.lower() != normalized:
            raise ValueError
        return normalized
    except (AttributeError, TypeError, ValueError):
        raise ConfigurationError("A required scan identity is invalid.") from None


def _storage_origin(value: str) -> str:
    # Validate the raw string before parsing; urlsplit silently removes some
    # control characters. Only an HTTPS origin (or its final slash) is allowed.
    if not isinstance(value, str) or not value or any(ord(char) <= 32 or ord(char) >= 127 for char in value) or "\\" in value:
        raise ConfigurationError("Storage configuration is invalid.")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        labels = hostname.split(".")
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
            or len(hostname) > 253
            or len(labels) < 2
            or labels[-1].lower() in {"localhost", "local", "internal"}
            or not re.fullmatch(r"[a-zA-Z]{2,63}", labels[-1])
            or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)
        ):
            raise ValueError
        return f"https://{hostname.lower()}"
    except ValueError:
        raise ConfigurationError("Storage configuration is invalid.") from None


def _privileged_key(value: str) -> tuple[str, bool]:
    if not isinstance(value, str) or not 1 <= len(value) <= 16384:
        raise ConfigurationError("Storage credentials are missing or invalid.")
    if re.fullmatch(r"sb_secret_[A-Za-z0-9_-]+", value):
        return value, False
    # Retain legacy service_role JWT compatibility, never public/anonymous keys.
    # This role check is configuration hygiene; Supabase verifies the signature.
    if re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value):
        try:
            encoded = value.split(".")[1]
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if isinstance(payload, dict) and payload.get("role") == "service_role":
                return value, True
        except (ValueError, UnicodeError):
            pass
    raise ConfigurationError("Storage credentials are missing or invalid.")


def validate_configuration(environ: Mapping[str, str], *, require_gemini: bool = False) -> Settings:
    scan_id = _required_uuid(environ.get("SCAN_RUN_ID", ""))
    owner_id = _required_uuid(environ.get("ALLOWED_USER_ID", ""))
    origin = _storage_origin(environ.get("SUPABASE_URL", ""))
    secret_key, legacy_jwt = _privileged_key(environ.get("SUPABASE_SECRET_KEY", ""))
    if require_gemini:
        key = environ.get("GEMINI_API_KEY", "")
        if not isinstance(key, str) or not 1 <= len(key) <= 4096 or any(ord(char) <= 32 or ord(char) >= 127 for char in key):
            raise ConfigurationError("Gemini configuration is missing or invalid.")
    return Settings(scan_id, owner_id, origin, secret_key, legacy_jwt)


def fail_queued_scan(*, environ: Mapping[str, str], http_open: Callable | None = None) -> bool:
    settings = validate_configuration(environ)
    query = urlencode({
        "id": f"eq.{settings.scan_id}",
        "owner_id": f"eq.{settings.owner_id}",
        "status": "eq.queued",
        "select": "id,owner_id,status",
    })
    payload = {
        "status": "failed",
        "safe_error": SAFE_SETUP_ERROR,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    headers = {
        "apikey": settings.secret_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }
    if settings.legacy_jwt:
        headers["Authorization"] = f"Bearer {settings.secret_key}"
    request = Request(
        f"{settings.url}/rest/v1/scan_runs?{query}",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    # Explicit no-redirect behavior, normal TLS certificate validation, no
    # ambient proxy or retry; a lost response never causes a second write.
    open_request = http_open or build_opener(ProxyHandler({}), NoRedirectHandler(), HTTPSHandler()).open
    with open_request(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise FinalizationError("The setup failure update was not confirmed.")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise FinalizationError("The setup failure update was not confirmed.")
    try:
        rows = json.loads(body)
    except (ValueError, UnicodeError):
        raise FinalizationError("The setup failure update was not confirmed.") from None
    if rows == []:
        return False
    if (
        not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], dict)
        or rows[0].get("id") != settings.scan_id
        or rows[0].get("owner_id") != settings.owner_id
        or rows[0].get("status") != "failed"
    ):
        raise FinalizationError("The setup failure update was not confirmed.")
    return True


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None, http_open: Callable | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--validate-only"]):
        print("Usage: fail_queued_scan.py [--validate-only]", file=sys.stderr)
        return 2
    settings = os.environ if environ is None else environ
    try:
        if args:
            validate_configuration(settings, require_gemini=True)
            print("Required scan configuration is valid.")
            return 0
        changed = fail_queued_scan(environ=settings, http_open=http_open)
    except ConfigurationError:
        print("Required scan configuration is missing or invalid. No setup failure update was attempted.", file=sys.stderr)
        return 2
    except Exception:
        # Exception text/provider bodies may contain credentials. Leave queued
        # recovery available and do not print them or an exception traceback.
        print("The setup failure update could not be confirmed. Check saved status before using queued recovery.", file=sys.stderr)
        return 1
    print("Queued scan marked failed after setup failure." if changed else "No eligible queued scan was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
