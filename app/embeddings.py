"""Embedding engine for semantic retrieval.

Auto-detects the best available embedding backend:

  1. BAAI/bge-m3 via sentence-transformers (if torch + sentence-transformers
     are installed) — highest quality, multilingual, ~2.5 GB install.
  2. nomic-embed-text via a local Ollama server (if running) — good quality,
     free, no Python ML stack needed.
  3. ChromaDB built-in default (all-MiniLM-L6-v2 via ONNX) — lightweight
     fallback that always works out-of-the-box.

The selected backend can be overridden with the EMBEDDING_BACKEND env var:
  "bge-m3" | "nomic" | "ollama" | "chroma"
"""

import os

try:
    from dotenv import load_dotenv

    _ENV_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    load_dotenv(_ENV_PATH)
except Exception:
    pass

DIM_BY_BACKEND = {
    "bge-m3": 1024,
    "nomic": 768,
    "ollama": 768,
    "chroma": 384,
}


class EmbeddingEngine:
    """Produces dense vectors for queries and document chunks."""

    def __init__(self):
        self.backend = os.getenv("EMBEDDING_BACKEND", "").strip().lower()
        self._model = None
        self._ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self._ollama_model = os.getenv(
            "OLLAMA_MODEL", "nomic-embed-text"
        )
        self._chroma_ef = None
        self._sentence_model = None
        self.backend = self._resolve_backend()

    # ------------------------------------------------------------------ #
    # Backend detection
    # ------------------------------------------------------------------ #
    def _resolve_backend(self) -> str:
        """Pick the first available backend matching the requested one."""
        preferred = self.backend

        if preferred in ("bge-m3", "bge_m3", "sentence"):
            if self._has_sentence_transformers():
                return "bge-m3"
            # fall through to auto-detect if not installed
        if preferred in ("nomic", "ollama"):
            if self._ollama_alive():
                return "ollama"
        if preferred == "chroma":
            return "chroma"
        if preferred:
            # Invalid requested backend -> auto-detect.
            pass

        # Auto-detect.
        if self._has_sentence_transformers():
            return "bge-m3"
        if self._ollama_alive():
            return "ollama"
        return "chroma"

    @staticmethod
    def _has_sentence_transformers() -> bool:
        try:
            import sentence_transformers  # noqa: F401
            import torch  # noqa: F401

            return True
        except Exception:
            return False

    def _ollama_alive(self) -> bool:
        try:
            import urllib.request

            with urllib.request.urlopen(
                f"{self._ollama_url}/api/tags", timeout=2
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Lazy model loading
    # ------------------------------------------------------------------ #
    def _ensure_model(self):
        if self.backend == "bge-m3" and self._sentence_model is None:
            from sentence_transformers import SentenceTransformer

            self._sentence_model = SentenceTransformer(
                os.getenv("BGE_M3_MODEL", "BAAI/bge-m3")
            )
        elif self.backend == "chroma" and self._chroma_ef is None:
            import chromadb.utils.embedding_functions as ef

            self._chroma_ef = ef.DefaultEmbeddingFunction()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def dimension(self) -> int:
        return DIM_BY_BACKEND.get(self.backend, 384)

    def embed(self, texts, batch_size: int = 8) -> list:
        """Embed a list of strings (or a single string) into vectors."""
        if isinstance(texts, str):
            texts = [texts]
        texts = [t[:2000] for t in texts]  # keep memory bounded

        self._ensure_model()

        if self.backend == "bge-m3":
            vecs = self._sentence_model.encode(
                texts, batch_size=batch_size, normalize_embeddings=True
            )
            return [v.tolist() for v in vecs]

        if self.backend == "ollama":
            return self._embed_ollama(texts)

        # chroma default
        self._ensure_model()
        out = self._chroma_ef(texts)
        if isinstance(out, tuple):
            out = out[0]
        return [list(map(float, v)) for v in out]

    def _embed_ollama(self, texts):
        import json
        import urllib.request

        vecs = []
        for t in texts:
            payload = json.dumps({"model": self._ollama_model, "prompt": t}).encode(
                "utf-8"
            )
            req = urllib.request.Request(
                f"{self._ollama_url}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vecs.append(data["embedding"])
        return vecs

    def info(self) -> dict:
        return {
            "backend": self.backend,
            "dimension": self.dimension(),
        }

