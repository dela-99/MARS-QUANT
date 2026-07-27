"""Feature registry."""
from __future__ import annotations
from typing import Iterable
from .feature import BaseFeature

class FeatureRegistry:
    def __init__(self) -> None:
        self._features: dict[str, type[BaseFeature]] = {}

    def register(self, cls: type[BaseFeature]) -> type[BaseFeature]:
        key = f"{cls.category}.{cls.name}@{cls.version}"
        self._features[key] = cls
        return cls

    def register_many(self, classes: Iterable[type[BaseFeature]]) -> None:
        for cls in classes:
            self.register(cls)

    def get(self, qualified_name: str) -> type[BaseFeature]:
        return self._features[qualified_name]

    def list(self) -> list[str]:
        return sorted(self._features)

    def create(self, qualified_name: str, **params) -> BaseFeature:
        return self.get(qualified_name)(**params)
