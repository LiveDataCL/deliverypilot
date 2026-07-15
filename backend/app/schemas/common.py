from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """The shape every API error responds with (CLAUDE.md §4)."""

    detail: str
    code: str
