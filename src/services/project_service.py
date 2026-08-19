from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from core.exceptions import AccessError
from models.project import Project

logger = logging.getLogger(__name__)

PROJECTS_FILE = str(Path.home() / ".yetee" / "projects.json")


class ProjectService:
    def __init__(self) -> None:
        self._config_dir = str(Path.home() / ".yetee")
        os.makedirs(self._config_dir, exist_ok=True)

    def load_projects(self) -> list[Project]:
        if not os.path.exists(PROJECTS_FILE):
            return []
        try:
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [Project.from_dict(item) for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, OSError) as ex:
            logger.warning("Failed to load projects: %s", ex)
            return []

    def save_projects(self, projects: list[Project]) -> None:
        try:
            data = [p.to_dict() for p in projects]
            with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as ex:
            logger.error("Failed to save projects: %s", ex)
            raise AccessError(f"Cannot save projects: {ex}") from ex

    def add_project(self, project: Project) -> None:
        projects = self.load_projects()
        projects = [p for p in projects if p.name != project.name]
        projects.append(project)
        self.save_projects(projects)

    def remove_project(self, name: str) -> None:
        projects = self.load_projects()
        projects = [p for p in projects if p.name != name]
        self.save_projects(projects)

    def get_project(self, name: str) -> Project | None:
        projects = self.load_projects()
        for p in projects:
            if p.name == name:
                return p
        return None

    def mark_opened(self, project: Project) -> None:
        project.last_opened = time.time()
        self.add_project(project)

    def get_last_project(self) -> Project | None:
        projects = self.load_projects()
        if not projects:
            return None
        opened = [p for p in projects if p.last_opened is not None]
        if not opened:
            return projects[-1]
        return max(opened, key=lambda p: p.last_opened or 0)
