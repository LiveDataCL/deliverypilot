from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, server_default="piloto")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, server_default="America/Santiago")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="CLP")
    settings_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
