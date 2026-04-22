"""Runtime feature-flag registry + override store.

Rationale:
    Flags live as ``FEATURE_*`` fields on ``Settings``. Those are loaded
    from environment variables at process start and cannot be changed
    without a restart. During pilot rollout we want managers to toggle a
    subset of flags without redeploying.

    This module exposes a tiny registry that:
      - Enumerates every FEATURE_* field declared on Settings with its
        current value + declared dependency hints (parsed from the
        docstring block in config.py).
      - Persists runtime overrides in a single ``Setting`` row
        (``runtime_feature_flags``), so multiple backend workers see the
        same view within 30 seconds (TTL on a tiny in-memory cache).
      - Provides ``is_enabled(name)`` used by feature-flag-aware code
        paths when they want to honour the override rather than the
        environment value.

    The admin override is read-through: override missing -> return
    ``settings`` value. Override present -> return override. Clearing the
    override (``remove_override``) reverts to the ``settings`` value.

    We intentionally DO NOT hot-swap the ``settings`` object itself;
    callers that read ``settings.FEATURE_X`` directly keep their
    compile-time behaviour. Migrate critical paths to
    ``is_enabled("FEATURE_X")`` as rollout pilots expand.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.models.setting import Setting

logger = logging.getLogger(__name__)

_OVERRIDE_KEY = "runtime_feature_flags"
_CACHE_TTL_SECONDS = 30.0

_override_cache: dict[str, bool] | None = None
_cache_expires_at: float = 0.0


# ── Registry -----------------------------------------------------------------


@dataclass(frozen=True)
class FeatureFlag:
    name: str
    default: bool
    env_value: bool
    description: str


def _flag_description(field) -> str:
    """Extract the Required by / Depends on hint from the field description.

    Pydantic keeps the inline docstring alternative under ``description`` /
    ``title`` when available; for our plain-typed fields we fall back to
    the field name."""
    meta = getattr(field, "description", None) or ""
    return meta.strip()


def enumerate_flags(src: Settings = settings) -> list[FeatureFlag]:
    rows: list[FeatureFlag] = []
    for name, field in src.model_fields.items():
        if not name.startswith("FEATURE_"):
            continue
        if field.annotation is not bool:
            continue
        rows.append(
            FeatureFlag(
                name=name,
                default=bool(field.default) if isinstance(field.default, bool) else False,
                env_value=bool(getattr(src, name)),
                description=_flag_description(field),
            )
        )
    return sorted(rows, key=lambda f: f.name)


# ── Override store -----------------------------------------------------------


async def _read_overrides(db: AsyncSession) -> dict[str, bool]:
    row = (
        await db.execute(select(Setting).where(Setting.key == _OVERRIDE_KEY))
    ).scalar_one_or_none()
    if not row or not row.value:
        return {}
    try:
        parsed = json.loads(row.value)
    except json.JSONDecodeError:
        logger.warning("feature_flags: invalid JSON in %s setting", _OVERRIDE_KEY)
        return {}
    return {str(k): bool(v) for k, v in parsed.items() if isinstance(v, bool)}


async def _write_overrides(db: AsyncSession, overrides: dict[str, bool]) -> None:
    stmt = select(Setting).where(Setting.key == _OVERRIDE_KEY)
    row = (await db.execute(stmt)).scalar_one_or_none()
    payload = json.dumps(overrides, sort_keys=True, ensure_ascii=False)
    if row:
        row.value = payload
    else:
        db.add(Setting(key=_OVERRIDE_KEY, value=payload))
    await db.flush()
    _invalidate_cache()


def _invalidate_cache() -> None:
    global _override_cache, _cache_expires_at
    _override_cache = None
    _cache_expires_at = 0.0


async def _get_overrides_cached(db: AsyncSession) -> dict[str, bool]:
    global _override_cache, _cache_expires_at
    now = time.monotonic()
    if _override_cache is not None and now < _cache_expires_at:
        return _override_cache
    _override_cache = await _read_overrides(db)
    _cache_expires_at = now + _CACHE_TTL_SECONDS
    return _override_cache


# ── Public API ---------------------------------------------------------------


async def list_flags(db: AsyncSession) -> list[dict]:
    """Return every FEATURE_* with env + override view, ready for the UI."""
    overrides = await _read_overrides(db)
    rows: list[dict] = []
    for flag in enumerate_flags():
        override = overrides.get(flag.name)
        effective = override if override is not None else flag.env_value
        rows.append(
            {
                "name": flag.name,
                "default": flag.default,
                "env_value": flag.env_value,
                "override": override,
                "effective": effective,
                "description": flag.description,
            }
        )
    return rows


async def set_override(db: AsyncSession, *, name: str, enabled: bool | None) -> dict[str, bool]:
    """Persist an override for ``name``. Pass ``enabled=None`` to clear it."""
    _validate_known_flag(name)
    overrides = await _read_overrides(db)
    if enabled is None:
        overrides.pop(name, None)
    else:
        overrides[name] = bool(enabled)
    await _write_overrides(db, overrides)
    return overrides


async def clear_overrides(db: AsyncSession) -> None:
    """Wipe every runtime override (fail-safe rollback button)."""
    await _write_overrides(db, {})


async def is_enabled(db: AsyncSession, name: str) -> bool:
    """Resolve the effective value of a flag (env + override)."""
    _validate_known_flag(name)
    overrides = await _get_overrides_cached(db)
    if name in overrides:
        return overrides[name]
    return bool(getattr(settings, name, False))


def _validate_known_flag(name: str) -> None:
    if not name.startswith("FEATURE_"):
        raise ValueError(f"Not a feature flag: {name}")
    if name not in settings.model_fields:
        raise ValueError(f"Unknown feature flag: {name}")
