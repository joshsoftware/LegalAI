"""Turns raw check data into the human-readable evidence the UI displays.

Every ValidationResult carries the same five evidence keys, so the frontend
can render any check without knowing its type:

    source_document  doc id the checked value came from    ("PAN")
    source_value     that value, as display text           ("RAHUL KUMAR")
    target_document  doc id it was compared against         ("AADHAAR")
    target_value     the value it was compared against
    message          one plain-English sentence explaining the outcome

Document ids stay raw ("SALARY_SLIP-0") in the *_document keys so they
remain stable identifiers; doc_label is only used inside the message text.
"""

from datetime import date

# Not real doc ids -- placeholders for checks that compare against a whole
# group of documents rather than one, e.g. "all submitted salary slips".
ALL_SALARY_SLIPS = "SALARY_SLIPS"

_DOC_LABELS = {
    "AADHAAR": "Aadhaar",
    "PAN": "PAN",
    "BANK_STATEMENT": "Bank Statement",
    ALL_SALARY_SLIPS: "Salary Slips",
}


def doc_label(doc_id: str | None) -> str:
    """Convert a document id into a name a person would recognise.

    Args:
        doc_id (str or None): e.g. "AADHAAR" or "SALARY_SLIP-0".

    Returns:
        str: e.g. "Aadhaar" or "Salary Slip 1". Slip numbers are shifted to
            start at 1, since "Salary Slip 0" reads like a bug to a user.
    """
    if doc_id is None:
        return "Unknown document"
    if doc_id in _DOC_LABELS:
        return _DOC_LABELS[doc_id]
    prefix, _, index = doc_id.partition("-")
    if prefix == "SALARY_SLIP" and index.isdigit():
        return f"Salary Slip {int(index) + 1}"
    return doc_id


def format_inr(amount: float | None) -> str | None:
    """Format a rupee amount with Indian digit grouping, e.g. 150000 -> "₹1,50,000".

    Args:
        amount (float or None): The amount in rupees.

    Returns:
        str or None: The formatted amount, or None when amount is None.
            Paise are shown only when the amount is not a whole number.
    """
    if amount is None:
        return None
    rupees, paise = divmod(round(abs(amount) * 100), 100)
    digits = str(rupees)
    # Indian grouping: the last 3 digits form one group, every 2 before that.
    last_three, rest = digits[-3:], digits[:-3]
    groups = []
    while rest:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    grouped = ",".join(groups + [last_three])
    sign = "-" if amount < 0 else ""
    return f"{sign}₹{grouped}" + (f".{paise:02d}" if paise else "")


def format_month(d: date | None) -> str | None:
    """Format a date as its month, e.g. "Mar 2026". None stays None."""
    return d.strftime("%b %Y") if d else None


def format_date(d: date | None) -> str | None:
    """Format a date for display, e.g. "01 Apr 2026". None stays None."""
    return d.strftime("%d %b %Y") if d else None


def comparison_evidence(
    source_document: str | None,
    source_value: str | None,
    target_document: str | None,
    target_value: str | None,
    message: str,
) -> dict:
    """Build the five standard evidence keys described in the module docstring.

    Returns:
        dict: Ready to merge with any check-specific evidence keys.
    """
    return {
        "source_document": source_document,
        "source_value": source_value,
        "target_document": target_document,
        "target_value": target_value,
        "message": message,
    }
