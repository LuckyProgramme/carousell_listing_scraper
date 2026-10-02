"""Server-only Supabase Data API adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import quote

import requests

from .models import Evaluation, Listing, ScanRun, ScanStatus, Target
from .repository import ActiveScanError, RepositoryError, ScanNotFoundError


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    server_key: str
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "SupabaseSettings":
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        server_key = (
            os.getenv("SUPABASE_SECRET_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        if not url or not server_key:
            raise RepositoryError(
                "Supabase server configuration is incomplete. Set SUPABASE_URL and "
                "SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY)."
            )
        if not url.startswith("https://"):
            raise RepositoryError("SUPABASE_URL must use HTTPS.")
        return cls(
            url=url,
            server_key=server_key,
            timeout_seconds=float(os.getenv("SUPABASE_TIMEOUT_SECONDS", "20")),
        )


class SupabaseRepository:
    """Persist domain records through PostgREST using a server-only key."""

    def __init__(
        self,
        settings: SupabaseSettings,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self._session = session or requests.Session()
        self._headers = {
            "apikey": settings.server_key,
            "Content-Type": "application/json",
        }
        # New sb_secret keys are not JWTs and must never be sent as bearer tokens.
        # Legacy service_role JWTs still use Authorization for PostgREST role selection.
        if not settings.server_key.startswith("sb_secret_"):
            self._headers["Authorization"] = f"Bearer {settings.server_key}"

    @classmethod
    def from_env(cls) -> "SupabaseRepository":
        return cls(SupabaseSettings.from_env())

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
        expected: tuple[int, ...] = (200, 201, 204),
    ) -> Any:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        try:
            response = self._session.request(
                method,
                f"{self.settings.url}/rest/v1/{path}",
                params=params,
                json=json,
                headers=headers,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RepositoryError("Supabase is temporarily unavailable.") from exc
        if response.status_code not in expected:
            # Do not include provider payloads: they can contain SQL details or echoed values.
            if response.status_code == 409:
                raise ActiveScanError("A scan is already queued or running.")
            raise RepositoryError(
                f"Supabase request failed safely (HTTP {response.status_code})."
            )
        if response.status_code == 204 or not getattr(response, "content", b""):
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise RepositoryError("Supabase returned an invalid response.") from exc

    def create_scan(self, owner_id: str) -> ScanRun:
        rows = self._request(
            "POST",
            "scan_runs",
            json={"owner_id": owner_id, "status": "queued"},
            prefer="return=representation",
        )
        if not isinstance(rows, list) or len(rows) != 1:
            raise RepositoryError("Supabase did not create the scan record.")
        return ScanRun.from_mapping(rows[0])

    def get_scan(self, scan_id: str, owner_id: str | None = None) -> ScanRun:
        params = {"id": f"eq.{scan_id}", "select": "*", "limit": "1"}
        if owner_id:
            params["owner_id"] = f"eq.{owner_id}"
        rows = self._request("GET", "scan_runs", params=params)
        if not isinstance(rows, list) or not rows:
            raise ScanNotFoundError("Scan not found.")
        return ScanRun.from_mapping(rows[0])

    def list_enabled_targets(self, owner_id: str) -> Sequence[Target]:
        rows = self._request(
            "GET",
            "targets",
            params={
                "owner_id": f"eq.{owner_id}",
                "enabled": "eq.true",
                "select": "*",
                "order": "created_at.asc",
            },
        )
        if not isinstance(rows, list):
            raise RepositoryError("Supabase returned invalid targets.")
        return tuple(Target.from_mapping(row) for row in rows)

    def update_scan(
        self,
        scan_id: str,
        owner_id: str,
        status: ScanStatus,
        **fields: Any,
    ) -> ScanRun:
        payload: dict[str, Any] = {"status": status, **fields}
        now = datetime.now(timezone.utc).isoformat()
        if status == "scanning":
            payload.setdefault("started_at", now)
        if status in {"completed", "failed"}:
            payload.setdefault("completed_at", now)
        rows = self._request(
            "PATCH",
            "scan_runs",
            params={"id": f"eq.{scan_id}", "owner_id": f"eq.{owner_id}"},
            json=payload,
            prefer="return=representation",
        )
        if not isinstance(rows, list) or not rows:
            raise ScanNotFoundError("Scan not found.")
        return ScanRun.from_mapping(rows[0])

    def claim_queued_scan(
        self,
        scan_id: str,
        owner_id: str,
        *,
        target_snapshot: Sequence[Mapping[str, Any]],
    ) -> ScanRun:
        """Atomically move one queued scan to scanning before doing any work."""
        rows = self._request(
            "PATCH",
            "scan_runs",
            params={
                "id": f"eq.{scan_id}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.queued",
            },
            json={
                "status": "scanning",
                "target_snapshot": list(target_snapshot),
                "safe_error": None,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=representation",
        )
        if rows == []:
            raise ScanNotFoundError("Queued scan was already recovered or started.")
        return self._verified_mutation(rows, scan_id, owner_id, "scanning")

    @staticmethod
    def _verified_mutation(
        rows: Any, scan_id: str, owner_id: str, status: ScanStatus
    ) -> ScanRun:
        """Only a single matching row proves an atomic mutation succeeded."""
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
            raise RepositoryError("Supabase did not confirm the scan transition safely.")
        row = rows[0]
        if row.get("id") != scan_id or row.get("owner_id") != owner_id or row.get("status") != status:
            raise RepositoryError("Supabase did not confirm the scan transition safely.")
        try:
            return ScanRun.from_mapping(row)
        except (TypeError, ValueError, KeyError):
            raise RepositoryError("Supabase returned an invalid scan transition.") from None

    def fail_queued_scan(
        self,
        scan_id: str,
        owner_id: str,
        safe_error: str,
    ) -> ScanRun | None:
        """Fail startup only if the owner's exact scan is still queued.

        This is one conditional write, not a read followed by a status update.
        An empty response means a claim/recovery won the race; never retry it.
        """
        rows = self._request(
            "PATCH",
            "scan_runs",
            params={"id": f"eq.{scan_id}", "owner_id": f"eq.{owner_id}", "status": "eq.queued"},
            json={
                "status": "failed",
                "safe_error": safe_error,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=representation",
        )
        if rows == []:
            return None
        return self._verified_mutation(rows, scan_id, owner_id, "failed")

    def recover_stale_queued_scan(
        self,
        owner_id: str,
        older_than: datetime,
    ) -> ScanRun | None:
        """Release only an old queued scan; running stages are never modified."""
        now = datetime.now(timezone.utc).isoformat()
        rows = self._request(
            "PATCH",
            "scan_runs",
            params={
                "owner_id": f"eq.{owner_id}",
                "status": "eq.queued",
                "created_at": f"lt.{older_than.astimezone(timezone.utc).isoformat()}",
            },
            json={
                "status": "failed",
                "safe_error": (
                    "The queued scan did not start and was released. Please try again."
                ),
                "completed_at": now,
            },
            prefer="return=representation",
        )
        if not isinstance(rows, list):
            raise RepositoryError("Supabase returned an invalid recovery response.")
        return ScanRun.from_mapping(rows[0]) if rows else None

    @staticmethod
    def _source_id(listing: Listing) -> str:
        return listing.source_id

    def save_scan_output(
        self,
        scan_id: str,
        owner_id: str,
        listings: Sequence[Listing],
        evaluations: Sequence[Evaluation],
    ) -> Mapping[str, int]:
        listing_rows = [
            {
                "scan_run_id": scan_id,
                "owner_id": owner_id,
                "source_listing_id": self._source_id(listing),
                "title": listing.title,
                "price": listing.price,
                "condition": listing.condition,
                "description": listing.description,
                "link": listing.link,
                "seller": listing.seller,
                "category": listing.category,
                "thumbnail_url": listing.thumbnail_url,
                "seller_rating": listing.seller_rating,
                "seller_rating_count": listing.seller_rating_count,
                "like_count": listing.like_count,
                "location": listing.location,
                "listing_timestamp": listing.listing_timestamp,
                "price_flag": listing.price_flag,
            }
            for listing in listings
        ]
        inserted = []
        if listing_rows:
            inserted = self._request(
                "POST",
                "listings",
                json=listing_rows,
                prefer="return=representation",
            )
        if not isinstance(inserted, list):
            raise RepositoryError("Supabase did not return saved listings.")
        listing_ids = {
            str(row["source_listing_id"]): str(row["id"])
            for row in inserted
            if row.get("source_listing_id") and row.get("id")
        }
        evaluation_rows: list[dict[str, Any]] = []
        for evaluation in evaluations:
            listing_id = listing_ids.get(evaluation.listing_source_id)
            if not listing_id:
                raise RepositoryError("An evaluation referenced an unsaved listing.")
            payload = evaluation.to_dict()
            payload.pop("listing_source_id", None)
            payload.update(
                {
                    "scan_run_id": scan_id,
                    "listing_id": listing_id,
                    "owner_id": owner_id,
                }
            )
            evaluation_rows.append(payload)
        if evaluation_rows:
            self._request(
                "POST",
                "evaluations",
                json=evaluation_rows,
                prefer="return=minimal",
            )
        return {"listings": len(listing_rows), "evaluations": len(evaluation_rows)}


def encode_filter_value(value: str) -> str:
    """Compatibility helper for callers constructing complex PostgREST filters."""
    return quote(value, safe="")
