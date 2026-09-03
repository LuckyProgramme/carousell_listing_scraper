import json
import os

import pytest

from deal_finder.config import CATEGORY_URL
from deal_finder.scraper import (
    ScraperStructureError,
    extract_from_html_fallback,
    extract_from_json_blob,
    normalize_price,
    scrape_all_categories,
    scrape_category,
)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, text):
        self.text = text

    def get(self, *_args, **_kwargs):
        return FakeResponse(self.text)


def _json_page(cards):
    payload = {"pageProps": {"SearchListing": {"listingCards": cards}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'


def test_json_blob_extraction_reads_below_fold_condition_and_normalizes_price():
    page = _json_page(
        [
            {
                "id": "123",
                "title": "Nintendo Switch OLED",
                "price": {"formattedAmount": "PHP 15,000"},
                "url": "/p/nintendo-switch-oled-123/",
                "seller": {"username": "switch_seller"},
                "belowFold": {
                    "description": "Complete with box.",
                    "attributes": [{"label": "Condition", "value": "Like new"}],
                },
            }
        ]
    )

    assert extract_from_json_blob(page) == [
        {
            "id": "123",
            "title": "Nintendo Switch OLED",
            "price": 15000.0,
            "condition": "Like New",
            "description": "Complete with box.",
            "link": "https://www.carousell.ph/p/nintendo-switch-oled-123/",
            "seller": "switch_seller",
        }
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("PHP 15,000", 15000.0), ("₱ 999.50", 999.5), ("12,345", 12345.0), ("Contact for price", None)],
)
def test_normalize_price(raw, expected):
    assert normalize_price(raw) == expected


def test_html_fallback_returns_48_listings_with_conditions():
    cards = "".join(
        f'''<article data-testid="listing-card-{number}" data-listing-id="{number}">
              <a href="/p/item-{number}-{number}/"><h3 data-testid="listing-card-title">Item {number}</h3></a>
              <span data-testid="listing-card-price">PHP {number:,}</span>
              <span data-testid="listing-card-condition">Lightly used</span>
              <span data-testid="listing-card-seller">Seller {number}</span>
            </article>'''
        for number in range(1, 49)
    )

    listings = extract_from_html_fallback(f"<main>{cards}</main>")

    assert len(listings) == 48
    assert all(listing["condition"] == "Lightly Used" for listing in listings)
    assert listings[0]["price"] == 1.0
    assert listings[-1]["link"].endswith("/p/item-48-48/")


def test_scrape_category_uses_html_when_json_has_no_listing_cards():
    html = '''<article data-testid="listing-card-1"><a href="/p/item-1/"><h3>Fallback item</h3></a>
    <span class="price">PHP 2,500</span><span class="condition">Brand new</span></article>'''
    listings = scrape_category("https://www.carousell.ph/categories/test", session=FakeSession(html))

    assert listings[0]["title"] == "Fallback item"
    assert listings[0]["condition"] == "Brand New"


def test_json_card_without_a_link_constructs_canonical_listing_url():
    listings = extract_from_json_blob(_json_page([{"id": "123", "title": "PS5 Slim", "price": "PHP 20,000"}]))

    assert listings[0]["link"] == "https://www.carousell.ph/p/ps5-slim-123/"


def test_scrape_category_raises_when_both_extraction_methods_are_empty():
    with pytest.raises(ScraperStructureError, match="Update needed for the structure"):
        scrape_category("https://www.carousell.ph/categories/test", session=FakeSession("<html></html>"))


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_CAROUSELL_TESTS") != "1",
    reason="Set RUN_LIVE_CAROUSELL_TESTS=1 to make live Carousell requests.",
)
def test_live_categories_return_about_48_listings_with_conditions():
    results = scrape_all_categories(delay_seconds=0)

    assert set(results) == set(CATEGORY_URL)
    for url, listings in results.items():
        assert 40 <= len(listings) <= 60, f"Unexpected listing count for {url}: {len(listings)}"
        assert all(listing["condition"] for listing in listings), f"Missing condition in {url}"
