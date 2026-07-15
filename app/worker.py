"""Воркер: читает заявки из RabbitMQ, скорит и сохраняет результат в PostgreSQL.

Обработка ошибок:
- битый JSON / невалидная заявка -> nack без requeue -> сообщение уходит в DLQ;
- ошибка БД -> nack с requeue (временная проблема, сообщение вернётся);
- повторная доставка того же application_id -> идемпотентный merge (upsert).
"""

import json
import logging
import time

import pika
from pydantic import ValidationError

from app.config import settings
from app.db import ApplicationResult, SessionLocal, init_db
from app.logging_config import setup_logging
from app.queue import declare_queues
from app.schemas import CreditApplication
from app.scoring import make_decision

setup_logging()
logger = logging.getLogger(__name__)


def process_message(body: bytes) -> None:
    """Разбор -> повторная валидация -> решение -> сохранение.

    ValueError/ValidationError означают «ядовитое» сообщение (в DLQ),
    остальные исключения считаем временными (requeue).
    """
    try:
        message = json.loads(body)
        application_id = message["application_id"]
        raw_application = message["application"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"malformed message: {exc}") from exc

    # Воркер не доверяет содержимому очереди и валидирует заявку повторно.
    application = CreditApplication.model_validate(raw_application)
    result = make_decision(application)

    with SessionLocal() as session:
        session.merge(
            ApplicationResult(
                application_id=application_id,
                client_id=application.client_id,
                full_name=application.full_name,
                requested_amount=application.requested_amount,
                requested_term_months=application.requested_term_months,
                monthly_income=application.monthly_income,
                decision=result.decision,
                score=result.score,
                pti=result.pti,
                reasons=result.reasons,
                payload=raw_application,
            )
        )
        session.commit()

    logger.info(
        "Application %s: %s (score=%d, pti=%.4f)",
        application_id, result.decision, result.score, result.pti,
    )


def on_message(channel, method, properties, body) -> None:
    try:
        process_message(body)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except (ValueError, ValidationError) as exc:
        logger.error("Poison message -> DLQ: %s", exc)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception:
        logger.exception("Transient failure, requeueing message")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        time.sleep(1)  # не молотить очередь в цикле, если БД лежит


def main() -> None:
    init_db()
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
            channel = connection.channel()
            declare_queues(channel)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=settings.QUEUE_NAME, on_message_callback=on_message)
            logger.info("Worker started, consuming from '%s'", settings.QUEUE_NAME)
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as exc:
            logger.warning("RabbitMQ unavailable (%s), retrying in 3s", exc)
            time.sleep(3)
        except KeyboardInterrupt:
            logger.info("Worker stopped")
            break


if __name__ == "__main__":
    main()
