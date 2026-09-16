"""Read-side aggregation services that back the Local API (spec section 38).

Kept separate from the API layer so they're testable without spinning up
FastAPI/HTTP at all, and separate from the write-side engines (risk,
thesis, loan, ...) which already live under ``engines/``.
"""
