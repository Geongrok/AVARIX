"""
Persistent cache for stable answers obtained from web research.

The curated AVARIX knowledge base remains authoritative and is checked first.
This cache is only a performance layer for previously answered, non-time-dependent
questions.

It stores:
    - the answer
    - structured AVARIX answer data
    - optional visual metadata
    - web provenance

Cache hits therefore require no new web/LLM API call.
"""

import json
import os
import re
import tempfile
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


class AnswerCache:
    def __init__(self, path: str, max_entries: int = 1000):
        self.path = os.path.abspath(path)
        self.max_entries = max(50, int(max_entries))

        self.entries: List[Dict] = []
        self._by_key: Dict[str, Dict] = {}

        self._load()

    # ------------------------------------------------------------------ #
    # Query normalization
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize(question: str) -> str:
        q = (question or "").lower()

        q = re.sub(r"[^a-z0-9]+", " ", q)
        q = re.sub(r"\s+", " ", q).strip()

        # Remove common question framing while preserving technical terms.
        q = re.sub(
            r"^(?:please\s+)?(?:can you|could you|would you)?\s*",
            "",
            q,
            flags=re.I,
        )

        q = re.sub(
            r"^(?:tell me|explain|define|describe)\s+(?:about\s+)?",
            "",
            q,
        )

        q = re.sub(
            r"^(?:what|whats)\s+(?:is|are)\s+",
            "",
            q,
        )

        return q.strip()

    @staticmethod
    def _tokens(text: str) -> set:
        return set(
            re.findall(
                r"[a-z0-9]{2,}",
                text.lower(),
            )
        )

    @classmethod
    def _similar(cls, a: str, b: str) -> float:
        if not a or not b:
            return 0.0

        if a == b:
            return 1.0

        ta, tb = cls._tokens(a), cls._tokens(b)

        if len(ta) >= 3 and len(tb) >= 3:
            jaccard = len(ta & tb) / max(
                1,
                len(ta | tb),
            )

            if jaccard >= 0.82:
                return max(
                    jaccard,
                    SequenceMatcher(
                        None,
                        a,
                        b,
                    ).ratio(),
                )

        return SequenceMatcher(
            None,
            a,
            b,
        ).ratio()

    # ------------------------------------------------------------------ #
    # Result cleaning
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clean_result(result: Dict) -> Dict:
        """
        Persist only UI/provenance fields from a web result.

        Internal provider flags and implementation-specific fields are
        intentionally excluded.
        """
        return {
            "title": str(
                result.get("title", "")
            ).strip(),

            "url": str(
                result.get("url", "")
            ).strip(),

            "snippet": str(
                result.get("snippet", "")
            )[:1200],
        }

    @staticmethod
    def _clean_visual(visual: Any) -> Optional[Dict]:
        """
        Normalize a visual descriptor before persistence.

        Visuals are metadata only. The cache never downloads or embeds
        image data.
        """
        if isinstance(visual, str):
            value = visual.strip()

            if not value:
                return None

            return {
                "title": value,
            }

        if not isinstance(visual, dict):
            return None

        cleaned = {}

        allowed_fields = (
            "title",
            "description",
            "url",
            "image_url",
            "thumbnail_url",
            "source",
            "source_url",
            "page",
            "type",
        )

        for field in allowed_fields:
            value = visual.get(field)

            if value is None:
                continue

            if isinstance(value, (str, int, float, bool)):
                if isinstance(value, str):
                    value = value.strip()

                    if not value:
                        continue

                cleaned[field] = value

        return cleaned or None

    @classmethod
    def _clean_visuals(cls, visuals: Any) -> List[Dict]:
        """
        Keep a small, safe list of visual metadata for cached answers.
        """
        if not isinstance(visuals, list):
            return []

        cleaned = []

        for visual in visuals[:8]:
            item = cls._clean_visual(visual)

            if item:
                cleaned.append(item)

        return cleaned

    @staticmethod
    def _clean_structured(structured: Any) -> Optional[Dict]:
        """
        Normalize the AVARIX structured-answer object.

        This deliberately keeps only the public response schema.
        """
        if not isinstance(structured, dict):
            return None

        result = {
            "answer": "",
            "explanation": "",
            "key_points": [],
            "formula": None,
            "applications": [],
            "examples": [],
        }

        result["answer"] = str(
            structured.get("answer") or ""
        ).strip()

        result["explanation"] = str(
            structured.get("explanation") or ""
        ).strip()

        for field in (
            "key_points",
            "applications",
            "examples",
        ):
            value = structured.get(field, [])

            if isinstance(value, str):
                value = (
                    [value.strip()]
                    if value.strip()
                    else []
                )

            if not isinstance(value, list):
                value = []

            cleaned = []

            for item in value[:8]:
                if isinstance(item, dict):
                    item = (
                        item.get("text")
                        or item.get("description")
                        or item.get("value")
                    )

                if item is None:
                    continue

                item = str(item).strip()

                if item:
                    cleaned.append(item)

            result[field] = cleaned

        formula = structured.get("formula")

        if formula is not None:
            if isinstance(formula, dict):
                result["formula"] = formula
            else:
                formula = str(formula).strip()

                if formula:
                    result["formula"] = formula

        # If absolutely nothing useful was supplied, don't persist
        # an empty structured object.
        if not any(
            (
                result["answer"],
                result["explanation"],
                result["key_points"],
                result["formula"],
                result["applications"],
                result["examples"],
            )
        ):
            return None

        return result

    # ------------------------------------------------------------------ #
    # Load / save
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        try:
            if not os.path.exists(self.path):
                return

            with open(
                self.path,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            entries = (
                data.get("entries", [])
                if isinstance(data, dict)
                else data
            )

            if not isinstance(entries, list):
                return

            cleaned_entries = []

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                if not entry.get("key"):
                    continue

                # Backward compatibility:
                # old cache files do not contain structured/visuals.
                entry.setdefault(
                    "structured",
                    None,
                )

                entry.setdefault(
                    "visuals",
                    [],
                )

                # Normalize potentially malformed/new fields.
                entry["structured"] = self._clean_structured(
                    entry.get("structured")
                )

                entry["visuals"] = self._clean_visuals(
                    entry.get("visuals")
                )

                cleaned_entries.append(entry)

            self.entries = cleaned_entries[
                -self.max_entries:
            ]

            self._by_key = {
                e["key"]: e
                for e in self.entries
            }

        except Exception as exc:
            print(
                f"[CACHE] Could not load answer cache: {exc}",
                flush=True,
            )

            self.entries = []
            self._by_key = {}

    def _save(self) -> None:
        os.makedirs(
            os.path.dirname(self.path),
            exist_ok=True,
        )

        payload = {
            "version": 2,
            "entries": self.entries[
                -self.max_entries:
            ],
        }

        fd, tmp = tempfile.mkstemp(
            prefix="web_answers_",
            suffix=".tmp",
            dir=os.path.dirname(self.path),
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    payload,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            os.replace(
                tmp,
                self.path,
            )

        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ------------------------------------------------------------------ #
    # Cache retrieval
    # ------------------------------------------------------------------ #

    def get(
        self,
        question: str,
    ) -> Optional[Dict]:
        key = self._normalize(question)

        if not key:
            return None

        exact = self._by_key.get(key)

        if exact:
            print(
                "[CACHE] Answer cache HIT (exact)",
                flush=True,
            )
            return exact

        best = None
        best_score = 0.0

        for entry in reversed(self.entries):
            score = self._similar(
                key,
                entry.get("key", ""),
            )

            if score > best_score:
                best_score = score
                best = entry

        # Conservative threshold to avoid answering a different question.
        if best is not None and best_score >= 0.90:
            print(
                f"[CACHE] Answer cache HIT "
                f"(similarity={best_score:.3f})",
                flush=True,
            )
            return best

        return None

    # ------------------------------------------------------------------ #
    # Cache storage
    # ------------------------------------------------------------------ #

    def put(
        self,
        question: str,
        answer: str,
        web_results: List[Dict],
        structured: Optional[Dict] = None,
        visuals: Optional[List] = None,
    ) -> None:
        """
        Store a completed web answer.

        New arguments:
            structured -> AVARIX adaptive answer sections
            visuals    -> optional related visual metadata

        Both are optional so existing callers remain compatible.
        """
        key = self._normalize(question)

        if not key or not answer:
            return

        entry = {
            "key": key,

            "question": (
                question or ""
            ).strip(),

            "answer": (
                answer or ""
            ).strip(),

            "structured": self._clean_structured(
                structured
            ),

            "visuals": self._clean_visuals(
                visuals
            ),

            "web_results": [
                self._clean_result(r)
                for r in (web_results or [])
                if isinstance(r, dict)
                and r.get("url")
            ],
        }

        if key in self._by_key:
            self._by_key[key].update(entry)

            self.entries = [
                entry
                if e.get("key") == key
                else e
                for e in self.entries
            ]

        else:
            self.entries.append(entry)
            self._by_key[key] = entry

        if len(self.entries) > self.max_entries:
            self.entries = self.entries[
                -self.max_entries:
            ]

            self._by_key = {
                e["key"]: e
                for e in self.entries
            }

        try:
            self._save()

            print(
                f"[CACHE] Saved web answer: "
                f"{question.strip()[:100]}",
                flush=True,
            )

        except Exception as exc:
            print(
                f"[CACHE] Could not save web answer: {exc}",
                flush=True,
            )

    # ------------------------------------------------------------------ #
    # Statistics
    # ------------------------------------------------------------------ #

    def stats(self) -> Dict:
        return {
            "entries": len(self.entries),
            "path": self.path,
        }