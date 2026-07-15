from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """The shape every API error responds with (CLAUDE.md §4)."""

    detail: str
    code: str


class Page(BaseModel, Generic[T]):
    """Shared envelope for every listing endpoint (CLAUDE.md §2: 'Paginación en
    todo endpoint que liste. Nunca retornes "todos los registros" sin límite.')."""

    items: list[T]
    total: int
    limit: int
    offset: int
