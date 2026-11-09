from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import aiohttp

class WebODMClient:
    def __init__(self):
        # CORREGIDO (contra-auditoría V9): el default anterior era
        # "http://localhost:8000" -- dentro del contenedor `api` de
        # docker-compose.prod.yml, ese es el propio puerto de uvicorn
        # (ver command: "uvicorn app.main:app --host 0.0.0.0 --port 8000"),
        # no WebODM. Sin WEBODM_URL configurado, este cliente le habría
        # pegado calladamente al propio backend en vez de fallar de forma
        # reconocible. WebODM es una capacidad externa opcional (mismo
        # patrón que ya usa app/main.py: "photogrammetry":
        # CONFIGURED si hay WEBODM_URL, si no CONFIG_REQUIRED) -- este
        # cliente ahora sigue ese mismo criterio: sin URL configurada, no
        # intenta adivinar, regresa error explícito.
        self.base_url = os.getenv("WEBODM_URL")
        self.token = os.getenv("WEBODM_TOKEN", "")
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"JWT {self.token}"
        return headers

    def _no_configurado(self) -> Dict[str, Any]:
        return {
            "error": "WEBODM_URL no está configurado -- fotogrametría es una "
                     "capacidad externa opcional (ver docker-compose.prod.yml). "
                     "No se intentó ninguna llamada de red.",
            "status": "config_required",
        }

    async def get_projects(self) -> List[Dict]:
        if not self.base_url:
            return []
        url = f"{self.base_url}/api/projects/"
        async with self.http.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data if isinstance(data, list) else data.get("results", [])
            return []

    async def create_project(self, name: str, description: str = "") -> Dict[str, Any]:
        """Crea un Project en WebODM (POST /api/projects/).

        CORREGIDO (F-06): routers/photogrammetry.py -> POST /projects ya
        llamaba a w.create_project(name, description), pero este cliente
        solo tenía get_projects/create_task/get_task_status -- create_project
        no existía, así que la ruta (registrada, autenticada, con plan
        mínimo PRO) tronaba con AttributeError en cuanto se invocaba.
        Confirmado contra la documentación oficial de WebODM
        (docs.webodm.org/reference/project/): "Create a project" es
        POST /api/projects/ con name (requerido) y description (opcional),
        y regresa el proyecto creado con su "id" -- endpoint real y
        distinto de create_task (que sube imágenes a un proyecto YA
        existente para lanzar un Task de fotogrametría).
        """
        if not self.base_url:
            return self._no_configurado()
        if not name:
            return {"error": "name es requerido para crear un proyecto"}
        url = f"{self.base_url}/api/projects/"
        payload = {"name": name, "description": description or ""}
        try:
            # data=payload se codifica como application/x-www-form-urlencoded
            # (igual que create_task más abajo) -- NO usar self._headers()
            # aquí, que fuerza Content-Type: application/json y rompería el
            # parseo en WebODM si el cuerpo real va form-encoded.
            async with self.http.post(
                url, data=payload, headers={"Authorization": f"JWT {self.token}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                return {"error": f"WebODM returned HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def create_task(self, project_id: int, images: List[str], options: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not self.base_url:
            return self._no_configurado()
        try:
            url = f"{self.base_url}/api/projects/{project_id}/tasks/"
            payload = {
                "name": f"Task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                "options": options or {},
            }

            data = aiohttp.FormData()
            data.add_field("name", payload["name"])
            data.add_field("options", json.dumps(payload["options"]))

            for i, img_path in enumerate(images[:50]):
                abs_path = Path(img_path).expanduser().resolve()
                if ".." in str(abs_path) or "~" in str(img_path):
                    raise ValueError(f"Invalid path: {img_path}")
                if not abs_path.exists() or not abs_path.is_file():
                    raise FileNotFoundError(f"Image not found: {img_path}")
                data.add_field(f"images[{i}]", abs_path.open("rb"))

            async with self.http.post(
                url,
                data=data,
                headers={"Authorization": f"JWT {self.token}"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                return {"error": f"WebODM returned HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def get_task_status(self, project_id: int, task_id: str) -> Dict[str, Any]:
        if not self.base_url:
            return self._no_configurado()
        url = f"{self.base_url}/api/projects/{project_id}/tasks/{task_id}/"
        async with self.http.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.json()
            return {"error": f"WebODM returned HTTP {resp.status}"}
