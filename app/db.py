"""Модель результата обработки заявки и сессия PostgreSQL."""

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class ApplicationResult(Base):
    __tablename__ = "application_results"

    application_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    requested_amount: Mapped[float] = mapped_column(Float)
    requested_term_months: Mapped[int] = mapped_column(Integer)
    monthly_income: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[int] = mapped_column(Integer)
    pti: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())


def init_db(retries: int = 10, delay: float = 2.0) -> None:
    """Создаёт таблицы; ждёт готовности Postgres (актуально в docker-compose)."""
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(engine)
            return
        except Exception as exc:
            logger.warning("DB not ready (attempt %d/%d): %s", attempt, retries, exc)
            if attempt == retries:
                raise
            time.sleep(delay)
