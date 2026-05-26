"""F-017 — generic optimistic-concurrency-control helper.

Three call sites care about lost-write races today: ``quotes``,
``contracts``, ``opportunities``. All three want the same pattern:

  1. Client fetches row v=N.
  2. Client submits an UPDATE with ``expected_row_version=N``.
  3. Server: ``UPDATE ... SET row_version=N+1 WHERE id=ID AND row_version=N``
  4. Affected rows == 0 → another writer raced. Return 409 + the
     server's current row so the client can do a three-way merge.

This helper isolates step 3 + 4 so endpoints can do::

    new_version = await guarded_update(
        db, Quote, id_=quote_id, expected_version=payload.row_version,
        updates={"discount_pct": payload.discount_pct, ...},
    )

If the row was changed concurrently, :class:`OptimisticLockConflict`
is raised; the endpoint converts it to a 409 with the current state.

Keeping this in one place ensures every entity adopting OCC behaves
identically (same exception, same fields, same client contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


class OptimisticLockConflict(Exception):
    """Raised when the row's ``row_version`` doesn't match the
    expected version supplied by the client.

    The HTTP layer should translate to:

        HTTP/1.1 409 Conflict
        {
          "error": {
            "code": "OPTIMISTIC_LOCK_CONFLICT",
            "message": "...",
            "current_row_version": <server's current value>
          }
        }
    """

    def __init__(self, *, model: str, id_: int, expected: int):
        self.model = model
        self.id_ = id_
        self.expected = expected
        super().__init__(
            f"{model}[{id_}] was changed by another writer "
            f"(expected row_version={expected})"
        )


@dataclass(frozen=True)
class UpdateResult:
    rows_changed: int
    new_row_version: int


async def guarded_update(
    db: AsyncSession,
    model: Any,
    *,
    id_: int,
    expected_version: int,
    updates: dict,
) -> UpdateResult:
    """Apply ``updates`` to row ``id_`` iff ``row_version`` matches.

    Returns :class:`UpdateResult` on success.
    Raises :class:`OptimisticLockConflict` when 0 rows match —
    either the row was deleted, doesn't exist, OR was concurrently
    updated. Caller decides which by re-reading.

    ``updates`` may *not* contain ``row_version`` (we bump it for you).
    """
    if "row_version" in updates:
        raise ValueError("Do not set row_version manually — guarded_update bumps it.")

    new_version = expected_version + 1
    stmt = (
        update(model)
        .where(model.id == id_, model.row_version == expected_version)
        .values(**updates, row_version=new_version)
    )
    result = await db.execute(stmt)
    rows = result.rowcount or 0
    if rows == 0:
        raise OptimisticLockConflict(
            model=model.__name__, id_=id_, expected=expected_version
        )
    return UpdateResult(rows_changed=rows, new_row_version=new_version)
