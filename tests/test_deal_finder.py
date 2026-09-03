from deal_finder import deal_finder
from deal_finder.scraper import ScraperStructureError


REFERENCE_ROWS = [
    {
        "Item Name": "Nintendo Switch",
        "Category": "video-gaming",
        "Deal Price (PHP)": 6000.0,
        "Keyword for Condition Downsizing": "issue",
        "Keyword for Finding Freebies": "includes",
    }
]


def test_end_to_end_pipeline_flattens_matches_and_writes_without_live_services():
    written = {}

    def scrape_categories():
        return {
            "https://www.carousell.ph/categories/video-gaming-884/?sort_by=3": [
                {
                    "id": "123",
                    "title": "Nintendo Switch OLED bundle",
                    "price": 5500.0,
                    "condition": "Like New",
                    "description": "Includes a case.",
                    "link": "https://www.carousell.ph/p/switch-123/",
                    "seller": "seller_a",
                }
            ]
        }

    def write_results(deals, listings):
        written["deals"] = deals
        written["listings"] = listings
        return {"current_deals": len(deals), "all_listings": len(listings), "history_appended": 1, "history_updated": 0}

    summary = deal_finder.run_pipeline(
        scrape_categories=scrape_categories,
        read_price_list=lambda: REFERENCE_ROWS,
        write_results=write_results,
    )

    assert summary == {
        "scraped": 1,
        "deals": 1,
        "current_deals": 1,
        "all_listings": 1,
        "history_appended": 1,
        "history_updated": 0,
    }
    assert written["listings"][0]["category"] == "video-gaming"
    assert written["deals"][0]["matched_item"] == "Nintendo Switch"


def test_structure_failure_stops_pipeline_before_price_or_sheet_work():
    called = {"price_list": False, "writer": False}

    def fail_scrape():
        raise ScraperStructureError("Carousell layout changed")

    def read_price_list():
        called["price_list"] = True
        return []

    def write_results(_deals, _listings):
        called["writer"] = True
        return {}

    try:
        deal_finder.run_pipeline(
            scrape_categories=fail_scrape,
            read_price_list=read_price_list,
            write_results=write_results,
        )
    except ScraperStructureError:
        pass
    else:
        raise AssertionError("ScraperStructureError should propagate to main().")

    assert called == {"price_list": False, "writer": False}


def test_main_returns_nonzero_and_reports_structure_failure(monkeypatch, capsys):
    monkeypatch.setattr(deal_finder, "configure_logging", lambda: None)

    def fail_pipeline():
        raise ScraperStructureError("layout changed")

    monkeypatch.setattr(deal_finder, "run_pipeline", fail_pipeline)

    assert deal_finder.main() == 1
    assert "Scrape stopped safely: layout changed" in capsys.readouterr().err
