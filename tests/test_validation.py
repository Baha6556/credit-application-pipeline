"""Тесты валидации: кейсы взяты из реальной «грязи» тестового датасета."""

import pytest
from pydantic import ValidationError

from app.schemas import CreditApplication

VALID = {
    "client_id": 1086,
    "full_name": "Шариф Каримов",
    "birth_date": "1980-03-24",
    "national_id": "49CC7681090",
    "phone": "+992988942330",
    "email": "user359@gmail.com",
    "monthly_income": 9335.54,
    "employment_status": "self_employed",
    "employment_duration_months": 74,
    "requested_amount": 30487.01,
    "requested_term_months": 6,
    "existing_loans_count": 2,
    "region": "Истаравшан",
    "marital_status": "divorced",
    "dependents_count": 2,
    "application_date": "2026-04-22",
}


def make(**overrides) -> CreditApplication:
    return CreditApplication(**{**VALID, **overrides})


def assert_invalid(**overrides) -> None:
    with pytest.raises(ValidationError):
        make(**overrides)


def test_valid_application_passes():
    app = make()
    assert app.client_id == 1086
    assert app.monthly_income == pytest.approx(9335.54)


# --- нормализация: это не ошибки, данные чистятся ---

def test_marital_status_case_and_spaces_normalized():
    assert make(marital_status="MARRIED").marital_status.value == "married"
    assert make(marital_status="divorced ").marital_status.value == "divorced"
    assert make(marital_status=" Single ").marital_status.value == "single"


def test_phone_with_spaces_normalized():
    app = make(phone="+992 96 226 9966  ")
    assert app.phone == "+992962269966"


def test_email_with_padding_normalized():
    assert make(email=" user306@gmail.com ").email == "user306@gmail.com"


# --- обязательные поля ---

def test_empty_full_name_rejected():
    assert_invalid(full_name="")
    assert_invalid(full_name="  ")


def test_missing_required_fields_rejected():
    for field in ("phone", "national_id", "requested_term_months", "application_date"):
        payload = {**VALID}
        del payload[field]
        with pytest.raises(ValidationError):
            CreditApplication(**payload)
    assert_invalid(phone=None)


# --- форматы ---

@pytest.mark.parametrize("phone", ["983590502", "+992408", "+992abc123456", "+992526"])
def test_bad_phone_rejected(phone):
    assert_invalid(phone=phone)


@pytest.mark.parametrize("email", ["user723@", "user951@@gmail.com", "user216gmail.com"])
def test_bad_email_rejected(email):
    assert_invalid(email=email)


@pytest.mark.parametrize("nid", ["521", "164", "####??1234", ""])
def test_bad_national_id_rejected(nid):
    assert_invalid(national_id=nid)


@pytest.mark.parametrize("d", ["31.02.2026", "2026/13/40", "12/31/2000", ""])
def test_bad_dates_rejected(d):
    assert_invalid(application_date=d)
    assert_invalid(birth_date=d)


# --- числовые диапазоны ---

@pytest.mark.parametrize("income", [0, -2966.62, 999999999, "не указано"])
def test_bad_income_rejected(income):
    assert_invalid(monthly_income=income)


@pytest.mark.parametrize("amount", [0, -2804.97, "unknown"])
def test_bad_amount_rejected(amount):
    assert_invalid(requested_amount=amount)


@pytest.mark.parametrize("term", [0, -12, 12.5, None])
def test_bad_term_rejected(term):
    assert_invalid(requested_term_months=term)


def test_negative_employment_duration_rejected():
    assert_invalid(employment_duration_months=-9)


@pytest.mark.parametrize("deps", [-1, 2.5])
def test_bad_dependents_rejected(deps):
    assert_invalid(dependents_count=deps)


# --- категории ---

@pytest.mark.parametrize("status", ["informal", "N/A", "не указано", ""])
def test_bad_employment_status_rejected(status):
    assert_invalid(employment_status=status)


@pytest.mark.parametrize("status", ["в браке", "unknown", ""])
def test_bad_marital_status_rejected(status):
    assert_invalid(marital_status=status)


# --- согласованность дат / возраст ---

def test_birth_date_in_future_rejected():
    assert_invalid(birth_date="2036-03-01")
    assert_invalid(birth_date="2029-06-24")


def test_underage_applicant_rejected():
    assert_invalid(birth_date="2011-09-24")
    assert_invalid(birth_date="2008-06-28", application_date="2026-02-02")


def test_too_old_applicant_rejected():
    assert_invalid(birth_date="1909-06-10")
    assert_invalid(birth_date="1913-10-01")


def test_application_date_in_future_rejected():
    assert_invalid(application_date="2099-01-01")


def test_boundary_age_18_accepted():
    app = make(birth_date="2008-04-22", application_date="2026-04-22")
    assert app.birth_date.year == 2008
