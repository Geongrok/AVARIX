from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

# ------------------------------------------------------------
# Project root
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from app.knowledge_base import KnowledgeBase

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

NORMAL_CACHE = PROJECT_ROOT / "cache"
PRIVATE_DATA = PROJECT_ROOT / "app" / "private_data"

NORMAL_INDEX = NORMAL_CACHE / "index.pkl"
NORMAL_MANIFEST = NORMAL_CACHE / "manifest.json"

BACKUP_ROOT = PROJECT_ROOT / "recovery_backup"

EXPECTED_NORMAL_CHUNKS = 2041


# ------------------------------------------------------------
# Safety checks
# ------------------------------------------------------------

if not NORMAL_INDEX.exists():
    raise FileNotFoundError(
        f"Normal cache not found: {NORMAL_INDEX}"
    )

if not PRIVATE_DATA.exists():
    raise FileNotFoundError(
        f"Private source directory not found: {PRIVATE_DATA}"
    )

# ------------------------------------------------------------
# Load existing normal cache
# ------------------------------------------------------------

with open(NORMAL_INDEX, "rb") as fh:
    normal_cache = pickle.load(fh)

normal_chunks = list(normal_cache.get("chunks", []))
normal_meta = list(normal_cache.get("meta", []))

print("=" * 70)
print("INTELLEX KB RECOVERY / MERGE")
print("=" * 70)

print(f"[RECOVERY] Existing normal chunks : {len(normal_chunks)}")
print(f"[RECOVERY] Private source directory: {PRIVATE_DATA}")

if len(normal_chunks) != EXPECTED_NORMAL_CHUNKS:
    raise RuntimeError(
        f"Expected {EXPECTED_NORMAL_CHUNKS} normal chunks, "
        f"but found {len(normal_chunks)}. "
        "Stopping to protect the existing cache."
    )

if len(normal_chunks) != len(normal_meta):
    raise RuntimeError(
        "Normal cache is inconsistent: chunks/meta lengths differ."
    )


# ------------------------------------------------------------
# Load KnowledgeBase against the EXISTING cache
# ------------------------------------------------------------

kb = KnowledgeBase(
    data_dir=str(PRIVATE_DATA),
    cache_dir=str(NORMAL_CACHE),
)

# Restore the existing 2041 chunks into memory.
kb.chunks = normal_chunks
kb.meta = kb._migrate_metadata(normal_meta)
kb._build_bm25()

print(
    f"[RECOVERY] Existing cache loaded safely: "
    f"{len(kb.chunks)} chunks"
)


# ------------------------------------------------------------
# Discover private source files
# ------------------------------------------------------------

private_files = sorted(
    str(p)
    for p in PRIVATE_DATA.glob("**/*")
    if p.is_file() and p.suffix.lower() == ".pdf"
)

print(f"[RECOVERY] Private PDFs found : {len(private_files)}")

if not private_files:
    raise RuntimeError("No private PDF files found.")

print(
    f"[RECOVERY] Private source files discovered: "
    f"{len(private_files)}"
)

if not private_files:
    raise RuntimeError("No private source files found.")


# ------------------------------------------------------------
# Prevent accidental duplicate ingestion
# ------------------------------------------------------------

existing_files = {
    str(meta.get("file", "")).strip()
    for meta in kb.meta
    if isinstance(meta, dict)
}

files_to_ingest = [
    path
    for path in private_files
    if os.path.basename(path) not in existing_files
]

print(
    f"[RECOVERY] New private files to ingest: "
    f"{len(files_to_ingest)}"
)

if not files_to_ingest:
    raise RuntimeError(
        "No new private files found. "
        "Stopping rather than changing the existing cache."
    )


# ------------------------------------------------------------
# Ingest private PDFs into EXISTING cache/chroma
# ------------------------------------------------------------

before_count = len(kb.chunks)

kb._ingest_files(files_to_ingest)

after_count = len(kb.chunks)

added_count = after_count - before_count

print()
print(
    f"[RECOVERY] Existing chunks : {before_count}"
)
print(
    f"[RECOVERY] Added chunks    : {added_count}"
)
print(
    f"[RECOVERY] Final chunks    : {after_count}"
)


# ------------------------------------------------------------
# Validate expected result
# ------------------------------------------------------------

if after_count != 3175:
    raise RuntimeError(
        f"Unexpected final count: {after_count}. "
        "Expected 3175. "
        "The script will NOT continue to manifest finalization."
    )


# ------------------------------------------------------------
# Build a safe combined manifest
# ------------------------------------------------------------

records = {}

# Existing cached documents are marked as legacy/cache-managed.
#
# Their original source files are not necessarily present anymore,
# so the normal synchronizer must preserve these cached documents.
for meta in normal_meta:

    filename = str(meta.get("file", "")).strip()

    if not filename:
        continue

    if filename not in records:

        records[filename] = {
            "filename": filename,
            "doc_id": kb._doc_id_for_filename(filename),
            "confidential": bool(
                meta.get(
                    "confidential",
                    kb._is_confidential_filename(filename),
                )
            ),
            "managed": False,
        }


# Current private source files are managed documents.
for path in files_to_ingest:

    record = kb._file_record(path)
    record["managed"] = True

    filename = os.path.basename(path)

    records[filename] = record

# ------------------------------------------------------------
# Write combined manifest
# ------------------------------------------------------------

manifest = {
    "version": 1,
    "documents": records,
}

with open(
    NORMAL_MANIFEST,
    "w",
    encoding="utf-8",
) as fh:

    json.dump(
        manifest,
        fh,
        indent=2,
    )


print()
print("=" * 70)
print("RECOVERY COMPLETE")
print("=" * 70)
print(f"Final compiled chunks : {after_count}")
print(f"Manifest documents    : {len(records)}")
print(f"Cache                 : {NORMAL_CACHE}")
print(f"Chroma                : {NORMAL_CACHE / 'chroma'}")
print("=" * 70)