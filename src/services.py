from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_HALF_UP,
)
from typing import Any

import pandas as pd

from .utils import (
    CATEGORY_COLUMN,
    DATE_COLUMN,
    DESCRIPTION_COLUMN,
    OPERATION_AMOUNT_COLUMN,
    STATUS_COLUMN,
)


logger = logging.getLogger(__name__)

CASHBACK_RATE = Decimal("0.05")
ALLOWED_INVESTMENT_LIMITS = {10, 50, 100}

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+7|8)\s*(?:\(\s*\d{3}\s*\)|\d{3})"
    r"[\s-]*\d{2,3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)"
)

PERSON_TRANSFER_PATTERN = re.compile(
    r"(?<![А-Яа-яЁё])"
    r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\."
)


def _to_text(value: Any) -> str:
    """Безопасно преобразует значение в строку."""

    if value is None:
        return ""

    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def _to_records(
    data: pd.DataFrame | Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Преобразует датафрейм или итерируемый объект в кортеж словарей."""

    if isinstance(data, pd.DataFrame):
        return tuple(data.to_dict(orient="records"))

    return tuple(dict(transaction) for transaction in data)


def _parse_transaction_date(value: Any) -> datetime:
    """Преобразует дату операции в datetime."""

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if isinstance(value, datetime):
        return value

    date_text = _to_text(value)

    try:
        return datetime.fromisoformat(date_text)
    except ValueError:
        pass

    formats = (
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
    )

    for date_format in formats:
        try:
            return datetime.strptime(date_text, date_format)
        except ValueError:
            continue

    raise ValueError(
        f"Не удалось преобразовать дату операции: {date_text}"
    )


def _get_amount(transaction: dict[str, Any]) -> Decimal:
    """Возвращает сумму операции в формате Decimal."""

    amount_text = _to_text(
        transaction.get(OPERATION_AMOUNT_COLUMN, 0)
    ).replace(",", ".")

    try:
        amount = Decimal(amount_text)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")

    if not amount.is_finite():
        return Decimal("0")

    return amount


def _is_successful(transaction: dict[str, Any]) -> bool:
    """ Проверяет успешность операции. """

    if STATUS_COLUMN not in transaction:
        return True

    return _to_text(transaction.get(STATUS_COLUMN)).upper() == "OK"


def _is_expense(transaction: dict[str, Any]) -> bool:
    """Проверяет, является ли операция расходом."""

    return _get_amount(transaction) < 0


def _is_in_year_month(
    transaction: dict[str, Any],
    year: int,
    month: int,
) -> bool:
    """Проверяет принадлежность операции указанному месяцу."""

    try:
        operation_date = _parse_transaction_date(
            transaction.get(DATE_COLUMN)
        )
    except ValueError:
        return False

    return (
        operation_date.year == year
        and operation_date.month == month
    )


def _json_compatible(value: Any) -> Any:
    """Приводит значения Pandas и Decimal к JSON-совместимому виду."""

    if isinstance(value, dict):
        return {
            str(key): _json_compatible(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]

    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(value, Decimal):
        return float(value)

    if value is None:
        return None

    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass

    return value


def _to_json(data: Any) -> str:
    """Возвращает корректную JSON-строку с русскими символами."""

    return json.dumps(
        _json_compatible(data),
        ensure_ascii=False,
        indent=4,
        allow_nan=False,
        default=str,
    )


def cashback_categories(
    data: pd.DataFrame | Iterable[dict[str, Any]],
    year: int,
    month: int,
) -> str:
    """Анализирует выгодность категорий повышенного кешбэка."""

    transactions = _to_records(data)

    month_expenses = tuple(
        filter(
            lambda transaction: (
                _is_successful(transaction)
                and _is_expense(transaction)
                and _is_in_year_month(transaction, year, month)
            ),
            transactions,
        )
    )

    categories = {
        _to_text(transaction.get(CATEGORY_COLUMN))
        for transaction in month_expenses
        if _to_text(transaction.get(CATEGORY_COLUMN))
    }

    category_cashback = [
        (
            category,
            (
                sum(
                    (
                        abs(_get_amount(transaction))
                        for transaction in month_expenses
                        if _to_text(
                            transaction.get(CATEGORY_COLUMN)
                        )
                        == category
                    ),
                    Decimal("0"),
                )
                * CASHBACK_RATE
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
        )
        for category in categories
    ]

    sorted_cashback = sorted(
        category_cashback,
        key=lambda item: (-item[1], item[0]),
    )

    result = {
        category: float(cashback)
        for category, cashback in sorted_cashback
    }

    logger.info(
        "Рассчитан кешбэк за %s.%s для %s категорий.",
        month,
        year,
        len(result),
    )

    return _to_json(result)


def _round_up_to_limit(
    amount: Decimal,
    limit: Decimal,
) -> Decimal:
    """Округляет сумму вверх до ближайшего лимита."""

    return (
        (amount / limit).to_integral_value(
            rounding=ROUND_CEILING
        )
        * limit
    )


def investment_bank(
    month: str,
    transactions: list[dict[str, Any]],
    limit: int,
) -> float:
    """
    Рассчитывает сумму, которую можно отложить в Инвесткопилку.

    month должен иметь формат YYYY-MM.
    limit может быть равен 10, 50 или 100.
    """

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit not in ALLOWED_INVESTMENT_LIMITS
    ):
        raise ValueError(
            "Порог округления должен быть одним из значений: "
            "10, 50, 100."
        )

    month_text = month.strip()

    try:
        target_date = datetime.strptime(month_text, "%Y-%m")
    except ValueError as error:
        raise ValueError(
            "Месяц должен быть указан в формате YYYY-MM."
        ) from error

    if target_date.strftime("%Y-%m") != month_text:
        raise ValueError(
            "Месяц должен быть указан в формате YYYY-MM."
        )

    limit_decimal = Decimal(str(limit))

    month_expenses = filter(
        lambda transaction: (
            _is_successful(transaction)
            and _is_expense(transaction)
            and _is_in_year_month(
                transaction,
                target_date.year,
                target_date.month,
            )
        ),
        transactions,
    )

    savings = map(
        lambda transaction: (
            _round_up_to_limit(
                abs(_get_amount(transaction)),
                limit_decimal,
            )
            - abs(_get_amount(transaction))
        ),
        month_expenses,
    )

    result = sum(savings, Decimal("0")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    logger.info(
        "Инвесткопилка за %s с лимитом %s: %s.",
        month_text,
        limit,
        result,
    )

    return float(result)


def simple_search(
    query: str,
    transactions: pd.DataFrame | Iterable[dict[str, Any]],
) -> str:
    """Ищет подстроку в категории или описании операций."""

    normalized_query = query.strip().casefold()

    if not normalized_query:
        return _to_json([])

    matched_transactions = filter(
        lambda transaction: (
            normalized_query
            in _to_text(
                transaction.get(CATEGORY_COLUMN)
            ).casefold()
            or normalized_query
            in _to_text(
                transaction.get(DESCRIPTION_COLUMN)
            ).casefold()
        ),
        _to_records(transactions),
    )

    result = list(matched_transactions)

    logger.info(
        "Простой поиск по запросу '%s' вернул %s операций.",
        query,
        len(result),
    )

    return _to_json(result)


def search_phone_numbers(
    transactions: pd.DataFrame | Iterable[dict[str, Any]],
) -> str:
    """Возвращает операции с мобильными номерами в описании."""

    result = list(
        filter(
            lambda transaction: bool(
                PHONE_PATTERN.search(
                    _to_text(
                        transaction.get(DESCRIPTION_COLUMN)
                    )
                )
            ),
            _to_records(transactions),
        )
    )

    logger.info(
        "Найдено операций с номерами телефона: %s.",
        len(result),
    )

    return _to_json(result)


def search_person_transfers(
    transactions: pd.DataFrame | Iterable[dict[str, Any]],
) -> str:
    """Ищет переводы физическим лицам."""

    result = list(
        filter(
            lambda transaction: (
                _to_text(
                    transaction.get(CATEGORY_COLUMN)
                ).casefold()
                == "переводы"
                and bool(
                    PERSON_TRANSFER_PATTERN.search(
                        _to_text(
                            transaction.get(DESCRIPTION_COLUMN)
                        )
                    )
                )
            ),
            _to_records(transactions),
        )
    )

    logger.info(
        "Найдено переводов физическим лицам: %s.",
        len(result),
    )

    return _to_json(result)