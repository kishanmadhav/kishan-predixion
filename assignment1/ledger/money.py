"""Money helpers. All amounts are stored as integer paise; floats are refused."""
from decimal import Decimal, InvalidOperation


class InvalidAmountError(ValueError):
    pass


def to_paise(value) -> int:
    """Convert rupees (Decimal, int or numeric string) to integer paise.

    Floats are rejected because 0.1 + 0.2 != 0.3; callers must pass Decimal or str.
    More than two decimal places is rejected rather than silently rounded.
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidAmountError(f"amount must be Decimal, int or str, not {type(value).__name__}")
    try:
        dec = Decimal(str(value).strip()) if not isinstance(value, Decimal) else value
    except (InvalidOperation, ValueError):
        raise InvalidAmountError(f"amount is not a number: {value!r}") from None
    if not dec.is_finite():
        raise InvalidAmountError(f"amount must be finite: {value!r}")
    paise = dec * 100
    if paise != paise.to_integral_value():
        raise InvalidAmountError(f"amount has more than 2 decimal places: {value!r}")
    return int(paise)


def from_paise(paise: int) -> Decimal:
    return (Decimal(paise) / 100).quantize(Decimal("0.01"))
