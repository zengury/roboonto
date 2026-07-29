"""Compatibility boundary for pre-0.9 ontology packs.

New code must use :mod:`roboonto.pack`.  The symbols here exist only to
perform a one-time, fail-closed migration into canonical PackModule 0.9.
"""

from .migrate_legacy import LegacyMigrationError, LegacyPackMigrator, MigrationResult

__all__ = ["LegacyMigrationError", "LegacyPackMigrator", "MigrationResult"]
