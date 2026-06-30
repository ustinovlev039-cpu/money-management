import json

from src.utils import (
    DATE_COLUMN,
    OPERATION_AMOUNT_COLUMN,
    load_user_settings,
    read_transactions,
)


def test_read_transactions_returns_dataframe():
    transactions = read_transactions()

    assert not transactions.empty
    assert DATE_COLUMN in transactions.columns
    assert OPERATION_AMOUNT_COLUMN in transactions.columns
    assert str(transactions[DATE_COLUMN].dtype).startswith("datetime")


def test_load_user_settings(tmp_path):
    settings_path = tmp_path / "user_settings.json"

    settings_path.write_text(
        json.dumps(
            {
                "user_currencies": ["usd", "EUR", "USD"],
                "user_stocks": ["aapl", "MSFT"],
            }
        ),
        encoding="utf-8",
    )

    settings = load_user_settings(settings_path)

    assert settings["user_currencies"] == ["USD", "EUR"]
    assert settings["user_stocks"] == ["AAPL", "MSFT"]


def test_load_user_settings_returns_empty_values_when_file_missing(
    tmp_path,
):
    settings = load_user_settings(
        tmp_path / "missing_user_settings.json"
    )

    assert settings == {
        "user_currencies": [],
        "user_stocks": [],
    }
