import json

import pandas as pd
import pytest

from src import reports


@pytest.fixture(autouse=True)
def isolate_report_files(monkeypatch, tmp_path):
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path)


@pytest.fixture
def transactions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Дата операции": "2021-08-30 10:00:00",
                "Статус": "OK",
                "Сумма платежа": -1000,
                "Категория": "Супермаркеты",
            },
            {
                "Дата операции": "2021-10-04 10:00:00",
                "Статус": "OK",
                "Сумма платежа": -100,
                "Категория": "Супермаркеты",
            },
            {
                "Дата операции": "2021-10-09 10:00:00",
                "Статус": "OK",
                "Сумма платежа": -500,
                "Категория": "Кафе",
            },
            {
                "Дата операции": "2021-10-11 10:00:00",
                "Статус": "OK",
                "Сумма платежа": -300,
                "Категория": "Супермаркеты",
            },
            {
                "Дата операции": "2021-12-20 10:00:00",
                "Статус": "OK",
                "Сумма платежа": -200,
                "Категория": "Супермаркеты",
            },
            {
                "Дата операции": "2021-12-21 10:00:00",
                "Статус": "FAILED",
                "Сумма платежа": -10000,
                "Категория": "Супермаркеты",
            },
            {
                "Дата операции": "2021-12-22 10:00:00",
                "Статус": "OK",
                "Сумма платежа": 5000,
                "Категория": "Пополнения",
            },
        ]
    )


def test_spending_by_category_returns_expenses_for_three_months(
    transactions,
    tmp_path,
):
    result = reports.spending_by_category(
        transactions,
        "супермаркеты",
        "2021-12-31",
    )

    assert len(result) == 3

    assert result["Сумма платежа"].tolist() == [
        100,
        300,
        200,
    ]

    report_path = tmp_path / "spending_by_category.json"

    assert report_path.exists()

    saved_report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert len(saved_report) == 3


def test_spending_by_weekday_returns_average_expenses(
    transactions,
    tmp_path,
):
    result = reports.spending_by_weekday(
        transactions,
        "2021-12-31",
    )

    monday = result.loc[
        result["День недели"] == "Понедельник",
        "Средние траты",
    ].iloc[0]
    
    saturday = result.loc[
        result["День недели"] == "Суббота",
        "Средние траты",
    ].iloc[0]

    assert monday == 200
    assert saturday == 500

    report_files = list(
        tmp_path.glob("spending_by_weekday_*.json")
    )

    assert len(report_files) == 1


def test_spending_by_workday_returns_workday_and_weekend_averages(
    transactions,
):
    result = reports.spending_by_workday(
        transactions,
        "2021-12-31",
    )

    workday = result.loc[
        result["Тип дня"] == "Рабочий день",
        "Средние траты",
    ].iloc[0]

    weekend = result.loc[
        result["Тип дня"] == "Выходной день",
        "Средние траты",
    ].iloc[0]

    assert workday == 200
    assert weekend == 500


def test_spending_by_category_rejects_invalid_date(transactions):
    with pytest.raises(ValueError):
        reports.spending_by_category(
            transactions,
            "Супермаркеты",
            "31-12-2021",
        )