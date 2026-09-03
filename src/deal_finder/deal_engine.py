"""Match scraped listings to Price List targets and enrich confirmed deals."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rapidfuzz import fuzz, process, utils

from .variant_tokens import build_variant_token_map, filter_candidates


MATCH_THRESHOLD = 60
NEGATION_WORDS = {"no", "not", "without", "never", "isn't", "wasn't", "hasn't", "none"}
DOWNSIZE_MAP = {
    "brand new": "Lightly Used",
    "like new": "Well Used",
    "lightly used": "Well Used",
}
FREEBIE_PATTERNS = (
    ("comes with", re.compile(r"comes\s+with\s+([^,.\n]+)", re.IGNORECASE)),
    ("includes", re.compile(r"includes?\s+([^,.\n]+)", re.IGNORECASE)),
    ("free", re.compile(r"free\s+([^,.\n]+)", re.IGNORECASE)),
    ("bundled with", re.compile(r"bundled\s+with\s+([^,.\n]+)", re.IGNORECASE)),
)


def _split_keywords(keywords: str | Iterable[str] | None) -> list[str]:
    if keywords is None:
        return []
    if isinstance(keywords, str):
        keywords = keywords.split(",")
    return [keyword.strip().lower() for keyword in keywords if keyword and keyword.strip()]


def _normalise_condition(condition: str) -> str:
    return " ".join(str(condition).split()).lower()


def _keyword_matches(description: str, keyword: str) -> Iterable[re.Match[str]]:
    # Phrase boundaries prevent "case" from accidentally matching "showcase".
    return re.finditer(rf"(?<!\w){re.escape(keyword)}(?!\w)", description, re.IGNORECASE)


def is_negated(description: str, keyword: str, window: int = 4) -> bool:
    """Return whether the first occurrence of ``keyword`` has a nearby negation."""
    match = next(iter(_keyword_matches(description, keyword.strip())), None)
    if match is None:
        return False
    preceding = re.findall(r"[\w']+", description[: match.start()].lower())[-window:]
    return any(token in NEGATION_WORDS for token in preceding)


def _has_non_negated_keyword(description: str, keyword: str) -> bool:
    for match in _keyword_matches(description, keyword):
        preceding = re.findall(r"[\w']+", description[: match.start()].lower())[-4:]
        if not any(token in NEGATION_WORDS for token in preceding):
            return True
    return False


def override_condition(
    original_condition: str,
    description: str,
    downsizing_keywords: str | Iterable[str] | None,
) -> tuple[str, bool]:
    """Downgrade a deal's condition only for non-negated keyword matches."""
    canonical_original = " ".join(str(original_condition).split()).title()
    new_condition = DOWNSIZE_MAP.get(_normalise_condition(original_condition), canonical_original)
    if new_condition == canonical_original:
        return canonical_original, False
    description = description or ""
    for keyword in _split_keywords(downsizing_keywords):
        if _has_non_negated_keyword(description, keyword):
            return new_condition, True
    return canonical_original, False


def _freebie_pattern_enabled(trigger: str, keyword_phrases: Sequence[str]) -> bool:
    return any(phrase in trigger or trigger in phrase for phrase in keyword_phrases)


def extract_freebies(
    description: str,
    keyword_phrases: str | Iterable[str] | None,
) -> list[str]:
    """Extract short bundle/freebie phrases following enabled trigger phrases."""
    phrases = _split_keywords(keyword_phrases)
    if not description or not phrases:
        return []
    found: list[str] = []
    for trigger, pattern in FREEBIE_PATTERNS:
        if not _freebie_pattern_enabled(trigger, phrases):
            continue
        for match in pattern.finditer(description):
            item = match.group(1).strip(" -:\t")
            if item and len(item.split()) <= 6 and item not in found:
                found.append(item)
    return found


def match_listing(
    listing_title: str,
    reference_items: Sequence[str],
    variant_map: dict[str, set[str]] | None = None,
    score_threshold: float = MATCH_THRESHOLD,
) -> tuple[str | None, float]:
    """Return the best variant-compatible reference item and fuzzy-match score."""
    variant_map = variant_map or build_variant_token_map(reference_items)
    candidates = [
        item
        for item in reference_items
        if filter_candidates(listing_title, item, variant_map, reference_items)
    ]
    result = process.extractOne(
        listing_title,
        candidates,
        scorer=fuzz.token_set_ratio,
        processor=utils.default_process,
    )
    if result is None or result[1] <= score_threshold:
        return None, 0.0
    return result[0], float(result[1])


def evaluate_listing(
    listing: Mapping[str, Any],
    reference_rows: Sequence[Mapping[str, Any]],
    variant_map: dict[str, set[str]] | None = None,
) -> dict[str, Any] | None:
    """Return an enriched deal record, or ``None`` when a listing is not a deal."""
    reference_by_name = {
        str(row.get("Item Name", "")).strip(): row
        for row in reference_rows
        if str(row.get("Item Name", "")).strip()
    }
    item_names = list(reference_by_name)
    if not item_names or not listing.get("title") or listing.get("price") is None:
        return None
    variant_map = variant_map or build_variant_token_map(item_names)
    matched_item, score = match_listing(str(listing["title"]), item_names, variant_map)
    if matched_item is None:
        return None

    reference = reference_by_name[matched_item]
    try:
        listing_price = float(listing["price"])
        deal_price = float(reference["Deal Price (PHP)"])
    except (KeyError, TypeError, ValueError):
        return None
    if listing_price > deal_price:
        return None

    final_condition, condition_overridden = override_condition(
        str(listing.get("condition", "")),
        str(listing.get("description", "")),
        reference.get("Keyword for Condition Downsizing"),
    )
    return {
        **dict(listing),
        "matched_item": matched_item,
        "match_score": score,
        "deal_price": deal_price,
        "savings": deal_price - listing_price,
        "final_condition": final_condition,
        "condition_overridden": condition_overridden,
        "bundles": extract_freebies(
            str(listing.get("description", "")),
            reference.get("Keyword for Finding Freebies"),
        ),
        "reference_category": reference.get("Category", ""),
    }


def find_deals(
    listings: Iterable[Mapping[str, Any]],
    reference_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate all listings using one rebuilt variant-token map per run."""
    item_names = [str(row.get("Item Name", "")).strip() for row in reference_rows]
    variant_map = build_variant_token_map([name for name in item_names if name])
    return [
        deal
        for listing in listings
        if (deal := evaluate_listing(listing, reference_rows, variant_map)) is not None
    ]
