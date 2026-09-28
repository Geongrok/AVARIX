#!/usr/bin/env python3

"""
Intellex Private Knowledge Base Builder

Provider workflow:

    1. Put private documents into private_data/
    2. Run:
           python tools/build_private_db.py
    3. The compiled Intellex cache is created in private_cache/

This tool intentionally uses Intellex's existing KnowledgeBase.
It does NOT create another indexing/database implementation.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.knowledge_base import KnowledgeBase, SUPPORTED_EXTS


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT = ROOT / "private_data"
DEFAULT_OUTPUT = ROOT / "private_cache"
DEFAULT_PACKAGE_DIR = ROOT / "private_db_packages"


def discover_files(input_dir: Path) -> list[Path]:

    files = sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTS
    )

    if not files:
        return []

    # Intellex's current manifest is keyed by basename.
    # Reject duplicate basenames rather than silently overwriting
    # one document's manifest entry.

    seen: dict[str, Path] = {}
    duplicates: list[tuple[Path, Path]] = []

    for path in files:

        key = path.name.lower()

        if key in seen:
            duplicates.append(
                (seen[key], path)
            )
        else:
            seen[key] = path

    if duplicates:

        print(
            "\nERROR: Duplicate filenames detected.\n"
            "Intellex's current manifest uses document basenames, "
            "so these files must be renamed:\n"
        )

        for first, second in duplicates:
            print(f"  {first}")
            print(f"  {second}")
            print()

        raise SystemExit(1)

    return files


def create_package(
    cache_dir: Path,
    package_dir: Path,
) -> Path:

    package_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    package = (
        package_dir /
        "intellex_private_cache.zip"
    )

    if package.exists():
        package.unlink()

    with ZipFile(
        package,
        "w",
        ZIP_DEFLATED,
    ) as archive:

        for path in cache_dir.rglob("*"):

            if path.is_file():

                archive.write(
                    path,
                    path.relative_to(cache_dir),
                )

    return package


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Build an Intellex private knowledge-base cache."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Directory containing private source documents.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory where the compiled cache is stored.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all documents.",
    )

    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete the existing output cache first.",
    )

    parser.add_argument(
        "--package",
        action="store_true",
        help="Create a ZIP containing only the compiled cache.",
    )

    parser.add_argument(
        "--package-dir",
        type=Path,
        default=DEFAULT_PACKAGE_DIR,
        help="Directory for the generated cache ZIP.",
    )

    args = parser.parse_args()

    input_dir = args.input.resolve()
    output_dir = args.output.resolve()

    input_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_files = discover_files(
        input_dir
    )

    if not source_files:

        raise SystemExit(
            f"\nNo supported source files found in:\n"
            f"{input_dir}\n\n"
            f"Supported extensions:\n"
            f"{', '.join(sorted(SUPPORTED_EXTS))}\n"
        )

    if (
        args.clean_output
        and output_dir.exists()
    ):

        print(
            f"Removing old cache: {output_dir}"
        )

        shutil.rmtree(
            output_dir
        )

    print()
    print("=" * 60)
    print("INTELLEX PRIVATE DATABASE BUILDER")
    print("=" * 60)
    print()
    print(
        f"Input : {input_dir}"
    )
    print(
        f"Output: {output_dir}"
    )
    print(
        f"Files : {len(source_files)}"
    )
    print()

    kb = KnowledgeBase(
        data_dir=str(input_dir),
        cache_dir=str(output_dir),
    )

    kb.build_index(
        force=args.force
    )

    print()
    print("=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print()
    print(
        f"Indexed chunks: {kb.doc_count()}"
    )
    print(
        f"Cache directory: {output_dir}"
    )

    if args.package:

        package = create_package(
            output_dir,
            args.package_dir.resolve(),
        )

        print()
        print(
            f"Package created: {package}"
        )

        print()
        print(
            "WARNING:"
        )

        print(
            "The compiled cache is NOT encrypted."
        )

        print(
            "It may contain extracted text from private documents."
        )

        print(
            "Do not place confidential cache files in a public repository."
        )


if __name__ == "__main__":
    main()