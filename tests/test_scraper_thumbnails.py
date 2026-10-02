import json

from deal_finder.scraper import extract_from_html_fallback, extract_from_json_blob


def test_structured_listing_extracts_thumbnail_url():
    payload = {
        "SearchListing": {
            "listingCards": [
                {
                    "id": "123",
                    "title": "PS5 Slim",
                    "price": 18000,
                    "thumbnail": {"url": "https://media.example.com/ps5.jpg"},
                }
            ]
        }
    }
    html = f"<script type='application/json'>{json.dumps(payload)}</script>"

    listings = extract_from_json_blob(html)

    assert listings[0]["thumbnail_url"] == "https://media.example.com/ps5.jpg"


def test_html_fallback_extracts_thumbnail_url():
    html = """
    <article data-testid="listing-card-123" data-listing-id="123">
      <a href="/p/ps5-slim-123"><h2>PS5 Slim</h2></a>
      <span data-testid="listing-price">PHP 18,000</span>
      <img src="https://media.example.com/ps5.jpg" alt="PS5 Slim">
    </article>
    """

    listings = extract_from_html_fallback(html)

    assert listings[0]["thumbnail_url"] == "https://media.example.com/ps5.jpg"
