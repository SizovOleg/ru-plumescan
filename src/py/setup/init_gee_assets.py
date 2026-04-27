"""
Создание GEE Asset folder structure для RU-PlumeScan.

Идемпотентен: уже существующие папки не пересоздаются и не падают.
Соответствует RNA.md §3.1 (full asset hierarchy).

Запуск::

    cd src/py
    python -m setup.init_gee_assets

Требования:
  * `earthengine-api` установлен.
  * `earthengine authenticate` выполнен (один раз на машину).
  * Учётка имеет write-доступ к проекту `nodal-thunder-481307-u1`.
"""

from __future__ import annotations

import logging
import os
import sys

import ee

PROJECT_ID = os.environ.get("GEE_PROJECT", "nodal-thunder-481307-u1")
PROJECT_ASSETS_ROOT = f"projects/{PROJECT_ID}/assets"

# Полный список папок per RNA.md §3.1.
# Порядок имеет значение: parent перед child (createAsset не создаёт промежуточные).
FOLDERS: tuple[str, ...] = (
    "RuPlumeScan",
    "RuPlumeScan/backgrounds",
    "RuPlumeScan/backgrounds/CH4",
    "RuPlumeScan/backgrounds/NO2",
    "RuPlumeScan/backgrounds/SO2",
    "RuPlumeScan/industrial",
    "RuPlumeScan/catalog",
    "RuPlumeScan/catalog/CH4",
    "RuPlumeScan/catalog/NO2",
    "RuPlumeScan/catalog/SO2",
    "RuPlumeScan/refs",
    # Reference Clean Zones (CHANGE-0017, DNA v2.2 §1.2)
    "RuPlumeScan/reference",
    # Reference Baselines per gas (CHANGE-0017, Algorithm v2.3 §11)
    "RuPlumeScan/baselines",
    "RuPlumeScan/baselines/CH4",
    "RuPlumeScan/baselines/NO2",
    "RuPlumeScan/baselines/SO2",
    "RuPlumeScan/comparisons",
    "RuPlumeScan/comparisons/ours_vs_schuit2023",
    "RuPlumeScan/comparisons/ours_vs_imeo_mars",
    "RuPlumeScan/comparisons/ours_vs_cams",
    "RuPlumeScan/presets",
    "RuPlumeScan/presets/built_in",
    "RuPlumeScan/presets/custom",
    "RuPlumeScan/runs",
    "RuPlumeScan/validation",
    "RuPlumeScan/validation/synthetic_injection",
    "RuPlumeScan/validation/regression",
)


def setup_logger() -> logging.Logger:
    """Простой stdout-logger без зависимостей."""
    logger = logging.getLogger("init_gee_assets")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    return logger


def ensure_folder(asset_path: str, logger: logging.Logger) -> str:
    """
    Создаёт папку если её нет, возвращает status строкой ("created" /
    "exists" / "error: ..."). Не поднимает исключения для 'already exists',
    но падает на других ошибках доступа.
    """
    try:
        ee.data.createAsset({"type": "Folder"}, asset_path)
        logger.info("Created: %s", asset_path)
        return "created"
    except ee.EEException as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "cannot overwrite" in msg:
            logger.info("Exists:  %s", asset_path)
            return "exists"
        logger.error("FAILED: %s — %s", asset_path, exc)
        raise


def init_gee(project_id: str, logger: logging.Logger) -> None:
    """
    Инициализация Earth Engine с явным project_id. При отсутствии креденшилов
    подсказывает запустить `earthengine authenticate`.
    """
    try:
        ee.Initialize(project=project_id)
        logger.info("Earth Engine initialized for project '%s'", project_id)
    except Exception as exc:
        logger.error(
            "Earth Engine init failed: %s\n"
            "Если ещё не аутентифицирован, запусти:\n"
            "    earthengine authenticate --project=%s",
            exc,
            project_id,
        )
        raise


def main() -> int:
    """Entry point. Возвращает exit code."""
    logger = setup_logger()
    logger.info("Initializing GEE Asset folders under %s", PROJECT_ASSETS_ROOT)
    init_gee(PROJECT_ID, logger)

    summary = {"created": 0, "exists": 0}
    for folder in FOLDERS:
        full_path = f"{PROJECT_ASSETS_ROOT}/{folder}"
        status = ensure_folder(full_path, logger)
        summary[status] = summary.get(status, 0) + 1

    logger.info(
        "Done. Created: %d, already existed: %d, total: %d",
        summary["created"],
        summary["exists"],
        len(FOLDERS),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
