"""Authenticated Cloud Run HTTP dispatcher for manual scans."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import requests
from flask import Flask, Response, jsonify, request
from google.auth import default as google_auth_default
from google.auth.transport.requests import AuthorizedSession

from .repository import ActiveScanError, DealRepository, RepositoryError
from .supabase_repository import SupabaseRepository


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str


class TokenVerifier(Protocol):
    def verify(self, authorization: str) -> AuthenticatedUser: ...


class JobLauncher(Protocol):
    def launch(self, scan_id: str) -> None: ...


class AuthenticationError(RuntimeError):
    pass


class AuthenticationDependencyError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


class JobLaunchError(RuntimeError):
    pass


class SupabaseTokenVerifier:
    """Validate a browser access token with Supabase Auth, not untrusted JWT claims."""

    def __init__(
        self,
        supabase_url: str,
        publishable_key: str,
        allowed_email: str,
        *,
        session: requests.Session | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.url = supabase_url.rstrip("/")
        self.publishable_key = publishable_key
        self.allowed_email = allowed_email.casefold().strip()
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "SupabaseTokenVerifier":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        email = os.getenv("ALLOWED_USER_EMAIL", "").strip()
        if not url or not key or not email:
            raise RuntimeError("Dispatcher authentication configuration is incomplete.")
        return cls(url, key, email)

    def verify(self, authorization: str) -> AuthenticatedUser:
        if not authorization.startswith("Bearer ") or len(authorization) <= 7:
            raise AuthenticationError("Authentication is required.")
        try:
            response = self.session.get(
                f"{self.url}/auth/v1/user",
                headers={
                    "apikey": self.publishable_key,
                    "Authorization": authorization,
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise AuthenticationDependencyError(
                "Authentication is temporarily unavailable."
            ) from exc
        if response.status_code >= 500:
            raise AuthenticationDependencyError(
                "Authentication is temporarily unavailable."
            )
        if response.status_code != 200:
            raise AuthenticationError("Your session is invalid or expired.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthenticationError("Authentication returned an invalid response.") from exc
        user_id = str(payload.get("id") or "").strip()
        email = str(payload.get("email") or "").casefold().strip()
        if not user_id or not email:
            raise AuthenticationError("Your session is invalid or expired.")
        if email != self.allowed_email:
            raise AuthorizationError("This account is not allowed to start scans.")
        return AuthenticatedUser(id=user_id, email=email)


class CloudRunJobLauncher:
    """Start one Cloud Run Job execution with a scan ID environment override."""

    def __init__(
        self,
        project_id: str,
        region: str,
        job_name: str,
        *,
        session: AuthorizedSession | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.job_path = f"projects/{project_id}/locations/{region}/jobs/{job_name}"
        if session is None:
            credentials, _ = google_auth_default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            session = AuthorizedSession(credentials)
        self.session = session
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "CloudRunJobLauncher":
        values = {
            "project_id": os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
            "region": os.getenv("CLOUD_RUN_REGION", "").strip(),
            "job_name": os.getenv("CLOUD_RUN_JOB_NAME", "").strip(),
        }
        if not all(values.values()):
            raise RuntimeError("Cloud Run Job configuration is incomplete.")
        return cls(**values)

    def launch(self, scan_id: str) -> None:
        response = self.session.post(
            f"https://run.googleapis.com/v2/{self.job_path}:run",
            json={
                "overrides": {
                    "containerOverrides": [
                        {"env": [{"name": "SCAN_RUN_ID", "value": scan_id}]}
                    ]
                }
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code not in {200, 201, 202}:
            raise JobLaunchError(
                f"Cloud Run Job could not be started (HTTP {response.status_code})."
            )


def _json_error(code: str, message: str, status: int) -> tuple[Response, int]:
    return jsonify({"error": {"code": code, "message": message}}), status


def create_app(
    *,
    repository: DealRepository | None = None,
    verifier: TokenVerifier | None = None,
    launcher: JobLauncher | None = None,
) -> Flask:
    """Application factory with injectable external boundaries for focused tests."""
    app = Flask(__name__)
    repo = repository or SupabaseRepository.from_env()
    token_verifier = verifier or SupabaseTokenVerifier.from_env()
    job_launcher = launcher or CloudRunJobLauncher.from_env()
    allowed_origin = os.getenv("FRONTEND_ORIGIN", "").strip().rstrip("/")
    stale_queued_minutes = int(os.getenv("STALE_QUEUED_SCAN_MINUTES", "15"))
    if not 5 <= stale_queued_minutes <= 1440:
        raise RuntimeError("STALE_QUEUED_SCAN_MINUTES must be between 5 and 1440.")

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        if allowed_origin and request.headers.get("Origin") == allowed_origin:
            response.headers["Access-Control-Allow-Origin"] = allowed_origin
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Vary"] = "Origin"
        return response

    @app.get("/health")
    def health() -> tuple[Response, int]:
        return jsonify({"data": {"status": "ok"}}), 200

    @app.route("/v1/scans", methods=["POST", "OPTIONS"])
    def start_scan() -> tuple[Response, int] | Response:
        if request.method == "OPTIONS":
            return Response(status=204)
        if request.content_length and request.content_length > 1024:
            return _json_error("invalid_request", "Request body is too large.", 400)
        if allowed_origin and request.headers.get("Origin") not in {None, allowed_origin}:
            return _json_error("origin_not_allowed", "This site cannot start scans.", 403)
        try:
            user = token_verifier.verify(request.headers.get("Authorization", ""))
            scan = repo.create_scan(user.id)
            try:
                job_launcher.launch(scan.id)
            except Exception as exc:
                repo.update_scan(
                    scan.id,
                    user.id,
                    "failed",
                    safe_error="The scanner could not be started. Please try again.",
                )
                if isinstance(exc, JobLaunchError):
                    raise
                raise JobLaunchError("The scanner could not be started.") from exc
        except AuthenticationError as exc:
            return _json_error("unauthenticated", str(exc), 401)
        except AuthenticationDependencyError:
            return _json_error(
                "authentication_unavailable",
                "Authentication is temporarily unavailable. Please try again.",
                503,
            )
        except AuthorizationError as exc:
            return _json_error("forbidden", str(exc), 403)
        except ActiveScanError as exc:
            return _json_error("scan_already_active", str(exc), 409)
        except JobLaunchError:
            return _json_error(
                "scanner_unavailable",
                "The scanner could not be started. Please try again.",
                503,
            )
        except RepositoryError:
            return _json_error(
                "storage_unavailable",
                "Saved data is temporarily unavailable. Please try again.",
                503,
            )
        return jsonify({"data": {"scan": {"id": scan.id, "status": scan.status}}}), 202

    @app.route("/v1/scans/recover-queued", methods=["POST", "OPTIONS"])
    def recover_queued_scan() -> tuple[Response, int] | Response:
        """Release a stale queued dispatch without touching running scans."""
        if request.method == "OPTIONS":
            return Response(status=204)
        if request.content_length and request.content_length > 1024:
            return _json_error("invalid_request", "Request body is too large.", 400)
        if allowed_origin and request.headers.get("Origin") not in {None, allowed_origin}:
            return _json_error("origin_not_allowed", "This site cannot recover scans.", 403)
        try:
            user = token_verifier.verify(request.headers.get("Authorization", ""))
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_queued_minutes)
            recovered = repo.recover_stale_queued_scan(user.id, cutoff)
        except AuthenticationError as exc:
            return _json_error("unauthenticated", str(exc), 401)
        except AuthenticationDependencyError:
            return _json_error(
                "authentication_unavailable",
                "Authentication is temporarily unavailable. Please try again.",
                503,
            )
        except AuthorizationError as exc:
            return _json_error("forbidden", str(exc), 403)
        except RepositoryError:
            return _json_error(
                "storage_unavailable",
                "Saved data is temporarily unavailable. Please try again.",
                503,
            )
        scan_payload = (
            {"id": recovered.id, "status": recovered.status} if recovered else None
        )
        return jsonify(
            {"data": {"recovered": recovered is not None, "scan": scan_payload}}
        ), 200

    return app


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    create_app().run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
