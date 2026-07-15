"""Тесты правила принятия решения (make_decision)."""

import pytest

from app.schemas import CreditApplication
from app.scoring import APPROVAL_THRESHOLD, make_decision

BASE = {
    "client_id": 1,
    "full_name": "Тест Тестов",
    "birth_date": "1990-01-01",
    "national_id": "49CC7681090",
    "phone": "+992988942330",
    "email": "test@example.com",
    "monthly_income": 10_000,
    "employment_status": "employed",
    "employment_duration_months": 24,
    "requested_amount": 24_000,
    "requested_term_months": 24,
    "existing_loans_count": 0,
    "region": "Душанбе",
    "marital_status": "married",
    "dependents_count": 1,
    "application_date": "2026-04-22",
}


def make(**overrides) -> CreditApplication:
    return CreditApplication(**{**BASE, **overrides})


def test_strong_applicant_approved():
    # payment=1000, pti=0.1, employed, стаж 24 мес, без кредитов
    result = make_decision(make())
    assert result.decision == "approved"
    assert result.score == 100
    assert result.pti == pytest.approx(0.1)


def test_high_pti_hard_rejected():
    # payment=5000 при доходе 2000 -> pti=2.5 > 0.5
    result = make_decision(make(monthly_income=2_000, requested_amount=30_000,
                                requested_term_months=6))
    assert result.decision == "rejected"
    assert result.score == 0
    assert any("hard reject" in r for r in result.reasons)


def test_pti_exactly_at_hard_limit_is_scored_not_hard_rejected():
    # payment=1000 при доходе 2000 -> pti=0.5, граница не превышена
    result = make_decision(make(monthly_income=2_000, requested_amount=12_000,
                                requested_term_months=12, dependents_count=0))
    assert not any("hard reject" in r for r in result.reasons)
    assert result.decision == "approved"  # 10+30+10+15+5 = 70


def test_unemployed_low_profile_rejected():
    result = make_decision(make(employment_status="unemployed",
                                employment_duration_months=5,
                                existing_loans_count=3,
                                dependents_count=4))
    assert result.decision == "rejected"
    assert result.score == 40  # только pti-баллы


def test_student_marginal_profile_rejected():
    # pti=0.2 (+25), student (+5), стаж (+10), 1 кредит (+5), 2 иждивенца (+5) = 50
    result = make_decision(make(employment_status="student",
                                requested_amount=24_000,
                                requested_term_months=12,
                                existing_loans_count=1,
                                dependents_count=2))
    assert result.decision == "rejected"
    assert result.score == 50


def test_score_exactly_at_threshold_approved():
    # pti=0.075 (+40), student (+5), стаж (+10), 2 кредита (+5), 3 иждивенца (+0) = 60
    result = make_decision(make(employment_status="student",
                                requested_amount=9_000,
                                requested_term_months=12,
                                existing_loans_count=2,
                                dependents_count=3))
    assert result.score == APPROVAL_THRESHOLD
    assert result.decision == "approved"


def test_reasons_are_always_populated():
    for overrides in ({}, {"monthly_income": 1_500, "requested_amount": 60_000,
                           "requested_term_months": 6}):
        result = make_decision(make(**overrides))
        assert result.reasons
        assert any(r.startswith("pti=") for r in result.reasons)
