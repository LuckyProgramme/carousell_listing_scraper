"""Scan outcomes independent of provider configuration and runtime imports."""


class ScanExecutionError(RuntimeError):
    """A safe scan failure; persistence is attempted but not guaranteed."""


class ScanClaimError(ScanExecutionError):
    """A worker could not exclusively claim a queued scan."""


class ScanNotQueuedError(ScanExecutionError):
    """A harmless repeated execution must perform no work."""
