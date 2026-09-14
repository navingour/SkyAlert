"""
Bridge module: exports db_manager from app.db_manager for unified database access.
"""
from app.db_manager import db_manager, DatabaseManager

__all__ = ["db_manager", "DatabaseManager"]
