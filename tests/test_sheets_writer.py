from deal_finder.sheets_writer import (
    ALL_LISTINGS_HEADERS,
    CURRENT_DEALS_HEADERS,
    HISTORY_HEADERS,
    get_listing_id,
    write_outputs,
)


class FakeWorksheet:
    def __init__(self, values=None):
        self.values = values or []

    def get_all_values(self):
        return self.values

    def clear(self):
        self.values = []

    def update(self, *, range_name, values):
        assert range_name == "A1"
        self.values = [list(row) for row in values]

    def append_rows(self, rows):
        self.values.extend([list(row) for row in rows])

    def update_cell(self, row, column, value):
        self.values[row - 1][column - 1] = value


class FakeSpreadsheet:
    def __init__(self):
        self.tabs = {}

    def worksheet(self, title):
        if title not in self.tabs:
            from gspread.exceptions import WorksheetNotFound

            raise WorksheetNotFound(title)
        return self.tabs[title]

    def add_worksheet(self, *, title, rows, cols):
        assert int(rows) >= 100
        self.tabs[title] = FakeWorksheet()
        return self.tabs[title]


DEAL = {
    "id": "123456",
    "matched_item": "Nintendo Switch",
    "title": "Nintendo Switch OLED bundle",
    "price": 5500.0,
    "deal_price": 6000.0,
    "savings": 500.0,
    "final_condition": "Like New",
    "bundles": ["case", "charger"],
    "reference_category": "video-gaming",
    "link": "https://www.carousell.ph/p/nintendo-switch-123456/",
    "seller": "seller_a",
    "match_score": 95.0,
}
LISTING = {
    "id": "123456",
    "title": "Nintendo Switch OLED bundle",
    "price": 5500.0,
    "condition": "Like New",
    "description": "Includes a case and charger.",
    "seller": "seller_a",
    "category": "video-gaming",
    "link": "https://www.carousell.ph/p/nintendo-switch-123456/",
}


def test_write_outputs_populates_all_three_tabs():
    spreadsheet = FakeSpreadsheet()

    result = write_outputs([DEAL], [LISTING], spreadsheet, seen_date="2026-09-03")

    assert result == {
        "current_deals": 1,
        "all_listings": 1,
        "history_appended": 1,
        "history_updated": 0,
    }
    assert spreadsheet.tabs["Current Deals"].values[0] == list(CURRENT_DEALS_HEADERS)
    assert spreadsheet.tabs["All Listings"].values[0] == list(ALL_LISTINGS_HEADERS)
    assert spreadsheet.tabs["History"].values[0] == list(HISTORY_HEADERS)
    assert spreadsheet.tabs["History"].values[1][-2:] == ["2026-09-03", "2026-09-03"]
    assert spreadsheet.tabs["Current Deals"].values[1][6] == "case, charger"


def test_repeat_run_overwrites_current_tabs_but_deduplicates_history():
    spreadsheet = FakeSpreadsheet()
    write_outputs([DEAL], [LISTING], spreadsheet, seen_date="2026-09-03")

    result = write_outputs([], [], spreadsheet, seen_date="2026-09-04")

    assert result["history_appended"] == 0
    assert result["history_updated"] == 0
    assert spreadsheet.tabs["Current Deals"].values == [list(CURRENT_DEALS_HEADERS)]
    assert spreadsheet.tabs["All Listings"].values == [list(ALL_LISTINGS_HEADERS)]

    result = write_outputs([DEAL], [LISTING], spreadsheet, seen_date="2026-09-04")

    assert result["history_appended"] == 0
    assert result["history_updated"] == 1
    assert len(spreadsheet.tabs["History"].values) == 2
    assert spreadsheet.tabs["History"].values[1][-2:] == ["2026-09-03", "2026-09-04"]


def test_listing_id_falls_back_to_the_carousell_url_suffix():
    assert get_listing_id({"link": "https://www.carousell.ph/p/example-987654/"}) == "987654"


def test_history_with_only_empty_formatted_cells_is_initialized():
    spreadsheet = FakeSpreadsheet()
    spreadsheet.tabs["History"] = FakeWorksheet([[]])

    write_outputs([DEAL], [LISTING], spreadsheet, seen_date="2026-09-03")

    assert spreadsheet.tabs["History"].values[0] == list(HISTORY_HEADERS)
