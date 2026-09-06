"""Central IAM platform client for user-role resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IamUserRole:
    email: str
    roles: list[str]


class IamServiceError(Exception):
    """Raised when the Central IAM API returns an unexpected response."""


class IamService:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = (base_url or settings.iam_backend_url).rstrip("/")
        self.client_id = client_id or settings.keycloak_client_id
        self.client_secret = client_secret or settings.iam_client_secret
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return settings.iam_sync_enabled

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Client-Secret": self.client_secret,
        }

    async def resolve_all_users(self) -> list[IamUserRole]:
        """Fetch all users and roles registered for this client."""
        if not self.configured:
            raise IamServiceError("IAM client is not configured (missing secret or client id)")

        url = f"{self.base_url}/user-roles/resolve"
        payload = {"client_id": self.client_id}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers())

        if response.status_code != 200:
            logger.error("IAM resolve_all failed (%s): %s", response.status_code, response.text)
            raise IamServiceError(f"IAM user-roles/resolve failed with status {response.status_code}")

        data = response.json()
        users = data.get("users") or []
        result: list[IamUserRole] = []
        for entry in users:
            email = str(entry.get("user_email") or entry.get("email") or "").strip().lower()
            if not email:
                continue
            roles = [str(r).strip().lower() for r in (entry.get("roles") or []) if str(r).strip()]
            result.append(IamUserRole(email=email, roles=roles))
        return result

    async def resolve_user(self, email: str) -> IamUserRole | None:
        """Fetch roles for a single user. Returns None when the user has no IAM assignment."""
        if not self.configured:
            raise IamServiceError("IAM client is not configured (missing secret or client id)")

        url = f"{self.base_url}/user-roles/resolve"
        payload = {"client_id": self.client_id, "email": email.strip().lower()}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers())

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.error("IAM resolve_user failed (%s): %s", response.status_code, response.text)
            raise IamServiceError(f"IAM user-roles/resolve failed with status {response.status_code}")

        data = response.json()
        roles = [str(r).strip().lower() for r in (data.get("roles") or []) if str(r).strip()]
        resolved_email = str(data.get("email") or data.get("user_email") or email).strip().lower()
        if not roles:
            return None
        return IamUserRole(email=resolved_email, roles=roles)
