"""Gemini Flash batch auditing with structured-output validation and fallbacks.

The module deliberately uses Gemini's REST ``generateContent`` endpoint instead
of an SDK. That keeps the runtime dependency surface small, makes the
per-chunk request timeout explicit, and keeps retry behaviour testable.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import (
    BASE_DIR,
    GEMINI_API_KEY,
    GEMINI_AUDIT_CHUNK_SIZE,
    GEMINI_AUDIT_TIMEOUT_SECONDS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_RETRIES,
)
from .models import AuditResult, Listing, PriceListTarget, validate_batch_audit_payload
from .text_cleaner import format_listing_data_block


DEFAULT_CHUNK_SIZE = GEMINI_AUDIT_CHUNK_SIZE
DEFAULT_TIMEOUT_SECONDS = GEMINI_AUDIT_TIMEOUT_SECONDS
DEFAULT_TIMEOUT_RETRIES = GEMINI_TIMEOUT_RETRIES
MAX_RETRIES = 3
BACKOFF_SECONDS = (1.0, 2.0, 4.0)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
PROMPT_PATH = Path(BASE_DIR) / "prompts" / "audit_v1.txt"

HttpPost = Callable[..., Any]
Sleep = Callable[[float], None]
LocalFallback = Callable[[Sequence[Any], Sequence[Any]], Sequence[Mapping[str, Any]]]


class GeminiAuditError(RuntimeError):
    """Raised when Gemini cannot produce a usable batch audit."""

    def __init__(
        self, message: str, *, attempts: int = 0, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.status_code = status_code


@dataclass(frozen=True)
class GeminiChunkResult:
    """Safe diagnostics for one sequential Gemini audit request."""

    chunk_number: int
    candidate_count: int
    attempts: int
    http_status: int | None
    succeeded: bool
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_number": self.chunk_number,
            "candidate_count": self.candidate_count,
            "attempts": self.attempts,
            "http_status": self.http_status,
            "succeeded": self.succeeded,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class AuditBatchResult:
    """Validated Gemini audits plus candidates routed to local fallback.

    ``fallback_deals`` is populated when the default or supplied local fallback
    can run.  The candidate list is always retained so the pipeline can perform
    fallback later if a caller intentionally disables it.
    """

    audits: tuple[AuditResult, ...]
    fallback_candidates: tuple[Any, ...]
    fallback_deals: tuple[Mapping[str, Any], ...]
    validation_errors: tuple[str, ...] = ()
    unknown_ids: frozenset[str] = frozenset()
    attempts: int = 0
    whole_batch_fallback: bool = False
    failure_reason: str | None = None
    model: str | None = None
    endpoint: str | None = None
    http_status: int | None = None
    chunk_results: tuple[GeminiChunkResult, ...] = ()

    @property
    def fallback_ids(self) -> frozenset[str]:
        return frozenset(_candidate_listing(candidate).id for candidate in self.fallback_candidates)


def _audit_response_schema() -> dict[str, Any]:
    """Return the standard JSON Schema used by Gemini 3 structured output."""
    audit = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "matched_item": {"type": ["string", "null"]},
            "confidence": {"type": "integer"},
            "specs_matched": {"type": "boolean"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "freebies": {"type": "array", "items": {"type": "string"}},
            "downgrade_condition": {"type": "boolean"},
            "is_accessory": {"type": "boolean"},
            "is_bundle": {"type": "boolean"},
            "individual_price": {"type": ["number", "null"]},
            "separately_available": {"type": "boolean"},
            "price_evidence": {"type": ["string", "null"]},
        },
        "required": [
            "id",
            "matched_item",
            "confidence",
            "specs_matched",
            "issues",
            "freebies",
            "downgrade_condition",
            "is_accessory",
            "is_bundle",
            "individual_price",
            "separately_available",
            "price_evidence",
        ],
    }
    return {
        "type": "object",
        "properties": {"audits": {"type": "array", "items": audit}},
        "required": ["audits"],
    }


def _read_prompt(prompt_path: Path = PROMPT_PATH) -> str:
    try:
        return prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GeminiAuditError(f"Could not read Gemini audit prompt: {exc}") from exc


def _candidate_listing(candidate: Any) -> Listing:
    """Normalize a candidate, CandidateMatch, or mapping to a Listing."""
    source = getattr(candidate, "listing", candidate)
    if isinstance(source, Listing):
        return source
    if isinstance(source, Mapping):
        return Listing.from_mapping(source)
    raise TypeError("candidate_listings must contain Listing, CandidateMatch, or mapping values.")


def _target_from_value(value: Any) -> PriceListTarget:
    if isinstance(value, PriceListTarget):
        return value
    if isinstance(value, Mapping):
        return PriceListTarget.from_mapping(value)
    raise TypeError("price_list_targets must contain PriceListTarget or mapping values.")


def _deduplicate_candidates(candidate_listings: Sequence[Any]) -> tuple[list[Any], dict[str, Listing]]:
    """Keep first candidate per listing ID and reject IDs unusable for fallback routing."""
    unique: list[Any] = []
    listings_by_id: dict[str, Listing] = {}
    for candidate in candidate_listings:
        listing = _candidate_listing(candidate)
        if not listing.id:
            raise ValueError("Every Gemini candidate must have a non-empty stable listing id.")
        if listing.id not in listings_by_id:
            unique.append(candidate)
            listings_by_id[listing.id] = listing
    return unique, listings_by_id


def _allowed_targets_by_listing(
    candidates: Iterable[Any], all_targets: Sequence[PriceListTarget]
) -> dict[str, set[str]]:
    """Build each listing's closed target whitelist from Stage 1 candidates."""
    default_targets = {target.item_name for target in all_targets}
    allowed: dict[str, set[str]] = {}
    for candidate in candidates:
        listing = _candidate_listing(candidate)
        candidate_target = getattr(candidate, "target", None)
        if isinstance(candidate_target, PriceListTarget):
            allowed.setdefault(listing.id, set()).add(candidate_target.item_name)
        elif isinstance(candidate_target, Mapping):
            allowed.setdefault(listing.id, set()).add(
                PriceListTarget.from_mapping(candidate_target).item_name
            )
        else:
            allowed.setdefault(listing.id, set(default_targets))
    return allowed


def _build_prompt(candidates: Sequence[Any], targets: Sequence[PriceListTarget]) -> str:
    template = _read_prompt()
    _, listings_by_id = _deduplicate_candidates(candidates)
    target_items = [
        {
            "item_name": target.item_name,
            "category": target.category,
            "deal_price": target.deal_price,
            "retail_price": target.retail_price,
            "notes": target.notes,
            "target_type": target.target_type,
            "allow_bundle_check": target.allow_bundle_check,
        }
        for target in targets
    ]
    listing_blocks = [
        format_listing_data_block(
            listing_id=listing.id,
            title=listing.title,
            price=listing.price,
            description=listing.description,
        )
        for listing in listings_by_id.values()
    ]
    # The prompt intentionally contains a literal JSON example, so do not use
    # ``str.format`` here: its braces are not template substitutions.
    return template.replace(
        "{target_items_json}",
        json.dumps(target_items, ensure_ascii=False, separators=(",", ":")),
    ).replace("{candidate_listings_xml}", "\n\n".join(listing_blocks)).replace(
        "{allowed_targets_json}",
        json.dumps(
            {key: sorted(names) for key, names in _allowed_targets_by_listing(candidates, targets).items()},
            ensure_ascii=False,
        ),
    )


def _request_payload(prompt: str) -> dict[str, Any]:
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseFormat": {
                "text": {
                    "mimeType": "APPLICATION_JSON",
                    "schema": _audit_response_schema(),
                }
            },
        },
    }


def _response_text(payload: Mapping[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiAuditError("Gemini response contains no generated candidates.")
    first = candidates[0]
    if not isinstance(first, Mapping):
        raise GeminiAuditError("Gemini response candidate has an invalid shape.")
    content = first.get("content")
    if not isinstance(content, Mapping):
        raise GeminiAuditError("Gemini response candidate contains no content.")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise GeminiAuditError("Gemini response content contains no parts.")
    text = "".join(
        str(part.get("text", "")) for part in parts if isinstance(part, Mapping)
    ).strip()
    if not text:
        raise GeminiAuditError("Gemini response contained an empty structured-output body.")
    return text


def _parse_structured_json(text: str) -> dict[str, Any]:
    """Parse JSON, accepting a fenced payload if a provider wraps the output."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
        if candidate.rstrip().endswith("```"):
            candidate = candidate.rstrip()[:-3].rstrip()
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise GeminiAuditError("Gemini response was not valid JSON.") from None
        try:
            decoded = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GeminiAuditError("Gemini response was not valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise GeminiAuditError("Gemini structured output must be a JSON object.")
    return decoded


def _default_local_fallback(
    candidates: Sequence[Any], price_list_targets: Sequence[Any]
) -> Sequence[Mapping[str, Any]]:
    """Use the existing deterministic matcher and tag its output as local fallback."""
    if not candidates:
        return ()
    # Imported lazily: callers can test Gemini validation without RapidFuzz installed.
    from .deal_engine import find_deals

    listings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        listing = _candidate_listing(candidate)
        if listing.id in seen_ids:
            continue
        seen_ids.add(listing.id)
        listing_dict = listing.to_dict()
        effective_price = getattr(candidate, "effective_price", None)
        if effective_price is not None:
            listing_dict["price"] = effective_price
        price_flag = getattr(candidate, "price_flag", None)
        if price_flag:
            listing_dict["price_flag"] = price_flag
        listings.append(listing_dict)

    reference_rows = [
        {
            "Item Name": target.item_name,
            "Category": target.category,
            "Retail Price (PHP)": target.retail_price,
            "Deal Price (PHP)": target.deal_price,
            "Keyword for Condition Downsizing": ", ".join(target.downsizing_keywords),
            "Keyword for Finding Freebies": ", ".join(target.freebie_keywords),
            "Notes": target.notes,
            "Target Type": target.target_type,
            "Allow Bundle Check": target.allow_bundle_check,
        }
        for target in (_target_from_value(value) for value in price_list_targets)
    ]
    fallback_deals: list[dict[str, Any]] = []
    for deal in find_deals(listings, reference_rows):
        local_score = float(deal.get("match_score", 0.0))
        fallback_deals.append(
            {
                **deal,
                "audit_source": "local_fallback",
                "local_match_score": local_score,
                "gemini_confidence": None,
                "specs_matched": None,
                "acceptance_reason": "Gemini audit unavailable or invalid; accepted by local matcher.",
            }
        )
    return fallback_deals


def _run_fallback(
    candidates: Sequence[Any],
    targets: Sequence[Any],
    fallback: LocalFallback | None,
) -> tuple[Mapping[str, Any], ...]:
    if not candidates:
        return ()
    handler = fallback or _default_local_fallback
    return tuple(handler(candidates, targets))


def _safe_error_summary(response: Any) -> str | None:
    """Extract a bounded provider error message without exposing request secrets."""
    try:
        payload = response.json()
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, Mapping):
        error = payload.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("message"), str):
            return " ".join(error["message"].split())[:300]
    return None


def _request_with_retry(
    *,
    api_key: str,
    model: str,
    payload: Mapping[str, Any],
    timeout: float,
    timeout_retries: int,
    http_post: HttpPost,
    sleep: Sleep,
) -> tuple[Mapping[str, Any], int]:
    """POST a Gemini request with independent timeout and HTTP retry budgets."""
    endpoint = f"{GEMINI_API_BASE_URL}/models/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    last_error = "Gemini request failed."
    attempts = 0
    timeout_failures = 0
    retryable_http_failures = 0

    while True:
        attempts += 1
        try:
            response = http_post(endpoint, headers=headers, json=payload, timeout=timeout)
        except requests.Timeout as exc:
            if timeout_failures >= timeout_retries:
                raise GeminiAuditError("Gemini request timed out.", attempts=attempts) from exc
            sleep(BACKOFF_SECONDS[min(timeout_failures, len(BACKOFF_SECONDS) - 1)])
            timeout_failures += 1
            continue
        except requests.RequestException as exc:
            raise GeminiAuditError(
                "Gemini network request failed.", attempts=attempts
            ) from exc

        status_code = int(getattr(response, "status_code", 0))
        if 200 <= status_code < 300:
            try:
                decoded = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise GeminiAuditError(
                    "Gemini HTTP response was not valid JSON.", attempts=attempts
                ) from exc
            if not isinstance(decoded, Mapping):
                raise GeminiAuditError(
                    "Gemini HTTP response must be a JSON object.", attempts=attempts
                )
            return decoded, attempts

        detail = _safe_error_summary(response)
        last_error = f"Gemini returned HTTP {status_code}."
        if detail:
            last_error = f"{last_error} {detail}"
        retryable = status_code == 429 or 500 <= status_code <= 599
        if not retryable or retryable_http_failures >= MAX_RETRIES:
            raise GeminiAuditError(
                last_error, attempts=attempts, status_code=status_code
            )
        sleep(BACKOFF_SECONDS[min(retryable_http_failures, len(BACKOFF_SECONDS) - 1)])
        retryable_http_failures += 1


def _validated_chunk_audits(
    candidates: Sequence[Any],
    targets: Sequence[PriceListTarget],
    parsed: Mapping[str, Any],
) -> tuple[tuple[AuditResult, ...], tuple[Any, ...], tuple[str, ...], frozenset[str]]:
    """Apply the existing strict response gates to one Gemini chunk."""
    _, listings_by_id = _deduplicate_candidates(candidates)
    audits, errors, missing_ids, unknown_ids = validate_batch_audit_payload(
        parsed, set(listings_by_id)
    )
    allowed_targets = _allowed_targets_by_listing(candidates, targets)
    accepted_audits: list[AuditResult] = []
    malformed_ids = set(missing_ids)
    for audit in audits:
        if audit.matched_item is not None and audit.matched_item not in allowed_targets[audit.id]:
            errors.append(
                f"Audit item '{audit.id}' selected target '{audit.matched_item}' outside its Stage 1 whitelist."
            )
            malformed_ids.add(audit.id)
            continue
        accepted_audits.append(audit)
    fallback_candidates = tuple(
        candidate for candidate in candidates if _candidate_listing(candidate).id in malformed_ids
    )
    return (
        tuple(accepted_audits),
        fallback_candidates,
        tuple(errors),
        frozenset(unknown_ids),
    )


def audit_batch(
    candidate_listings: Sequence[Any],
    price_list_targets: Sequence[Any],
    *,
    api_key: str | None = None,
    model: str = GEMINI_MODEL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timeout_retries: int = DEFAULT_TIMEOUT_RETRIES,
    http_post: HttpPost = requests.post,
    sleep: Sleep = time.sleep,
    local_fallback: LocalFallback | None = None,
) -> AuditBatchResult:
    """Audit candidates in sequential Gemini structured-output chunks.

    A successful response may still route individual missing, malformed, or
    target-hallucinating IDs to local fallback. A failed chunk is isolated:
    its candidates remain available for dry-run comparison but cannot publish
    as local fallback during a normal pipeline run.
    """
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero.")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if timeout_retries < 0:
        raise ValueError("timeout_retries must not be negative.")
    targets = tuple(_target_from_value(target) for target in price_list_targets)
    candidates, _ = _deduplicate_candidates(candidate_listings)
    if not candidates:
        return AuditBatchResult((), (), (), attempts=0, model=model)
    if not targets:
        raise ValueError("price_list_targets must not be empty.")

    effective_api_key = api_key if api_key is not None else GEMINI_API_KEY
    endpoint = f"{GEMINI_API_BASE_URL}/models/{model}:generateContent"
    candidate_chunks = tuple(
        tuple(candidates[index : index + chunk_size])
        for index in range(0, len(candidates), chunk_size)
    )
    if not effective_api_key.strip():
        fallback_deals = _run_fallback(candidates, targets, local_fallback)
        return AuditBatchResult(
            audits=(),
            fallback_candidates=tuple(candidates),
            fallback_deals=fallback_deals,
            attempts=0,
            whole_batch_fallback=True,
            failure_reason="Gemini API key is not configured.",
            model=model,
            endpoint=endpoint,
            chunk_results=tuple(
                GeminiChunkResult(
                    chunk_number=index,
                    candidate_count=len(chunk),
                    attempts=0,
                    http_status=None,
                    succeeded=False,
                    failure_reason="Gemini API key is not configured.",
                )
                for index, chunk in enumerate(candidate_chunks, start=1)
            ),
        )

    accepted_audits: list[AuditResult] = []
    fallback_candidates: list[Any] = []
    fallback_deals: list[Mapping[str, Any]] = []
    validation_errors: list[str] = []
    unknown_ids: set[str] = set()
    chunk_results: list[GeminiChunkResult] = []
    total_attempts = 0
    failures: list[str] = []
    successful_chunks = 0

    for chunk_number, chunk in enumerate(candidate_chunks, start=1):
        http_status: int | None = None
        request_attempts = 0
        try:
            prompt = _build_prompt(chunk, targets)
            raw_response, attempts = _request_with_retry(
                api_key=effective_api_key,
                model=model,
                payload=_request_payload(prompt),
                timeout=timeout,
                timeout_retries=timeout_retries,
                http_post=http_post,
                sleep=sleep,
            )
            request_attempts = attempts
            http_status = 200
            parsed = _parse_structured_json(_response_text(raw_response))
            audits, malformed_candidates, errors, chunk_unknown_ids = _validated_chunk_audits(
                chunk, targets, parsed
            )
        except GeminiAuditError as exc:
            attempts = exc.attempts or request_attempts
            if exc.status_code is not None:
                http_status = exc.status_code
            reason = str(exc)
            total_attempts += attempts
            failures.append(f"chunk {chunk_number}: {reason}")
            validation_errors.append(f"Chunk {chunk_number}: {reason}")
            fallback_candidates.extend(chunk)
            fallback_deals.extend(_run_fallback(chunk, targets, local_fallback))
            chunk_results.append(
                GeminiChunkResult(
                    chunk_number=chunk_number,
                    candidate_count=len(chunk),
                    attempts=attempts,
                    http_status=http_status,
                    succeeded=False,
                    failure_reason=reason,
                )
            )
            continue

        total_attempts += attempts
        successful_chunks += 1
        accepted_audits.extend(audits)
        fallback_candidates.extend(malformed_candidates)
        fallback_deals.extend(_run_fallback(malformed_candidates, targets, local_fallback))
        validation_errors.extend(errors)
        unknown_ids.update(chunk_unknown_ids)
        chunk_results.append(
            GeminiChunkResult(
                chunk_number=chunk_number,
                candidate_count=len(chunk),
                attempts=attempts,
                http_status=http_status,
                succeeded=True,
            )
        )

    whole_batch_fallback = successful_chunks == 0
    if whole_batch_fallback and len(failures) == 1:
        failure_reason = failures[0].split(": ", 1)[1]
    else:
        failure_reason = "; ".join(failures) if failures else None
    # A successful chunk proves the model endpoint was reachable even when a
    # different chunk timed out. Individual chunk status remains in diagnostics.
    aggregate_status = 200 if successful_chunks else next(
        (chunk.http_status for chunk in chunk_results if chunk.http_status is not None), None
    )
    return AuditBatchResult(
        audits=tuple(accepted_audits),
        fallback_candidates=tuple(fallback_candidates),
        fallback_deals=tuple(fallback_deals),
        validation_errors=tuple(validation_errors),
        unknown_ids=frozenset(unknown_ids),
        attempts=total_attempts,
        whole_batch_fallback=whole_batch_fallback,
        failure_reason=failure_reason,
        model=model,
        endpoint=endpoint,
        http_status=aggregate_status,
        chunk_results=tuple(chunk_results),
    )
