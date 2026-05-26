"""V2 sidecar dataclasses — pure data carriers for V2 row builders (PRP-35).

The V2 row builders (``rows_v2.py``) accept every input beyond the V1 surface
through these two frozen dataclasses. They are pure data — stdlib only,
``app/shared/**`` leaf-level — so the DB-loading side (``v2_loaders.py`` in the
forecasting slice) stays cross-slice-import-free for ``app/shared``.

Alignment contract (the row builders raise ``ValueError`` when violated):

- Every per-day tuple aligned with ``dates`` (or ``test_dates`` for the future
  sidecar) MUST have the same length as that ``dates`` tuple WHENEVER the
  owning :class:`~app.shared.feature_frames.contract_v2.FeatureGroup` is
  enabled. Length mismatch is a programmer/contract error, not a missing-data
  case.
- Sets / mappings (``promo_dates``, ``holiday_dates``, ``weather_per_day``,
  ``macro_per_day``) are queried by date membership. A date with no entry → a
  ``NaN`` cell at that row, NEVER a zero-fill.
- ``replenishment_event_dates`` / ``replenishment_event_qty`` are event-time
  arrays (one entry per receipt event), NOT per-day-aligned. Their only
  alignment invariant is length parity between the two tuples.

When a feature group is NOT enabled, the matching sidecar fields MAY be empty
tuples / dicts; the row builder will not read them. When a group IS enabled
but a per-day source value is missing (``on_hand_qty[i] is None``, no entry in
``weather_per_day[dates[i]]``, no replenishment event before day ``i``), the
cell is NaN. HGBR consumes NaN natively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class V2HistoricalSidecar:
    """Inputs the historical V2 builder needs beyond the V1 surface.

    See module docstring for the alignment invariants. Empty defaults mean
    "this group's data is not supplied" — safe to leave when the matching
    :class:`FeatureGroup` is disabled, an error if the group IS enabled
    (caught loud in the row builder).

    Attributes:
        promo_dates: V1 carryover — days a promotion covered.
        holiday_dates: V1 carryover — calendar holiday days.
        launch_date: V1 carryover — product's launch date, or None.
        discontinue_date: Product's discontinue date, or None.
        on_hand_qty: Per-day on-hand inventory, aligned with ``dates``;
            entries MAY be None when the snapshot is absent.
        is_stockout_per_day: Per-day stockout flag, aligned with ``dates``.
        replenishment_event_dates: Event-time dates of replenishment receipts
            within the data window, sorted ascending.
        replenishment_event_qty: Event-time received quantities; same length
            as ``replenishment_event_dates``.
        returns_qty_per_day: Per-day returned-units count, aligned with
            ``dates``; ``0`` for days with no return.
        promo_kinds_per_day: Per-day set of active promotion kinds (subset of
            ``{"pct_off", "bogo", "bundle", "markdown"}``); empty set on days
            with no promotion.
        promo_discount_pct_per_day: Per-day discount fraction (0.0..1.0);
            ``0.0`` on days with no promotion.
        weather_per_day: ``{date: {signal_name: value}}`` for store-specific
            weather signals; absent dates → NaN cell.
        macro_per_day: ``{date: {signal_name: value}}`` for chain-wide macro
            signals; absent dates → NaN cell.
    """

    # V1 carryover
    promo_dates: frozenset[date] = field(default_factory=frozenset)
    holiday_dates: frozenset[date] = field(default_factory=frozenset)
    launch_date: date | None = None
    # Lifecycle
    discontinue_date: date | None = None
    # Inventory (per-day, aligned with dates)
    on_hand_qty: tuple[float | None, ...] = ()
    is_stockout_per_day: tuple[bool, ...] = ()
    # Replenishment (timestamps, NOT per-day)
    replenishment_event_dates: tuple[date, ...] = ()
    replenishment_event_qty: tuple[int, ...] = ()
    # Returns (per-day quantity, 0 when no return)
    returns_qty_per_day: tuple[int, ...] = ()
    # Promotion (per-day kind set + discount pct)
    promo_kinds_per_day: tuple[frozenset[str], ...] = ()
    promo_discount_pct_per_day: tuple[float, ...] = ()
    # Exogenous (date → signal_name → value)
    weather_per_day: dict[date, dict[str, float]] = field(default_factory=dict)
    macro_per_day: dict[date, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class V2FutureSidecar:
    """Inputs the future V2 builder accepts when re-forecasting.

    EVERY field is either knowable at origin ``T`` (calendar holidays,
    ``launch_date`` / ``discontinue_date``) or *posited by the caller as an
    assumption* (price, promotion). For truly-unknowable groups (weather,
    macro) the caller MAY supply observed-then-projected values or leave the
    dict empty → the corresponding column is NaN at the horizon row.

    See module docstring for alignment invariants — all per-day tuples align
    with ``test_dates``.
    """

    holiday_dates: frozenset[date] = field(default_factory=frozenset)
    launch_date: date | None = None
    discontinue_date: date | None = None
    # Per-day exogenous inputs (None / 0.0 / empty == "not posited" → NaN cell)
    price_factor_per_day: tuple[float | None, ...] = ()
    promo_active_per_day: tuple[bool, ...] = ()
    promo_kinds_per_day: tuple[frozenset[str], ...] = ()
    promo_discount_pct_per_day: tuple[float, ...] = ()
    # Phase 2 future inputs — typically all-None / empty for V2 MVP
    inventory_on_hand_per_day: tuple[float | None, ...] = ()
    weather_per_day: dict[date, dict[str, float]] = field(default_factory=dict)
    macro_per_day: dict[date, dict[str, float]] = field(default_factory=dict)
