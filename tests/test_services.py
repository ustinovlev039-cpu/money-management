import json

import pandas as pd
import pytest

from src.services import (
    cashback_categories,
    investment_bank,
    search_person_transfers,
    search_phone_numbers,
    simple_search,
)


def test_cashback_categories_returns_monthly_cashback():
    transactions = pd.DataFrame(
        [
            {
                "Дата операции": "2021-12-01 10:00:00",
                "Статус": "OK",
                "Сумма операции": -2000,
                "Категория": "Супермаркеты",
            },
            {
                "Дата операции": "2021-12-02 10:00:00",
                "Статус": "OK",
                "Сумма операции": -600,
                "Категория": "Кафе",
            },
            {
                "Дата операции": "2021-12-03 10:00:00",
                "Статус": "OK",
                "Сумма операции": -100,
                "Категория": "Транспорт",
            },
            {
                "Дата операции": "2021-11-20 10:00:00",
                "Статус": "OK",
                "Сумма операции": -5000,
                "Категория": "Прошлый месяц",
            },
            {
                "Дата операции": "2021-12-04 10:00:00",
                "Статус": "FAILED",
                "Сумма операции": -9000,
                "Категория": "Не учитывать",
            },
            {
                "Дата операции": "2021-12-05 10:00:00",
                "Статус": "OK",
                "Сумма операции": 10000,
                "Категория": "Пополнения",
            },
        ]
    )

    result = json.loads(
        cashback_categories(transactions, 2021, 12)
    )

    assert result == {
        "Супермаркеты": 100.0,
        "Кафе": 30.0,
        "Транспорт": 5.0,
    }


def test_investment_bank_calculates_rounding_difference():
    transactions = [
        {
            "Дата операции": "2021-12-01",
            "Сумма операции": -1712,
        },
        {
            "Дата операции": "2021-12-05",
            "Сумма операции": -1,
        },
        {
            "Дата операции": "2021-12-10",
            "Сумма операции": -200,
        },
        {
            "Дата операции": "2021-12-12",
            "Сумма операции": 500,
        },
        {
            "Дата операции": "2022-01-01",
            "Сумма операции": -1000,
        },
    ]

    result = investment_bank(
        "2021-12",
        transactions,
        50,
    )

    assert result == 87.0


def test_investment_bank_rejects_invalid_limit():
    with pytest.raises(ValueError):
        investment_bank(
            "2021-12",
            [],
            25,
        )


def test_simple_search_is_case_insensitive():
    transactions = [
        {
            "Категория": "Различные товары",
            "Описание": "Ozon.ru",
        },
        {
            "Категория": "OZON Бонусы",
            "Описание": "Начисление",
        },
        {
            "Категория": "Супермаркеты",
            "Описание": "Лента",
        },
    ]

    result = json.loads(
        simple_search("oZoN", transactions)
    )

    assert len(result) == 2
    assert result[0]["Описание"] == "Ozon.ru"
    assert result[1]["Категория"] == "OZON Бонусы"


def test_search_phone_numbers_supports_different_formats():
    transactions = [
        {
            "Описание": "Я МТС +7 (900) 000-00-00",
        },
        {
            "Описание": "Тинькофф Мобайл 89000000000",
        },
        {
            "Описание": "Покупка в магазине",
        },
    ]

    result = json.loads(
        search_phone_numbers(transactions)
    )

    assert len(result) == 2


def test_search_person_transfers_returns_only_required_operations():
    transactions = [
        {
            "Категория": "Переводы",
            "Описание": "Валерий А.",
        },
        {
            "Категория": "Переводы",
            "Описание": "Сергей З.",
        },
        {
            "Категория": "Переводы",
            "Описание": "Перевод в банк",
        },
        {
            "Категория": "Супермаркеты",
            "Описание": "Артем П.",
        },
    ]

    result = json.loads(
        search_person_transfers(transactions)
    )

    assert len(result) == 2
    assert result[0]["Описание"] == "Валерий А."
    assert result[1]["Описание"] == "Сергей З."