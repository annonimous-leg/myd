# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Configuración de logging estructurado.
"""
import structlog
import logging
import sys


def configure_logging():
    """Configura logging estructurado para Megalodon."""
    # PENDIENTE J (request-id end-to-end): instala el LogRecordFactory
    # que hace que request_id llegue a CUALQUIER log del proceso (tanto
    # app.* vía structlog como tezcatlipoca.* vía stdlib logging
    # directo). Ver app/core/observability.py para el detalle de por
    # qué es un LogRecordFactory y no un logging.Filter.
    from app.core.observability import install_request_id_log_factory
    install_request_id_log_factory()

    structlog.configure(
        processors=[
            # merge_contextvars primero: toma lo que
            # RequestContextMiddleware puso con bind_contextvars
            # (request_id) y lo mezcla al evento ANTES de que el resto
            # de los processors lo froteen -- así "request_id" queda
            # como una key más del JSON final, no algo que cada
            # logger.info(...) tenga que pasar a mano.
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
