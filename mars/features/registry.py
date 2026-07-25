"""Feature registry for discovery and composition."""
 
from __future__ import annotations
 
from typing import Iterable, Optional, Type
 
from mars.features.base import BaseFeature
 
 
class FeatureRegistry:
    """
    Central registry of feature classes / instances.
 
    Enables research code to request features by name@version without
    hard-coding imports across the codebase.
    """
 
    def __init__(self) -> None:
        self._features: dict[str, BaseFeature] = {}
 
    def register(self, feature: BaseFeature, overwrite: bool = False) -> None:
        key = feature.metadata.qualified_name()
        if key in self._features and not overwrite:
            raise KeyError(f"Feature already registered: {key}")
        self._features[key] = feature
 
    def register_class(
        self,
        cls: Type[BaseFeature],
        overwrite: bool = False,
        **init_kwargs,
    ) -> BaseFeature:
        instance = cls(**init_kwargs)
        self.register(instance, overwrite=overwrite)
        return instance
 
    def get(self, name: str, version: Optional[str] = None) -> BaseFeature:
        if version is not None:
            key = f"{name}@v{version}"
            if key not in self._features:
                raise KeyError(f"Feature not found: {key}")
            return self._features[key]
        # latest match by name prefix
        matches = [k for k in self._features if k.startswith(f"{name}@v")]
        if not matches:
            raise KeyError(f"Feature not found: {name}")
        matches.sort()
        return self._features[matches[-1]]
 
    def list(self, category: Optional[str] = None) -> list[str]:
        if category is None:
            return sorted(self._features.keys())
        return sorted(
            k
            for k, f in self._features.items()
            if f.metadata.category == category
        )
 
    def all(self) -> Iterable[BaseFeature]:
        return self._features.values()
 
 
# Process-wide default registry (modules may register on import)
DEFAULT_REGISTRY = FeatureRegistry()