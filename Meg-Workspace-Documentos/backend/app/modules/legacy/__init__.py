# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Módulo de compatibilidad legacy."""
from app.modules.legacy.adapters import ModelAdapter, EndpointAdapter, DataMigrationHelper

__all__ = ["ModelAdapter", "EndpointAdapter", "DataMigrationHelper"]
