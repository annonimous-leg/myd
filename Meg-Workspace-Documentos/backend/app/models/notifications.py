# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelo de notificaciones persistentes (canal "panel").

RESTAURADO: app/modules/notifications/service.py ya importaba
NotificationLog (dentro de _guardar_panel/obtener_pendientes/marcar_leida)
pero el modelo nunca se había creado -- mismo patrón de import roto que
ValidacionPropuesta, sólo que aquí el import es diferido (dentro del
cuerpo de cada método), así que el módulo importaba bien pero cualquier
notificación de canal "panel" tronaba en cuanto se usaba.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, ForeignKey
from app.db.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class NotificationLog(Base, UUIDMixin):
    """Registro de una notificación enviada por el canal "panel"
    (notificaciones persistentes que el usuario ve dentro de la app,
    a diferencia de email/SMS/WebSocket que son "fire and forget").

    El tenant es obligatorio para notificaciones persistidas en panel; el
    destinatario no es un boundary de seguridad suficiente porque puede ser
    reutilizado entre organizaciones.
    """
    __tablename__ = "notification_logs"

    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    destinatario: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # email, sms, websocket, panel
    asunto: Mapped[str] = mapped_column(String(500), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)

    # BUG EVITADO: 'metadata' es un atributo reservado de la clase base
    # declarativa de SQLAlchemy (Base.metadata es la colección MetaData).
    # Definir una columna mapeada con ese mismo nombre revienta con
    # InvalidRequestError en cuanto se define la clase. Se usa 'metadatos'
    # (consistente con el resto del código en español, p. ej.
    # Levantamiento.metadatos) y así se evita el choque de nombres.
    metadatos: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", nullable=False, index=True)
    # PENDIENTE | LEIDA | LEGACY_UNSCOPED

    leida_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
