"""Persistent Chroma vector store for Intellex.

Chroma is the semantic-search layer of Intellex.

The original documents do NOT need to be opened during a normal query.
Documents are embedded when they are ingested and the vectors remain
persistent on disk.
"""

import os
from typing import Dict, List, Optional

from .embeddings import EmbeddingEngine


COLLECTION_NAME = "intellex_docs"


class VectorStore:

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedding=None,
    ):
        # Render:
        #   INTELLEX_CACHE_DIR=/var/data/intellex/kb
        #
        # Local:
        #   cache/chroma
        default_dir = os.path.join(
            os.getenv("INTELLEX_CACHE_DIR", "cache"),
            "chroma",
        )

        self.persist_dir = persist_dir or default_dir

        os.makedirs(self.persist_dir, exist_ok=True)

        self.embedding = embedding or EmbeddingEngine()

        self._client = None
        self._collection = None
        self._available = False

        try:
            self._ensure_client()
            self._available = True

            print(
                f"[VectorStore] Ready: {self.persist_dir}",
                flush=True,
            )

        except Exception as exc:
            print(
                f"[VectorStore] Disabled: {exc}",
                flush=True,
            )

            self._available = False

    # ================================================================
    # Chroma lifecycle
    # ================================================================

    def _ensure_client(self):

        import chromadb

        self._client = chromadb.PersistentClient(
            path=self.persist_dir
        )

        try:

            self._collection = self._client.get_collection(
                COLLECTION_NAME
            )

        except Exception:

            self._collection = self._client.create_collection(
                COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine",
                    "dim": self.embedding.dimension(),
                },
            )

    def _check_collection_metadata(self):

        if self._collection is None:
            return

        try:

            metadata = self._collection.metadata or {}

            stored_dim = int(
                metadata.get("dim", 0)
            )

        except Exception:

            return

        expected_dim = self.embedding.dimension()

        if stored_dim and stored_dim != expected_dim:

            print(
                "[VectorStore] Embedding dimension changed. "
                "Recreating vector collection.",
                flush=True,
            )

            try:

                self._client.delete_collection(
                    COLLECTION_NAME
                )

            except Exception:
                pass

            self._collection = (
                self._client.create_collection(
                    COLLECTION_NAME,
                    metadata={
                        "hnsw:space": "cosine",
                        "dim": expected_dim,
                    },
                )
            )

    # ================================================================
    # Adding documents
    # ================================================================

    def add_documents(
        self,
        ids: List[str],
        texts: List[str],
        metadatas: List[Dict],
    ) -> None:

        if not ids or not self._available:
            return

        try:

            self._check_collection_metadata()

            print(
                f"[VectorStore] Embedding {len(texts)} chunks...",
                flush=True,
            )

            vectors = self.embedding.embed(texts)

            # upsert instead of add:
            #
            # If a document is processed again, the same ID replaces
            # the previous vector instead of producing duplicates.
            self._collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=vectors,
                metadatas=metadatas,
            )

            print(
                f"[VectorStore] Added {len(texts)} chunks.",
                flush=True,
            )

        except Exception as exc:

            print(
                f"[VectorStore] add_documents failed: {exc}",
                flush=True,
            )

    # ================================================================
    # Semantic search
    # ================================================================

    def query(
        self,
        text: str,
        top_k: int = 5,
    ) -> List[Dict]:

        if not self._available:
            return []

        if self._collection is None:
            return []

        try:

            count = self._collection.count()

            if count == 0:
                return []

            # Only now do we generate an embedding.
            vector = self.embedding.embed(text)[0]

            result = self._collection.query(
                query_embeddings=[vector],
                n_results=min(top_k, count),
                include=[
                    "documents",
                    "metadatas",
                    "distances",
                ],
            )

        except Exception as exc:

            print(
                f"[VectorStore] query failed: {exc}",
                flush=True,
            )

            return []

        results = []

        ids = result.get("ids", [[]])[0]
        documents = result.get(
            "documents",
            [[]],
        )[0]

        metadatas = result.get(
            "metadatas",
            [[]],
        )[0]

        distances = result.get(
            "distances",
            [[]],
        )[0]

        for index, doc_id in enumerate(ids):

            metadata = (
                metadatas[index]
                if index < len(metadatas)
                else {}
            ) or {}

            distance = (
                float(distances[index])
                if index < len(distances)
                else 1.0
            )

            # Chroma cosine distance:
            #
            # similarity ≈ 1 - distance
            score = max(
                0.0,
                min(
                    1.0,
                    1.0 - distance,
                ),
            )

            results.append(
                {
                    "id": doc_id,

                    "text": (
                        documents[index]
                        if index < len(documents)
                        else ""
                    ),

                    "file": metadata.get(
                        "file",
                        "unknown",
                    ),

                    "page": metadata.get(
                        "page"
                    ),

                    "distance": distance,

                    "score": score,

                    "vector_score": score,
                }
            )

        return results

    # ================================================================
    # Delete by source file
    # ================================================================

    def delete_by_file(
        self,
        filename: str,
    ) -> None:

        if not self._available:
            return

        if self._collection is None:
            return

        try:

            self._collection.delete(
                where={
                    "file": filename,
                }
            )

            print(
                f"[VectorStore] Removed vectors for {filename}",
                flush=True,
            )

        except Exception as exc:

            print(
                f"[VectorStore] delete_by_file failed: {exc}",
                flush=True,
            )

    # ================================================================
    # Delete by managed document ID
    # ================================================================

    def delete_by_document(self, doc_id: str) -> None:
        """Delete all vectors belonging to a managed document ID."""
        if not self._available or self._collection is None:
            return
        target = str(doc_id or "").strip().upper()
        if not target:
            return
        try:
            self._collection.delete(where={"doc_id": target})
            print(
                f"[VectorStore] Removed vectors for document {target}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"[VectorStore] delete_by_document failed: {exc}",
                flush=True,
            )

    # ================================================================
    # Delete by source file
    # ================================================================

    def delete_by_file(self, filename: str) -> None:
        """Delete all vectors belonging to a source filename."""
        if not self._available or self._collection is None:
            return
        name = str(filename or "").strip()
        if not name:
            return
        try:
            self._collection.delete(where={"file": name})
            print(
                f"[VectorStore] Removed vectors for {name}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"[VectorStore] delete_by_file failed: {exc}",
                flush=True,
            )

    # ================================================================
    # Utility
    # ================================================================

    def count(self) -> int:

        if not self._available:
            return 0

        if self._collection is None:
            return 0

        try:

            return self._collection.count()

        except Exception:

            return 0

    def clear(self) -> None:

        if not self._available:
            return

        try:

            self._client.delete_collection(
                COLLECTION_NAME
            )

        except Exception:
            pass

        try:

            self._collection = (
                self._client.create_collection(
                    COLLECTION_NAME,
                    metadata={
                        "hnsw:space": "cosine",
                        "dim": self.embedding.dimension(),
                    },
                )
            )

        except Exception:

            self._ensure_client()

    def info(self) -> dict:

        return {
            "count": self.count(),

            "embedding": self.embedding.info(),

            "persist_dir": self.persist_dir,
        }