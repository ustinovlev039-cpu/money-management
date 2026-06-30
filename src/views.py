from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from .utils import (
    CARD_COLUMN,
    CATEGORY_COLUMN,
    DATE_COLUMN,
    DESCRIPTION_COLUMN,
    PAYMENT_AMOUNT_COLUMN,
    STATUS_COLUMN,
    get_currency_rates,
    get_stock_prices,
    load_user_settings,
    read_transactions,
)


logger = logging.getLogger(__name__)


def _parse_datetime(value: str) -> datetime:
    """Преобразует строку даты в объект datetime."""

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y",
    )

    for date_format in formats:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue

    raise ValueError(
        "Дата должна быть в формате YYYY-MM-DD или "
        "YYYY-MM-DD HH:MM:SS."
    )


def get_greeting(current_date: datetime) -> str:
    """Возвращает приветствие по часу переданной даты."""

    hour = current_date.hour

    if 6 <= hour <= 11:
        return "Доброе утро"
    if 12 <= hour <= 17:
        return "Добрый день"
    if 18 <= hour <= 22:
        return "Добрый вечер"

    return "Доброй ночи"


def _to_transaction_datetime(value: Any) -> pd.Timestamp:
    """Преобразует дату операции или возвращает NaT при ошибке."""

    if pd.isna(value):
        return pd.NaT

    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value)

    try:
        return pd.Timestamp(_parse_datetime(str(value)))
    except ValueError:
        return pd.NaT


def _prepare_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Копирует и приводит даты и суммы к подходящим типам."""

    data = transactions.copy()

    data[DATE_COLUMN] = data[DATE_COLUMN].map(
        _to_transaction_datetime
    )
    data[PAYMENT_AMOUNT_COLUMN] = pd.to_numeric(
        data[PAYMENT_AMOUNT_COLUMN],
        errors="coerce",
    )

    return data.dropna(
        subset=[
            DATE_COLUMN,
            PAYMENT_AMOUNT_COLUMN,
        ]
    )


def _completed_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Оставляет только успешно выполненные операции."""

    status = transactions[STATUS_COLUMN].fillna("").astype(str)

    return transactions[status.eq("OK")].copy()


def _transactions_in_range(
    transactions: pd.DataFrame,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame:
    """Отбирает транзакции из заданного включительного диапазона."""

    return transactions.loc[
        (transactions[DATE_COLUMN] >= start_date)
        & (transactions[DATE_COLUMN] <= end_date)
    ].copy()


def _to_text(value: Any) -> str:
    """Безопасно приводит значение из DataFrame к строке."""

    if pd.isna(value):
        return ""

    return str(value)


def get_cards(transactions: pd.DataFrame) -> list[dict[str, str | float]]:
    """Формирует информацию о расходах и кешбэке по картам."""

    expenses = transactions[
        (transactions[PAYMENT_AMOUNT_COLUMN] < 0)
        & transactions[CARD_COLUMN].notna()
    ].copy()

    expenses = expenses[
        expenses[CARD_COLUMN].astype(str).str.strip().ne("")
    ]

    grouped = (
        expenses.groupby(CARD_COLUMN, as_index=False)[
            PAYMENT_AMOUNT_COLUMN
        ]
        .sum()
        .sort_values(PAYMENT_AMOUNT_COLUMN)
    )

    result = []

    for _, row in grouped.iterrows():
        total_spent = round(
            abs(float(row[PAYMENT_AMOUNT_COLUMN])),
            2,
        )

        result.append(
            {
                "last_digits": _to_text(row[CARD_COLUMN])[-4:],
                "total_spent": total_spent,
                "cashback": round(total_spent / 100, 2),
            }
        )

    return result


def get_top_transactions(
    transactions: pd.DataFrame,
    limit: int = 5,
) -> list[dict[str, str | float]]:
    """Возвращает самые большие по сумме платежа операции."""

    top_transactions = (
        transactions.sort_values(
            PAYMENT_AMOUNT_COLUMN,
            ascending=False,
        )
        .head(limit)
        .copy()
    )

    result = []

    for _, row in top_transactions.iterrows():
        result.append(
            {
                "date": row[DATE_COLUMN].strftime("%d.%m.%Y"),
                "amount": round(
                    float(row[PAYMENT_AMOUNT_COLUMN]),
                    2,
                ),
                "category": _to_text(row[CATEGORY_COLUMN]),
                "description": _to_text(row[DESCRIPTION_COLUMN]),
            }
        )

    return result


def _get_market_data(
) -> tuple[
    list[dict[str, str | float]],
    list[dict[str, str | float]],
]:
    """Загружает валюты и акции из пользовательских настроек."""

    settings = load_user_settings()

    try:
        currency_rates = get_currency_rates(
            settings["user_currencies"]
        )
    except Exception as error:
        logger.error("Не удалось загрузить курсы валют: %s", error)
        currency_rates = []

    try:
        stock_prices = get_stock_prices(settings["user_stocks"])
    except Exception as error:
        logger.error("Не удалось загрузить цены акций: %s", error)
        stock_prices = []

    return currency_rates, stock_prices


def home_page(
    date: str,
    transactions: pd.DataFrame | None = None,
) -> str:
    """
    Возвращает JSON-данные для страницы «Главная».

    Анализируется период от начала месяца до переданной даты и времени.
    """

    current_date = _parse_datetime(date)

    data = read_transactions() if transactions is None else transactions
    data = _prepare_transactions(data)
    data = _completed_transactions(data)

    start_date = current_date.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    period_transactions = _transactions_in_range(
        data,
        start_date,
        current_date,
    )

    currency_rates, stock_prices = _get_market_data()

    response = {
        "greeting": get_greeting(current_date),
        "cards": get_cards(period_transactions),
        "top_transactions": get_top_transactions(period_transactions),
        "currency_rates": currency_rates,
        "stock_prices": stock_prices,
    }

    logger.info(
        "Сформирована главная страница за период %s — %s.",
        start_date,
        current_date,
    )

    return json.dumps(
        response,
        ensure_ascii=False,
        indent=4,
    )

def _get_period_start(
    current_date: datetime,
    period: str,
) -> datetime | None:
    """
    Возвращает начало периода для страницы «События».

    None означает: взять все данные до переданной даты.
    """

    normalized_period = period.upper()

    if normalized_period == "W":
        return current_date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) - pd.Timedelta(days=current_date.weekday())

    if normalized_period == "M":
        return current_date.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    if normalized_period == "Y":
        return current_date.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    if normalized_period == "ALL":
        return None

    raise ValueError(
        "Период должен быть одним из значений: W, M, Y, ALL."
    )


def _get_events_transactions(
    transactions: pd.DataFrame,
    current_date: datetime,
    period: str,
) -> pd.DataFrame:
    """Возвращает успешные операции за выбранный период."""

    start_date = _get_period_start(current_date, period)

    data = _prepare_transactions(transactions)
    data = _completed_transactions(data)

    if start_date is None:
        return data.loc[
            data[DATE_COLUMN] <= current_date
        ].copy()

    return _transactions_in_range(
        data,
        start_date,
        current_date,
    )


def _group_category_amounts(
    transactions: pd.DataFrame,
    amount_column: str,
) -> pd.DataFrame:
    """Группирует операции по категориям и сортирует по сумме."""

    grouped = (
        transactions.groupby(
            CATEGORY_COLUMN,
            as_index=False,
        )[amount_column]
        .sum()
        .sort_values(
            amount_column,
            ascending=False,
        )
        .reset_index(drop=True)
    )

    return grouped


def _build_category_response(
    grouped: pd.DataFrame,
    amount_column: str,
) -> list[dict[str, str | int]]:
    """Преобразует сгруппированные категории в JSON-совместимый список."""

    return [
        {
            "category": _to_text(row[CATEGORY_COLUMN]),
            "amount": int(round(float(row[amount_column]))),
        }
        for _, row in grouped.iterrows()
    ]


def _get_expenses_response(
    transactions: pd.DataFrame,
) -> dict[str, int | list[dict[str, str | int]]]:
    """Формирует блок расходов для страницы «События»."""

    expenses = transactions[
        transactions[PAYMENT_AMOUNT_COLUMN] < 0
    ].copy()

    expenses["expense_amount"] = expenses[
        PAYMENT_AMOUNT_COLUMN
    ].abs()

    total_amount = int(round(expenses["expense_amount"].sum()))

    transfers_and_cash_categories = {
        "Переводы",
        "Наличные",
    }

    transfers_and_cash = expenses[
        expenses[CATEGORY_COLUMN].isin(
            transfers_and_cash_categories
        )
    ].copy()

    main_expenses = expenses[
        ~expenses[CATEGORY_COLUMN].isin(
            transfers_and_cash_categories
        )
    ].copy()

    grouped_main = _group_category_amounts(
        main_expenses,
        "expense_amount",
    )

    top_categories = grouped_main.head(7).copy()
    other_categories = grouped_main.iloc[7:]

    if not other_categories.empty:
        other_amount = other_categories["expense_amount"].sum()

        top_categories = pd.concat(
            [
                top_categories,
                pd.DataFrame(
                    [
                        {
                            CATEGORY_COLUMN: "Остальное",
                            "expense_amount": other_amount,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    grouped_transfers_and_cash = _group_category_amounts(
        transfers_and_cash,
        "expense_amount",
    )

    return {
        "total_amount": total_amount,
        "main": _build_category_response(
            top_categories,
            "expense_amount",
        ),
        "transfers_and_cash": _build_category_response(
            grouped_transfers_and_cash,
            "expense_amount",
        ),
    }


def _get_income_response(
    transactions: pd.DataFrame,
) -> dict[str, int | list[dict[str, str | int]]]:
    """Формирует блок поступлений для страницы «События»."""

    income = transactions[
        transactions[PAYMENT_AMOUNT_COLUMN] > 0
    ].copy()

    total_amount = int(round(income[PAYMENT_AMOUNT_COLUMN].sum()))

    grouped_income = _group_category_amounts(
        income,
        PAYMENT_AMOUNT_COLUMN,
    )

    return {
        "total_amount": total_amount,
        "main": _build_category_response(
            grouped_income,
            PAYMENT_AMOUNT_COLUMN,
        ),
    }


def events_page(
    date: str,
    period: str = "M",
    transactions: pd.DataFrame | None = None,
) -> str:
    """ Возвращает JSON-данные для страницы «События». """

    current_date = _parse_datetime(date)

    data = read_transactions() if transactions is None else transactions

    period_transactions = _get_events_transactions(
        data,
        current_date,
        period,
    )

    currency_rates, stock_prices = _get_market_data()

    response = {
        "expenses": _get_expenses_response(period_transactions),
        "income": _get_income_response(period_transactions),
        "currency_rates": currency_rates,
        "stock_prices": stock_prices,
    }

    logger.info(
        "Сформирована страница событий за период %s до %s.",
        period.upper(),
        current_date,
    )

    return json.dumps(
        response,
        ensure_ascii=False,
        indent=4,
    )
