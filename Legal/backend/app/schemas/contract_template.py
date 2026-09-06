from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContractTemplateCreate(BaseModel):
    contract_type: str
    name: str
    description: str | None = None
    template_text: str
    is_active: bool = True


class ContractTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    template_text: str | None = None
    is_active: bool | None = None


class ContractTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    contract_type: str
    name: str
    description: str | None
    template_text: str
    storage_key: str | None
    version: int
    is_active: bool
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


class ContractTemplateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    contract_type: str
    name: str
    description: str | None
    version: int
    is_active: bool


class TemplateLibraryItemOut(BaseModel):
    name: str
    filename: str
    doc_kind: str
    contract_type: str
    description: str | None = None
    storage_key: str
    content_type: str | None = None
    size_bytes: int | None = None
    updated_at: datetime | None = None
    source: str = "gcs"
    db_id: int | None = None


class TemplateLibraryCategoriesOut(BaseModel):
    doc_kinds: list[dict[str, str]]
    contract_types: list[str]
    allowed_extensions: list[str]
    bucket: str
    prefix: str  # templates prefix (legacy field)
    templates_prefix: str = "legal_templates"
    contracts_prefix: str = "contracts"


class TemplateLibraryPreviewOut(BaseModel):
    name: str
    filename: str
    doc_kind: str
    contract_type: str
    storage_key: str
    content_type: str | None = None
    size_bytes: int | None = None
    text: str
    char_count: int
    truncated: bool = False
