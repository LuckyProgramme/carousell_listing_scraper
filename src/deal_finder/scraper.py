"""Fetch and normalize category listings from Carousell."""

from __future__ import annotations

import html as html_lib
import json
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .config import CATEGORY_URL, HEADERS, REQUEST_DELAY_SECONDS


CAROUSELL_BASE_URL = "https://www.carousell.ph"
DEFAULT_TIMEOUT_SECONDS = 30
KNOWN_CONDITIONS = {
    "brand new",
    "like new",
    "lightly used",
    "well used",
    "heavily used",
}


class ScraperStructureError(RuntimeError):
    """Raised when neither structured JSON nor HTML contains listing cards."""


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


def extract_from_json_blob(page_html: str, base_url: str = CAROUSELL_BASE_URL) -> list[dict[str, Any]]:
    """Extract ``SearchListing.listingCards`` cards from embedded JSON documents."""
    cards: list[Mapping[str, Any]] = []
    for document in _json_documents(page_html):
        for node in _walk(document):
            if isinstance(node, Mapping):
                listing_cards = node.get("listingCards") or node.get("listing_cards")
                if isinstance(listing_cards, list):
                    cards.extend(card for card in listing_cards if isinstance(card, Mapping))
    return _deduplicate(
        listing for card in cards if (listing := _normalise_card(card, base_url)) is not None
    )


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


def _fetch_html(url: str, session: requests.Session | None, timeout: float) -> str:
    client = session or requests.Session()
    response = client.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def scrape_category(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Fetch one category, preferring JSON extraction and falling back to HTML."""
    page_html = _fetch_html(url, session, timeout)
    listings = extract_from_json_blob(page_html, base_url=url)
    if not listings:
        listings = extract_from_html_fallback(page_html, base_url=url)
    if not listings:
        raise ScraperStructureError(
            "Failed to retrieve deals from Carousell. Update needed for the structure. "
            f"(URL: {url})"
        )
    return listings


def scrape_all_categories(
    urls: Sequence[str] = CATEGORY_URL,
    *,
    session: requests.Session | None = None,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
) -> dict[str, list[dict[str, Any]]]:
    """Scrape every configured category, preserving each URL as the result key."""
    results: dict[str, list[dict[str, Any]]] = {}
    for index, url in enumerate(urls):
        if index and delay_seconds:
            time.sleep(delay_seconds)
        results[url] = scrape_category(url, session=session)
    return results
