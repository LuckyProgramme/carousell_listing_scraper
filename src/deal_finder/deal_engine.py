"""Match scraped listings to Price List targets and enrich confirmed deals."""

from __future__ import annotations

import re
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process, utils

from .accessory_checker import is_accessory_only_listing
from .candidate_filter import BUNDLE_PRICE_MULTIPLIER, CandidateMatch, find_candidate_matches
from .text_cleaner import clean_description_for_audit, expand_aliases
from .gemini_auditor import AuditBatchResult, audit_batch
from .models import (
    AuditResult,
    ConfirmedDeal,
    PriceListTarget,
    is_acceptable_gemini_deal,
    is_acceptable_local_deal,
)
from .variant_tokens import build_family_lookup, build_variant_token_map, filter_candidates


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
TRIAGE_PRICE_FLAGS = frozenset({"placeholder_zero", "suspiciously_low"})
GAME_PACKAGING_PATTERN = re.compile(
    r"\b(?:cartridge\s+only|(?:no|without|missing)\s+(?:the\s+)?(?:case|box)|"
    r"(?:case|box)\s+(?:missing|not\s+included))\b", re.I
)


def _verified_deal_price(candidate: CandidateMatch, audit: AuditResult) -> float | None:
    """Require source-backed separate asking prices before accepting a bundle."""
    if not audit.is_bundle:
        # Above-threshold bundle triage cannot be cleared with a non-bundle response.
        return candidate.effective_price
    target, listing = candidate.target, candidate.listing
    price = audit.individual_price
    if (
        not target.allow_bundle_check or not audit.separately_available
        or type(price) not in (int, float) or not math.isfinite(price) or price <= 0
        or price > target.deal_price or not audit.price_evidence
        or (listing.price is not None and (
            not math.isfinite(listing.price)
            or listing.price > BUNDLE_PRICE_MULTIPLIER * target.deal_price
        ))
    ):
        return None
    if re.search(
        r"\b(?:(?:bundle|take\s*all|set)\s+only|no\s+(?:split(?:ting)?|individual\s+sales)|"
        r"not\s+sold\s+separately)\b", f"{listing.title}\n{listing.description}", re.I
    ):
        return None
    evidence = " ".join(audit.price_evidence.split())
    source_lines = clean_description_for_audit(listing.description).splitlines()
    evidence_pattern = re.compile(r"(?<!\w)" + re.escape(evidence) + r"(?![\w.,])")
    containing_lines = [
        " ".join(line.split()) for line in source_lines
        if evidence_pattern.search(" ".join(line.split()))
    ]
    if not containing_lines:
        return None
    if re.search(
        r"\b(?:sold|reserved|deposit|down\s*payment|original(?:ly)?|retail|was|used\s+to|"
        r"if\s+(?:you\s+)?buy|when\s+(?:you\s+)?buy)\b", "\n".join(containing_lines), re.I
    ):
        return None
    # Require all meaningful target tokens in the quoted price line. Aliases are
    # expanded on both sides; generic language such as 'the' is not required.
    ignored = {"the", "of", "a", "an", "for", "nintendo", "switch", "game", "games"}
    target_tokens = set(re.findall(r"\w+", expand_aliases(target.item_name).casefold())) - ignored
    evidence_tokens = set(re.findall(r"\w+", expand_aliases(evidence).casefold()))
    if not target_tokens or not target_tokens.issubset(evidence_tokens):
        return None
    amounts = []
    for match in re.finditer(r"(?<![\w.])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(k\b)?(?![\w.])", evidence, re.I):
        amounts.append(float(match[1].replace(",", "")) * (1000 if match[2] else 1))
    # A quote containing multiple prices cannot establish which one buys the target.
    # Ignore bare model numbers already present in the requested Item Name.
    target_numbers = {float(token) for token in target_tokens if token.isdecimal()}
    asking_prices = [amount for amount in amounts if amount not in target_numbers]
    return float(price) if asking_prices == [price] else None


@dataclass(frozen=True)
class CascadeResult:
    """Output of the price/recall -> Gemini audit cascade."""

    deals: tuple[dict[str, Any], ...]
    candidates: tuple[CandidateMatch, ...]
    listings: tuple[dict[str, Any], ...]
    audit_result: AuditBatchResult
    source_summaries: tuple[dict[str, Any], ...] = ()

    def audit_report(self) -> dict[str, Any]:
        """Return a JSON-safe, PII-minimized comparison report for dry runs."""
        return {
            "scraped": len(self.listings),
            "scrape_sources": list(self.source_summaries),
            "candidate_matches": [
                {
                    "listing_id": candidate.listing.id,
                    "title": candidate.listing.title,
                    "target_item": candidate.target.item_name,
                    "target_type": candidate.target.target_type,
                    "allow_bundle_check": candidate.target.allow_bundle_check,
                    "effective_price": candidate.effective_price,
                    "price_flag": candidate.price_flag,
                    "rapidfuzz_score": candidate.lexical_score,
                }
                for candidate in self.candidates
            ],
            "gemini_audits": [audit.to_dict() for audit in self.audit_result.audits],
            "gemini_chunks": [
                chunk.to_dict() for chunk in self.audit_result.chunk_results
            ],
            "fallback_listing_ids": sorted(self.audit_result.fallback_ids),
            "unknown_gemini_ids": sorted(self.audit_result.unknown_ids),
            "validation_errors": list(self.audit_result.validation_errors),
            "whole_batch_fallback": self.audit_result.whole_batch_fallback,
            "gemini_failure_reason": self.audit_result.failure_reason,
            "gemini_attempts": self.audit_result.attempts,
            "gemini_model": self.audit_result.model,
            "gemini_endpoint": self.audit_result.endpoint,
            "gemini_http_status": self.audit_result.http_status,
            "local_fallback_decisions": [
                {
                    "listing_id": deal.get("id", deal.get("listing_id", "")),
                    "matched_item": deal.get("matched_item", ""),
                    "local_match_score": deal.get("local_match_score", deal.get("match_score")),
                    "price": deal.get("price", deal.get("carousell_price")),
                    "deal_price": deal.get("deal_price"),
                    "original_listing_price": deal.get("original_listing_price"),
                    "is_bundle": deal.get("is_bundle", False),
                    "price_evidence": deal.get("price_evidence"),
                    "acceptance_reason": deal.get("acceptance_reason"),
                }
                for deal in self.audit_result.fallback_deals
            ],
            "confirmed_deals": [
                {
                    "listing_id": deal.get("id", ""),
                    "matched_item": deal.get("matched_item", ""),
                    "audit_source": deal.get("audit_source", ""),
                    "gemini_confidence": deal.get("gemini_confidence"),
                    "local_match_score": deal.get("local_match_score"),
                    "price": deal.get("price"),
                    "deal_price": deal.get("deal_price"),
                    "original_listing_price": deal.get("original_listing_price"),
                    "is_bundle": deal.get("is_bundle", False),
                    "price_evidence": deal.get("price_evidence"),
                    "acceptance_reason": deal.get("acceptance_reason"),
                }
                for deal in self.deals
            ],
        }


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
    family_lookup: Mapping[str, Sequence[str]] | None = None,
    score_threshold: float = MATCH_THRESHOLD,
) -> tuple[str | None, float]:
    """Return the best variant-compatible reference item and fuzzy-match score."""
    variant_map = variant_map or build_variant_token_map(reference_items)
    family_lookup = family_lookup or build_family_lookup(reference_items)
    candidates = [
        item
        for item in reference_items
        if filter_candidates(listing_title, item, variant_map, family_lookup=family_lookup)
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
    family_lookup: Mapping[str, Sequence[str]] | None = None,
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
    reference_by_name = {
        name: row for name, row in reference_by_name.items()
        if not is_accessory_only_listing(
            str(listing["title"]), str(listing.get("description", "")),
            target_type=PriceListTarget.from_mapping(row).target_type,
        )
    }
    item_names = list(reference_by_name)
    if not item_names:
        return None
    variant_map = variant_map or build_variant_token_map(item_names)
    family_lookup = family_lookup or build_family_lookup(item_names)
    matched_item, score = match_listing(
        str(listing["title"]), item_names, variant_map, family_lookup=family_lookup
    )
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
        "bundles": [] if listing.get("price_flag") == "bundle_candidate" else extract_freebies(
            str(listing.get("description", "")),
            reference.get("Keyword for Finding Freebies"),
        ),
        "reference_category": reference.get("Category", ""),
    }


def find_deals(
    listings: Iterable[Mapping[str, Any]],
    reference_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate all listings using precomputed variant-token and family-lookup maps."""
    item_names = [str(row.get("Item Name", "")).strip() for row in reference_rows]
    valid_names = [name for name in item_names if name]
    variant_map = build_variant_token_map(valid_names)
    family_lookup = build_family_lookup(valid_names)
    return [
        deal
        for listing in listings
        if (deal := evaluate_listing(listing, reference_rows, variant_map, family_lookup=family_lookup)) is not None
    ]


def _price_targets(reference_rows: Sequence[Mapping[str, Any]]) -> tuple[PriceListTarget, ...]:
    """Normalize usable Price List rows for the recall candidate filter."""
    targets: list[PriceListTarget] = []
    for row in reference_rows:
        target = PriceListTarget.from_mapping(row)
        if target.item_name and target.deal_price > 0:
            targets.append(target)
    return tuple(targets)


def _annotate_listings(
    listings: Iterable[Mapping[str, Any]], candidates: Iterable[CandidateMatch]
) -> tuple[dict[str, Any], ...]:
    """Preserve price-triage state on All Listings rows without dropping listings."""
    priority = {"normal": 0, "placeholder_zero": 1, "suspiciously_low": 2, "text_recovered": 3, "bundle_candidate": 4}
    selected: dict[str, CandidateMatch] = {}
    for candidate in candidates:
        previous = selected.get(candidate.listing.id)
        if previous is None or priority[candidate.price_flag] > priority[previous.price_flag]:
            selected[candidate.listing.id] = candidate

    annotated: list[dict[str, Any]] = []
    for raw_listing in listings:
        listing = dict(raw_listing)
        candidate = selected.get(str(listing.get("id", "")).strip())
        if candidate is not None:
            listing["price_flag"] = candidate.price_flag
            if candidate.price_flag == "text_recovered":
                listing["price"] = candidate.effective_price
        else:
            listing.setdefault("price_flag", "normal")
        annotated.append(listing)
    return tuple(annotated)


def _condition_after_audit(
    candidate: CandidateMatch, audit: AuditResult
) -> tuple[str, bool]:
    """Combine deterministic condition clues with Gemini's defect assessment."""
    listing = candidate.listing
    description = listing.description
    packaging_only = False
    packaging_text = f"{listing.title}\n{listing.description}"
    if candidate.target.is_game_target:
        description = GAME_PACKAGING_PATTERN.sub("", description)
        packaging_only = bool(GAME_PACKAGING_PATTERN.search(packaging_text)) and not any(
            not GAME_PACKAGING_PATTERN.search(issue) for issue in audit.issues
        )
    final_condition, locally_downgraded = override_condition(
        listing.condition, description, candidate.target.downsizing_keywords
    )
    if audit.downgrade_condition and not locally_downgraded and not packaging_only:
        final_condition = DOWNSIZE_MAP.get(_normalise_condition(listing.condition), final_condition)
        return final_condition, final_condition != listing.condition
    return final_condition, locally_downgraded


def _gemini_deal(candidate: CandidateMatch, audit: AuditResult, verified_price: float) -> dict[str, Any]:
    """Create a provenance-safe deal record after the Gemini acceptance gate."""
    final_condition, condition_overridden = _condition_after_audit(candidate, audit)
    listing = candidate.listing
    deal = ConfirmedDeal(
        listing_id=listing.id,
        title=listing.title,
        carousell_price=verified_price,
        matched_item=candidate.target.item_name,
        deal_price=candidate.target.deal_price,
        savings=candidate.target.deal_price - verified_price,
        link=listing.link,
        seller=listing.seller,
        # Item Name sources deliberately carry no category. Category-mode
        # sources set listing.category while building the scrape batch.
        category=listing.category,
        original_condition=listing.condition,
        final_condition=final_condition,
        condition_overridden=condition_overridden,
        freebies=() if audit.is_bundle else audit.freebies,
        issues=tuple(dict.fromkeys((*audit.issues, *(
            ("Cartridge only / missing case",)
            if candidate.target.is_game_target and GAME_PACKAGING_PATTERN.search(f"{listing.title}\n{listing.description}")
            else ()
        )))),
        retail_price=candidate.target.retail_price,
        thumbnail_url=listing.thumbnail_url,
        seller_rating=listing.seller_rating,
        seller_rating_count=listing.seller_rating_count,
        like_count=listing.like_count,
        location=listing.location,
        listing_timestamp=listing.listing_timestamp,
        price_flag=candidate.price_flag,
        audit_source="gemini",
        gemini_confidence=audit.confidence,
        specs_matched=audit.specs_matched,
        acceptance_reason=(
            f"Split from bundle (Original listing: PHP {listing.price or 0:.2f}); "
            "Gemini verified separate asking price and target match at >=80% confidence."
            if audit.is_bundle else "Gemini exact-spec audit met the 80% acceptance threshold."
        ),
    )
    payload = deal.to_dict()
    payload["reference_category"] = listing.category
    payload["original_listing_price"] = listing.price
    payload["is_bundle"] = audit.is_bundle
    payload["individual_price"] = audit.individual_price if audit.is_bundle else None
    payload["price_evidence"] = audit.price_evidence if audit.is_bundle else None
    return payload


def _accept_local_fallback_deals(
    fallback_deals: Iterable[Mapping[str, Any]], candidates: Iterable[CandidateMatch]
) -> list[dict[str, Any]]:
    """Apply the local-only gate without treating lexical score as Gemini confidence."""
    candidate_list = tuple(candidates)
    candidate_by_id_target = {
        (candidate.listing.id, candidate.target.item_name): candidate
        for candidate in candidate_list
    }
    target_names = tuple({candidate.target.item_name for candidate in candidate_list})
    variant_map = build_variant_token_map(target_names)
    family_lookup = build_family_lookup(target_names)
    accepted: list[dict[str, Any]] = []
    for raw_deal in fallback_deals:
        deal = dict(raw_deal)
        listing_id = str(deal.get("id") or deal.get("listing_id") or "").strip()
        matched_item = str(deal.get("matched_item") or "").strip()
        candidate = candidate_by_id_target.get((listing_id, matched_item))
        if candidate is None or candidate.price_flag in TRIAGE_PRICE_FLAGS | {"bundle_candidate"}:
            continue
        try:
            local_score = float(deal.get("local_match_score", deal.get("match_score", 0.0)))
            listing_price = float(deal.get("price", deal.get("carousell_price")))
            deal_price = float(deal["deal_price"])
        except (KeyError, TypeError, ValueError):
            continue
        variant_pass = filter_candidates(
            candidate.listing.title,
            candidate.target.item_name,
            variant_map,
            family_lookup=family_lookup,
        )
        if not is_acceptable_local_deal(local_score, listing_price, deal_price, variant_pass):
            continue
        deal.update(
            {
                "audit_source": "local_fallback",
                "local_match_score": local_score,
                "gemini_confidence": None,
                "specs_matched": None,
                "price_flag": candidate.price_flag,
                "carousell_price": listing_price,
                "acceptance_reason": deal.get(
                    "acceptance_reason",
                    "Gemini audit unavailable; accepted by the local lexical fallback.",
                ),
            }
        )
        accepted.append(deal)
    return accepted


def run_two_stage_cascade(
    listings: Iterable[Mapping[str, Any]],
    reference_rows: Sequence[Mapping[str, Any]],
    *,
    audit_candidates: Callable[[Sequence[Any], Sequence[Any]], AuditBatchResult] = audit_batch,
    include_local_fallback: bool = False,
) -> CascadeResult:
    """Run recall candidate generation, Gemini auditing, and independent gates.

    Stage 1 never removes zero/very-low-price matches: they are retained as
    triage candidates and annotated in ``listings``.  They cannot become
    confirmed deals until a real in-text price has been recovered.
    """
    raw_listings = [dict(listing) for listing in listings]
    targets = _price_targets(reference_rows)
    candidates_list: list[CandidateMatch] = []
    for listing in raw_listings:
        allowed_names = listing.get("eligible_target_names")
        if allowed_names is None:
            eligible_targets = targets
        else:
            if isinstance(allowed_names, str):
                allowed = {allowed_names}
            else:
                allowed = {str(name) for name in allowed_names}
            eligible_targets = tuple(target for target in targets if target.item_name in allowed)
        candidates_list.extend(find_candidate_matches(listing, eligible_targets))
    candidates = tuple(candidates_list)
    annotated_listings = _annotate_listings(raw_listings, candidates)
    if not candidates:
        return CascadeResult(
            deals=(),
            candidates=(),
            listings=annotated_listings,
            audit_result=AuditBatchResult((), (), ()),
        )

    audit_result = audit_candidates(candidates, targets)
    candidate_by_id_target = {
        (candidate.listing.id, candidate.target.item_name): candidate
        for candidate in candidates
    }
    gemini_deals: list[dict[str, Any]] = []
    accepted_ids: set[str] = set()
    for audit in audit_result.audits:
        if audit.matched_item is None or audit.id in accepted_ids:
            continue
        candidate = candidate_by_id_target.get((audit.id, audit.matched_item))
        if candidate is None or candidate.price_flag in TRIAGE_PRICE_FLAGS:
            continue
        verified_price = _verified_deal_price(candidate, audit)
        if verified_price is None:
            continue
        if not is_acceptable_gemini_deal(
            audit, verified_price, candidate.target.deal_price
        ):
            continue
        gemini_deals.append(_gemini_deal(candidate, audit, verified_price))
        accepted_ids.add(candidate.listing.id)

    local_deals = (
        _accept_local_fallback_deals(
            audit_result.fallback_deals, audit_result.fallback_candidates
        )
        if include_local_fallback
        else []
    )
    all_deals = [*gemini_deals]
    all_deals.extend(
        deal
        for deal in local_deals
        if str(deal.get("id") or deal.get("listing_id") or "") not in accepted_ids
    )
    return CascadeResult(
        deals=tuple(all_deals),
        candidates=candidates,
        listings=annotated_listings,
        audit_result=audit_result,
    )
