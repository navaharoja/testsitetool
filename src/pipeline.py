import argparse
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return _repo_root() / path


def _configure_logging(log_file: Path, debug: bool) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _discover_collectors() -> List[str]:
    import pkgutil
    import src.collectors as collectors_pkg

    names: List[str] = []
    for mod in pkgutil.iter_modules(collectors_pkg.__path__):
        if mod.ispkg:
            continue
        if mod.name.startswith("_") or mod.name == "__init__":
            continue
        names.append(mod.name)
    return sorted(names)


def _load_collector(source: str):
    module_path = f"src.collectors.{source}"
    module = importlib.import_module(module_path)
    if not hasattr(module, "collect"):
        raise AttributeError(f"Collector '{source}' has no collect()")
    return module


def _run_source(source: str, limit: int, timeout: int, retries: int) -> int:
    log = logging.getLogger("pipeline")
    module = _load_collector(source)
    log.info("Collecting source=%s limit=%s", source, limit)
    items = module.collect(limit=limit, timeout=timeout, retries=retries)
    log.info("Collected %d items from source=%s", len(items), source)
    return len(items)


def main(argv: Iterable[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Scraping pipeline")
    parser.add_argument("--source", help="Collector source name (e.g. example_site)")
    parser.add_argument("--all", action="store_true", help="Run all collectors")
    parser.add_argument("--limit", type=int, default=50, help="Max items per source")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    if not args.source and not args.all:
        parser.error("Provide --source or --all")

    log_file = _resolve_path(os.getenv("LOG_FILE", "logs/pipeline.log"))
    _configure_logging(log_file, args.debug)
    log = logging.getLogger("pipeline")

    timeout = int(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))
    retries = int(os.getenv("HTTP_RETRIES", "3"))

    sources = [args.source] if args.source else _discover_collectors()
    if not sources:
        log.error("No collectors found")
        return 1

    total = 0
    for source in sources:
        try:
            total += _run_source(source, args.limit, timeout, retries)
        except Exception as exc:
            log.exception("Failed source=%s: %s", source, exc)

    log.info("Pipeline finished. Total items collected: %d", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
