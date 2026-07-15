"""Валидация кредитной заявки.

Модуль не зависит от FastAPI/RabbitMQ/БД — используется и в API (входной
контроль), и в воркере (defense in depth: воркер не доверяет очереди).
"""

import re
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

PHONE_RE = re.compile(r"^\+992\d{9}$")
NATIONAL_ID_RE = re.compile(r"^\d{2}[A-Z]{2}\d{7}$")

MIN_AGE_YEARS = 18
MAX_AGE_YEARS = 75

# Продуктовые ограничения (сомони)
MAX_MONTHLY_INCOME = 500_000
MAX_REQUESTED_AMOUNT = 1_000_000
MIN_TERM_MONTHS = 3
MAX_TERM_MONTHS = 60


class EmploymentStatus(str, Enum):
    employed = "employed"
    self_employed = "self_employed"
    unemployed = "unemployed"
    retired = "retired"
    student = "student"


class MaritalStatus(str, Enum):
    single = "single"
    married = "married"
    divorced = "divorced"
    widowed = "widowed"


class CreditApplication(BaseModel):
    client_id: int = Field(ge=1)
    full_name: str
    birth_date: date
    national_id: str
    phone: str
    email: EmailStr
    monthly_income: float = Field(gt=0, le=MAX_MONTHLY_INCOME)
    employment_status: EmploymentStatus
    employment_duration_months: int = Field(ge=0, le=600)
    requested_amount: float = Field(gt=0, le=MAX_REQUESTED_AMOUNT)
    requested_term_months: int = Field(ge=MIN_TERM_MONTHS, le=MAX_TERM_MONTHS)
    existing_loans_count: int = Field(ge=0, le=50)
    region: str
    marital_status: MaritalStatus
    dependents_count: int = Field(ge=0, le=20)
    application_date: date

    # --- нормализация текстовых полей до основной валидации ---

    @field_validator(
        "full_name", "national_id", "phone", "email", "region",
        "employment_status", "marital_status",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("employment_status", "marital_status", mode="before")
    @classmethod
    def _lowercase_enums(cls, v):
        # В данных встречаются "MARRIED", "Single " — регистр не считаем ошибкой.
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v):
        # "+992 96 226 9966" -> "+992962269966": пробелы/дефисы не считаем ошибкой.
        if isinstance(v, str):
            return re.sub(r"[\s\-()]", "", v)
        return v

    # --- содержательные проверки ---

    @field_validator("full_name")
    @classmethod
    def _validate_full_name(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("full_name is required and must be at least 2 characters")
        return v

    @field_validator("region")
    @classmethod
    def _validate_region(cls, v: str) -> str:
        if not v:
            raise ValueError("region is required")
        return v

    @field_validator("national_id")
    @classmethod
    def _validate_national_id(cls, v: str) -> str:
        if not NATIONAL_ID_RE.fullmatch(v):
            raise ValueError("national_id must match format NNAANNNNNNN (e.g. 49CC7681090)")
        return v

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        if not PHONE_RE.fullmatch(v):
            raise ValueError("phone must match +992XXXXXXXXX")
        return v

    @model_validator(mode="after")
    def _validate_dates(self) -> "CreditApplication":
        if self.application_date > date.today():
            raise ValueError("application_date cannot be in the future")
        age = _age_at(self.birth_date, self.application_date)
        if age < MIN_AGE_YEARS:
            raise ValueError(f"applicant must be at least {MIN_AGE_YEARS} years old")
        if age > MAX_AGE_YEARS:
            raise ValueError(f"applicant must be at most {MAX_AGE_YEARS} years old")
        return self


def _age_at(birth: date, on: date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))
