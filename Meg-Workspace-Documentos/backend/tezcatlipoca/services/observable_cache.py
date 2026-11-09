"""ObservableCache — Dict-like cache with change notifications."""

from typing import Any, Callable, Dict, List, Optional
import logging

logger = logging.getLogger("tezcatlipoca.observable_cache")

class ObservableCache:
    """Cache that notifies observers when keys change."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._observers: List[Callable[[str, Any], None]] = []
        self._layer_observers: Dict[str, List[Callable[[Any], None]]] = {}

    def add_observer(self, callback: Callable[[str, Any], None]):
        """Add a global observer called on any key change."""
        self._observers.append(callback)

    def add_layer_observer(self, layer: str, callback: Callable[[Any], None]):
        """Add an observer for a specific layer/key."""
        if layer not in self._layer_observers:
            self._layer_observers[layer] = []
        self._layer_observers[layer].append(callback)

    def remove_observer(self, callback: Callable[[str, Any], None]):
        """Remove a global observer."""
        if callback in self._observers:
            self._observers.remove(callback)

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key, [])

    def __setitem__(self, key: str, value: Any):
        self._data[key] = value
        # Notify global observers
        for observer in self._observers:
            try:
                observer(key, value)
            except Exception as exc:
                logger.exception("observable_cache_observer_failed", extra={"key": key, "error": str(exc)})
        # Notify layer-specific observers
        for observer in self._layer_observers.get(key, []):
            try:
                observer(value)
            except Exception as exc:
                logger.exception("observable_cache_observer_failed", extra={"key": key, "error": str(exc)})

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def clear(self):
        self._data.clear()
