from __future__ import annotations

import logging
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from pandas.tseries.offsets import DateOffset

from .utils import (
    CATEGORY_COLUMN,
    DATE_COLUMN,
    PAYMENT_AMOUNT_COLUMN,
    STATUS_COLUMN,
)


logger = logging.getLogger(__name__)

REPORTS_DIR = Path("reports")

WEEKDAY_NAMES = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


def save_report(
    function_or_filename: Callable | str | None = None,
) -> Callable:
    """Декоратор сохранения отчёта в JSON-файл."""
    def decorator(function: Callable) -> Callable:
        @wraps(function)
        def wrapper(*args, **kwargs) -> pd.DataFrame:
            result = function(*args, **kwargs)

            REPORTS_DIR.mkdir(parents=True, exist_ok=True)

            if isinstance(function_or_filename, str):
                filename = function_or_filename
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = (
                    f"{function.__name__}_{timestamp}.json"
                )

            file_path = REPORTS_DIR / filename

            result.to_json(
                file_path,
                orient="records",
                force_ascii=False,
                indent=4,
                date_format="iso",
            )

            logger.info(
                "Отчёт '%s' сохранён в файл %s.",
                function.__name__,
                file_path,
            )

            return result

        return wrapper

    if callable(function_or_filename):
        return decorator(function_or_filename)

    return decorator


def _parse_report_date(date: Optional[str] = None) -> pd.Timestamp:
    """Возвращает конечную дату отчёта. Если дата не передано, передается сегондяшняя дата."""
    if date is None:
        return pd.Timestamp.now()

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
    )

    for date_format in formats:
        try:
            return pd.Timestamp(
                datetime.strptime(date, date_format)
            )
        except ValueError:
            continue

    raise ValueError(
        "Дата должна быть в формате YYYY-MM-DD, "
        "YYYY-MM-DD HH:MM:SS, DD.MM.YYYY или "
        "DD.MM.YYYY HH:MM:SS."
    )


def _get_period_bounds(
    date: Optional[str] = None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Возвращает границы периода последних трёх месяцев."""
    report_date = _parse_report_date(date)

    start_date = (
        report_date.normalize() - DateOffset(months=3)
    )

    end_date = (
        report_date.normalize()
        + pd.Timedelta(days=1)
        - pd.Timedelta(nanoseconds=1)
    )

    return start_date, end_date


def _prepare_expenses(
    transactions: pd.DataFrame,
    date: Optional[str] = None,
) -> pd.DataFrame:
    """Подготавливает успешные расходные операции за последние три месяца."""
    required_columns = {
        DATE_COLUMN,
        CATEGORY_COLUMN,
        PAYMENT_AMOUNT_COLUMN,
    }

    missing_columns = required_columns.difference(
        transactions.columns
    )

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Отсутствуют обязательные столбцы: {missing}"
        )

    data = transactions.copy()

    data[DATE_COLUMN] = pd.to_datetime(
        data[DATE_COLUMN],
        errors="coerce",
        dayfirst=True,
    )

    data[PAYMENT_AMOUNT_COLUMN] = pd.to_numeric(
        data[PAYMENT_AMOUNT_COLUMN],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            DATE_COLUMN,
            PAYMENT_AMOUNT_COLUMN,
        ]
    )

    if STATUS_COLUMN in data.columns:
        status = data[STATUS_COLUMN].fillna("").astype(str)

        data = data[
            status.str.upper().eq("OK")
        ].copy()

    start_date, end_date = _get_period_bounds(date)

    data = data[
        (data[DATE_COLUMN] >= start_date)
        & (data[DATE_COLUMN] <= end_date)
    ].copy()

    data = data[
        data[PAYMENT_AMOUNT_COLUMN] < 0
    ].copy()

    data[PAYMENT_AMOUNT_COLUMN] = (
        data[PAYMENT_AMOUNT_COLUMN].abs()
    )

    logger.info(
        "Подготовлено %s расходных операций за период "
        "с %s по %s.",
        len(data),
        start_date.date(),
        end_date.date(),
    )

    return data


@save_report("spending_by_category.json")
def spending_by_category(
    transactions: pd.DataFrame,
    category: str,
    date: Optional[str] = None,
) -> pd.DataFrame:
    """Возвращает траты по указанной категории за последние три месяца."""
    data = _prepare_expenses(transactions, date)

    normalized_category = category.strip().casefold()

    result = data[
        data[CATEGORY_COLUMN]
        .fillna("")
        .astype(str)
        .str.casefold()
        .eq(normalized_category)
    ].copy()

    return (
        result.sort_values(DATE_COLUMN)
        .reset_index(drop=True)
    )


@save_report
def spending_by_weekday(
    transactions: pd.DataFrame,
    date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Возвращает средние траты по дням недели
    за последние три месяца.
    """

    data = _prepare_expenses(transactions, date)

    data["Номер дня недели"] = data[DATE_COLUMN].dt.weekday

    grouped = (
        data.groupby(
            "Номер дня недели",
            as_index=False,
        )[PAYMENT_AMOUNT_COLUMN]
        .mean()
    )

    all_weekdays = pd.DataFrame(
        {
            "Номер дня недели": list(WEEKDAY_NAMES),
            "День недели": list(WEEKDAY_NAMES.values()),
        }
    )

    result = all_weekdays.merge(
        grouped,
        on="Номер дня недели",
        how="left",
    )

    result[PAYMENT_AMOUNT_COLUMN] = (
        result[PAYMENT_AMOUNT_COLUMN]
        .fillna(0)
        .round(2)
    )

    result = result.rename(
        columns={
            PAYMENT_AMOUNT_COLUMN: "Средние траты",
        }
    )

    return result.drop(
        columns="Номер дня недели"
    ).reset_index(drop=True)


@save_report("spending_by_workday.json")
def spending_by_workday(
    transactions: pd.DataFrame,
    date: Optional[str] = None,
) -> pd.DataFrame:
    """Возвращает средние траты в рабочие и выходные дни за последние три месяца."""
    data = _prepare_expenses(transactions, date)

    data["Тип дня"] = data[DATE_COLUMN].dt.weekday.map(
        lambda weekday: (
            "Рабочий день"
            if weekday < 5
            else "Выходной день"
        )
    )

    grouped = (
        data.groupby(
            "Тип дня",
            as_index=False,
        )[PAYMENT_AMOUNT_COLUMN]
        .mean()
    )

    day_types = pd.DataFrame(
        {
            "Тип дня": [
                "Рабочий день",
                "Выходной день",
            ]
        }
    )

    result = day_types.merge(
        grouped,
        on="Тип дня",
        how="left",
    )

    result[PAYMENT_AMOUNT_COLUMN] = (
        result[PAYMENT_AMOUNT_COLUMN]
        .fillna(0)
        .round(2)
    )

    return result.rename(
        columns={
            PAYMENT_AMOUNT_COLUMN: "Средние траты",
        }
    )