"""Declarative base export.

Only :class:`Base` lives here to avoid an import cycle (model modules import
``app.models.base``, which runs this package init). Model modules are imported
for metadata registration where needed — see :mod:`app.models.registry`, which
Alembic's ``env.py`` imports.
"""
from app.models.base import Base

__all__ = ["Base"]
