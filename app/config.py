import os


class Settings:
    """Конфигурация из переменных окружения (12-factor)."""

    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
    QUEUE_NAME: str = os.getenv("QUEUE_NAME", "credit_applications")
    DLQ_NAME: str = os.getenv("DLQ_NAME", "credit_applications.dlq")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://credit:credit@localhost:5432/credit"
    )
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
