import pytest

from deal_finder.models import Evaluation, Listing, Target


def test_target_maps_canonical_and_scanner_fields():
    target = Target.from_mapping(
        {
            "id": "target-1",
            "owner_id": "owner-1",
            "item_name": "PS5 Slim",
            "category": "Video Gaming",
            "search_mode": "Category",
            "deal_price": 20000,
            "retail_price": 25000,
            "downsizing_keywords": ["scratch"],
            "enabled": True,
        }
    )

    assert target.item_name == "PS5 Slim"
    assert target.to_scanner_mapping()["Deal Price (PHP)"] == 20000
    assert target.to_scanner_mapping()["Search Mode"] == "Category"


@pytest.mark.parametrize("deal_price", [0, -1, float("inf")])
def test_target_rejects_invalid_price(deal_price):
    with pytest.raises(ValueError, match="deal_price"):
        Target(item_name="Console", category="Video Gaming", deal_price=deal_price)


def test_evaluation_rejects_out_of_range_confidence():
    with pytest.raises(ValueError, match="confidence"):
        Evaluation(
            listing_source_id="123",
            target_snapshot_id="11111111-1111-1111-1111-111111111111",
            accepted=False,
            target_snapshot={"id": "11111111-1111-1111-1111-111111111111"},
            confidence=101,
        )


def test_listing_drops_untrusted_links_but_keeps_https_thumbnail():
    listing = Listing.from_mapping(
        {
            "id": "1",
            "title": "Console",
            "price": 100,
            "link": "javascript:alert(1)",
            "thumbnail_url": "https://media.example.com/image.jpg",
        }
    )
    assert listing.link == ""
    assert listing.thumbnail_url == "https://media.example.com/image.jpg"
