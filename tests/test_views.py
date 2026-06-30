import json
from datetime import datetime

import pandas as pd
import pytest
from src import views


def _transactions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Дата операции": "2021-12-01 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": -1000,
                "Категория": "Супермаркеты",
                "Описание": "Магазин",
            },
            {
                "Дата операции": "2021-12-02 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": -100,
                "Категория": "Кафе",
                "Описание": "Кофейня",
            },
            {
                "Дата операции": "2021-12-03 10:00:00",
                "Номер карты": "*2222",
                "Статус": "OK",
                "Сумма платежа": -50,
                "Категория": "Транспорт",
                "Описание": "Такси",
            },
            {
                "Дата операции": "2021-12-04 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": 450,
                "Категория": "Бонусы",
                "Описание": "Кешбэк",
            },
            {
                "Дата операции": "2021-12-05 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": 900,
                "Категория": "Пополнения",
                "Описание": "Перевод",
            },
            {
                "Дата операции": "2021-12-06 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": 1000,
                "Категория": "Пополнения",
                "Описание": "Зарплата",
            },
            {
                "Дата операции": "2021-11-30 10:00:00",
                "Номер карты": "*3333",
                "Статус": "OK",
                "Сумма платежа": 99999,
                "Категория": "Пополнения",
                "Описание": "Прошлый месяц",
            },
            {
                "Дата операции": "2021-12-07 10:00:00",
                "Номер карты": "*4444",
                "Статус": "FAILED",
                "Сумма платежа": 88888,
                "Категория": "Пополнения",
                "Описание": "Неуспешная операция",
            },
        ]
    )


def _mock_market_data(monkeypatch) -> None:
    monkeypatch.setattr(
        views,
        "load_user_settings",
        lambda: {
            "user_currencies": ["USD", "EUR"],
            "user_stocks": ["AAPL", "MSFT"],
        },
    )

    monkeypatch.setattr(
        views,
        "get_currency_rates",
        lambda currencies: [
            {"currency": currency, "rate": 100.0}
            for currency in currencies
        ],
    )

    monkeypatch.setattr(
        views,
        "get_stock_prices",
        lambda stocks: [
            {"stock": stock, "price": 200.0}
            for stock in stocks
        ],
    )


def test_get_greeting_for_all_intervals():
    assert (
        views.get_greeting(datetime(2021, 1, 1, 6, 0))
        == "Доброе утро"
    )
    assert (
        views.get_greeting(datetime(2021, 1, 1, 12, 0))
        == "Добрый день"
    )
    assert (
        views.get_greeting(datetime(2021, 1, 1, 18, 0))
        == "Добрый вечер"
    )
    assert (
        views.get_greeting(datetime(2021, 1, 1, 23, 0))
        == "Доброй ночи"
    )


def test_home_page_returns_expected_data(monkeypatch):
    _mock_market_data(monkeypatch)

    response = json.loads(
        views.home_page(
            "2021-12-31 23:59:59",
            transactions=_transactions(),
        )
    )

    assert response["greeting"] == "Доброй ночи"

    assert response["currency_rates"] == [
        {"currency": "USD", "rate": 100.0},
        {"currency": "EUR", "rate": 100.0},
    ]

    assert response["stock_prices"] == [
        {"stock": "AAPL", "price": 200.0},
        {"stock": "MSFT", "price": 200.0},
    ]

    assert len(response["top_transactions"]) == 5

    amounts = [
        transaction["amount"]
        for transaction in response["top_transactions"]
    ]

    assert amounts == sorted(amounts, reverse=True)
    assert 99999 not in amounts
    assert 88888 not in amounts

    assert response["cards"] == [
        {
            "last_digits": "1111",
            "total_spent": 1100.0,
            "cashback": 11.0,
        },
        {
            "last_digits": "2222",
            "total_spent": 50.0,
            "cashback": 0.5,
        },
    ]


def test_events_page_groups_expenses_and_income(monkeypatch):
    _mock_market_data(monkeypatch)

    transactions = pd.DataFrame(
        [
            {
                "Дата операции": "2021-12-01 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": -1000.4,
                "Категория": "Супермаркеты",
                "Описание": "Магазин",
            },
            {
                "Дата операции": "2021-12-02 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": -200.2,
                "Категория": "Наличные",
                "Описание": "Снятие наличных",
            },
            {
                "Дата операции": "2021-12-03 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": -300.3,
                "Категория": "Переводы",
                "Описание": "Перевод",
            },
            {
                "Дата операции": "2021-12-04 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": 2500.6,
                "Категория": "Пополнения",
                "Описание": "Зарплата",
            },
            {
                "Дата операции": "2021-11-30 10:00:00",
                "Номер карты": "*1111",
                "Статус": "OK",
                "Сумма платежа": -9999,
                "Категория": "Прошлый месяц",
                "Описание": "Не учитывать",
            },
        ]
    )

    response = json.loads(
        views.events_page(
            "2021-12-31 23:59:59",
            transactions=transactions,
        )
    )

    assert response["expenses"]["total_amount"] == 1501

    assert response["expenses"]["main"] == [
        {
            "category": "Супермаркеты",
            "amount": 1000,
        }
    ]

    assert response["expenses"]["transfers_and_cash"] == [
        {
            "category": "Переводы",
            "amount": 300,
        },
        {
            "category": "Наличные",
            "amount": 200,
        },
    ]

    assert response["income"] == {
        "total_amount": 2501,
        "main": [
            {
                "category": "Пополнения",
                "amount": 2501,
            }
        ],
    }


def test_events_page_all_period_includes_previous_month(monkeypatch):
    _mock_market_data(monkeypatch)

    transactions = _transactions()

    response = json.loads(
        views.events_page(
            "2021-12-31 23:59:59",
            period="ALL",
            transactions=transactions,
        )
    )

    categories = [
        item["category"]
        for item in response["income"]["main"]
    ]

    assert "Пополнения" in categories


def test_events_page_rejects_unknown_period():
    with pytest.raises(ValueError):
        views.events_page(
            "2021-12-31 23:59:59",
            period="INVALID",
            transactions=pd.DataFrame(),
        )
