import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    level: int = logging.DEBUG,
    log_dir: str | None = None,
    max_bytes: int = 1_048_576,
    backup_count: int = 3,
) -> None:
    if log_dir is None:
        log_dir = str(Path.home() / ".yetee" / "logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    log_path = Path(log_dir) / "types_editor.log"

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)
