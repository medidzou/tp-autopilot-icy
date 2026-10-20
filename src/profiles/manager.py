"""Profile manager for persistent student profile storage and calibration management."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.profiles.models import StudentProfile


class ProfileManager:
    """Manages creation, loading, updating, and listing of student profiles."""

    def __init__(self, storage_dir: Union[str, Path] = "profiles") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_profile_dir(self, name: str) -> Path:
        """Returns the profile directory path for a given student name."""
        return self.storage_dir / name

    def _get_profile_path(self, name: str) -> Path:
        """Returns the JSON file path for a given student name."""
        return self._get_profile_dir(name) / "profile.json"

    def profile_exists(self, name: str) -> bool:
        """Checks if a profile already exists on disk."""
        return self._get_profile_path(name).is_file()

    def get_profile(self, name: str) -> StudentProfile:
        """Loads and parses a student profile from disk.

        Raises:
            FileNotFoundError: If the profile does not exist.
        """
        profile_path = self._get_profile_path(name)
        if not profile_path.is_file():
            raise FileNotFoundError(f"Profile for student '{name}' not found at {profile_path}")

        content = profile_path.read_text(encoding="utf-8")
        return StudentProfile.model_validate_json(content)

    def list_profiles(self) -> List[str]:
        """Returns a sorted list of all available student profile names."""
        if not self.storage_dir.exists():
            return []

        names: List[str] = []
        for entry in self.storage_dir.iterdir():
            if entry.is_dir() and (entry / "profile.json").is_file():
                names.append(entry.name)

        return sorted(names)

    def create_or_update_profile(
        self,
        name: str,
        calibration_answers: Optional[Dict[str, str]] = None,
        samples: Optional[List[str]] = None,
        verbosity_metrics: Optional[Dict[str, Any]] = None,
        style_preferences: Optional[Dict[str, Any]] = None,
    ) -> StudentProfile:
        """Creates a new student profile or updates an existing one and persists it to disk."""
        now_str = datetime.now(timezone.utc).isoformat()

        if self.profile_exists(name):
            profile = self.get_profile(name)
            if calibration_answers is not None:
                profile.calibration_answers.update(calibration_answers)
            if samples is not None:
                profile.samples = samples
            if style_preferences is not None:
                profile.style_preferences.update(style_preferences)
            if verbosity_metrics is not None:
                profile.verbosity_metrics = verbosity_metrics
            else:
                profile.refresh_metrics()
            profile.updated_at = now_str
        else:
            profile = StudentProfile(
                name=name,
                calibration_answers=calibration_answers or {},
                samples=samples or [],
                verbosity_metrics=verbosity_metrics or {},
                style_preferences=style_preferences or {},
                created_at=now_str,
                updated_at=now_str,
            )
            if not profile.verbosity_metrics:
                profile.refresh_metrics()

        # Persist to disk
        profile_dir = self._get_profile_dir(name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_path = self._get_profile_path(name)
        profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

        return profile

    def delete_profile(self, name: str) -> bool:
        """Deletes a student profile directory if it exists."""
        profile_dir = self._get_profile_dir(name)
        if profile_dir.is_dir():
            shutil.rmtree(profile_dir)
            return True
        return False
