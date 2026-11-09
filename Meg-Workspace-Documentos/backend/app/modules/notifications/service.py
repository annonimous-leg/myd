# Copyright © 2026 Cristian Rodriguez
"""Servicio de notificaciones — SMTP + SMS + WebSocket + Panel."""
import smtplib
from typing import Optional, Dict, Any, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.config import settings
from app.core.errors import MegalodonException, ErrorCode
from enum import Enum


class NotificationError(MegalodonException):
    """Error al enviar/persistir una notificación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.NORMATIVO_GENERICO, message, 502, details)


class TipoNotificacion(str, Enum):
    """Canales de notificación soportados por NotificationService.enviar()."""
    EMAIL = "email"
    SMS = "sms"
    WEBSOCKET = "websocket"
    PANEL = "panel"
    TODOS = "all"


class CanalNotificacion(str, Enum):
    """Nombres de canal devueltos en el resultado de cada envío."""
    SMTP = "SMTP"
    TWILIO = "Twilio"
    WEBSOCKET = "WebSocket"
    PANEL = "Panel"


class NotificationService:
    """Servicio de notificaciones multi-canal."""

    def __init__(self):
        self.smtp_host = getattr(settings, 'SMTP_HOST', None)
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_user = getattr(settings, 'SMTP_USER', None)
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
        self.smtp_tls = getattr(settings, 'SMTP_TLS', True)
        self.twilio_sid = getattr(settings, 'TWILIO_SID', None)
        self.twilio_token = getattr(settings, 'TWILIO_TOKEN', None)
        self.twilio_from = getattr(settings, 'TWILIO_FROM_NUMBER', None)

    async def enviar(
        self,
        db: AsyncSession,
        tipo: str,  # email, sms, websocket, panel, all
        destinatario: str,
        asunto: str,
        mensaje: str,
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Envía notificación por el canal especificado."""
        resultados = {}

        if tipo in ("email", "all"):
            resultados["email"] = await self._enviar_email(destinatario, asunto, mensaje)
        if tipo in ("sms", "all"):
            resultados["sms"] = await self._enviar_sms(destinatario, mensaje)
        if tipo in ("websocket", "all"):
            resultados["websocket"] = await self._enviar_websocket(destinatario, asunto, mensaje, metadata)
        if tipo in ("panel", "all"):
            resultados["panel"] = await self._guardar_panel(db, destinatario, asunto, mensaje, metadata, tenant_id=tenant_id)

        return {
            "enviado": any(r.get("enviado") for r in resultados.values()),
            "canales": resultados,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _enviar_email(
        self,
        destinatario: str,
        asunto: str,
        mensaje: str,
    ) -> Dict[str, Any]:
        """Envía email vía SMTP."""
        if not all([self.smtp_host, self.smtp_user, self.smtp_password]):
            return {"enviado": False, "motivo": "SMTP no configurado"}

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = destinatario
            msg["Subject"] = asunto
            msg.attach(MIMEText(mensaje, "html" if "<" in mensaje else "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            return {"enviado": True, "estado": "SENT", "canal": "SMTP"}
        except Exception as e:
            return {"enviado": False, "motivo": str(e)}

    async def _enviar_sms(
        self,
        destinatario: str,
        mensaje: str,
    ) -> Dict[str, Any]:
        """Envía SMS vía Twilio."""
        if not all([self.twilio_sid, self.twilio_token, self.twilio_from]):
            return {"enviado": False, "motivo": "SMS no configurado (Twilio)"}

        try:
            from twilio.rest import Client
            client = Client(self.twilio_sid, self.twilio_token)
            message = client.messages.create(
                body=mensaje[:1600],  # Twilio limit
                from_=self.twilio_from,
                to=destinatario,
            )
            return {"enviado": True, "estado": "SENT", "canal": "Twilio", "sid": message.sid}
        except ImportError:
            return {"enviado": False, "motivo": "Librería twilio no instalada"}
        except Exception as e:
            return {"enviado": False, "motivo": str(e)}

    async def _enviar_websocket(
        self,
        destinatario: str,
        asunto: str,
        mensaje: str,
        metadata: Optional[Dict[str, Any]],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Envía notificación vía WebSocket."""
        # El WebSocket manager se inyecta desde el main app
        from app.api.v1.websocket import manager
        payload = {
            "tipo": "notificacion",
            "destinatario": destinatario,
            "asunto": asunto,
            "mensaje": mensaje,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            # destinatario es el user_id lógico del canal WebSocket.
            # Nunca se usa broadcast aquí: las notificaciones son datos
            # privados y un broadcast por capa/usuario podría cruzar tenants.
            await manager.send_to_user(destinatario, payload)
            return {"enviado": True, "estado": "SENT", "canal": "WebSocket"}
        except Exception as e:
            return {"enviado": False, "motivo": str(e)}

    async def _guardar_panel(
        self,
        db: AsyncSession,
        destinatario: str,
        asunto: str,
        mensaje: str,
        metadata: Optional[Dict[str, Any]],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Guarda notificación persistente en panel."""
        from app.models.notifications import NotificationLog
        effective_tenant_id = tenant_id or (metadata or {}).get("tenant_id")
        if not effective_tenant_id:
            raise NotificationError("No se puede persistir una notificación sin tenant_id.")
        log = NotificationLog(
            destinatario=destinatario,
            tenant_id=effective_tenant_id,
            tipo="panel",
            asunto=asunto,
            mensaje=mensaje,
            metadatos=metadata,
            estado="PENDIENTE",
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return {"enviado": True, "estado": "PERSISTED", "canal": "Panel", "log_id": str(log.id)}

    async def obtener_pendientes(
        self,
        db: AsyncSession,
        destinatario: str,
        limite: int = 50,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Obtiene notificaciones pendientes del panel."""
        from app.models.notifications import NotificationLog
        if not tenant_id:
            raise NotificationError("tenant_id requerido para consultar notificaciones persistentes.")
        stmt = select(NotificationLog).where(
            and_(
                NotificationLog.tenant_id == tenant_id,
                NotificationLog.destinatario == destinatario,
                NotificationLog.estado == "PENDIENTE",
            )
        ).order_by(NotificationLog.created_at.desc()).limit(limite)
        logs = (await db.execute(stmt)).scalars().all()
        return [{"id": str(l.id), "asunto": l.asunto, "mensaje": l.mensaje,
                 "created_at": l.created_at.isoformat()} for l in logs]

    async def marcar_leida(
        self,
        db: AsyncSession,
        notification_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Marca una notificación como leída."""
        from app.models.notifications import NotificationLog
        if not tenant_id:
            raise NotificationError("tenant_id requerido para modificar notificaciones persistentes.")
        result = await db.execute(
            select(NotificationLog).where(
                NotificationLog.id == notification_id,
                NotificationLog.tenant_id == tenant_id,
            )
        )
        log = result.scalar_one_or_none()
        if log:
            log.estado = "LEIDA"
            log.leida_at = datetime.utcnow()
            await db.commit()
            return True
        return False