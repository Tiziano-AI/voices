from datetime import UTC, datetime


def utc_now() -> str:
    """Return the current UTC timestamp in persisted schema-v2 form."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_compact() -> str:
    """Return the current UTC timestamp in render-artifact basename form."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
