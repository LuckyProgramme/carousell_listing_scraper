import pytest

from deal_finder.sheets_handler import (
    DEFAULT_PRICE_LIST_ROWS,
    PRICE_LIST_HEADERS,
    PriceListError,
    ensure_price_list_tab,
    read_price_list_rows,
)


class FakeWorksheet:
    def __init__(self, values=None):
        self.values = values or []

    def get_all_values(self):
        return self.values

    def update(self, *, range_name, values):
        if range_name == "A1":
            self.values = [[str(cell) for cell in row] for row in values]
        else:
            self.values.extend([[str(cell) for cell in row] for row in values])

    def append_rows(self, rows):
        self.values.extend([[str(cell) for cell in row] for row in rows])


class FakeSpreadsheet:
    def __init__(self, worksheet=None):
        self.price_list = worksheet

    def worksheet(self, _title):
        if self.price_list is None:
            from gspread.exceptions import WorksheetNotFound

            raise WorksheetNotFound("Price List")
        return self.price_list

    def add_worksheet(self, **_kwargs):
        self.price_list = FakeWorksheet()
        return self.price_list


def test_ensure_price_list_creates_and_seeds_missing_tab():
    spreadsheet = FakeSpreadsheet()

    worksheet = ensure_price_list_tab(spreadsheet)

    assert worksheet.values[0] == list(PRICE_LIST_HEADERS)
    assert len(worksheet.values) == len(DEFAULT_PRICE_LIST_ROWS) + 1


def test_ensure_price_list_seeds_an_empty_existing_tab_without_overwriting_headers():
    worksheet = FakeWorksheet([list(PRICE_LIST_HEADERS)])

    ensure_price_list_tab(FakeSpreadsheet(worksheet))

    assert worksheet.values[1] == [str(cell) for cell in DEFAULT_PRICE_LIST_ROWS[0]]


def test_read_price_list_rows_normalizes_prices_and_preserves_existing_data():
    worksheet = FakeWorksheet(
        [
            list(PRICE_LIST_HEADERS),
            ["PS5 Slim", "Video Gaming", "PHP 30,000", "18,000", "issue", "includes", "disc"],
        ]
    )

    rows = read_price_list_rows(FakeSpreadsheet(worksheet))

    assert rows == [
        {
            "Item Name": "PS5 Slim",
            "Category": "Video Gaming",
            "Retail Price (PHP)": 30000.0,
            "Deal Price (PHP)": 18000.0,
            "Keyword for Condition Downsizing": "issue",
            "Keyword for Finding Freebies": "includes",
            "Notes": "disc",
        }
    ]
    assert len(worksheet.values) == 2


def test_invalid_existing_headers_are_not_overwritten():
    worksheet = FakeWorksheet([["Item", "Target Price"]])

    with pytest.raises(PriceListError, match="Could not find the required header row"):
        ensure_price_list_tab(FakeSpreadsheet(worksheet))


def test_reader_finds_the_price_list_table_below_a_dashboard_header():
    worksheet = FakeWorksheet(
        [
            ["", "Deal Hunter & Bargain Tracker"],
            ["", ""],
            [
                "",
                "Item Name",
                "Category",
                "Retail Price (PHP)",
                "Deal Price (PHP)",
                "Savings (PHP)",
                "Discount %",
                "Keyword for Condition Downsizing",
                "Keyword for Finding Freebies",
                "Notes",
            ],
            ["", "Nintendo Switch", "video-gaming", "PHP 12,000", "PHP 6,000", "", "", "issue", "includes", ""],
        ]
    )

    rows = read_price_list_rows(FakeSpreadsheet(worksheet))

    assert rows[0]["Item Name"] == "Nintendo Switch"
    assert rows[0]["Deal Price (PHP)"] == 6000.0
