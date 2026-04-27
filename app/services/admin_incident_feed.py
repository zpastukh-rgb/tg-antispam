"""Обратная совместимость: реализация в admin_diagnostics_service."""

from app.services.admin_diagnostics_service import (  # noqa: F401
    extract_init_data_header_from_request_headers,
    record_http_server_error,
    record_user_incident,
)
