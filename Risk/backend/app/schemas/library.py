from datetime import datetime
from uuid import UUID

from app.schemas.common import ORMBase


class RegulationDocumentResponse(ORMBase):
    id: UUID
    regulator: str
    instrument: str
    source_doc: str
    filename: str
    status: str
    uploaded_by: UUID | None
    created_at: datetime
    activated_at: datetime | None
    archived_at: datetime | None
    clause_count: int = 0
