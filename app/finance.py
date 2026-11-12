"""Pure financial calculators. Agents never do arithmetic themselves - they call these."""
from __future__ import annotations


def emi(principal: float, annual_rate: float, tenure_months: int) -> dict:
    """Equated monthly instalment on a reducing-balance loan."""
    if principal <= 0 or tenure_months <= 0 or annual_rate < 0:
        raise ValueError("principal and tenure must be positive, rate non-negative")
    r = annual_rate / 12 / 100
    if r == 0:
        monthly = principal / tenure_months
    else:
        growth = (1 + r) ** tenure_months
        monthly = principal * r * growth / (growth - 1)
    total = monthly * tenure_months
    return {
        "emi": round(monthly, 2),
        "total_payment": round(total, 2),
        "total_interest": round(total - principal, 2),
    }


def max_principal_for_emi(max_emi: float, annual_rate: float, tenure_months: int) -> float:
    """Inverse of emi(): the largest loan a given EMI can service."""
    if max_emi <= 0:
        return 0.0
    r = annual_rate / 12 / 100
    if r == 0:
        return round(max_emi * tenure_months, 2)
    growth = (1 + r) ** tenure_months
    return round(max_emi * (growth - 1) / (r * growth), 2)


def fd_maturity(principal: float, annual_rate: float, tenure_months: int) -> dict:
    """Cumulative fixed deposit, interest compounded quarterly."""
    if principal <= 0 or tenure_months <= 0:
        raise ValueError("principal and tenure must be positive")
    amount = principal * (1 + annual_rate / 400) ** (tenure_months / 3)
    return {
        "maturity_amount": round(amount, 2),
        "interest_earned": round(amount - principal, 2),
    }


def rd_maturity(monthly_installment: float, annual_rate: float, tenure_months: int) -> dict:
    """Recurring deposit, each instalment compounded quarterly until maturity."""
    if monthly_installment <= 0 or tenure_months <= 0:
        raise ValueError("installment and tenure must be positive")
    q = 1 + annual_rate / 400
    amount = sum(
        monthly_installment * q ** ((tenure_months - i) / 3) for i in range(tenure_months)
    )
    deposited = monthly_installment * tenure_months
    return {
        "maturity_amount": round(amount, 2),
        "total_deposited": round(deposited, 2),
        "interest_earned": round(amount - deposited, 2),
    }
