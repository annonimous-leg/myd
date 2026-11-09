"""Snapshot Store - Persistencia real en disco con JSON."""
import os
import json
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from pathlib import Path

from core.observability import build_logger

logger = build_logger("tu_osint.snapshot_store")


class SnapshotStore:
    """Almacena snapshots con persistencia en disco (JSON)."""

    def __init__(self, data_dir: str = "./data/snapshots"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.data_dir / "index.json"
        self.snapshots: Dict[str, Dict] = self._load_index()

    def _load_index(self) -> Dict[str, Dict]:
        if self.index_file.exists():
            try:
                with open(self.index_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                # Un index.json corrupto significa que se pierde la
                # referencia a TODOS los snapshots existentes en disco
                # (los archivos .json individuales siguen ahí, pero
                # list_snapshots()/get_snapshot() ya no los "ven"). Es un
                # problema de datos real, no un caso esperado -- se sube a
                # warning en vez de tragarlo en silencio.
                logger.warning(f"snapshot index corrupto en {self.index_file}, se reinicia vacío: {e}")
        return {}

    def _save_index(self):
        with open(self.index_file, "w") as f:
            json.dump(self.snapshots, f, indent=2, default=str)

    def _snapshot_path(self, snapshot_id: str) -> Path:
        return self.data_dir / f"{snapshot_id}.json"

    def create_snapshot(self, label: str, data: Dict[str, Any]) -> str:
        timestamp = datetime.now(timezone.utc)
        payload = json.dumps(data, sort_keys=True, default=str)
        snapshot_id = hashlib.sha256(
            f"{label}:{timestamp.isoformat()}:{payload}".encode()
        ).hexdigest()[:16]

        snapshot = {
            "id": snapshot_id,
            "label": label,
            "timestamp": timestamp.isoformat(),
            "data_keys": list(data.keys()),
            "size_bytes": len(payload.encode()),
        }

        snapshot_path = self._snapshot_path(snapshot_id)
        with open(snapshot_path, "w") as f:
            json.dump({"metadata": snapshot, "data": data}, f, indent=2, default=str)

        self.snapshots[snapshot_id] = snapshot
        self._save_index()
        return snapshot_id

    def list_snapshots(self) -> List[Dict]:
        return [
            {"id": sid, "label": meta["label"], "timestamp": meta["timestamp"],
             "size_bytes": meta["size_bytes"]}
            for sid, meta in sorted(self.snapshots.items(), key=lambda x: x[1]["timestamp"], reverse=True)
        ]

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        snapshot_path = self._snapshot_path(snapshot_id)
        if snapshot_path.exists():
            try:
                with open(snapshot_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                # Igual que arriba: un snapshot corrupto en disco se
                # devolvía como "no existe" (None), indistinguible de un
                # id inválido. Se deja traza para poder diferenciar los
                # dos casos al depurar.
                logger.warning(f"snapshot {snapshot_id} corrupto en {snapshot_path}: {e}")
        return None

    def delete_snapshot(self, snapshot_id: str) -> bool:
        snapshot_path = self._snapshot_path(snapshot_id)
        if snapshot_path.exists():
            snapshot_path.unlink()
        if snapshot_id in self.snapshots:
            del self.snapshots[snapshot_id]
            self._save_index()
            return True
        return False

    def interpolate_frames(self, snapshot_a: str, snapshot_b: str, ratio: float = 0.5) -> Dict:
        snap_a = self.get_snapshot(snapshot_a)
        snap_b = self.get_snapshot(snapshot_b)
        if not snap_a or not snap_b:
            return {"error": "Snapshots no encontrados"}
        return {
            "snapshot_a": snapshot_a, "snapshot_b": snapshot_b,
            "ratio": ratio, "interpolated": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
