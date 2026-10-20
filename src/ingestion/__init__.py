"""Ingestion package for TP subjects and skeleton code parsing."""

from src.ingestion.parser import (
    ParsedSubject,
    SubjectParser,
    SubjectRequirement,
)
from src.ingestion.skeleton import (
    FunctionSignature,
    SkeletonParser,
    SkeletonProject,
    TodoSlot,
)

__all__ = [
    "FunctionSignature",
    "ParsedSubject",
    "SkeletonParser",
    "SkeletonProject",
    "SubjectParser",
    "SubjectRequirement",
    "TodoSlot",
]
