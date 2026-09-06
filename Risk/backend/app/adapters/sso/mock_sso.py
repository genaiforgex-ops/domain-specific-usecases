from starlette.requests import Request

from app.adapters.protocols import Identity


class MockSSOAdapter:
    async def get_identity(self, request: Request) -> Identity | None:
        dev_user = request.headers.get("X-Dev-User")
        if dev_user:
            return Identity(
                email=dev_user,
                display_name=dev_user.split("@")[0].replace(".", " ").title(),
                groups=[],
            )
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            if "@" in token:
                return Identity(email=token, display_name=token.split("@")[0], groups=[])
        return None
