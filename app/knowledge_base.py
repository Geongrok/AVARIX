"""Intellex compiled knowledge base.

Documents are processed when they are added/updated.

Runtime questions search the compiled cache rather than reopening the
original PDF/DOCX/PPTX files.

Storage:

    cache/
        index.pkl
        manifest.json
        chroma/

The manifest records SHA-256 hashes so new/changed/deleted documents can
be handled incrementally.
"""

import hashlib
import json
import os
import pickle
import re

from typing import Dict, List, Optional, Tuple

import numpy as np

from rank_bm25 import BM25Okapi

from .vector_store import VectorStore


# ================================================================
# Optional document libraries
# ================================================================

try:
    import pymupdf

except ImportError:
    pymupdf = None


try:
    from pypdf import PdfReader

except ImportError:
    PdfReader = None


try:
    import docx

except ImportError:
    docx = None


try:
    from pptx import Presentation

except ImportError:
    Presentation = None


try:
    import openpyxl

except ImportError:
    openpyxl = None


try:
    from rapidocr_onnxruntime import RapidOCR

    _OCR = RapidOCR()

    _OCR_AVAILABLE = True

except Exception:

    _OCR = None

    _OCR_AVAILABLE = False


# ================================================================
# Paths
# ================================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DEFAULT_DATA_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
)

DEFAULT_CACHE_DIR = os.path.join(
    PROJECT_ROOT,
    "cache",
)


# ================================================================
# Supported formats
# ================================================================

SUPPORTED_EXTS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".txt",
    ".md",
    ".csv",

    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


# ================================================================
# Chunking
# ================================================================

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

DOCUMENT_ID_PATTERN = re.compile(
    r"^(CONF-\d{3,}|DOC-\d{3,})(?:[_\-\s]|$)",
    re.IGNORECASE
)


# ================================================================
# Stop words
# ================================================================

STOP_WORDS = set(
    """
    a an and are as at be but by for from have has he her his
    i if in is it its of on or our she so that the their them
    then there these they this to was we what when which who
    will with you your
    """.split()
)


class KnowledgeBase:

    def __init__(
        self,
        data_dir: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ):

        # Render can use:
        #
        # INTELLEX_DATA_DIR=/var/data/intellex/documents
        # INTELLEX_CACHE_DIR=/var/data/intellex/kb

        self.data_dir = (
            data_dir
            or os.getenv(
                "INTELLEX_DATA_DIR"
            )
            or DEFAULT_DATA_DIR
        )

        self.cache_dir = (
            cache_dir
            or os.getenv(
                "INTELLEX_CACHE_DIR"
            )
            or DEFAULT_CACHE_DIR
        )

        os.makedirs(
            self.data_dir,
            exist_ok=True,
        )

        self.cache_dir = (
            cache_dir
            or os.getenv("INTELLEX_CACHE_DIR")
            or DEFAULT_CACHE_DIR
        )

        # --------------------------------------------------------
        # Additional source directories
        # --------------------------------------------------------
        extra_dirs_raw = os.getenv("INTELLEX_EXTRA_DATA_DIRS", "")

        self.extra_data_dirs = [
            os.path.abspath(item.strip())
            for item in extra_dirs_raw.split(";")
            if item.strip()
        ]

        os.makedirs(
            self.cache_dir,
            exist_ok=True,
        )

        # --------------------------------------------------------
        # Compiled text cache
        # --------------------------------------------------------

        self._cache_path = os.path.join(
            self.cache_dir,
            "index.pkl",
        )

        # --------------------------------------------------------
        # File manifest
        # --------------------------------------------------------

        self._manifest_path = os.path.join(
            self.cache_dir,
            "manifest.json",
        )

        # --------------------------------------------------------
        # In-memory BM25
        # --------------------------------------------------------

        self.chunks: List[str] = []

        self.meta: List[Dict] = []

        self._extraction_types: Dict[Tuple[str, Optional[int]], str] = {}

        self.tokenized: List[List[str]] = []

        self.bm25: Optional[BM25Okapi] = None

        # --------------------------------------------------------
        # Persistent semantic database
        # --------------------------------------------------------

        self.vector = VectorStore(
            persist_dir=os.path.join(
                self.cache_dir,
                "chroma",
            )
        )

    # ============================================================
    # BUILD INDEX
    # ============================================================

    def build_index(
        self,
        force: bool = False,
    ) -> None:

        files = self._list_files()

        print(
            f"[KB] DATA_DIR  = {self.data_dir}",
            flush=True,
        )

        print(
            f"[KB] CACHE_DIR = {self.cache_dir}",
            flush=True,
        )

        print(
            f"[KB] Files discovered = {len(files)}",
            flush=True,
        )

        # --------------------------------------------------------
        # Explicit rebuild
        # --------------------------------------------------------

        if force:

            print(
                "[KB] FULL rebuild requested.",
                flush=True,
            )

            self.rebuild()

            return

        # --------------------------------------------------------
        # Load compiled cache
        # --------------------------------------------------------

        cached = self._load_cache()

        if cached:

            cached_chunks = cached.get(
                "chunks",
                [],
            )

            cached_meta = cached.get(
                "meta",
                [],
            )

            if (
                isinstance(cached_chunks, list)
                and isinstance(cached_meta, list)
            ):

                self.chunks = cached_chunks

                self.meta = self._migrate_metadata(cached_meta)

                self._build_bm25()

                print(
                    f"[KB] Loaded compiled cache: "
                    f"{len(self.chunks)} chunks.",
                    flush=True,
                )

        # --------------------------------------------------------
        # No cache
        # --------------------------------------------------------

        if not cached:

            print(
                "[KB] No compiled cache found.",
                flush=True,
            )

            self.rebuild()

            return

        # --------------------------------------------------------
        # Manifest
        # --------------------------------------------------------

        manifest = self._load_manifest()

        if manifest:

            self._synchronize_files(
                files,
                manifest,
            )

            return

        # --------------------------------------------------------
        # Backward compatibility with your existing index.pkl
        # --------------------------------------------------------

        print(
            "[KB] No manifest found. "
            "Using existing cache and detecting new files.",
            flush=True,
        )

        indexed_files = {
            str(
                meta.get(
                    "file",
                    "",
                )
            ).strip()

            for meta in self.meta

            if isinstance(meta, dict)
        }

        new_files = [
            path
            for path in files

            if os.path.basename(path)
            not in indexed_files
        ]

        if new_files:

            self._ingest_files(
                new_files
            )

        else:

            # Create manifest from existing
            # source files.

            records = {
                os.path.basename(path):
                self._file_record(path)

                for path in files
            }

            self._save_manifest(
                records
            )

            self._save_cache()

            print(
                "[KB] Existing cache is ready.",
                flush=True,
            )

    # ============================================================
    # SYNCHRONIZE FILES
    # ============================================================

    def _synchronize_files(
        self,
        files,
        manifest,
    ):

        old_documents = manifest.get(
            "documents",
            {},
        )

        current_documents = {
            os.path.basename(path):
            self._file_record(path)

            for path in files
        }

        new_files = []

        changed_files = []

        deleted_files = []

        # --------------------------------------------------------
        # Detect new/changed
        # --------------------------------------------------------

        for filename, record in current_documents.items():

            old_record = old_documents.get(
                filename
            )

            if old_record is None:

                new_files.append(
                    record["path"]
                )

                continue

            if (
                old_record.get("hash")
                != record["hash"]
            ):

                changed_files.append(
                    record["path"]
                )

        # --------------------------------------------------------
        # Detect deleted
        # --------------------------------------------------------

        for filename, old_record in old_documents.items():

            if filename in current_documents:
                continue

            # Legacy cached documents may no longer have their original
            # source file locally. Preserve them unless explicitly managed.
            if old_record.get("managed", True) is False:
                continue

            deleted_files.append(filename)

        print(
            f"[KB] New files     : {len(new_files)}",
            flush=True,
        )

        print(
            f"[KB] Changed files : {len(changed_files)}",
            flush=True,
        )

        print(
            f"[KB] Deleted files : {len(deleted_files)}",
            flush=True,
        )

        # --------------------------------------------------------
        # Remove deleted documents
        # --------------------------------------------------------

        if deleted_files:

            deleted_set = set(
                deleted_files
            )

            keep_indices = [
                index

                for index, meta in enumerate(
                    self.meta
                )

                if meta.get("file")
                not in deleted_set
            ]

            self.chunks = [
                self.chunks[index]
                for index in keep_indices
            ]

            self.meta = [
                self.meta[index]
                for index in keep_indices
            ]

            for filename in deleted_files:

                self.vector.delete_by_file(
                    filename
                )

            self._build_bm25()

        # --------------------------------------------------------
        # Remove changed documents
        # --------------------------------------------------------

        if changed_files:

            changed_names = {
                os.path.basename(path)

                for path in changed_files
            }

            keep_indices = [
                index

                for index, meta in enumerate(
                    self.meta
                )

                if meta.get("file")
                not in changed_names
            ]

            self.chunks = [
                self.chunks[index]
                for index in keep_indices
            ]

            self.meta = [
                self.meta[index]
                for index in keep_indices
            ]

            for filename in changed_names:

                self.vector.delete_by_file(
                    filename
                )

            self._build_bm25()

        # --------------------------------------------------------
        # Add new/changed
        # --------------------------------------------------------

        files_to_ingest = (
            new_files
            + changed_files
        )

        if files_to_ingest:

            self._ingest_files(
                files_to_ingest
            )

        else:

            self._save_cache()

            self._save_manifest(
                current_documents
            )

            print(
                "[KB] Compiled KB is already up to date.",
                flush=True,
            )

    # ============================================================
    # INGEST FILES
    # ============================================================

    def _ingest_files(
        self,
        paths: List[str],
    ) -> None:

        all_ids = []

        all_texts = []

        all_meta = []

        for path in paths:

            filename = os.path.basename(
                path
            )
            doc_id = self._doc_id_for_filename(filename)
            confidential = self._is_confidential_filename(filename)

            print(
                f"[KB] Compiling: {filename}",
                flush=True,
            )

            try:

                segments = (
                    self._extract_segments(
                        path
                    )
                )

            except Exception as exc:

                print(
                    f"[KB] Failed: {filename}: {exc}",
                    flush=True,
                )

                continue

            segment_count = 0

            chunk_count = 0

            for seg_idx, (
                text,
                page,
            ) in enumerate(segments):

                segment_count += 1

                pieces = self._chunk(
                    text
                )

                for piece_idx, piece in enumerate(
                    pieces
                ):

                    if not piece:
                        continue

                    self.chunks.append(
                        piece
                    )

                    extraction_type = self._extraction_types.get(
                        (path, page),
                        "text",
                    )

                    self.meta.append(
                        {
                            "file": filename,
                            "page": page,
                            "doc_id": doc_id,
                            "confidential": confidential,
                            "extraction_type": extraction_type,
                        }
                    )

                    # ------------------------------------------------
                    # Stable vector ID
                    # ------------------------------------------------

                    relative_path = (
                        os.path.relpath(
                            path,
                            self.data_dir,
                        )
                    )

                    vector_id = hashlib.md5(
                        (
                            f"{relative_path}|"
                            f"{page}|"
                            f"{seg_idx}|"
                            f"{piece_idx}|"
                            f"{piece}"
                        ).encode(
                            "utf-8"
                        )
                    ).hexdigest()

                    all_ids.append(
                        vector_id
                    )

                    all_texts.append(
                        piece
                    )

                    all_meta.append(
                        {
                            "file": filename,
                            "page": page or "",
                            "doc_id": doc_id,
                            "confidential": confidential,
                            "extraction_type": extraction_type,
                        }
                    )

                    chunk_count += 1

            print(
                f"[KB]   segments={segment_count} "
                f"chunks={chunk_count}",
                flush=True,
            )

        # --------------------------------------------------------
        # Rebuild BM25 in memory
        # --------------------------------------------------------

        self._build_bm25()

        # --------------------------------------------------------
        # Add only new/changed vectors
        # --------------------------------------------------------

        if all_texts:

            print(
                f"[KB] Adding {len(all_texts)} "
                f"chunks to semantic index...",
                flush=True,
            )

            self.vector.add_documents(
                all_ids,
                all_texts,
                all_meta,
            )

        # --------------------------------------------------------
        # Persist compiled KB
        # --------------------------------------------------------

        self._save_cache()

        records = {
            os.path.basename(path):
            self._file_record(path)

            for path in self._list_files()
        }

        self._save_manifest(
            records
        )

        print(
            f"[KB] Compilation complete. "
            f"Total chunks={len(self.chunks)}",
            flush=True,
        )

    # ============================================================
    # FULL REBUILD
    # ============================================================

    def rebuild(self) -> None:

        print(
            "[KB] Starting full rebuild...",
            flush=True,
        )

        self.chunks = []

        self.meta = []

        self._extraction_types = {}

        self.tokenized = []

        self.bm25 = None

        # Destroy old vectors only during
        # an explicit/full rebuild.

        self.vector.clear()

        self._ingest_files(
            self._list_files()
        )

    # ============================================================
    # DOCUMENT MANAGEMENT
    # ============================================================

    @staticmethod
    def _doc_id_for_filename(filename: str) -> str:
        name = os.path.basename(str(filename or "")).strip()
        match = DOCUMENT_ID_PATTERN.match(name)
        if match:
            return match.group(1).upper()
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10].upper()
        return f"DOC-{digest}"

    @classmethod
    def _is_confidential_filename(cls, filename: str) -> bool:
        return cls._doc_id_for_filename(filename).startswith("CONF-")

    def _migrate_metadata(self, meta: List[Dict]) -> List[Dict]:
        migrated = []
        for item in meta or []:
            record = dict(item) if isinstance(item, dict) else {}
            filename = str(record.get("file", "")).strip()
            doc_id = str(record.get("doc_id", "")).strip()
            if not doc_id and filename:
                doc_id = self._doc_id_for_filename(filename)
            record["doc_id"] = doc_id
            record["confidential"] = bool(record.get("confidential", self._is_confidential_filename(filename)))
            record.setdefault("extraction_type", "text")
            migrated.append(record)
        return migrated

    def list_documents(self) -> List[Dict]:
        manifest = self._load_manifest() or {}
        documents = manifest.get("documents", {})
        if documents:
            out = []
            for filename, record in sorted(documents.items()):
                item = dict(record)
                item["filename"] = filename
                item["doc_id"] = item.get("doc_id") or self._doc_id_for_filename(filename)
                item["confidential"] = bool(item.get("confidential", self._is_confidential_filename(filename)))
                out.append(item)
            return out
        return [
            {
                "filename": filename,
                "doc_id": self._doc_id_for_filename(filename),
                "confidential": self._is_confidential_filename(filename),
            }
            for filename in self.file_names()
        ]

    def remove_document(self, doc_id: str, delete_source: bool = True) -> Dict:
        """Remove one document from source storage and all compiled indexes."""
        target = str(doc_id or "").strip().upper()
        if not target:
            raise ValueError("Document ID is required, e.g. CONF-001")

        matches = [item for item in self.list_documents() if str(item.get("doc_id", "")).upper() == target]
        if not matches:
            raise FileNotFoundError(f"Document ID not found: {target}")

        record = matches[0]
        filename = str(record.get("filename", "")).strip()
        source_path = os.path.join(self.data_dir, filename)

        keep = []
        for index, meta in enumerate(self.meta):
            meta_doc_id = str(meta.get("doc_id", "")).upper()
            meta_file = str(meta.get("file", ""))
            if meta_doc_id == target or meta_file == filename:
                continue
            keep.append(index)

        self.chunks = [self.chunks[index] for index in keep]
        self.meta = [self.meta[index] for index in keep]
        self._build_bm25()

        if hasattr(self.vector, "delete_by_document"):
            self.vector.delete_by_document(target)
        if hasattr(self.vector, "delete_by_file"):
            self.vector.delete_by_file(filename)

        if delete_source and os.path.isfile(source_path):
            os.remove(source_path)

        remaining = {os.path.basename(path): self._file_record(path) for path in self._list_files()}
        self._save_manifest(remaining)
        self._save_cache()

        print(f"[KB] Removed document {target}: {filename}", flush=True)
        return {
            "doc_id": target,
            "filename": filename,
            "confidential": bool(record.get("confidential", False)),
            "deleted_source": bool(delete_source and not os.path.exists(source_path)),
            "remaining_chunks": len(self.chunks),
            "remaining_files": len(remaining),
        }

    # ============================================================
    # SEARCH
    # ============================================================

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict]:

        keyword = self.search_keyword(
            query,
            top_k=top_k,
        )

        # Strong keyword result:
        # don't waste time creating a vector.

        if (
            keyword
            and keyword[0].get(
                "score",
                0,
            ) >= 0.55
        ):

            return keyword

        semantic = self.search_semantic(
            query,
            top_k=top_k,
        )

        return self.fuse_results(
            keyword,
            semantic,
            top_k,
        )

    # ============================================================
    # FAST KEYWORD SEARCH
    # ============================================================

    def search_keyword(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict]:

        if not self.bm25:
            return []

        if not self.chunks:
            return []

        query_tokens = self.tokenize(
            query
        )

        if not query_tokens:
            return []

        unique_query = {
            token

            for token in query_tokens

            if token not in STOP_WORDS
        }

        if not unique_query:

            unique_query = set(
                query_tokens
            )

        scores = self.bm25.get_scores(
            query_tokens
        )

        ranked = sorted(
            zip(
                scores,
                range(len(self.chunks)),
            ),
            key=lambda item: item[0],
            reverse=True,
        )

        results = []

        window = min(
            max(
                top_k * 6,
                200,
            ),
            len(self.chunks),
        )

        for bm25_score, index in ranked[
            :window
        ]:

            chunk_tokens = set(
                self.tokenized[index]
            )

            hits = (
                unique_query
                & chunk_tokens
            )

            if not hits:
                continue

            coverage = (
                len(hits)
                /
                len(unique_query)
            )

            # Single common-word match is weak.

            if (
                len(hits) == 1
                and len(unique_query) > 1
            ):

                coverage -= 0.35

            score = max(
                float(coverage),
                0.0,
            )

            filename = str(
                self.meta[index].get(
                    "file",
                    "",
                )
            )

            filename_tokens = set(
                self.tokenize(
                    filename
                )
            )

            filename_match = bool(
                unique_query
                & filename_tokens
            )

            # Filename matches are highly
            # valuable for document-specific
            # questions.

            if filename_match:

                score = min(
                    1.0,
                    score + 0.45,
                )

            results.append(
                {
                    "text": self.chunks[index],

                    "file": filename,

                    "page": self.meta[index].get(
                        "page"
                    ),

                    "score": score,

                    "bm25": float(
                        bm25_score
                    ),

                    "filename_match":
                        filename_match,
                }
            )

        results.sort(
            key=lambda item:
            item["score"],
            reverse=True,
        )

        return results[
            :top_k
        ]

    # ============================================================
    # SEMANTIC SEARCH
    # ============================================================

    def search_semantic(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict]:

        return self.vector.query(
            query,
            top_k=top_k,
        )

    # ============================================================
    # FUSION
    # ============================================================

    @staticmethod
    def fuse_results(
        keyword,
        semantic,
        top_k=5,
    ):

        fused = {}

        for result in keyword:

            key = result[
                "text"
            ][:200]

            fused[key] = dict(
                result
            )

        for result in semantic:

            key = result[
                "text"
            ][:200]

            if key in fused:

                fused[key][
                    "score"
                ] = max(
                    float(
                        fused[key].get(
                            "score",
                            0,
                        )
                    ),

                    float(
                        result.get(
                            "score",
                            0,
                        )
                    ),
                )

                fused[key][
                    "vector_score"
                ] = result.get(
                    "score",
                    0,
                )

            else:

                fused[key] = {

                    "text":
                        result.get(
                            "text",
                            "",
                        ),

                    "file":
                        result.get(
                            "file",
                            "unknown",
                        ),

                    "page":
                        result.get(
                            "page"
                        ),

                    "score":
                        float(
                            result.get(
                                "score",
                                0,
                            )
                        ) * 0.85,

                    "vector_score":
                        result.get(
                            "score",
                            0,
                        ),
                }

        results = sorted(
            fused.values(),

            key=lambda item:
            float(
                item.get(
                    "score",
                    0,
                )
            ),

            reverse=True,
        )

        return results[
            :top_k
        ]

    # ============================================================
    # STATUS
    # ============================================================

    def doc_count(self) -> int:

        return len(
            self.chunks
        )

    def file_names(self) -> List[str]:

        return sorted(
            {
                meta.get(
                    "file",
                    "",
                )

                for meta in self.meta

                if meta.get(
                    "file"
                )
            }
        )

    # ============================================================
    # TOKENIZATION
    # ============================================================

    @staticmethod
    def tokenize(
        text: str,
    ) -> List[str]:

        return re.findall(
            r"\w+",
            text.lower(),
        )

    def _build_bm25(self) -> None:

        self.tokenized = [
            self.tokenize(
                chunk
            )

            for chunk in self.chunks
        ]

        self.bm25 = (
            BM25Okapi(
                self.tokenized
            )

            if self.tokenized

            else None
        )

    # ============================================================
    # FILE HASHING
    # ============================================================

    @staticmethod
    def _file_hash(
        path: str,
    ) -> str:

        sha256 = hashlib.sha256()

        with open(
            path,
            "rb",
        ) as fh:

            for block in iter(
                lambda:
                fh.read(
                    1024 * 1024
                ),
                b"",
            ):

                sha256.update(
                    block
                )

        return sha256.hexdigest()

    def _file_record(
        self,
        path: str,
    ) -> Dict:

        stat = os.stat(
            path
        )
        filename = os.path.basename(path)

        return {
            "path": path,

            "filename": filename,

            "doc_id": self._doc_id_for_filename(filename),

            "confidential": self._is_confidential_filename(filename),

            "hash":
                self._file_hash(
                    path
                ),

            "size":
                stat.st_size,

            "mtime":
                int(
                    stat.st_mtime
                ),
        }

    # ============================================================
    # CACHE
    # ============================================================

    def _save_cache(self):

        try:

            with open(
                self._cache_path,
                "wb",
            ) as fh:

                pickle.dump(
                    {
                        "version": 3,

                        "chunks":
                            self.chunks,

                        "meta":
                            self.meta,
                    },

                    fh,

                    protocol=
                    pickle.HIGHEST_PROTOCOL,
                )

        except Exception as exc:

            print(
                f"[KB] Cache save failed: {exc}",
                flush=True,
            )

    def _load_cache(self):

        if not os.path.exists(
            self._cache_path
        ):

            return None

        try:

            with open(
                self._cache_path,
                "rb",
            ) as fh:

                data = pickle.load(
                    fh
                )

            if not isinstance(
                data,
                dict,
            ):

                return None

            return data

        except Exception as exc:

            print(
                f"[KB] Cache load failed: {exc}",
                flush=True,
            )

            return None

    # ============================================================
    # MANIFEST
    # ============================================================

    def _save_manifest(
        self,
        records,
    ) -> None:

        try:

            documents = {}

            for filename, record in records.items():

                item = dict(
                    record
                )

                item.pop(
                    "path",
                    None,
                )

                documents[
                    filename
                ] = item

            with open(
                self._manifest_path,
                "w",
                encoding="utf-8",
            ) as fh:

                json.dump(
                    {
                        "version": 1,

                        "documents":
                            documents,
                    },

                    fh,

                    indent=2,
                )

        except Exception as exc:

            print(
                f"[KB] Manifest save failed: {exc}",
                flush=True,
            )

    def _load_manifest(self):

        if not os.path.exists(
            self._manifest_path
        ):

            return None

        try:

            with open(
                self._manifest_path,
                "r",
                encoding="utf-8",
            ) as fh:

                data = json.load(
                    fh
                )

            if not isinstance(
                data,
                dict,
            ):

                return None

            return data

        except Exception:

            return None

    # ============================================================
    # FILE DISCOVERY
    # ============================================================

    def _list_files(self):
        """
        Return all supported knowledge-base files from the primary
        data directory and any configured extra data directories.
        """
        files = []

        roots = [self.data_dir]

        # Optional additional source directories
        extra_dirs = getattr(self, "extra_data_dirs", [])

        if extra_dirs:
            roots.extend(extra_dirs)

        for root in roots:
            if not root:
                continue

            root = os.path.abspath(root)

            if not os.path.isdir(root):
                continue

            for dirpath, _, filenames in os.walk(root):
                for filename in filenames:
                    ext = os.path.splitext(filename)[1].lower()

                    if ext in SUPPORTED_EXTS:
                        files.append(
                            os.path.join(
                                dirpath,
                                filename,
                            )
                        )

        return sorted(set(files))

    # ============================================================
    # EXTRACTION
    # ============================================================

    def _extract_segments(
        self,
        path: str,
    ) -> List[
        Tuple[
            str,
            Optional[int]
        ]
    ]:

        extension = os.path.splitext(
            path
        )[1].lower()

        if extension == ".pdf":

            return self._extract_pdf(
                path
            )

        if extension == ".docx":

            return self._extract_docx(
                path
            )

        if extension == ".pptx":

            return self._extract_pptx(
                path
            )

        if extension == ".xlsx":

            return self._extract_xlsx(
                path
            )

        if extension in IMAGE_EXTS:

            return self._extract_image(
                path
            )

        if extension in (
            ".txt",
            ".md",
            ".csv",
        ):

            with open(
                path,
                "r",
                encoding="utf-8",
                errors="ignore",
            ) as fh:

                return [
                    (
                        fh.read(),
                        None,
                    )
                ]

        return []

    # ============================================================
    # PDF
    # ============================================================

    def _extract_pdf(
        self,
        path: str,
        ) -> List[Tuple[str, Optional[int]]]:
        """
        Fast PDF extraction.

        Strategy:
            1. Use PyMuPDF text extraction first.
            2. If a page contains sufficient text, use it directly.
            3. OCR only genuinely empty/sparse pages.
            4. Keep the PDF open once instead of reopening it per page.
            5. Use 1.5x rendering for OCR instead of 2x.
        """

        segments: List[Tuple[str, Optional[int]]] = []

        # --------------------------------------------------------------
        # Prefer PyMuPDF for fast native PDF text extraction
        # --------------------------------------------------------------
        if pymupdf is not None:
            pdf_document = None

            try:
                pdf_document = pymupdf.open(path)

                total_pages = len(pdf_document)
                ocr_pages = 0
                text_pages = 0

                print(
                    f"[KB] PDF pages: {total_pages}",
                    flush=True,
                )

                for page_number, pdf_page in enumerate(
                    pdf_document,
                    start=1,
                ):
                    text = ""

                    # --------------------------------------------------
                    # FAST PATH: native PDF text
                    # --------------------------------------------------
                    try:
                        text = pdf_page.get_text("text") or ""
                    except Exception as exc:
                        print(
                            f"[KB] Text extraction failed "
                            f"{os.path.basename(path)} "
                            f"page {page_number}: {exc}",
                            flush=True,
                        )

                    clean_len = len(
                        "".join(text.split())
                    )

                    # --------------------------------------------------
                    # Normal digital PDF page
                    # --------------------------------------------------
                    if clean_len >= 20:
                        segments.append(
                            (
                                text,
                                page_number,
                            )
                        )

                        text_pages += 1

                    # --------------------------------------------------
                    # OCR FALLBACK
                    # --------------------------------------------------
                    elif _OCR_AVAILABLE:
                        try:
                            pixmap = pdf_page.get_pixmap(
                                matrix=pymupdf.Matrix(
                                    1.5,
                                    1.5,
                                ),
                                alpha=False,
                            )

                            image_array = np.frombuffer(
                                pixmap.samples,
                                dtype=np.uint8,
                            ).reshape(
                                pixmap.height,
                                pixmap.width,
                                pixmap.n,
                            )

                            # Remove alpha channel.
                            if pixmap.n == 4:
                                image_array = image_array[:, :, :3]

                            result, _ = _OCR(
                                image_array
                            )

                            if result:
                                ocr_text = "\n".join(
                                    item[1]
                                    for item in result
                                    if (
                                        len(item) > 1
                                        and item[1]
                                    )
                                )

                                if ocr_text.strip():
                                    segments.append(
                                        (
                                            ocr_text,
                                            page_number,
                                        )
                                    )

                                    self._extraction_types[
                                        (path, page_number)
                                    ] = "ocr"

                                    ocr_pages += 1

                        except Exception as exc:
                            print(
                                f"[KB] OCR failed "
                                f"{os.path.basename(path)} "
                                f"page {page_number}: "
                                f"{exc}",
                                flush=True,
                            )

                    # --------------------------------------------------
                    # Progress
                    # --------------------------------------------------
                    if (
                        page_number == 1
                        or page_number % 25 == 0
                        or page_number == total_pages
                    ):
                        print(
                            f"[KB] PDF progress: "
                            f"{page_number}/{total_pages} "
                            f"({page_number / total_pages * 100:.1f}%)",
                            flush=True,
                        )

                print(
                    f"[KB] PDF extraction complete: "
                    f"text={text_pages}, "
                    f"OCR={ocr_pages}",
                    flush=True,
                )

                return segments

            except Exception as exc:
                print(
                    f"[KB] PyMuPDF PDF extraction failed "
                    f"for {os.path.basename(path)}: {exc}",
                    flush=True,
                )

            finally:
                if pdf_document is not None:
                    try:
                        pdf_document.close()
                    except Exception:
                        pass

    # --------------------------------------------------------------
        # Fallback: pypdf
        # --------------------------------------------------------------
        if PdfReader is not None:
            try:
                reader = PdfReader(path)

                for page_number, page in enumerate(
                    reader.pages,
                    start=1,
                ):
                    try:
                        text = page.extract_text() or ""

                        if text.strip():
                            segments.append(
                                (
                                    text,
                                    page_number,
                                )
                            )

                    except Exception as exc:
                        print(
                            f"[KB] Fallback PDF extraction failed "
                            f"{os.path.basename(path)} "
                            f"page {page_number}: {exc}",
                            flush=True,
                        )

            except Exception as exc:
                print(
                    f"[KB] Failed to open PDF "
                    f"{os.path.basename(path)}: {exc}",
                    flush=True,
                )

        return segments

    # ============================================================
    # DOCX
    # ============================================================

    def _extract_docx(
        self,
        path: str,
    ) -> List[
        Tuple[
            str,
            Optional[int]
        ]
    ]:

        if docx is None:

            return [
                (
                    "[DOCX support not installed]",
                    None,
                )
            ]

        document = docx.Document(
            path
        )

        parts = [
            paragraph.text

            for paragraph in document.paragraphs

            if paragraph.text.strip()
        ]

        for table in document.tables:

            for row in table.rows:

                cells = [
                    cell.text.strip()

                    for cell in row.cells
                ]

                line = " | ".join(
                    cell

                    for cell in cells

                    if cell
                )

                if line:

                    parts.append(
                        line
                    )

        return [
            (
                "\n".join(parts),
                None,
            )
        ]

    # ============================================================
    # PPTX
    # ============================================================

    def _extract_pptx(
        self,
        path: str,
    ) -> List[
        Tuple[
            str,
            Optional[int]
        ]
    ]:

        if Presentation is None:

            return [
                (
                    "[PPTX support not installed]",
                    None,
                )
            ]

        presentation = Presentation(
            path
        )

        segments = []

        for slide_number, slide in enumerate(
            presentation.slides,
            start=1,
        ):

            texts = []

            for shape in slide.shapes:

                if getattr(
                    shape,
                    "has_text_frame",
                    False,
                ):

                    for paragraph in (
                        shape.text_frame.paragraphs
                    ):

                        text = "".join(
                            run.text

                            for run in paragraph.runs
                        ).strip()

                        if text:

                            texts.append(
                                text
                            )

                if getattr(
                    shape,
                    "has_table",
                    False,
                ):

                    for row in shape.table.rows:

                        cells = [
                            cell.text.strip()

                            for cell in row.cells
                        ]

                        line = " | ".join(
                            cell

                            for cell in cells

                            if cell
                        )

                        if line:

                            texts.append(
                                line
                            )

            if texts:

                segments.append(
                    (
                        "\n".join(texts),
                        slide_number,
                    )
                )

        return segments

    # ============================================================
    # XLSX
    # ============================================================

    def _extract_xlsx(
        self,
        path: str,
    ) -> List[
        Tuple[
            str,
            Optional[int]
        ]
    ]:

        if openpyxl is None:

            return [
                (
                    "[XLSX support not installed]",
                    None,
                )
            ]

        workbook = openpyxl.load_workbook(
            path,
            data_only=True,
            read_only=True,
        )

        segments = []

        for worksheet in workbook.worksheets:

            rows = []

            for row in worksheet.iter_rows(
                values_only=True
            ):

                values = [
                    str(value).strip()

                    for value in row

                    if (
                        value is not None
                        and str(value).strip()
                    )
                ]

                if values:

                    rows.append(
                        " | ".join(values)
                    )

            if rows:

                segments.append(
                    (
                        f"[Sheet: {worksheet.title}]\n"
                        + "\n".join(rows),
                        None,
                    )
                )

        return segments

    # ============================================================
    # IMAGE
    # ============================================================

    def _extract_image(
        self,
        path: str,
    ) -> List[
        Tuple[
            str,
            Optional[int]
        ]
    ]:

        if not _OCR_AVAILABLE:

            return [
                (
                    "[OCR not available for this image]",
                    None,
                )
            ]

        try:

            result, _ = _OCR(
                path
            )

            if not result:

                return []

            text = "\n".join(
                item[1]

                for item in result

                if len(item) > 1
                and item[1]
            )

            if not text.strip():

                return []

            self._extraction_types[(path, None)] = "ocr"

            return [
                (
                    f"[Image OCR: "
                    f"{os.path.basename(path)}]\n"
                    f"{text}",

                    None,
                )
            ]

        except Exception as exc:

            return [
                (
                    f"[Image OCR failed: {exc}]",
                    None,
                )
            ]

    # ============================================================
    # CHUNKING
    # ============================================================

    @staticmethod
    def _chunk(
        text: str,
    ) -> List[str]:

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        if not text:

            return []

        if len(text) <= CHUNK_SIZE:

            return [
                text
            ]

        chunks = []

        start = 0

        while start < len(text):

            end = (
                start
                + CHUNK_SIZE
            )

            if end < len(text):

                cut = text.rfind(
                    " ",
                    start,
                    end,
                )

                if (
                    cut
                    > start
                    + CHUNK_SIZE // 2
                ):

                    end = cut

            chunks.append(
                text[
                    start:end
                ].strip()
            )

            start = max(
                end - CHUNK_OVERLAP,
                start + 1,
            )

        return chunks