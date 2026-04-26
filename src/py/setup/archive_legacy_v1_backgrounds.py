"""
One-off скрипт: архивация legacy V1 climatology assets.

Контекст
--------

В `RuPlumeScan/backgrounds/` от прежней V1-итерации лежат 25 IMAGE-ассетов:

  CH4, CH4_05..10              (7 — месячные ML--SO climatology за май-октябрь?)
  NO2, NO2_03..10              (9)
  SO2, SO2_03..10              (9)

V1-методология использовала monthly composites + threshold для plume
detection — это deprecated по DNA v2.1 §2.1 и OpenSpec CHANGE-A001.
Эти ассеты НЕ соответствуют Algorithm v2.2 §3.4 (regional climatology
с industrial buffer exclusion + annulus correction) и не должны
использоваться в Phase 1 (P-01.0).

Дополнительно: имена `CH4`, `NO2`, `SO2` (без подкаталогов) конфликтуют
с RNA §3.1 структурой `backgrounds/<gas>/climatology_*` где `<gas>` —
Folder. Этот скрипт также пересоздаёт три Folder-узла после удаления
конфликтующих Image.

Что делает скрипт
-----------------

1. Создаёт `RuPlumeScan/_legacy_v1_archive` (Folder).
2. Создаёт `RuPlumeScan/_legacy_v1_archive/backgrounds` (Folder, плоский).
3. Копирует все 25 IMAGE через `ee.data.copyAsset()`.
4. Verify: все 25 копии присутствуют в архиве.
5. Удаляет 25 оригиналов через `ee.data.deleteAsset()`.
6. Пересоздаёт `backgrounds/CH4`, `backgrounds/NO2`, `backgrounds/SO2`
   как Folder.
7. Записывает description в архивную папку — «do not use, scheduled
   for deletion after Phase 1 completion».

Идемпотентность: при повторном запуске пропускает шаги, чьи цели уже
существуют (copy с allowOverwrite=False даёт ошибку — обрабатывается
как "already archived").

Запуск::

    cd src/py
    python -m setup.archive_legacy_v1_backgrounds

Безопасность: оригиналы удаляются ТОЛЬКО после успешной верификации
всех 25 копий. При любой ошибке на этапе copy — оригиналы не трогаем.

Удаление архива (после публикации tool-paper / на v1.0 release)::

    python -m setup.archive_legacy_v1_backgrounds --purge

(`--purge` рекурсивно удаляет `_legacy_v1_archive/`.)
"""

from __future__ import annotations

import argparse
import logging
import sys

import ee

PROJECT_ID = "nodal-thunder-481307-u1"
ASSETS_ROOT = f"projects/{PROJECT_ID}/assets"
RU_ROOT = f"{ASSETS_ROOT}/RuPlumeScan"
SOURCE_PARENT = f"{RU_ROOT}/backgrounds"
ARCHIVE_ROOT = f"{RU_ROOT}/_legacy_v1_archive"
ARCHIVE_PARENT = f"{ARCHIVE_ROOT}/backgrounds"

# Имена газовых Folder-ов которые мы пересоздадим после архивации
GAS_FOLDER_NAMES = ("CH4", "NO2", "SO2")

ARCHIVE_DESCRIPTION = (
    "DO NOT USE — legacy V1 climatology assets, deprecated per DNA v2.1 §2.1 "
    "(monthly composites + threshold approach concept-error). "
    "Scheduled for deletion after Phase 1 (P-01.0) completes successful sanity-check "
    "with new climatology + after tool-paper publication. "
    "См. OpenSpec CHANGE-A001 (V1 archived) и CHANGE-A002 (this archive)."
)


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("archive_legacy")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def ensure_folder(asset_path: str, logger: logging.Logger) -> str:
    """Создать Folder если не существует. Возвращает 'created' / 'exists'."""
    try:
        ee.data.createAsset({"type": "Folder"}, asset_path)
        logger.info("Created folder: %s", asset_path)
        return "created"
    except ee.EEException as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "cannot overwrite" in msg:
            logger.info("Folder exists: %s", asset_path)
            return "exists"
        raise


def list_legacy_images(logger: logging.Logger) -> list[str]:
    """Список Image-ассетов которые надо архивировать (под backgrounds/)."""
    r = ee.data.listAssets({"parent": SOURCE_PARENT})
    images = [a for a in r.get("assets", []) if a.get("type") == "IMAGE"]
    logger.info("Found %d legacy IMAGE assets under %s", len(images), SOURCE_PARENT)
    return [a["id"] for a in images]


def copy_to_archive(source_id: str, logger: logging.Logger) -> str:
    """
    Копирует source → archive с тем же basename.
    Возвращает 'copied' / 'already_archived'.
    """
    name = source_id.split("/")[-1]
    dest_id = f"{ARCHIVE_PARENT}/{name}"
    try:
        ee.data.copyAsset(source_id, dest_id, allowOverwrite=False)
        logger.info("Copied: %s -> %s", name, dest_id)
        return "copied"
    except ee.EEException as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "cannot overwrite" in msg:
            logger.info("Already archived: %s", name)
            return "already_archived"
        raise


def verify_archive(source_ids: list[str], logger: logging.Logger) -> bool:
    """Проверка: все 25 копий существуют в архиве."""
    r = ee.data.listAssets({"parent": ARCHIVE_PARENT})
    archived = {a["id"].split("/")[-1] for a in r.get("assets", [])}
    expected = {sid.split("/")[-1] for sid in source_ids}
    missing = expected - archived
    if missing:
        logger.error("VERIFY FAILED: %d missing from archive: %s", len(missing), missing)
        return False
    logger.info("VERIFY OK: all %d expected copies present in archive", len(expected))
    return True


def delete_originals(source_ids: list[str], logger: logging.Logger) -> int:
    """Удалить оригиналы. Возвращает count deleted."""
    count = 0
    for sid in source_ids:
        try:
            ee.data.deleteAsset(sid)
            logger.info("Deleted original: %s", sid.split("/")[-1])
            count += 1
        except ee.EEException as exc:
            logger.error("Failed to delete %s: %s", sid, exc)
            raise
    return count


def recreate_gas_folders(logger: logging.Logger) -> None:
    """Пересоздать backgrounds/CH4, NO2, SO2 как Folder per RNA §3.1."""
    for gas in GAS_FOLDER_NAMES:
        ensure_folder(f"{SOURCE_PARENT}/{gas}", logger)


def tag_archive_with_description(logger: logging.Logger) -> None:
    """
    Записать description в archive folder через `setAssetProperties`.
    Earth Engine не поддерживает 'description' для Folder напрямую,
    но можно использовать `update` / `setAssetProperties` с user-defined
    metadata. На случай если API не даёт — лог в stdout.
    """
    try:
        # API в новых версиях: ee.data.updateAsset
        ee.data.updateAsset(
            ARCHIVE_ROOT,
            {"properties": {"description": ARCHIVE_DESCRIPTION, "scheduled_for_deletion": "true"}},
            ["properties"],
        )
        logger.info("Tagged archive folder with deletion notice")
    except Exception as exc:  # pragma: no cover — API surface может различаться
        logger.warning(
            "Could not tag archive folder properties (%s). Notice is in OpenSpec CHANGE-A002.",
            exc,
        )


def purge_archive(logger: logging.Logger) -> int:
    """
    Рекурсивное удаление _legacy_v1_archive. Запускается ТОЛЬКО при `--purge`.
    """
    logger.warning("PURGE MODE: recursively deleting %s", ARCHIVE_ROOT)
    deleted = 0

    def recurse(parent: str) -> None:
        nonlocal deleted
        try:
            r = ee.data.listAssets({"parent": parent})
        except ee.EEException as exc:
            # Image (не Folder) — listAssets не работает, удаляем сразу.
            if "is not a folder" in str(exc).lower():
                ee.data.deleteAsset(parent)
                logger.info("Deleted image: %s", parent)
                deleted += 1
                return
            raise
        for child in r.get("assets", []):
            recurse(child["id"])
        ee.data.deleteAsset(parent)
        logger.info("Deleted folder: %s", parent)
        deleted += 1

    recurse(ARCHIVE_ROOT)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--purge",
        action="store_true",
        help="DESTRUCTIVE: рекурсивно удалить _legacy_v1_archive после публикации.",
    )
    args = parser.parse_args()

    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized for '%s'", PROJECT_ID)

    if args.purge:
        confirm = input(
            f"\nPURGE: This permanently deletes {ARCHIVE_ROOT} and all 25+ assets inside.\n"
            "Type 'PURGE' to confirm: "
        )
        if confirm != "PURGE":
            logger.info("Aborted.")
            return 1
        n = purge_archive(logger)
        logger.info("Purged %d assets/folders.", n)
        return 0

    # 1. Архивные папки
    ensure_folder(ARCHIVE_ROOT, logger)
    ensure_folder(ARCHIVE_PARENT, logger)

    # 2. Список оригиналов
    source_ids = list_legacy_images(logger)
    if not source_ids:
        logger.info("Nothing to archive (no IMAGE assets directly under backgrounds/).")
    else:
        # 3. Копирование
        logger.info("=== Phase 1: copy %d IMAGE to archive ===", len(source_ids))
        copy_summary: dict[str, int] = {}
        for sid in source_ids:
            status = copy_to_archive(sid, logger)
            copy_summary[status] = copy_summary.get(status, 0) + 1
        logger.info("Copy summary: %s", copy_summary)

        # 4. Verification
        logger.info("=== Phase 2: verify archive completeness ===")
        if not verify_archive(source_ids, logger):
            logger.error("Aborting: originals NOT deleted because verification failed.")
            return 2

        # 5. Удаление оригиналов
        logger.info("=== Phase 3: delete originals ===")
        n_deleted = delete_originals(source_ids, logger)
        logger.info("Deleted %d originals.", n_deleted)

    # 6. Пересоздание Folder-ов
    logger.info("=== Phase 4: recreate backgrounds/{CH4,NO2,SO2} as Folder ===")
    recreate_gas_folders(logger)

    # 7. Tag
    logger.info("=== Phase 5: tag archive folder with deletion notice ===")
    tag_archive_with_description(logger)

    logger.info("Done. Archive at %s. See OpenSpec CHANGE-A002.", ARCHIVE_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
