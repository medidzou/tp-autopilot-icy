"""Profiles package for student calibration and writing style profiles."""

from src.profiles.manager import ProfileManager
from src.profiles.models import (
    DEFAULT_CALIBRATION_QUESTIONS,
    StudentProfile,
    compute_text_verbosity_metrics,
)

__all__ = [
    "ProfileManager",
    "StudentProfile",
    "DEFAULT_CALIBRATION_QUESTIONS",
    "compute_text_verbosity_metrics",
]
