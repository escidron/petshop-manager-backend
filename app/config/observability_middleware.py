import logging
import time
import traceback
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.modules.auth.token import decode_token
from app.config.logging_config import tenant_id_var, user_id_var

logger = logging.getLogger("api.observability")

class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Extract tenant_id and user_id from the access token securely
        token = request.cookies.get("access_token")
        
        tenant_id = "N/A"
        user_id = "N/A"
        
        if token:
            try:
                payload = decode_token(token)
                if payload:
                    tenant_id = str(payload.get("tenant_id", "N/A"))
                    user_id = str(payload.get("user_id", "N/A"))
            except Exception:
                # Ignore token decoding issues in request logging middleware
                pass

        # Set ContextVars for logging
        tenant_token = tenant_id_var.set(tenant_id)
        user_token = user_id_var.set(user_id)

        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            
            # Add security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            
            # Don't log health checks to reduce spam
            if request.url.path != "/health":
                process_time = (time.perf_counter() - start_time) * 1000
                logger.info(
                    f"[{request.method}] {request.url.path} -> "
                    f"Status {response.status_code} ({process_time:.2f}ms)"
                )
            
            return response
            
        except Exception as exc:
            # 2. Log unhandled exceptions with full tracebacks
            process_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Unhandled Exception on [{request.method}] {request.url.path} "
                f"after {process_time:.2f}ms: {str(exc)}\n"
                f"{traceback.format_exc()}"
            )
            
            error_response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Erro interno do servidor. O incidente foi registrado para análise."
                }
            )
            error_response.headers["X-Content-Type-Options"] = "nosniff"
            error_response.headers["X-Frame-Options"] = "DENY"
            error_response.headers["X-XSS-Protection"] = "1; mode=block"
            return error_response
        finally:
            # Clean up context vars
            tenant_id_var.reset(tenant_token)
            user_id_var.reset(user_token)
