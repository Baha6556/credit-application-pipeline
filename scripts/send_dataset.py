"""Прогон тестового датасета через API.

Читает CSV, отправляет каждую строку в POST /applications и печатает сводку:
сколько заявок принято в очередь, сколько отклонено валидацией и почему.

Запуск (стек должен быть поднят):
    python scripts/send_dataset.py [путь_к_csv] [базовый_URL]
"""

import csv
import sys
from collections import Counter

import httpx

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/credit_applications_test_dataset.csv"
BASE_URL = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

NUMERIC_FIELDS = {
    "client_id", "monthly_income", "employment_duration_months",
    "requested_amount", "requested_term_months", "existing_loans_count",
    "dependents_count",
}


def row_to_payload(row: dict) -> dict:
    """CSV отдаёт строки; пустые значения превращаем в null, числа не трогаем —
    типизацию и диапазоны проверяет API."""
    payload = {}
    for key, value in row.items():
        value = value.strip() if isinstance(value, str) else value
        if value == "" or value is None:
            payload[key] = None
        elif key in NUMERIC_FIELDS:
            try:
                num = float(value)
                payload[key] = int(num) if num.is_integer() else num
            except ValueError:
                payload[key] = value  # пусть API отклонит с понятной ошибкой
        else:
            payload[key] = value
    return payload


def main() -> None:
    accepted, rejected = 0, 0
    rejection_fields: Counter = Counter()

    with open(CSV_PATH, encoding="utf-8-sig") as f, httpx.Client(timeout=10) as client:
        for i, row in enumerate(csv.DictReader(f), start=1):
            response = client.post(f"{BASE_URL}/applications", json=row_to_payload(row))
            if response.status_code == 202:
                accepted += 1
            elif response.status_code == 422:
                rejected += 1
                for err in response.json()["detail"]:
                    field = str(err["loc"][-1] if err["loc"] else "?")
                    rejection_fields[field] += 1
                print(f"row {i:3d} (client_id={row.get('client_id')}): rejected -> "
                      + "; ".join(f"{e['loc'][-1] if e['loc'] else '?'}: {e['msg']}"
                                  for e in response.json()["detail"]))
            else:
                print(f"row {i:3d}: unexpected {response.status_code}: {response.text}")

    print(f"\nИтого: {accepted} принято в очередь, {rejected} отклонено валидацией")
    if rejection_fields:
        print("Отклонения по полям:")
        for field, count in rejection_fields.most_common():
            print(f"  {field}: {count}")


if __name__ == "__main__":
    main()
