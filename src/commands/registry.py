from __future__ import annotations

from collections.abc import Callable

from commands.protocols import IAppCommand


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, IAppCommand] = {}
        self._listeners: list[Callable[[], None]] = []

    def register(self, command: IAppCommand) -> None:
        self._commands[command.command_id] = command

    def get(self, command_id: str) -> IAppCommand | None:
        return self._commands.get(command_id)

    def all(self) -> list[IAppCommand]:
        return list(self._commands.values())

    def execute(self, command_id: str) -> None:
        command = self._commands.get(command_id)
        if command is None or not command.enabled:
            return
        command.execute()
        self.refresh()

    def invoke(self, command_id: str) -> None:
        command = self._commands.get(command_id)
        if command is None:
            return
        command.execute()
        self.refresh()

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def refresh(self) -> None:
        for listener in self._listeners:
            listener()


class AppCommand:
    def __init__(
        self,
        command_id: str,
        title: str,
        handler: Callable[[], None],
        enabled_fn: Callable[[], bool] | None = None,
        title_fn: Callable[[], str] | None = None,
    ) -> None:
        self._id = command_id
        self._title = title
        self._title_fn = title_fn
        self._handler = handler
        self._enabled_fn = enabled_fn

    @property
    def command_id(self) -> str:
        return self._id

    @property
    def title(self) -> str:
        if self._title_fn is not None:
            return self._title_fn()
        return self._title

    @property
    def enabled(self) -> bool:
        if self._enabled_fn is None:
            return True
        return self._enabled_fn()

    def execute(self) -> None:
        self._handler()