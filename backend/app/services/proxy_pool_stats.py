"""Health-score weighting for ``get_random_healthy`` and pool stats math.

Kept in its own module so the weighting is unit-testable without a DB.
``ValidProxyService`` stays the only caller — this is not a new service
layer, just the small helpers behind it.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.models.valid_proxy import ValidProxy

# Floor applied so failure-only proxies remain theoretically reachable —
# a proxy that failed every validation is still preferred over a dead pool.
MIN_SUCCESS_WEIGHT = 0.01

# Weight of a proxy with no validation data (never checked).
NEUTRAL_SUCCESS_WEIGHT = 0.5

# How many random candidates are drawn from SQL before the weighted pick.
CANDIDATE_LIMIT = 50



def success_weight(proxy: ValidProxy) -> float:
    """Weight = recent success ratio, floored so failures stay reachable.

    - ``success / (success + failure)`` when the proxy has validation data.
    - ``NEUTRAL_SUCCESS_WEIGHT`` when never checked (neutral).
    - ``MIN_SUCCESS_WEIGHT`` floor for all-failure proxies.
    """
    total = max(proxy.success_count, 0) + max(proxy.failure_count, 0)
    if total <= 0:
        return NEUTRAL_SUCCESS_WEIGHT
    ratio = max(proxy.success_count, 0) / total
    return max(MIN_SUCCESS_WEIGHT, ratio)


def weighted_pick[T](candidates: Sequence[T], weights: Sequence[float]) -> T:
    """Single weighted-random draw (deterministic under ``random.seed``)."""
    return random.choices(list(candidates), weights=list(weights), k=1)[0]


def expiring_window_bound(now: datetime, ttl_window_seconds: int) -> datetime:
    """``expires_at`` upper bound for the expiring-soon count."""
    return now + timedelta(seconds=ttl_window_seconds)


def utcnow() -> datetime:
    return datetime.now(UTC)
