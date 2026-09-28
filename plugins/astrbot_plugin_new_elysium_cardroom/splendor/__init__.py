"""Splendor mode for New Elysium Cardroom."""

__all__ = ["SplendorManager"]


def __getattr__(name: str):
    if name == "SplendorManager":
        from .manager import SplendorManager

        return SplendorManager
    raise AttributeError(name)
