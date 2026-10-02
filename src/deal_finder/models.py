"""Domain models and validation schemas for listings, targets, audits, and deals."""

from __future__ import annotations

import math
import re
import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlsplit


AuditSource = Literal["gemini", "local_fallback"]
SearchMode = Literal["Category", "Item Name"]
ScanStatus = Literal["queued", "scanning", "evaluating", "saving", "completed", "failed"]


def parse_target_type(value: Any) -> str:
    normalized = str(value or "Hardware").strip().casefold() or "hardware"
    if normalized not in {"hardware", "game"}:
        raise ValueError("Target Type must be Hardware or Game (blank defaults to Hardware).")
    return normalized.title()


def parse_bundle_check(value: Any) -> bool:
    normalized = str(value if value is not None else "").strip().casefold()
    if normalized in {"", "false", "no", "0"}:
        return False
    if normalized in {"true", "yes", "1"}:
        return True
    raise ValueError("Allow Bundle Check must be TRUE/FALSE, Yes/No, or 1/0.")


def _clean_str(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _parse_keywords(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        parts = [p.strip().lower() for p in value.split(",")]
        return tuple(p for p in parts if p)
    if isinstance(value, Sequence):
        parts = [_clean_str(p).lower() for p in value]
        return tuple(p for p in parts if p)
    return ()


def _safe_https_url(value: Any, *, carousell_only: bool = False) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 3000:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    if carousell_only and parsed.hostname.casefold() not in {
        "carousell.ph",
        "www.carousell.ph",
    }:
        return ""
    return text


@dataclass(frozen=True)
class Listing:
    """Scraped marketplace listing representation.

    Captured from Carousell JSON blob or HTML fallback scraper.
    """

    id: str
    title: str
    price: float | None
    condition: str = ""
    description: str = ""
    link: str = ""
    seller: str = ""
    category: str = ""
    thumbnail_url: str | None = None
    seller_rating: float | None = None
    seller_rating_count: int | None = None
    like_count: int | None = None
    location: str | None = None
    listing_timestamp: str | None = None
    price_flag: str = "Normal"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Listing:
        raw_price = data.get("price")
        price = float(raw_price) if raw_price is not None and str(raw_price).strip() != "" else None
        if price is not None and not math.isfinite(price):
            price = None
        link = _safe_https_url(data.get("link"), carousell_only=True)
        thumbnail_url = _safe_https_url(data.get("thumbnail_url")) or None
        seller_rating = (
            float(data["seller_rating"]) if data.get("seller_rating") is not None else None
        )
        if seller_rating is not None and (
            not math.isfinite(seller_rating) or not 0 <= seller_rating <= 5
        ):
            seller_rating = None
        seller_rating_count = (
            int(data["seller_rating_count"])
            if data.get("seller_rating_count") is not None
            else None
        )
        if seller_rating_count is not None and seller_rating_count < 0:
            seller_rating_count = None
        like_count = int(data["like_count"]) if data.get("like_count") is not None else None
        if like_count is not None and like_count < 0:
            like_count = None
        return cls(
            id=_clean_str(data.get("id"))[:300],
            title=_clean_str(data.get("title"))[:500],
            price=price,
            condition=_clean_str(data.get("condition"))[:120],
            description=str(data.get("description", "")).strip(),
            link=link,
            seller=_clean_str(data.get("seller"))[:300],
            category=_clean_str(data.get("category"))[:200],
            thumbnail_url=thumbnail_url,
            seller_rating=seller_rating,
            seller_rating_count=seller_rating_count,
            like_count=like_count,
            location=_clean_str(data.get("location"))[:300] or None,
            listing_timestamp=_clean_str(data.get("listing_timestamp"))[:200] or None,
            price_flag=_clean_str(
                data.get("price_flag") or data.get("price_status") or "Normal"
            )[:80],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def source_id(self) -> str:
        """Return the marketplace ID or a deterministic scan-safe fallback."""
        if self.id.strip():
            return self.id.strip()
        seed = f"{self.link}\n{self.title}".encode("utf-8")
        return f"generated-{hashlib.sha256(seed).hexdigest()[:32]}"


@dataclass(frozen=True)
class Target:
    """Provider-neutral product target used by the scanner and web application."""

    item_name: str
    category: str
    deal_price: float
    retail_price: float | None = None
    downsizing_keywords: tuple[str, ...] = ()
    freebie_keywords: tuple[str, ...] = ()
    notes: str = ""
    target_type: str = "Hardware"
    allow_bundle_check: bool = False
    search_mode: SearchMode = "Category"
    enabled: bool = True
    id: str | None = None
    owner_id: str | None = None

    def __post_init__(self) -> None:
        if not self.item_name.strip():
            raise ValueError("Target item_name is required.")
        if not math.isfinite(self.deal_price) or self.deal_price <= 0:
            raise ValueError("Target deal_price must be a finite positive number.")
        if self.retail_price is not None and (
            not math.isfinite(self.retail_price) or self.retail_price <= 0
        ):
            raise ValueError("Target retail_price must be a finite positive number or null.")
        if self.search_mode not in {"Category", "Item Name"}:
            raise ValueError("Target search_mode must be Category or Item Name.")
        if self.search_mode == "Category" and not self.category.strip():
            raise ValueError("Category search targets require a category.")

    @property
    def is_game_target(self) -> bool:
        return self.target_type == "Game"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Target:
        item_name = _clean_str(data.get("Item Name") or data.get("item_name"))
        category = _clean_str(data.get("Category") or data.get("category"))
        raw_deal_price = data.get("Deal Price (PHP)") or data.get("deal_price")
        if raw_deal_price is None:
            raise ValueError(f"Target '{item_name}' is missing required deal_price.")
        deal_price = float(raw_deal_price)

        raw_retail_price = data.get("Retail Price (PHP)") or data.get("retail_price")
        retail_price = float(raw_retail_price) if raw_retail_price is not None else None

        downsizing = _parse_keywords(
            data.get("Keyword for Condition Downsizing") or data.get("downsizing_keywords")
        )
        freebies = _parse_keywords(
            data.get("Keyword for Finding Freebies") or data.get("freebie_keywords")
        )
        notes = str(data.get("Notes") or data.get("notes") or "").strip()

        raw_mode = _clean_str(data.get("Search Mode") or data.get("search_mode") or "Category")
        normalized_mode: SearchMode
        if raw_mode.casefold() == "category":
            normalized_mode = "Category"
        elif raw_mode.casefold() == "item name":
            normalized_mode = "Item Name"
        else:
            raise ValueError("Search Mode must be Category or Item Name.")

        return cls(
            item_name=item_name,
            category=category,
            deal_price=deal_price,
            retail_price=retail_price,
            downsizing_keywords=downsizing,
            freebie_keywords=freebies,
            notes=notes,
            target_type=parse_target_type(data.get("Target Type", data.get("target_type"))),
            allow_bundle_check=parse_bundle_check(
                data.get("Allow Bundle Check", data.get("allow_bundle_check"))
            ),
            search_mode=normalized_mode,
            enabled=bool(data.get("enabled", True)),
            id=_clean_str(data.get("id")) or None,
            owner_id=_clean_str(data.get("owner_id")) or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_scanner_mapping(self) -> dict[str, Any]:
        """Return the legacy-shaped boundary payload expected by scanner modules."""
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "Item Name": self.item_name,
            "Category": self.category,
            "Search Mode": self.search_mode,
            "Deal Price (PHP)": self.deal_price,
            "Retail Price (PHP)": self.retail_price,
            "Keyword for Condition Downsizing": list(self.downsizing_keywords),
            "Keyword for Finding Freebies": list(self.freebie_keywords),
            "Notes": self.notes,
            "Target Type": self.target_type,
            "Allow Bundle Check": self.allow_bundle_check,
            "enabled": self.enabled,
        }


# Temporary compatibility name while the existing deterministic engine migrates
# away from its former Google Sheets terminology.
PriceListTarget = Target


@dataclass(frozen=True)
class ScanRun:
    """Canonical lifecycle record for one user-requested scan."""

    id: str
    owner_id: str
    status: ScanStatus
    listings_count: int = 0
    candidates_count: int = 0
    deals_count: int = 0
    safe_error: str | None = None
    target_snapshot: tuple[dict[str, Any], ...] = ()
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ScanRun:
        status = _clean_str(data.get("status"))
        if status not in {"queued", "scanning", "evaluating", "saving", "completed", "failed"}:
            raise ValueError(f"Invalid scan status '{status}'.")

        def parse_time(value: Any) -> datetime | None:
            if value in (None, ""):
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        snapshot = data.get("target_snapshot") or ()
        if not isinstance(snapshot, (list, tuple)) or not all(isinstance(v, Mapping) for v in snapshot):
            raise ValueError("Scan target_snapshot must be a list of objects.")
        return cls(
            id=_clean_str(data.get("id")),
            owner_id=_clean_str(data.get("owner_id")),
            status=status,  # type: ignore[arg-type]
            listings_count=int(data.get("listings_count") or 0),
            candidates_count=int(data.get("candidates_count") or 0),
            deals_count=int(data.get("deals_count") or 0),
            safe_error=_clean_str(data.get("safe_error")) or None,
            target_snapshot=tuple(dict(value) for value in snapshot),
            created_at=parse_time(data.get("created_at")),
            started_at=parse_time(data.get("started_at")),
            completed_at=parse_time(data.get("completed_at")),
        )


@dataclass(frozen=True)
class Evaluation:
    """Canonical deterministic/model decision for one listing and target."""

    listing_source_id: str
    target_snapshot_id: str
    accepted: bool
    matched_item: str | None = None
    target_id: str | None = None
    target_snapshot: dict[str, Any] = field(default_factory=dict)
    audit_source: AuditSource | None = None
    confidence: int | None = None
    specs_matched: bool | None = None
    local_match_score: float | None = None
    issues: tuple[str, ...] = ()
    freebies: tuple[str, ...] = ()
    final_condition: str | None = None
    condition_overridden: bool = False
    deal_price: float | None = None
    retail_price: float | None = None
    evaluated_price: float | None = None
    savings: float | None = None
    acceptance_reason: str | None = None
    is_bundle: bool = False
    individual_price: float | None = None
    price_evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.listing_source_id.strip():
            raise ValueError("Evaluation listing_source_id is required.")
        try:
            uuid.UUID(self.target_snapshot_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("Evaluation target_snapshot_id must be a UUID.") from exc
        if str(self.target_snapshot.get("id") or "") != self.target_snapshot_id:
            raise ValueError(
                "Evaluation target_snapshot_id must match target_snapshot.id."
            )
        if self.confidence is not None and not 0 <= self.confidence <= 100:
            raise ValueError("Evaluation confidence must be between 0 and 100.")
        if self.local_match_score is not None and not 0 <= self.local_match_score <= 100:
            raise ValueError("Evaluation local_match_score must be between 0 and 100.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditResult:
    """Per-listing audit evaluation returned by Gemini Flash.

    Structured output payload verifying semantics, specs, defects, and freebies.
    """

    id: str
    matched_item: str | None
    confidence: int
    specs_matched: bool
    issues: tuple[str, ...] = ()
    freebies: tuple[str, ...] = ()
    downgrade_condition: bool = False
    is_accessory: bool = False
    is_bundle: bool = False
    individual_price: float | None = None
    separately_available: bool = False
    price_evidence: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> AuditResult:
        raw_id = data.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ValueError("AuditResult requires a non-empty string id.")
        listing_id = _clean_str(raw_id)

        raw_matched_item = data.get("matched_item")
        if raw_matched_item is not None and not isinstance(raw_matched_item, str):
            raise ValueError(
                f"AuditResult matched_item for id '{listing_id}' must be a string or null."
            )
        matched_item = _clean_str(raw_matched_item) or None

        raw_conf = data.get("confidence")
        if type(raw_conf) is not int:
            raise ValueError(
                f"AuditResult confidence for id '{listing_id}' must be an integer."
            )
        confidence = raw_conf
        if not (0 <= confidence <= 100):
            raise ValueError(f"AuditResult confidence {confidence} out of range [0, 100].")

        specs_matched = data.get("specs_matched")
        if type(specs_matched) is not bool:
            raise ValueError(
                f"AuditResult specs_matched for id '{listing_id}' must be a boolean."
            )

        raw_issues = data.get("issues")
        if not isinstance(raw_issues, list) or not all(
            isinstance(issue, str) for issue in raw_issues
        ):
            raise ValueError(
                f"AuditResult issues for id '{listing_id}' must be a list of strings."
            )
        issues = tuple(issue.strip() for issue in raw_issues if issue.strip())

        raw_freebies = data.get("freebies")
        if not isinstance(raw_freebies, list) or not all(
            isinstance(freebie, str) for freebie in raw_freebies
        ):
            raise ValueError(
                f"AuditResult freebies for id '{listing_id}' must be a list of strings."
            )
        freebies = tuple(freebie.strip() for freebie in raw_freebies if freebie.strip())

        downgrade_condition = data.get("downgrade_condition", False)
        if type(downgrade_condition) is not bool:
            raise ValueError(
                f"AuditResult downgrade_condition for id '{listing_id}' must be a boolean."
            )

        is_accessory = data.get("is_accessory")
        if type(is_accessory) is not bool:
            raise ValueError(
                f"AuditResult is_accessory for id '{listing_id}' must be a boolean."
            )

        for name in ("is_bundle", "separately_available"):
            if type(data.get(name)) is not bool:
                raise ValueError(f"AuditResult {name} must be a boolean.")
        individual_price = data.get("individual_price")
        if "individual_price" not in data or (individual_price is not None and (
            type(individual_price) not in (int, float)
            or not math.isfinite(individual_price) or individual_price <= 0
        )):
            raise ValueError("AuditResult individual_price must be a finite positive number or null.")
        price_evidence = data.get("price_evidence")
        if "price_evidence" not in data or (price_evidence is not None and (
            not isinstance(price_evidence, str) or not price_evidence.strip()
            or len(price_evidence) > 800
        )):
            raise ValueError("AuditResult price_evidence must be a non-empty excerpt (max 800) or null.")
        if not data["is_bundle"] and (individual_price is not None or data["separately_available"]):
            raise ValueError("Non-bundle audit cannot contain split-price decisions.")

        return cls(
            id=listing_id,
            matched_item=matched_item,
            confidence=confidence,
            specs_matched=specs_matched,
            issues=issues,
            freebies=() if data["is_bundle"] else freebies,
            downgrade_condition=downgrade_condition,
            is_accessory=is_accessory,
            is_bundle=data["is_bundle"],
            individual_price=float(individual_price) if individual_price is not None else None,
            separately_available=data["separately_available"],
            price_evidence=price_evidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfirmedDeal:
    """An accepted deal meeting all price and verification criteria.

    CRITICAL ARCHITECTURAL CONTRACT:
    Gemini confidence (semantic verification 0-100) and RapidFuzz score
    (lexical token similarity 0.0-100.0) MUST NOT be conflated.
    They are stored in distinct fields, validated through distinct acceptance
    gates, and tagged with an explicit audit_source.
    """

    listing_id: str
    title: str
    carousell_price: float
    matched_item: str
    deal_price: float
    savings: float
    link: str = ""
    seller: str = ""
    category: str = ""
    original_condition: str = ""
    final_condition: str = ""
    condition_overridden: bool = False
    bundles: tuple[str, ...] = ()
    freebies: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    retail_price: float | None = None
    thumbnail_url: str | None = None
    seller_rating: float | None = None
    seller_rating_count: int | None = None
    like_count: int | None = None
    location: str | None = None
    listing_timestamp: str | None = None
    price_flag: str = "Normal"

    # Provenance & Acceptance Tracking (STRICT SEPARATION)
    audit_source: AuditSource = "gemini"
    gemini_confidence: int | None = None  # 0 to 100, ONLY populated when audit_source == "gemini"
    specs_matched: bool | None = None  # ONLY populated when audit_source == "gemini"
    local_match_score: float | None = None  # 0.0 to 100.0 (RapidFuzz), populated for local matcher
    acceptance_reason: str = ""

    def __post_init__(self) -> None:
        # Harmonize legacy bundles and audit freebies
        if self.bundles and not self.freebies:
            object.__setattr__(self, "freebies", self.bundles)
        elif self.freebies and not self.bundles:
            object.__setattr__(self, "bundles", self.freebies)

        if self.audit_source == "gemini":
            if self.gemini_confidence is None or self.specs_matched is None:
                raise ValueError("Gemini-audited deal must define gemini_confidence and specs_matched.")
            if not (0 <= self.gemini_confidence <= 100):
                raise ValueError(f"gemini_confidence {self.gemini_confidence} out of range [0, 100].")
        elif self.audit_source == "local_fallback":
            if self.local_match_score is None:
                raise ValueError("Local-fallback deal must define local_match_score (RapidFuzz).")
            if not (0.0 <= self.local_match_score <= 100.0):
                raise ValueError(f"local_match_score {self.local_match_score} out of range [0.0, 100.0].")

    @property
    def formatted_badge(self) -> str:
        """Return unambiguous display badge for UI and Google Sheets."""
        if self.audit_source == "gemini":
            status = "Specs Matched" if self.specs_matched else "Specs Warning"
            return f"Gemini {self.gemini_confidence}% ({status})"
        return f"Local Match {self.local_match_score:.1f}% (Lexical)"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ConfirmedDeal:
        audit_source: AuditSource = data.get("audit_source", "gemini")
        raw_freebies = data.get("freebies") or data.get("bundles") or ()
        if isinstance(raw_freebies, str):
            freebies = tuple(b.strip() for b in raw_freebies.split(",") if b.strip())
        else:
            freebies = tuple(str(b).strip() for b in raw_freebies if str(b).strip())

        issues_raw = data.get("issues", ())
        if isinstance(issues_raw, str):
            issues = tuple(i.strip() for i in issues_raw.split(",") if i.strip())
        else:
            issues = tuple(str(i).strip() for i in issues_raw if str(i).strip())

        return cls(
            listing_id=_clean_str(data.get("listing_id") or data.get("id")),
            title=_clean_str(data.get("title")),
            carousell_price=float(data["price"] if "price" in data else data["carousell_price"]),
            matched_item=_clean_str(data.get("matched_item")),
            deal_price=float(data.get("deal_price", 0.0)),
            savings=float(data.get("savings", 0.0)),
            link=str(data.get("link", "")).strip(),
            seller=_clean_str(data.get("seller")),
            category=_clean_str(data.get("category") or data.get("reference_category")),
            original_condition=_clean_str(data.get("original_condition") or data.get("condition")),
            final_condition=_clean_str(data.get("final_condition") or data.get("condition")),
            condition_overridden=bool(data.get("condition_overridden", False)),
            bundles=freebies,
            freebies=freebies,
            issues=issues,
            retail_price=float(data["retail_price"]) if data.get("retail_price") is not None else None,
            thumbnail_url=data.get("thumbnail_url"),
            seller_rating=float(data["seller_rating"]) if data.get("seller_rating") is not None else None,
            seller_rating_count=int(data["seller_rating_count"]) if data.get("seller_rating_count") is not None else None,
            like_count=int(data["like_count"]) if data.get("like_count") is not None else None,
            location=data.get("location"),
            listing_timestamp=data.get("listing_timestamp"),
            price_flag=_clean_str(data.get("price_flag") or data.get("price_status") or "Normal"),
            audit_source=audit_source,
            gemini_confidence=int(data["gemini_confidence"]) if data.get("gemini_confidence") is not None else None,
            specs_matched=bool(data["specs_matched"]) if data.get("specs_matched") is not None else None,
            local_match_score=float(data["local_match_score"]) if data.get("local_match_score") is not None else None,
            acceptance_reason=str(data.get("acceptance_reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["match_score"] = self.formatted_badge
        d["price"] = self.carousell_price
        d["id"] = self.listing_id
        return d


def is_acceptable_gemini_deal(
    audit: AuditResult,
    listing_price: float,
    deal_price: float,
    min_confidence: int = 80,
) -> bool:
    """Acceptance gate for Gemini-audited listings."""
    if not math.isfinite(listing_price) or listing_price <= 0 or listing_price > deal_price:
        return False
    if not audit.matched_item:
        return False
    if not audit.specs_matched:
        return False
    if audit.is_accessory:
        return False
    return audit.confidence >= min_confidence


def is_acceptable_local_deal(
    local_score: float,
    listing_price: float,
    deal_price: float,
    variant_pass: bool = True,
    min_score: float = 60.0,
) -> bool:
    """Acceptance gate for local fallback listings."""
    if listing_price > deal_price:
        return False
    if not variant_pass:
        return False
    return local_score >= min_score


def validate_batch_audit_payload(
    payload: Any,
    expected_ids: set[str],
) -> tuple[list[AuditResult], list[str], set[str], set[str]]:
    """Validate and sanitize a raw Gemini batch audit JSON response.

    Returns:
        (valid_audits, errors, missing_ids, unknown_ids)
    """
    if not isinstance(payload, dict):
        return [], ["Payload is not a JSON object."], set(expected_ids), set()

    audits_list = payload.get("audits")
    if not isinstance(audits_list, list):
        return [], ["Payload missing 'audits' list."], set(expected_ids), set()

    valid_audits: list[AuditResult] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    unknown_ids: set[str] = set()

    for item in audits_list:
        if not isinstance(item, dict):
            errors.append(f"Invalid audit item (not a dict): {item}")
            continue

        raw_id = _clean_str(item.get("id"))
        if not raw_id:
            errors.append("Audit item missing 'id' field.")
            continue

        if raw_id not in expected_ids:
            unknown_ids.add(raw_id)
            continue

        if raw_id in seen_ids:
            errors.append(f"Duplicate audit entry for ID '{raw_id}'; ignoring duplicate.")
            continue

        try:
            audit = AuditResult.from_mapping(item)
            valid_audits.append(audit)
            seen_ids.add(raw_id)
        except (ValueError, TypeError) as exc:
            errors.append(f"Audit item '{raw_id}' validation failed: {exc}")

    missing_ids = expected_ids - seen_ids
    return valid_audits, errors, missing_ids, unknown_ids
