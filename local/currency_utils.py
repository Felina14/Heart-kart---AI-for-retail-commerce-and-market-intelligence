"""
Currency utilities for HeartKart.

We keep all stored monetary values in USD for simplicity, and convert to
Indian rupees (INR) at the presentation layer for anything shown to users
or vendors (UI, emails, PDFs, call scripts, etc).
"""

import os
from typing import Union

Number = Union[int, float]


# Default conversion rate if environment variable is not set.
# Example: 1 USD ≈ 89.6 INR (19.99 → 1791.59).
USD_TO_INR_DEFAULT: float = 89.6


def get_usd_to_inr_rate() -> float:
    """
    Return the USD→INR conversion rate.

    You can override this by setting the USD_TO_INR environment variable.
    """
    value = os.getenv("USD_TO_INR")
    if not value:
        return USD_TO_INR_DEFAULT
    try:
        return float(value)
    except (TypeError, ValueError):
        return USD_TO_INR_DEFAULT


def usd_to_inr(amount_usd: Number) -> float:
    """
    Convert a USD amount to INR using the configured rate.

    Always returns a float rounded to 2 decimal places.
    """
    try:
        rate = get_usd_to_inr_rate()
        return round(float(amount_usd) * rate, 2)
    except Exception:
        return 0.0


def format_inr(amount_usd: Number) -> str:
    """
    Convenience helper to format a USD amount as a INR string.

    This is primarily for CLI/logging; UI code should usually format on the
    frontend.
    """
    inr = usd_to_inr(amount_usd)
    return f"₹{inr:,.2f}"


