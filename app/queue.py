"""Публикация заявок в RabbitMQ.

Ленивое singleton-соединение с переподключением при обрыве. Очередь durable,
сообщения persistent, у основной очереди настроен dead-letter на DLQ —
«ядовитые» сообщения не теряются и не крутятся в бесконечном redelivery.
"""

import json
import logging
import threading

import pika

from app.config import settings

logger = logging.getLogger(__name__)


class QueuePublisher:
    def __init__(self) -> None:
        self._connection: pika.BlockingConnection | None = None
        self._channel = None
        self._lock = threading.Lock()

    def _ensure_channel(self):
        if self._channel is None or self._channel.is_closed:
            self._connection = pika.BlockingConnection(
                pika.URLParameters(settings.RABBITMQ_URL)
            )
            self._channel = self._connection.channel()
            declare_queues(self._channel)
        return self._channel

    def publish(self, message: dict) -> None:
        body = json.dumps(message, ensure_ascii=False, default=str).encode("utf-8")
        with self._lock:
            try:
                channel = self._ensure_channel()
                channel.basic_publish(
                    exchange="",
                    routing_key=settings.QUEUE_NAME,
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=pika.DeliveryMode.Persistent,
                        content_type="application/json",
                    ),
                )
            except pika.exceptions.AMQPError:
                # Одна попытка переподключения: соединение могло протухнуть.
                logger.warning("AMQP connection lost, reconnecting")
                self._reset()
                channel = self._ensure_channel()
                channel.basic_publish(
                    exchange="",
                    routing_key=settings.QUEUE_NAME,
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=pika.DeliveryMode.Persistent,
                        content_type="application/json",
                    ),
                )

    def _reset(self) -> None:
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._channel = None


def declare_queues(channel) -> None:
    """Идемпотентное объявление очередей — вызывается и в API, и в воркере."""
    channel.queue_declare(queue=settings.DLQ_NAME, durable=True)
    channel.queue_declare(
        queue=settings.QUEUE_NAME,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": settings.DLQ_NAME,
        },
    )


publisher = QueuePublisher()
