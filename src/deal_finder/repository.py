"""Persistence boundary for Deal Finder domain records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from .models import Evaluation, Listing, ScanRun, ScanStatus, Target


class RepositoryError(RuntimeError):
    """A safe, provider-neutral persistence failure."""


class ActiveScanError(RepositoryError):
    """Raised when an owner already has a queued or running scan."""


class ScanNotFoundError(RepositoryError):
    """Raised when a scan does not exist or belongs to another owner."""


class DealRepository(Protocol):
    """Storage operations required by the dispatcher and scanner."""

    def create_scan(self, owner_id: str) -> ScanRun: ...

    def get_scan(self, scan_id: str, owner_id: str | None = None) -> ScanRun: ...

    def list_enabled_targets(self, owner_id: str) -> Sequence[Target]: ...

    def update_scan(
        self,
        scan_id: str,
        owner_id: str,
        status: ScanStatus,
        **fields: Any,
    ) -> ScanRun: ...

    def claim_queued_scan(
        self,
        scan_id: str,
        owner_id: str,
        *,
        target_snapshot: Sequence[Mapping[str, Any]],
    ) -> ScanRun: ...

    def recover_stale_queued_scan(
        self,
        owner_id: str,
        older_than: datetime,
    ) -> ScanRun | None: ...

    def fail_queued_scan(
        self,
        scan_id: str,
        owner_id: str,
        safe_error: str,
    ) -> ScanRun | None: ...

    def save_scan_output(
        self,
        scan_id: str,
        owner_id: str,
        listings: Sequence[Listing],
        evaluations: Sequence[Evaluation],
    ) -> Mapping[str, int]: ...
