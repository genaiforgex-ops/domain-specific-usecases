from fastapi import APIRouter

from app.api.v1 import (
    admin,
    agents,
    auth,
    classifications,
    cross,
    dashboards,
    forms,
    library,
    metrics,
    projects,
    vendors,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(classifications.router)
api_router.include_router(agents.router)
api_router.include_router(vendors.router)
api_router.include_router(projects.router)
api_router.include_router(cross.router)
api_router.include_router(forms.router)
api_router.include_router(admin.router)
api_router.include_router(dashboards.router)
api_router.include_router(library.router)
api_router.include_router(metrics.router)
