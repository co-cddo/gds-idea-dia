"""Pipeline logging configuration.

Sets up dual logging: INFO to console (clean progress), DEBUG to file (full detail).
Log files are named after the data source and date for easy identification.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

PIPELINE_LOGGER_NAME = "dia.pipeline"

_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_CONSOLE_FORMAT = "%(levelname)-8s %(message)s"


def setup_pipeline_logging(
    source_name: str,
    log_dir: Path | str | None = None,
) -> Path:
    """Configure pipeline logging with console and file handlers.

    Console: INFO level, clean progress output.
    File: DEBUG level, full detail including tracebacks. Appends if file exists.

    Args:
        source_name: Name of the data source (used in log filename).
        log_dir: Directory for log files. Defaults to ./logs/.

    Returns:
        Path to the log file created/appended to.
    """
    log_dir = Path(log_dir) if log_dir else Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    log_file = log_dir / f"{source_name}-{date_str}.log"

    logger = logging.getLogger(PIPELINE_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)

    # Remove any existing handlers (avoids duplicates on repeated calls)
    logger.handlers.clear()

    # File handler — DEBUG, append mode
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    logger.addHandler(file_handler)

    # Console handler — INFO
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    logger.addHandler(console_handler)

    # Prevent propagation to root logger (avoids duplicate output)
    logger.propagate = False

    # Suppress noisy third-party loggers — pdfminer/pdfplumber emit warnings
    # like "Could not get FontBBox from font descriptor" for malformed PDFs
    # that aren't actionable and clutter the console during bulk extraction.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    logging.getLogger("pdfplumber").setLevel(logging.ERROR)

    logger.debug("Logging initialised: file=%s, source=%s", log_file, source_name)

    return log_file
