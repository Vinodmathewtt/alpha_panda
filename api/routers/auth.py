from fastapi import APIRouter, Depends, Request
from dependency_injector.wiring import inject, Provide
from dataclasses import asdict
import time

from app.containers import AppContainer
from services.auth.service import AuthService
from core.logging.enhanced_logging import get_api_logger, get_audit_logger, get_error_logger

router = APIRouter(tags=["Authentication"])

# Initialize loggers
api_logger = get_api_logger("auth_api")
audit_logger = get_audit_logger("auth_audit")
error_logger = get_error_logger("auth_errors")


@router.get("/auth/status")
@inject
async def get_auth_status(
    request: Request,
    auth_service: AuthService = Depends(Provide[AppContainer.auth_service]),
):
    """
    Check Zerodha authentication status.
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    api_logger.info("Authentication status check requested",
                   client_ip=client_ip,
                   endpoint="/auth/status",
                   method="GET")
    
    try:
        is_authenticated = auth_service.is_authenticated()
        user_profile = None
        
        if is_authenticated:
            user_profile = await auth_service.get_current_user_profile()
            
            # Log successful authentication check to audit log
            audit_logger.info("Authentication status verified",
                            user_id=getattr(user_profile, 'user_id', 'unknown') if user_profile else 'unknown',
                            authenticated=True,
                            client_ip=client_ip,
                            action="AUTH_STATUS_CHECK")
        
        processing_time = (time.time() - start_time) * 1000
        
        api_logger.info("Authentication status check completed",
                       client_ip=client_ip,
                       authenticated=is_authenticated,
                       processing_time_ms=processing_time,
                       response_code=200)
        
        return {
            "authenticated": is_authenticated,
            "provider": "zerodha",
            "user_profile": asdict(user_profile) if user_profile else None
        }
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        error_logger.error("Authentication status check failed",
                          client_ip=client_ip,
                          error=str(e),
                          processing_time_ms=processing_time,
                          exc_info=True)
        
        api_logger.error("Authentication API error",
                        client_ip=client_ip,
                        error=str(e),
                        processing_time_ms=processing_time,
                        response_code=500)
        
        raise