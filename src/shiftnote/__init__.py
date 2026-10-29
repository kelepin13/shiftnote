"""Shiftnote: nurse handover notes to validated, structured care documentation."""

from .models import CareNote, StructureResult
from .pipeline import structure_note

__all__ = ["CareNote", "StructureResult", "structure_note"]
