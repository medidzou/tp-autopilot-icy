"""Models for ICy 3A Syllabus and course metadata."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MatiereInfo(BaseModel):
    """Represents an academic subject/course from the ICy 3A syllabus."""

    id: str
    nom: str
    alias: Optional[str] = None
    ue: Optional[str] = None
    enseignant: Optional[str] = None
    notebook_url: str
    default_language: str = "c"
    keywords: List[str] = Field(default_factory=list)
    compilation_rules: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
