"""Contract template CRUD helpers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contract_template import ContractTemplate


def list_templates(db: Session, contract_type: str | None = None, active_only: bool = True):
    q = select(ContractTemplate).order_by(ContractTemplate.name)
    if contract_type:
        q = q.where(ContractTemplate.contract_type == contract_type)
    if active_only:
        q = q.where(ContractTemplate.is_active.is_(True))
    return db.execute(q).scalars().all()


def get_template(db: Session, template_id: int) -> ContractTemplate | None:
    return db.get(ContractTemplate, template_id)
