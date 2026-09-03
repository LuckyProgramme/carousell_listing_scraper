from deal_finder.deal_engine import evaluate_listing, extract_freebies, find_deals, override_condition


REFERENCE_ROWS = [
    {
        "Item Name": "PS5 Slim",
        "Category": "Video Gaming",
        "Deal Price (PHP)": 18000.0,
        "Keyword for Condition Downsizing": "issue, defect",
        "Keyword for Finding Freebies": "comes with, free, includes",
    },
    {
        "Item Name": "PS5 Slim Digital",
        "Category": "Video Gaming",
        "Deal Price (PHP)": 16000.0,
        "Keyword for Condition Downsizing": "issue, defect",
        "Keyword for Finding Freebies": "comes with, free, includes",
    },
]


def test_find_deals_matches_price_eligible_listing_and_enriches_it():
    listing = {
        "title": "PS5 Slim, complete set",
        "price": 17500.0,
        "condition": "Brand New",
        "description": "Comes with an extra controller, no issue at all.",
    }

    deal = evaluate_listing(listing, REFERENCE_ROWS)

    assert deal is not None
    assert deal["matched_item"] == "PS5 Slim"
    assert deal["savings"] == 500.0
    assert deal["final_condition"] == "Brand New"
    assert not deal["condition_overridden"]
    assert deal["bundles"] == ["an extra controller"]


def test_variant_filter_prevents_digital_listing_from_matching_base_ps5():
    listings = [{"title": "PS5 Slim Digital, mint", "price": 17000.0, "condition": "Like New", "description": ""}]

    assert find_deals(listings, REFERENCE_ROWS) == []


def test_non_negated_keyword_downgrades_but_negated_and_fixed_conditions_do_not():
    assert override_condition("Brand New", "There is a cosmetic issue.", "issue") == ("Lightly Used", True)
    assert override_condition("Brand New", "No issue at all.", "issue") == ("Brand New", False)
    assert override_condition("Well Used", "There is an issue.", "issue") == ("Well Used", False)


def test_freebie_extraction_is_targeted_deduplicated_and_short():
    description = "Includes a case and charger, free screen protector. Includes a case and charger."

    assert extract_freebies(description, "includes, free") == ["a case and charger", "screen protector"]
