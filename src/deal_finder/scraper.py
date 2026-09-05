"""Plan, fetch, and normalize category or item-name searches from Carousell."""

from __future__ import annotations

import html as html_lib
import json
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

from .config import CATEGORY_URL, CATEGORY_URLS_BY_NAME, HEADERS, REQUEST_DELAY_SECONDS
from .models import parse_bundle_check
from .candidate_filter import BUNDLE_PRICE_MULTIPLIER


CAROUSELL_BASE_URL = "https://www.carousell.ph"
ITEM_SEARCH_QUERY_SOURCE = "ss_dropdown"
ITEM_NAME_RESULT_LIMIT = 20
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
KNOWN_CONDITIONS = {
    "brand new",
    "like new",
    "lightly used",
    "well used",
    "heavily used",
}


class ScraperError(RuntimeError):
    """Base error for safely aborted Carousell scraping runs."""


class ScraperStructureError(ScraperError):
    """Raised when neither structured JSON nor HTML contains listing cards."""


class ScraperRequestError(ScraperError):
    """Raised when a Carousell source cannot be fetched successfully."""


class ScrapePlanError(ScraperError):
    """Raised when Price List rows cannot produce a safe scrape plan."""


@dataclass(frozen=True)
class ScrapeSource:
    """One deduplicated Carousell source and the targets eligible for its listings."""

    mode: str
    url: str
    target_items: tuple[str, ...]
    category: str = ""
    query: str = ""
    fetch_bundle_descriptions: bool = False
    bundle_price_ceiling: float | None = None


@dataclass(frozen=True)
class ScrapeSourceSummary:
    """PII-safe request diagnostics for audit reports."""

    mode: str
    url: str
    target_items: tuple[str, ...]
    category: str
    query: str
    http_status: int
    attempts: int
    listing_count: int
    fetched_listing_count: int
    retained_listing_count: int
    duplicates_removed: int
    description_requests: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScrapeBatchResult:
    """Deduplicated listings and diagnostics from a complete scrape plan."""

    listings: tuple[dict[str, Any], ...]
    source_summaries: tuple[ScrapeSourceSummary, ...]


def _normalise_cell(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def build_item_search_url(item_name: str) -> str:
    """Build Carousell's recent-first item-name search URL."""
    query = _normalise_cell(item_name)
    if not query:
        raise ValueError("Item Name search requires a non-empty Item Name.")
    encoded_query = quote(query.lower(), safe="")
    return (
        f"{CAROUSELL_BASE_URL}/search/{encoded_query}"
        f"?sort_by=3&t-search_query_source={ITEM_SEARCH_QUERY_SOURCE}"
    )


def _category_config(category: str) -> tuple[str, str] | None:
    normalized = _normalise_cell(category).casefold()
    for canonical, url in CATEGORY_URLS_BY_NAME.items():
        category_slug = url.split("/categories/", 1)[-1].split("/", 1)[0]
        accepted_names = {
            canonical.casefold(),
            canonical.replace("&", "and").casefold(),
            category_slug.rsplit("-", 1)[0].casefold(),
        }
        if normalized in accepted_names:
            return canonical, url
    return None


def build_scrape_sources(reference_rows: Sequence[Mapping[str, Any]]) -> tuple[ScrapeSource, ...]:
    """Validate Price List search modes and collapse repeated source URLs."""
    sources: dict[str, dict[str, Any]] = {}
    seen_item_names: set[str] = set()
    valid_modes = {"category": "Category", "item name": "Item Name"}

    for row_number, row in enumerate(reference_rows, start=2):
        item_name = _normalise_cell(row.get("Item Name") or row.get("item_name"))
        if not item_name:
            continue
        item_key = item_name.casefold()
        if item_key in seen_item_names:
            raise ScrapePlanError(
                f"Duplicate Item Name '{item_name}' in Price List row {row_number}."
            )
        seen_item_names.add(item_key)

        raw_mode = _normalise_cell(row.get("Search Mode") or row.get("search_mode"))
        mode_key = raw_mode.casefold() or "category"
        mode = valid_modes.get(mode_key)
        if mode is None:
            raise ScrapePlanError(
                f"Invalid Search Mode '{raw_mode}' for '{item_name}'. "
                "Allowed values are Category and Item Name."
            )

        if mode == "Category":
            raw_category = _normalise_cell(row.get("Category") or row.get("category"))
            configured = _category_config(raw_category)
            if configured is None:
                allowed = ", ".join(CATEGORY_URLS_BY_NAME)
                raise ScrapePlanError(
                    f"Unknown Category '{raw_category}' for '{item_name}'. "
                    f"Allowed categories are: {allowed}."
                )
            category, url = configured
            query = ""
        else:
            category = ""
            query = item_name
            url = build_item_search_url(item_name)

        source = sources.setdefault(
            url,
            {"mode": mode, "url": url, "target_items": [], "category": category, "query": query},
        )
        source["target_items"].append(item_name)
        try:
            allow_bundle_check = parse_bundle_check(row.get("Allow Bundle Check", row.get("allow_bundle_check")))
            if allow_bundle_check:
                ceiling = float(row.get("Deal Price (PHP)", row.get("deal_price", 0))) * BUNDLE_PRICE_MULTIPLIER
                source["fetch_bundle_descriptions"] = True
                source["bundle_price_ceiling"] = max(source.get("bundle_price_ceiling", 0), ceiling)
        except (TypeError, ValueError) as exc:
            raise ScrapePlanError(f"Invalid bundle settings for '{item_name}': {exc}") from exc

    return tuple(
        ScrapeSource(
            mode=source["mode"],
            url=source["url"],
            target_items=tuple(source["target_items"]),
            category=source["category"],
            query=source["query"],
            fetch_bundle_descriptions=source.get("fetch_bundle_descriptions", False),
            bundle_price_ceiling=source.get("bundle_price_ceiling"),
        )
        for source in sources.values()
    )


def normalize_price(value: Any) -> float | None:
    """Convert a displayed PHP price (for example ``PHP 15,000``) to a float."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Mapping):
        for key in ("amount", "value", "price", "formattedAmount", "formatted"):
            if key in value:
                price = normalize_price(value[key])
                if price is not None:
                    return price
        return None

    text = html_lib.unescape(str(value)).replace("\u00a0", " ").strip()
    match = re.search(
        r"(?:PHP|₱)?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    return float(match.group(1).replace(",", "")) if match else None


def _first_string(mapping: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _walk(value: Any) -> Iterable[Any]:
    """Yield nested values without assuming a stable JSON document shape."""
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            yield from _walk(child)


def _condition_from(value: Any) -> str:
    if isinstance(value, str):
        condition = " ".join(value.split()).lower()
        return condition.title() if condition in KNOWN_CONDITIONS else ""
    if isinstance(value, Mapping):
        direct = _first_string(value, ("condition", "conditionName", "itemCondition", "value"))
        condition = _condition_from(direct)
        if condition:
            return condition
        label = _first_string(value, ("label", "title", "name", "key")).lower()
        if "condition" in label:
            for key in ("value", "text", "content", "description", "displayValue"):
                condition = _condition_from(value.get(key))
                if condition:
                    return condition
        for child in value.values():
            condition = _condition_from(child)
            if condition:
                return condition
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            condition = _condition_from(child)
            if condition:
                return condition
    return ""


def _condition_from_below_fold(card: Mapping[str, Any]) -> str:
    """Extract the condition from the card's ``belowFold`` structured data."""
    for key in ("belowFold", "below_fold", "belowTheFold"):
        if key in card:
            condition = _condition_from(card[key])
            if condition:
                return condition
    return _condition_from({key: card.get(key) for key in ("condition", "conditionName", "itemCondition")})


def _description_from(card: Mapping[str, Any]) -> str:
    for key in ("description", "summary", "details"):
        value = card.get(key)
        if isinstance(value, str):
            return value.strip()
    for key in ("belowFold", "below_fold", "belowTheFold"):
        below_fold = card.get(key)
        if isinstance(below_fold, Mapping):
            description = _first_string(below_fold, ("description", "details", "summary"))
            if description:
                return description
    return ""


def _price_from(card: Mapping[str, Any]) -> float | None:
    for key in ("price", "displayPrice", "formattedPrice", "priceFormatted", "amount"):
        price = normalize_price(card.get(key))
        if price is not None:
            return price
    return None


def _seller_from(card: Mapping[str, Any]) -> str:
    direct = _first_string(card, ("sellerName", "sellerUsername", "username", "seller"))
    if direct:
        return direct
    for key in ("seller", "user", "profile"):
        nested = card.get(key)
        if isinstance(nested, Mapping):
            seller = _first_string(nested, ("username", "name", "displayName", "display_name"))
            if seller:
                return seller
    return ""


def _listing_link(title: str, listing_id: str, raw_link: str, base_url: str) -> str:
    """Return the supplied link, or construct Carousell's canonical title-ID URL."""
    if raw_link:
        return urljoin(base_url, raw_link)
    if not listing_id:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{CAROUSELL_BASE_URL}/p/{slug}-{listing_id}/" if slug else ""


def _normalise_card(card: Mapping[str, Any], base_url: str) -> dict[str, Any] | None:
    title = _first_string(card, ("title", "name", "listingTitle"))
    if not title:
        return None
    listing_id = _first_string(card, ("id", "listingId", "listingID", "listing_id"))
    raw_link = _first_string(card, ("url", "listingUrl", "listing_url", "urlPath", "path", "href"))
    return {
        "id": listing_id,
        "title": title,
        "price": _price_from(card),
        "condition": _condition_from_below_fold(card),
        "description": _description_from(card),
        "link": _listing_link(title, listing_id, raw_link, base_url),
        "seller": _seller_from(card),
    }


def _deduplicate(listings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for listing in listings:
        key = (str(listing["id"]), str(listing["link"]), str(listing["title"]))
        if key not in seen:
            seen.add(key)
            unique.append(listing)
    return unique


def _json_documents(page_html: str) -> Iterable[Any]:
    soup = BeautifulSoup(page_html, "html.parser")
    for script in soup.find_all("script"):
        raw = (script.string or script.get_text()).strip()
        if not raw:
            continue
        try:
            yield json.loads(raw)
            continue
        except json.JSONDecodeError:
            pass

        # Supports assignments such as ``window.__INITIAL_STATE__ = {...};``.
        decoder = json.JSONDecoder()
        for match in re.finditer(r'(?:=|:|JSON\.parse\()\s*(\{|\")', raw):
            try:
                candidate, _ = decoder.raw_decode(raw[match.start(1) :])
                yield json.loads(candidate) if isinstance(candidate, str) else candidate
            except (json.JSONDecodeError, TypeError):
                continue


def _extract_structured_listings(
    page_html: str, base_url: str = CAROUSELL_BASE_URL
) -> tuple[bool, list[dict[str, Any]]]:
    """Return whether listingCards exists and all normalized cards found within it."""
    cards: list[Mapping[str, Any]] = []
    structure_found = False
    for document in _json_documents(page_html):
        for node in _walk(document):
            if isinstance(node, Mapping):
                if "listingCards" in node:
                    listing_cards = node["listingCards"]
                elif "listing_cards" in node:
                    listing_cards = node["listing_cards"]
                else:
                    continue
                if isinstance(listing_cards, list):
                    structure_found = True
                    cards.extend(card for card in listing_cards if isinstance(card, Mapping))
    return (
        structure_found,
        _deduplicate(
            listing
            for card in cards
            if (listing := _normalise_card(card, base_url)) is not None
        ),
    )


def extract_from_json_blob(page_html: str, base_url: str = CAROUSELL_BASE_URL) -> list[dict[str, Any]]:
    """Extract ``SearchListing.listingCards`` cards from embedded JSON documents."""
    _, listings = _extract_structured_listings(page_html, base_url)
    return listings


def _text_from(card: Tag, selectors: Sequence[str]) -> str:
    for selector in selectors:
        node = card.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return ""


def extract_from_html_fallback(page_html: str, base_url: str = CAROUSELL_BASE_URL) -> list[dict[str, Any]]:
    """Extract listing cards from rendered category HTML as a fallback."""
    soup = BeautifulSoup(page_html, "html.parser")
    cards = soup.select('[data-testid^="listing-card-"]')
    if not cards:
        cards = soup.select('[data-testid="listing-card"], [data-testid*="listing-card"]')

    listings: list[dict[str, Any]] = []
    for card in cards:
        title = _text_from(card, ('[data-testid*="title"]', "h1, h2, h3, h4", "a[title]"))
        if not title:
            continue
        link_node = card.select_one("a[href]")
        raw_link = link_node.get("href", "") if link_node else ""
        listings.append(
            {
                "id": card.get("data-listing-id", card.get("data-id", "")),
                "title": title,
                "price": normalize_price(_text_from(card, ('[data-testid*="price"]', ".price"))),
                "condition": _condition_from(_text_from(card, ('[data-testid*="condition"]', ".condition"))),
                "description": _text_from(card, ('[data-testid*="description"]', ".description")),
                "link": urljoin(base_url, raw_link) if raw_link else "",
                "seller": _text_from(card, ('[data-testid*="seller"]', ".seller")),
            }
        )
    return _deduplicate(listings)


def _fetch_html_with_metadata(
    url: str,
    session: requests.Session,
    timeout: float,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> tuple[str, int, int, str]:
    """Fetch one source with bounded retries and return response diagnostics."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_error: Exception | None = None
    last_status: int | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            status = int(getattr(response, "status_code", 200))
            last_status = status
            if 400 <= status < 500 and status != 429:
                raise ScraperRequestError(
                    f"Carousell returned permanent HTTP {status} for {url}."
                )
            if status == 429 or status >= 500:
                raise requests.HTTPError(f"retryable HTTP {status}", response=response)
            response.raise_for_status()
            return response.text, status, attempt, str(getattr(response, "url", url))
        except ScraperRequestError:
            raise
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            if retry_backoff_seconds:
                time.sleep(retry_backoff_seconds * (2 ** (attempt - 1)))

    status_text = f"HTTP {last_status}" if last_status is not None else "network error"
    raise ScraperRequestError(
        f"Carousell source failed after {max_attempts} attempt(s): {status_text} for {url}. "
        f"{last_error or ''}".strip()
    ) from last_error


def _fetch_html(url: str, session: requests.Session | None, timeout: float) -> str:
    if session is not None:
        return _fetch_html_with_metadata(url, session, timeout)[0]
    with requests.Session() as client:
        return _fetch_html_with_metadata(url, client, timeout)[0]


def _extract_page_listings(page_html: str, url: str) -> list[dict[str, Any]]:
    structure_found, listings = _extract_structured_listings(page_html, base_url=url)
    if listings:
        return listings
    html_listings = extract_from_html_fallback(page_html, base_url=url)
    if html_listings:
        return html_listings
    if structure_found:
        return []
    raise ScraperStructureError(
        "Failed to retrieve deals from Carousell. Update needed for the structure. "
        f"(URL: {url})"
    )


def scrape_category(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Fetch one category, preferring JSON extraction and falling back to HTML."""
    page_html = _fetch_html(url, session, timeout)
    return _extract_page_listings(page_html, url)


def scrape_all_categories(
    urls: Sequence[str] = CATEGORY_URL,
    *,
    session: requests.Session | None = None,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, list[dict[str, Any]]]:
    """Scrape every configured category using a single shared Session for connection pooling."""
    results: dict[str, list[dict[str, Any]]] = {}
    client = session or requests.Session()
    try:
        for index, url in enumerate(urls):
            if index and delay_seconds:
                time.sleep(delay_seconds)
            results[url] = scrape_category(url, session=client, timeout=timeout)
    finally:
        if session is None:
            client.close()
    return results


def _listing_identity(listing: Mapping[str, Any]) -> tuple[str, str]:
    listing_id = _normalise_cell(listing.get("id"))
    if listing_id:
        return ("id", listing_id)
    link = _normalise_cell(listing.get("link"))
    if link:
        return ("link", link)
    return ("title", _normalise_cell(listing.get("title")).casefold())


def _merge_source_listing(
    existing: dict[str, Any], incoming: Mapping[str, Any]
) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"eligible_target_names", "source_modes", "source_urls", "source_queries"}:
            current = list(merged.get(key, ()))
            for item in value or ():
                if item not in current:
                    current.append(item)
            merged[key] = tuple(current)
        elif not merged.get(key) and value:
            merged[key] = value
    return merged


def extract_listing_description(page_html: str, listing_id: str) -> str:
    """Read the primary listing description, never recommendation or condition text."""
    products: list[Mapping[str, Any]] = []
    for document in _json_documents(page_html):
        for node in _walk(document):
            if not isinstance(node, Mapping):
                continue
            if str(node.get("id", "")) == listing_id and isinstance(node.get("description"), str):
                return node["description"].strip()
            if node.get("@type") == "Product" and isinstance(node.get("description"), str):
                products.append(node)
    if len(products) == 1:
        return html_lib.unescape(str(products[0]["description"])).strip()
    raise ScraperStructureError(f"Listing {listing_id} has no recognized detail description structure.")


def scrape_sources(
    sources: Sequence[ScrapeSource],
    *,
    session: requests.Session | None = None,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> ScrapeBatchResult:
    """Fetch a validated hybrid scrape plan and merge duplicate listings."""
    client = session or requests.Session()
    merged_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    summaries: list[ScrapeSourceSummary] = []
    description_cache: dict[tuple[str, str], str] = {}
    try:
        for index, source in enumerate(sources):
            if index and delay_seconds:
                time.sleep(delay_seconds)
            page_html, status, attempts, final_url = _fetch_html_with_metadata(
                source.url,
                client,
                timeout,
                max_attempts=max_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
            )
            source_listings = _extract_page_listings(page_html, source.url)
            fetched_listing_count = len(source_listings)
            retained_listings = (
                source_listings[:ITEM_NAME_RESULT_LIMIT]
                if source.mode == "Item Name"
                else source_listings
            )
            duplicate_count = 0
            description_requests: list[dict[str, Any]] = []
            for raw_listing in retained_listings:
                listing = {
                    **dict(raw_listing),
                    "category": source.category,
                    "eligible_target_names": source.target_items,
                    "source_modes": (source.mode,),
                    "source_urls": (final_url,),
                    "source_queries": (source.query,) if source.query else (),
                }
                identity = _listing_identity(listing)
                if (
                    source.fetch_bundle_descriptions and not listing.get("description")
                    and (source.bundle_price_ceiling is None or listing.get("price") is None
                         or listing["price"] <= source.bundle_price_ceiling)
                ):
                    if identity not in description_cache:
                        detail_url = listing.get("link", "")
                        parsed_url = urlsplit(detail_url)
                        if (parsed_url.scheme != "https"
                            or parsed_url.hostname not in {"www.carousell.ph", "carousell.ph"}
                            or not parsed_url.path.startswith("/p/")):
                            raise ScraperStructureError("Cannot retrieve bundle description: invalid Carousell listing URL.")
                        if delay_seconds:
                            time.sleep(delay_seconds)
                        detail_html, detail_status, detail_attempts, detail_final_url = _fetch_html_with_metadata(
                            detail_url, client, timeout,
                            max_attempts=max_attempts,
                            retry_backoff_seconds=retry_backoff_seconds,
                        )
                        description_cache[identity] = extract_listing_description(detail_html, str(listing["id"]))
                        description_requests.append({
                            "listing_id": listing["id"], "url": detail_final_url,
                            "http_status": detail_status, "attempts": detail_attempts,
                            "description_available": bool(description_cache[identity]),
                        })
                    listing["description"] = description_cache[identity]
                previous = merged_by_identity.get(identity)
                if previous is None:
                    merged_by_identity[identity] = listing
                else:
                    duplicate_count += 1
                    merged_by_identity[identity] = _merge_source_listing(previous, listing)
            summaries.append(
                ScrapeSourceSummary(
                    mode=source.mode,
                    url=final_url,
                    target_items=source.target_items,
                    category=source.category,
                    query=source.query,
                    http_status=status,
                    attempts=attempts,
                    listing_count=len(retained_listings),
                    fetched_listing_count=fetched_listing_count,
                    retained_listing_count=len(retained_listings),
                    duplicates_removed=duplicate_count,
                    description_requests=tuple(description_requests),
                )
            )
    finally:
        if session is None:
            client.close()

    return ScrapeBatchResult(
        listings=tuple(merged_by_identity.values()),
        source_summaries=tuple(summaries),
    )


def scrape_price_list_sources(
    reference_rows: Sequence[Mapping[str, Any]],
    **kwargs: Any,
) -> ScrapeBatchResult:
    """Build and execute the hybrid scrape plan for Price List rows."""
    return scrape_sources(build_scrape_sources(reference_rows), **kwargs)
