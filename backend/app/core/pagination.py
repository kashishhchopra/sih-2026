"""Bounded list-query parameters shared across list endpoints.

`list_tourists` and `list_incidents` used to run `db.query(...).all()` with no
bound at all -- fine at demo scale (a handful of seeded rows), but a genuine
resource risk once ping/incident history accumulates: every request would load
the entire table into Python regardless of what the client needed.

This intentionally does NOT change response shape (still a plain JSON list) to
avoid a breaking change across every frontend page that already consumes these
endpoints as arrays. The total row count is returned in an `X-Total-Count`
header instead, which a future paged UI can read without an API redesign.
"""
from fastapi import Query
from sqlalchemy.orm import Query as ORMQuery


class PageParams:
    def __init__(
        self,
        limit: int = Query(200, ge=1, le=500, description="Max rows to return."),
        offset: int = Query(0, ge=0, description="Rows to skip."),
    ) -> None:
        self.limit = limit
        self.offset = offset

    def apply(self, query: ORMQuery) -> ORMQuery:
        return query.offset(self.offset).limit(self.limit)
