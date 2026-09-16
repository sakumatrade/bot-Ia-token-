"""Domain engines: risk, safety, lineage, treasury and learning.

Layering (spec section 58) — a lower layer may never bypass a higher one:

    SECURITY -> CUSTODY -> TREASURY -> EXECUTION -> RISK -> STRATEGY -> LEARNING

In practice: Learning proposes, Strategy proposes, Risk decides, Execution
only ever acts on a RiskEngine-approved decision, and Execution itself must
respect Custody/Treasury/Security (wallet abstractions, treasury limits).
"""
