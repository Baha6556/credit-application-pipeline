# Credit Applications Pipeline

Упрощённый пайплайн обработки кредитных заявок:

```
клиент ── POST /applications ──> FastAPI ── валидация (Pydantic) ──> RabbitMQ ──> воркер
                                    │                                                │
                                    └── 422 + причины отказа            скоринг + запись в PostgreSQL
```

## Как запустить

```bash
docker compose up --build
```

Поднимаются 4 контейнера: `api` (порт 8000), `worker`, `rabbitmq` (management UI на
http://localhost:15672, guest/guest), `postgres`.

Проверка:

```bash
# валидная заявка -> 202 {application_id, status: queued}
curl -X POST http://localhost:8000/applications -H "Content-Type: application/json" -d '{
  "client_id": 1086, "full_name": "Шариф Каримов", "birth_date": "1980-03-24",
  "national_id": "49CC7681090", "phone": "+992988942330", "email": "user359@gmail.com",
  "monthly_income": 9335.54, "employment_status": "self_employed",
  "employment_duration_months": 74, "requested_amount": 30487.01,
  "requested_term_months": 6, "existing_loans_count": 2, "region": "Истаравшан",
  "marital_status": "divorced", "dependents_count": 2, "application_date": "2026-04-22"
}'

# результат обработки (после воркера)
curl http://localhost:8000/applications/<application_id>
```

Swagger UI: http://localhost:8000/docs

### Тесты

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows (Linux: source .venv/bin/activate)
pip install -r requirements.txt
pytest -v
```

Тесты покрывают валидацию и логику принятия решения; внешние сервисы не нужны.

## Архитектура и принятые решения

### Валидация — на входе в API ([app/schemas.py](app/schemas.py))

Невалидная заявка **отклоняется сразу с 422 и списком причин** — она не попадает в
очередь: отправитель сразу узнаёт, что исправить, а тащить заведомо битые данные
через брокер бессмысленно.

Основные правила:

- обязательные поля: ФИО, даты, телефон, email, доход, сумма, срок и т.д.;
- форматы: телефон `+992XXXXXXXXX`, email, `national_id` вида `49CC7681090`,
  даты только ISO `YYYY-MM-DD`;
- диапазоны: доход `0 < x <= 500 000`, сумма `0 < x <= 1 000 000`, срок — целое
  `3..60` мес., стаж/кредиты/иждивенцы — неотрицательные целые;
- категории: `employment_status` и `marital_status` — строгие enum;
- согласованность: возраст 18–75 на дату заявки, дата заявки не в будущем.

Граница «нормализовать vs отклонить»: чистим только однозначно восстановимое
(пробелы, регистр — `"MARRIED"`, `"+992 96 226 9966"` принимаются). Всё, где
пришлось бы гадать (битый email, неполный телефон), — отклоняем: в кредитном
пайплайне молчаливое «додумывание» данных опаснее отказа.

### Очередь (RabbitMQ, [app/queue.py](app/queue.py))

- Durable-очередь + persistent-сообщения — заявки переживают рестарт брокера.
- Настроен **DLQ**: «ядовитые» сообщения (битый JSON) уходят в
  `credit_applications.dlq` для разбора, а не крутятся в бесконечном redelivery.
- Если брокер недоступен, API отвечает `503` — клиент знает, что заявка не принята.

### Воркер ([app/worker.py](app/worker.py))

- `prefetch_count=1` + ручной ack **после** записи в БД — сообщение не теряется,
  если воркер упал посреди обработки (at-least-once).
- Повторная доставка не создаёт дублей: запись по `application_id` идемпотентна (merge).
- **Повторная валидация** заявки из очереди — воркер не доверяет содержимому брокера.
- Ошибки разделены: битое сообщение → nack в DLQ; временная (БД недоступна) →
  nack с requeue и паузой.

### Скоринг ([app/scoring.py](app/scoring.py))

Чистая функция без I/O — тестируется в изоляции, при желании заменяется на ML-модель.
Интерпретируемая (каждая причина решения пишется в БД):

1. **Жёсткое правило**: PTI = (сумма/срок)/доход > 0.5 → отказ сразу.
2. Иначе баллы: PTI (до 40), статус занятости (до 30), стаж ≥ 12 мес (+10),
   текущие кредиты (до 15), иждивенцы ≤ 2 (+5). Порог одобрения — **60 из 100**.

### БД (PostgreSQL, [app/db.py](app/db.py))

Одна таблица `application_results`: решение, скор, PTI, список причин (JSON) и полный
исходный payload (JSON) — для аудита. Схема создаётся воркером при старте
(`create_all` с ретраями); для продакшена — Alembic-миграции.

### Что бы добавил для продакшена

Alembic-миграции, аутентификацию API, метрики (Prometheus), correlation id в логах,
retry с экспоненциальной задержкой, интеграционные тесты с testcontainers.
