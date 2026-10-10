"""Offline Gen 1-4 dex. Import from here, not from submodules."""

from .dex import Dex, UnknownDexEntryError

__all__ = ["Dex", "UnknownDexEntryError"]
