from __future__ import annotations

from typing import Protocol


class IAppCommand(Protocol):
    @property
    def command_id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def enabled(self) -> bool: ...

    def execute(self) -> None: ...