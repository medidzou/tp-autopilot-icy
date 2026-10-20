"""Syllabus detection and Notion NotebookLM mapping module for ICy 3A."""

from src.syllabus.detector import CourseNotFoundError, SyllabusDetector
from src.syllabus.models import MatiereInfo

__all__ = ["SyllabusDetector", "CourseNotFoundError", "MatiereInfo"]
