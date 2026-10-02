"""Provider-neutral entry point for one explicitly requested scan."""

from __future__ import annotations

import os
import sys
from uuid import UUID

from .models import ScanRun
from .repository import DealRepository, RepositoryError
from .scan_errors import ScanClaimError, ScanExecutionError, ScanNotQueuedError
from .supabase_repository import SupabaseRepository


def configure_logging() -> None:
    # Runtime modules parse optional provider configuration when imported.
    # Keep that work inside main's safe boundary, after ID validation.
    from .deal_finder import configure_logging as configure

    configure()


def run_repository_scan(
    repository: DealRepository, scan_id: str, *, expected_owner_id: str
) -> ScanRun:
    from .scan_service import run_repository_scan as execute

    return execute(repository, scan_id, expected_owner_id=expected_owner_id)


def _required_uuid(name: str) -> str:
    value = os.getenv(name, "").strip()
    # Accept case/whitespace normalization, not alternate UUID encodings or
    # anything that could change a storage filter's meaning.
    normalized = str(UUID(value))
    if value.lower() != normalized:
        raise ValueError("A canonical UUID is required.")
    return normalized


def main() -> int:
    try:
        scan_id = _required_uuid("SCAN_RUN_ID")
        owner_id = _required_uuid("ALLOWED_USER_ID")
    except ValueError:
        print("SCAN_RUN_ID and ALLOWED_USER_ID must be valid UUIDs.", file=sys.stderr)
        return 2
    try:
        configure_logging()
        completed = run_repository_scan(
            SupabaseRepository.from_env(), scan_id, expected_owner_id=owner_id
        )
    except ScanNotQueuedError:
        print("Scan skipped: it is no longer queued. No work was performed.")
        return 0
    except ScanClaimError:
        print("The scan could not be claimed safely. Check its status before starting another scan.", file=sys.stderr)
        return 1
    except (RepositoryError, ScanExecutionError):
        print("The scan could not complete safely. Check its saved status and configuration.", file=sys.stderr)
        return 1
    except Exception:
        # Never expose provider bodies, configuration values, or tracebacks in
        # hosted job logs, including unexpected startup/configuration failures.
        print("The scan stopped unexpectedly. Check its saved status and configuration.", file=sys.stderr)
        return 1
    print(
        f"Scan completed: listings={completed.listings_count} "
        f"candidates={completed.candidates_count} deals={completed.deals_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
