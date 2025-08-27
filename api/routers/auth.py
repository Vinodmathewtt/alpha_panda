from fastapi import APIRouter, Depends
from dependency_injector.wiring import inject, Provide
from dataclasses import asdict

from app.containers import AppContainer
from services.auth.service import AuthService

router = APIRouter(tags=["Authentication"])


@router.get("/auth/status")
@inject
async def get_auth_status(
    auth_service: AuthService = Depends(Provide[AppContainer.auth_service]),
):
    """
    Check Zerodha authentication status.
    """
    is_authenticated = auth_service.is_authenticated()
    user_profile = None
    
    if is_authenticated:
        user_profile = await auth_service.get_current_user_profile()
    
    return {
        "authenticated": is_authenticated,
        "provider": "zerodha",
        "user_profile": asdict(user_profile) if user_profile else None
    }