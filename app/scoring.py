"""Правило принятия решения по заявке.

Чистая функция без I/O — легко тестировать и заменить на ML-модель.

Модель простая и интерпретируемая:
1. Жёсткое правило: PTI (платёж/доход) > 0.5 — отказ без скоринга.
2. Иначе балльный скоринг (0..100), порог одобрения — 60.
"""

from dataclasses import dataclass, field

from app.schemas import CreditApplication, EmploymentStatus

APPROVAL_THRESHOLD = 60
HARD_MAX_PTI = 0.5

_EMPLOYMENT_POINTS = {
    EmploymentStatus.employed: 30,
    EmploymentStatus.self_employed: 20,
    EmploymentStatus.retired: 15,
    EmploymentStatus.student: 5,
    EmploymentStatus.unemployed: 0,
}


@dataclass
class DecisionResult:
    decision: str  # "approved" | "rejected"
    score: int
    pti: float
    reasons: list[str] = field(default_factory=list)


def make_decision(app: CreditApplication) -> DecisionResult:
    monthly_payment = app.requested_amount / app.requested_term_months
    pti = round(monthly_payment / app.monthly_income, 4)
    reasons: list[str] = [f"monthly_payment={monthly_payment:.2f}", f"pti={pti}"]

    if pti > HARD_MAX_PTI:
        reasons.append(f"hard reject: pti > {HARD_MAX_PTI}")
        return DecisionResult(decision="rejected", score=0, pti=pti, reasons=reasons)

    score = 0

    if pti <= 0.15:
        score += 40
        reasons.append("pti <= 0.15: +40")
    elif pti <= 0.30:
        score += 25
        reasons.append("pti <= 0.30: +25")
    else:
        score += 10
        reasons.append("pti <= 0.50: +10")

    emp_points = _EMPLOYMENT_POINTS[app.employment_status]
    score += emp_points
    reasons.append(f"employment_status={app.employment_status.value}: +{emp_points}")

    if app.employment_duration_months >= 12:
        score += 10
        reasons.append("employment_duration >= 12 months: +10")

    if app.existing_loans_count == 0:
        score += 15
        reasons.append("no existing loans: +15")
    elif app.existing_loans_count <= 2:
        score += 5
        reasons.append("existing_loans_count <= 2: +5")
    else:
        reasons.append(f"existing_loans_count={app.existing_loans_count}: +0")

    if app.dependents_count <= 2:
        score += 5
        reasons.append("dependents_count <= 2: +5")

    decision = "approved" if score >= APPROVAL_THRESHOLD else "rejected"
    reasons.append(f"score={score}, threshold={APPROVAL_THRESHOLD}")
    return DecisionResult(decision=decision, score=score, pti=pti, reasons=reasons)
