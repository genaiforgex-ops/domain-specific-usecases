"""ORM models — import each here so it registers on the declarative Base."""

from app.models.agent_prompt import AgentPrompt
from app.models.ai_call import AiCall
from app.models.approval_otp import ApprovalOtp
from app.models.banner_image import BannerImage
from app.models.banner_image_message import BannerImageMessage
from app.models.banner_template import BannerTemplate
from app.models.brief import Brief
from app.models.brief_event import BriefEvent
from app.models.brief_reference_image import BriefReferenceImage
from app.models.creative import Creative
from app.models.creative_version import CreativeVersion
from app.models.design_prompt import DesignPrompt
from app.models.figma_credential import FigmaCredential
from app.models.image_prompt import ImagePrompt
from app.models.role_default import RoleDefault
from app.models.user import User

__all__ = [
    "AgentPrompt",
    "AiCall",
    "ApprovalOtp",
    "BannerImage",
    "BannerImageMessage",
    "BannerTemplate",
    "Brief",
    "BriefEvent",
    "BriefReferenceImage",
    "Creative",
    "CreativeVersion",
    "DesignPrompt",
    "FigmaCredential",
    "ImagePrompt",
    "RoleDefault",
    "User",
]
