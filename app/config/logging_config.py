import logging
import sys
from contextvars import ContextVar
from typing import Optional

# ContextVars to hold the tenant_id and user_id of the current request session
tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default="N/A")
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default="N/A")

class ContextFilter(logging.Filter):
    """
    Injects request-specific context parameters (tenant_id, user_id)
    into the log record dynamically using ContextVars.
    """
    def filter(self, record):
        record.tenant_id = tenant_id_var.get()
        record.user_id = user_id_var.get()
        return True

def setup_logging():
    log_format = (
        "[%(asctime)s] [%(levelname)s] [Tenant:%(tenant_id)s] [User:%(user_id)s] "
        "[%(filename)s:%(lineno)d] - %(message)s"
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    
    # Avoid duplicate handlers if already configured
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(log_format))
        handler.addFilter(ContextFilter())
        root_logger.addHandler(handler)
        
    root_logger.setLevel(logging.INFO)
    
    # Configure other library loggers
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Middleware logs HTTP requests now
