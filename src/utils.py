from __future__ import annotations

import json
import logging
import os
import xml.etree.ElementTree as element_tree
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

OPERATIONS_PATH = DATA_DIR / "operations.xlsx"
SETTINGS_PATH = DATA_DIR / "user_settings.json"

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

DATE_COLUMN = "Дата операции"
CARD_COLUMN = "Номер карты"
STATUS_COLUMN = "Статус"
OPERATION_AMOUNT_COLUMN = "Сумма операции"
PAYMENT_AMOUNT_COLUMN = "Сумма платежа"
CATEGORY_COLUMN = "Категория"
DESCRIPTION_COLUMN = "Описание"

REQUIRED_COLUMNS = {
    DATE_COLUMN,
    CARD_COLUMN,
    STATUS_COLUMN,
    OPERATION_AMOUNT_COLUMN,
    PAYMENT_AMOUNT_COLUMN,
    CATEGORY_COLUMN,
    DESCRIPTION_COLUMN,
}

load_dotenv(PROJECT_ROOT / ".env")


def read_transactions(file_path: Path = OPERATIONS_PATH) -> pd.DataFrame:
    """
    Читает файл операций и приводит дату и суммы к корректным типам.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"Файл с операциями не найден: {file_path}"
        )

    transactions = pd.read_excel(file_path)

    missing_columns = REQUIRED_COLUMNS.difference(transactions.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"В Excel отсутствуют обязательные столбцы: {missing}"
        )

    transactions[DATE_COLUMN] = pd.to_datetime(
        transactions[DATE_COLUMN],
        dayfirst=True,
        errors="coerce",
    )

    transactions[OPERATION_AMOUNT_COLUMN] = pd.to_numeric(
        transactions[OPERATION_AMOUNT_COLUMN],
        errors="coerce",
    )

    transactions[PAYMENT_AMOUNT_COLUMN] = pd.to_numeric(
        transactions[PAYMENT_AMOUNT_COLUMN],
        errors="coerce",
    )

    invalid_dates = transactions[DATE_COLUMN].isna().sum()

    if invalid_dates:
        logger.warning(
            "Не удалось преобразовать дат: %s",
            invalid_dates,
        )

    logger.info(
        "Загружено операций из Excel: %s",
        len(transactions),
    )

    return transactions


def _normalize_codes(values: list[Any]) -> list[str]:
    """Очищает, приводит к верхнему регистру и убирает дубликаты."""

    normalized = [
        str(value).strip().upper()
        for value in values
        if value is not None and str(value).strip()
    ]

    return list(dict.fromkeys(normalized))


def load_user_settings(
    file_path: Path = SETTINGS_PATH,
) -> dict[str, list[str]]:
    """Загружает пользовательские настройки валют и акций."""

    default_settings = {
        "user_currencies": [],
        "user_stocks": [],
    }

    if not file_path.exists():
        logger.warning(
            "Файл пользовательских настроек не найден: %s",
            file_path,
        )
        return default_settings

    try:
        with file_path.open("r", encoding="utf-8") as file:
            raw_settings = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        logger.error(
            "Не удалось прочитать user_settings.json: %s",
            error,
        )
        return default_settings

    currencies = raw_settings.get("user_currencies", [])
    stocks = raw_settings.get("user_stocks", [])

    if not isinstance(currencies, list):
        logger.warning("user_currencies должен быть списком.")
        currencies = []

    if not isinstance(stocks, list):
        logger.warning("user_stocks должен быть списком.")
        stocks = []

    return {
        "user_currencies": _normalize_codes(currencies),
        "user_stocks": _normalize_codes(stocks),
    }


def get_currency_rates(
    currencies: list[str],
) -> list[dict[str, str | float]]:
    """
    Получает текущие курсы валют к рублю через API Банка России.
    """

    requested_currencies = _normalize_codes(currencies)

    if not requested_currencies:
        return []

    try:
        response = requests.get(CBR_DAILY_URL, timeout=10)
        response.raise_for_status()
        root = element_tree.fromstring(response.content)
    except (
        requests.RequestException,
        element_tree.ParseError,
    ) as error:
        logger.error(
            "Не удалось получить курсы валют: %s",
            error,
        )
        return []

    rates_by_currency: dict[str, float] = {}

    for valute in root.findall("Valute"):
        code = valute.findtext("CharCode")
        nominal_text = valute.findtext("Nominal")
        value_text = valute.findtext("Value")

        if not code or not nominal_text or not value_text:
            continue

        try:
            nominal = float(nominal_text)
            value = float(value_text.replace(",", "."))
        except ValueError:
            continue

        if nominal > 0 and value > 0:
            rates_by_currency[code] = round(value / nominal, 4)

    result = [
        {
            "currency": currency,
            "rate": float(rates_by_currency[currency]),
        }
        for currency in requested_currencies
        if currency in rates_by_currency
    ]

    missing_currencies = set(requested_currencies).difference(
        rates_by_currency
    )

    if missing_currencies:
        logger.warning(
            "Не найдены курсы валют: %s",
            ", ".join(sorted(missing_currencies)),
        )

    return result


def get_stock_prices(
    stocks: list[str],
) -> list[dict[str, str | float]]:
    """
    Получает стоимость акций через Alpha Vantage.

    При ошибке по одной акции остальные продолжают обрабатываться.
    """

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    requested_stocks = _normalize_codes(stocks)

    if not requested_stocks:
        return []

    if not api_key:
        logger.warning(
            "Не задан ALPHA_VANTAGE_API_KEY. "
            "Цены акций не будут загружены."
        )
        return []

    result: list[dict[str, str | float]] = []

    for stock in requested_stocks:
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": stock,
            "apikey": api_key,
        }

        try:
            response = requests.get(
                ALPHA_VANTAGE_URL,
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            payload = response.json()
            quote = payload.get("Global Quote", {})
            price = float(quote.get("05. price", 0))

            if price <= 0:
                raise ValueError("API вернул пустую или некорректную цену.")

        except (
            requests.RequestException,
            ValueError,
            TypeError,
        ) as error:
            logger.error(
                "Не удалось получить цену акции %s: %s",
                stock,
                error,
            )
            continue

        result.append(
            {
                "stock": stock,
                "price": round(price, 2),
            }
        )

    return result
