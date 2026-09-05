"""Recall-oriented candidate filter with alias expansion and price triage."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Final, Mapping, Sequence

from rapidfuzz import fuzz

from .accessory_checker import is_accessory_only_listing
from .models import Listing, PriceListTarget
from .text_cleaner import expand_aliases, recover_price_from_text


TOKEN_SET_THRESHOLD = 50.0
PARTIAL_RATIO_THRESHOLD = 65.0
LOW_PRICE_RATIO = 0.10  # Prices < 10% of deal threshold require triage
BUNDLE_PRICE_MULTIPLIER = 3.0


def has_bundle_cues(title: str, description: str = "") -> bool:
    text = f"{title}\n{description}"
    return bool(
        re.search(r"\b(?:bundle|lot|set|each|games|package|take\s+all)\b", text, re.I)
        or re.search(r"(?<!\d),(?!\d)|[+&/]", title)
        or len(re.findall(r"(?m)^.*\d[\d,.]*\s*(?:k\b)?\s*[-:–].+$", description)) >= 2
    )


@dataclass(frozen=True)
class CandidateMatch:
    """A qualified candidate deal paired with a target product."""

    listing: Listing
    target: PriceListTarget
    effective_price: float
    lexical_score: float
    price_flag: str  # "normal", "text_recovered", "placeholder_zero", "suspiciously_low"


def compute_lexical_recall_score(title: str, target_name: str) -> tuple[float, float, float]:
    """Compute multi-scorer lexical similarity after alias expansion.

    Returns:
        (best_score, token_set_score, partial_score)
    """
    expanded_title = expand_aliases(title).lower()
    target_lower = expand_aliases(target_name).lower()

    token_set = float(fuzz.token_set_ratio(expanded_title, target_lower))
    partial = float(fuzz.partial_ratio(expanded_title, target_lower))
    best = max(token_set, partial)
    return best, token_set, partial


CORE_TARGET_TOKENS: Final[dict[str, list[set[str]]]] = {
    "PS5 Slim": [{"ps5"}, {"playstation", "5"}],
    "PS5 Slim Digital": [{"ps5"}, {"playstation", "5"}],
    "Nintendo Switch OLED": [
        {"switch", "oled"},
        {"nintendo", "switch"},
        {"nsw", "oled"},
        {"oled", "console"},
        {"oled", "unit"},
    ],
    "iPhone 15": [{"iphone", "15"}, {"ip15"}],
    "iPhone 15 Pro Max": [{"iphone", "15", "max"}, {"15pm"}, {"ip15pm"}, {"15", "pro", "max"}],
    "iPad Air 5": [{"ipad", "air"}, {"ipad", "5"}, {"air", "5"}],
    "M1 MacBook Air": [{"macbook", "m1"}, {"mba", "m1"}, {"macbook", "air"}],
    "Sony WH-1000XM5": [{"xm5"}, {"wh1000xm5"}, {"1000xm5"}, {"sony", "xm5"}],
}


def _tokenize(text: str) -> set[str]:
    import re
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def passes_lexical_recall_filter(title: str, target_name: str) -> bool:
    """Evaluate whether a title has sufficient target overlap for Stage 1 candidate generation."""
    expanded = expand_aliases(title).lower()
    title_tokens = _tokenize(expanded)

    # Signal 1: Core target token set check (guarantees zero false negatives on core models)
    if target_name in CORE_TARGET_TOKENS:
        for token_set in CORE_TARGET_TOKENS[target_name]:
            if token_set.issubset(title_tokens):
                return True

    # Signal 2: Multi-scorer fuzzy similarity
    _, token_set, partial = compute_lexical_recall_score(title, target_name)
    return token_set >= TOKEN_SET_THRESHOLD or partial >= PARTIAL_RATIO_THRESHOLD


def triage_listing_price(
    raw_price: float | None,
    title: str,
    description: str,
    deal_price: float,
) -> tuple[float | None, str]:
    """Apply Three-Tier price policy to detect genuine deals vs placeholders.

    Returns:
        (effective_price, price_flag)
    """
    is_zero_or_none = raw_price is None or raw_price <= 0.0
    is_suspiciously_low = raw_price is not None and (0.0 < raw_price < deal_price * LOW_PRICE_RATIO)

    # Tier 1: In-Text Price Recovery
    if is_zero_or_none or is_suspiciously_low:
        recovered, source = recover_price_from_text(title, description, deal_price)
        if recovered is not None and deal_price * LOW_PRICE_RATIO <= recovered <= deal_price:
            return recovered, "text_recovered"

    # Tier 2: Classification of unrecovered prices
    if is_zero_or_none:
        return (0.0, "placeholder_zero")
    if is_suspiciously_low:
        return (raw_price, "suspiciously_low")

    return (raw_price, "normal")


def find_candidate_matches(
    listing_data: Mapping[str, Any],
    targets: Sequence[PriceListTarget],
) -> list[CandidateMatch]:
    """Find all plausible target candidates for a scraped listing without silent dropping.

    Returns a list of CandidateMatch objects for listings that pass lexical & price criteria.
    """
    listing = Listing.from_mapping(listing_data)
    candidates: list[CandidateMatch] = []

    for target in targets:
        if is_accessory_only_listing(
            listing.title, listing.description, target_type=target.target_type
        ):
            continue
        bundle_cues = has_bundle_cues(listing.title, listing.description)
        if listing.price is not None and (
            not math.isfinite(listing.price)
            or listing.price > target.deal_price * BUNDLE_PRICE_MULTIPLIER
        ):
            continue
        # Lexical recall check
        match_text = listing.title
        if bundle_cues and target.allow_bundle_check:
            match_text += "\n" + listing.description
        if not passes_lexical_recall_filter(match_text, target.item_name):
            continue

        if bundle_cues and target.allow_bundle_check:
            candidates.append(CandidateMatch(
                listing=listing, target=target,
                effective_price=listing.price or 0.0,
                lexical_score=compute_lexical_recall_score(match_text, target.item_name)[0],
                price_flag="bundle_candidate",
            ))
            continue

        # Price triage
        effective_price, price_flag = triage_listing_price(
            listing.price,
            listing.title,
            # Never recover an unrelated item's first price from a multi-item post.
            "" if bundle_cues else listing.description,
            target.deal_price,
        )

        # Valid prices can proceed as candidate deals. Placeholder and very-low
        # prices are also retained for Gemini triage and output visibility; the
        # cascade later prevents them from becoming confirmed deals until a real
        # in-text price is recovered.
        is_price_eligible = (
            effective_price is not None
            and target.deal_price * LOW_PRICE_RATIO <= effective_price <= target.deal_price
        )
        is_triage_candidate = price_flag in {"placeholder_zero", "suspiciously_low"}
        if is_price_eligible or is_triage_candidate:
            best_score, _, _ = compute_lexical_recall_score(listing.title, target.item_name)
            candidates.append(
                CandidateMatch(
                    listing=listing,
                    target=target,
                    effective_price=float(effective_price or 0.0),
                    lexical_score=best_score,
                    price_flag=price_flag,
                )
            )

    return candidates
