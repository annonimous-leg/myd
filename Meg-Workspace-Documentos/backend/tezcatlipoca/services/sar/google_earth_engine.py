"""Google Earth Engine - Análisis de datos satelitales en la nube."""
import os
from typing import Dict, List, Any
from datetime import datetime, timezone


class GoogleEarthEngineClient:
    """Cliente para Google Earth Engine (requiere cuenta Google Cloud + autenticación)."""

    def __init__(self):
        self.project_id = os.getenv("GEE_PROJECT_ID", "")
        self.credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        self.initialized = False

    def _check_auth(self) -> bool:
        """Verificar autenticación GEE."""
        if not self.project_id:
            return False
        try:
            import ee
            if not self.initialized:
                ee.Initialize(project=self.project_id)
                self.initialized = True
            return True
        except Exception as e:
            print(f"⚠️  GEE not initialized: {e}")
            return False

    def get_sar_collection(self, collection_id: str = "COPERNICUS/S1_GRD",
                           bbox: List[float] = None,
                           start_date: str = None,
                           end_date: str = None,
                           limit: int = 10) -> List[Dict]:
        """Obtener colección SAR de GEE."""
        if not self._check_auth():
            return [{"error": "GEE_PROJECT_ID not configured or ee not installed"}]

        try:
            import ee
            collection = ee.ImageCollection(collection_id)

            if start_date and end_date:
                collection = collection.filterDate(start_date, end_date)

            if bbox:
                region = ee.Geometry.Rectangle(bbox)
                collection = collection.filterBounds(region)

            # Limitar resultados
            collection = collection.limit(limit)

            # Obtener información
            info = collection.getInfo()
            features = info.get("features", [])

            return [{
                "id": f.get("id", ""),
                "properties": f.get("properties", {}),
                "bbox": bbox,
                "source": "earthengine.google.com",
                "timestamp": datetime.now(timezone.utc).isoformat()
            } for f in features]
        except Exception as e:
            print(f"⚠️  Error GEE SAR: {e}")
        return []

    def compute_ndvi(self, image_id: str, region: List[float]) -> Dict[str, Any]:
        """Computar NDVI sobre una imagen (ejemplo de procesamiento)."""
        if not self._check_auth():
            return {"error": "GEE not initialized"}

        try:
            import ee
            image = ee.Image(image_id)
            ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")

            region_geom = ee.Geometry.Rectangle(region)
            stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region_geom,
                scale=30,
                maxPixels=1e9
            )

            return {
                "image_id": image_id,
                "ndvi_mean": stats.get("NDVI").getInfo(),
                "region": region,
                "source": "earthengine.google.com",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            print(f"⚠️  Error GEE NDVI: {e}")
        return {"error": "Failed to compute NDVI"}
