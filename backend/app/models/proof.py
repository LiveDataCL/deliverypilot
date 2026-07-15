from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, ForeignKeyConstraint, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ProofType


class Proof(Base):
    __tablename__ = "proofs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "business_id"],
            ["orders.id", "orders.business_id"],
            name="fk_proofs_order_business",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    type: Mapped[ProofType] = mapped_column(SAEnum(ProofType, name="proof_type"), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    receiver_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
