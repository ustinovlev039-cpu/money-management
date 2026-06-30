from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from .reports import (
    spending_by_category,
    spending_by_weekday,
    spending_by_workday,
)
from .services import (
    cashback_categories,
    investment_bank,
    search_person_transfers,
    search_phone_numbers,
    simple_search,
)
from .utils import DATE_COLUMN, PROJECT_ROOT, read_transactions
from .views import events_page, home_page


logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"


def configure_logging() -> None:
    """Настраивает вывод логов в терминал и файл."""

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                LOGS_DIR / "application.log",
                encoding="utf-8",
            ),
        ],
    )


def parse_cli_date(value: str) -> datetime:
    """
    Преобразует дату из аргумента командной строки в datetime.
    """

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
    )

    for date_format in formats:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue

    raise argparse.ArgumentTypeError(
        "Дата должна быть в формате YYYY-MM-DD HH:MM:SS "
        "или YYYY-MM-DD."
    )


def get_latest_operation_date(
    transactions: pd.DataFrame,
) -> datetime:
    """
    Возвращает конец последнего дня с операциями.
    """

    dates = pd.to_datetime(
        transactions[DATE_COLUMN],
        errors="coerce",
    )

    latest_date = dates.max()

    if pd.isna(latest_date):
        raise ValueError(
            "В файле операций нет корректных значений даты."
        )

    return pd.Timestamp(latest_date).to_pydatetime().replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=0,
    )


def write_json_text(
    file_path: Path,
    json_text: str,
) -> None:
    """Сохраняет JSON-строку в файл с красивым форматированием."""

    file_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.loads(json_text)

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=4,
        )


def write_dataframe(
    file_path: Path,
    dataframe: pd.DataFrame,
) -> None:
    """Сохраняет DataFrame как JSON-файл."""

    file_path.parent.mkdir(parents=True, exist_ok=True)

    dataframe.to_json(
        file_path,
        orient="records",
        force_ascii=False,
        indent=4,
        date_format="iso",
    )


def get_display_path(path: Path) -> str:
    """Возвращает удобный путь для вывода в терминал."""

    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def generate_project_outputs(
    transactions: pd.DataFrame,
    target_date: datetime,
    period: str,
    category: str,
    search_query: str,
    investment_limit: int,
    output_dir: Path,
) -> dict[str, Path]:
    """Запускает все функции проекта и сохраняет результаты."""

    output_dir.mkdir(parents=True, exist_ok=True)

    date_text = target_date.strftime("%Y-%m-%d %H:%M:%S")
    report_date = target_date.strftime("%Y-%m-%d")
    investment_month = target_date.strftime("%Y-%m")

    records = transactions.to_dict(orient="records")

    generated_files: dict[str, Path] = {}

    home_path = output_dir / "home.json"
    write_json_text(
        home_path,
        home_page(date_text, transactions=transactions),
    )
    generated_files["Главная страница"] = home_path

    events_path = output_dir / "events.json"
    write_json_text(
        events_path,
        events_page(
            date_text,
            period=period,
            transactions=transactions,
        ),
    )
    generated_files["Страница событий"] = events_path

    cashback_path = output_dir / "cashback_categories.json"
    write_json_text(
        cashback_path,
        cashback_categories(
            transactions,
            target_date.year,
            target_date.month,
        ),
    )
    generated_files["Категории кешбэка"] = cashback_path

    investment_path = output_dir / "investment_bank.json"
    investment_result = {
        "month": investment_month,
        "limit": investment_limit,
        "saved_amount": investment_bank(
            investment_month,
            records,
            investment_limit,
        ),
    }

    with investment_path.open("w", encoding="utf-8") as file:
        json.dump(
            investment_result,
            file,
            ensure_ascii=False,
            indent=4,
        )

    generated_files["Инвесткопилка"] = investment_path

    search_path = output_dir / "simple_search.json"
    write_json_text(
        search_path,
        simple_search(search_query, transactions),
    )
    generated_files["Простой поиск"] = search_path

    phone_numbers_path = output_dir / "phone_numbers.json"
    write_json_text(
        phone_numbers_path,
        search_phone_numbers(transactions),
    )
    generated_files["Поиск телефонов"] = phone_numbers_path

    person_transfers_path = output_dir / "person_transfers.json"
    write_json_text(
        person_transfers_path,
        search_person_transfers(transactions),
    )
    generated_files[
        "Переводы физическим лицам"
    ] = person_transfers_path

    category_report = spending_by_category(
        transactions,
        category,
        report_date,
    )

    category_report_path = output_dir / "spending_by_category.json"
    write_dataframe(category_report_path, category_report)
    generated_files["Отчёт по категории"] = category_report_path

    weekday_report = spending_by_weekday(
        transactions,
        report_date,
    )

    weekday_report_path = output_dir / "spending_by_weekday.json"
    write_dataframe(weekday_report_path, weekday_report)
    generated_files["Отчёт по дням недели"] = weekday_report_path

    workday_report = spending_by_workday(
        transactions,
        report_date,
    )

    workday_report_path = output_dir / "spending_by_workday.json"
    write_dataframe(workday_report_path, workday_report)
    generated_files[
        "Отчёт по рабочим и выходным"
    ] = workday_report_path

    return generated_files


def create_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""

    parser = argparse.ArgumentParser(
        description=(
            "Анализ банковских транзакций из operations.xlsx."
        )
    )

    parser.add_argument(
        "--date",
        type=parse_cli_date,
        default=None,
        help=(
            "Конечная дата анализа. По умолчанию берётся "
            "последняя дата из Excel."
        ),
    )

    parser.add_argument(
        "--period",
        type=str.upper,
        choices=("W", "M", "Y", "ALL"),
        default="M",
        help=(
            "Период для страницы событий: "
            "W, M, Y или ALL. По умолчанию M."
        ),
    )

    parser.add_argument(
        "--category",
        default="Супермаркеты",
        help="Категория для отчёта трат.",
    )

    parser.add_argument(
        "--search",
        default="Ozon",
        help="Текст для простого поиска.",
    )

    parser.add_argument(
        "--investment-limit",
        type=int,
        choices=(10, 50, 100),
        default=50,
        help="Шаг округления Инвесткопилки.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Папка для созданных JSON-файлов.",
    )

    return parser


def main() -> None:
    """Запускает приложение."""

    configure_logging()

    parser = create_parser()
    arguments = parser.parse_args()

    transactions = read_transactions()

    target_date = (
        arguments.date
        if arguments.date is not None
        else get_latest_operation_date(transactions)
    )

    logger.info(
        "Запуск анализа на дату: %s.",
        target_date.strftime("%Y-%m-%d %H:%M:%S"),
    )

    generated_files = generate_project_outputs(
        transactions=transactions,
        target_date=target_date,
        period=arguments.period,
        category=arguments.category,
        search_query=arguments.search,
        investment_limit=arguments.investment_limit,
        output_dir=arguments.output_dir,
    )

    print("\nГотово. Были сформированы файлы:")

    for title, path in generated_files.items():
        print(f"- {title}: {get_display_path(path)}")

    print("\nФайлы декораторов дополнительно сохранены в папке reports/.")
    print(f"Лог работы: {get_display_path(LOGS_DIR / 'application.log')}")


if __name__ == "__main__":
    main()