from pydantic import BaseModel


class UserProfileOut(BaseModel):
    """Minimal read used to exercise + test the tenant-isolation mechanism in
    Fase 0 (GET /api/v1/users/{user_id}). Full Personal CRUD (create, invite by
    link, activate/deactivate) is a Fase 1 task."""

    id: int
    business_id: int
    role: str
    email: str
    phone: str | None
    is_active: bool

    model_config = {"from_attributes": True}
