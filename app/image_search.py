"""
AVARIX image search service.

Provides lightweight technical image retrieval for the chatbot.

Priority:
    DDGS image search
        ↓ on failure or no usable results
    Wikimedia Commons API
        ↓
    normalized AVARIX visual objects

This module is deliberately optional:
if image search is unavailable or fails, it returns an empty list
without affecting the main chatbot pipeline.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional
from urllib.parse import urlparse


class ImageSearch:

    VALID_BACKENDS = {
        "auto",
        "bing",
        "duckduckgo",
    }

    DEFAULT_MAX_RESULTS = 4
    DEFAULT_TIMEOUT = 6

    # Conservative filters for obvious non-technical or unsuitable results.
    BLOCKED_DOMAINS = {
        "pinterest.com",
        "pinterest.ca",
        "pinterest.co.uk",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
    }

    BLOCKED_TERMS = {
        "adult",
        "porn",
        "xxx",
        "coloring page",
        "clipart",
        "sticker",
        "meme",
    }

    COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"

    # ============================================================
    # VISUAL QUALITY / SAFETY FILTERS
    # ============================================================
    # Words that commonly indicate useful engineering/scientific
    # visual material.
    TECHNICAL_TERMS = {
        "diagram",
        "schematic",
        "figure",
        "fig",
        "graph",
        "plot",
        "mesh",
        "finite",
        "element",
        "analysis",
        "engineering",
        "aerospace",
        "aerodynamic",
        "aerodynamics",
        "airfoil",
        "flow",
        "pressure",
        "velocity",
        "force",
        "stress",
        "strain",
        "structure",
        "structural",
        "simulation",
        "model",
        "mathematical",
        "equation",
        "mechanics",
        "thermodynamic",
        "thermodynamics",
        "propulsion",
        "rocket",
        "aircraft",
        "wing",
        "turbine",
        "compressor",
        "nozzle",
        "mach",
        "boundary",
        "layer",
        "lift",
        "drag",
        "moment",
        "trajectory",
        "orbit",
        "satellite",
        "sensor",
        "control",
        "circuit",
        "material",
        "composite",
    }

    STOP_WORDS = {
        "what",
        "is",
        "are",
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "in",
        "on",
        "and",
        "or",
        "how",
        "why",
        "where",
        "when",
        "does",
        "do",
        "used",
        "use",
        "with",
        "from",
        "this",
        "that",
        "can",
        "be",
        "its",
        "it",
        "technical",
        "diagram",
        "image",
        "images",
    }

    def __init__(
        self,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: Optional[float] = None,
        backend: Optional[str] = None,
    ):
        self.max_results = max(
            1,
            min(
                int(max_results),
                8,
            ),
        )

        self.timeout = self._read_timeout(
            timeout
        )

        configured_backend = (
            backend
            or os.getenv(
                "IMAGE_SEARCH_BACKEND",
                "auto",
            )
        )

        self.backend = (
            str(configured_backend)
            .strip()
            .lower()
        )

        if self.backend not in self.VALID_BACKENDS:
            print(
                "[IMAGE SEARCH] Invalid backend "
                f"'{self.backend}'. Using 'auto'.",
                flush=True,
            )
            self.backend = "auto"

        self._ddgs = None
        self._available = False
        self._backend_name = "unavailable"

        self._initialize()

    # ============================================================
    # CONFIGURATION
    # ============================================================

    @staticmethod
    def _read_timeout(
        timeout: Optional[float],
    ) -> float:

        if timeout is not None:
            try:
                return max(
                    1.0,
                    float(timeout),
                )
            except (
                TypeError,
                ValueError,
            ):
                pass

        try:
            return max(
                1.0,
                float(
                    os.getenv(
                        "IMAGE_SEARCH_TIMEOUT",
                        str(
                            ImageSearch.DEFAULT_TIMEOUT
                        ),
                    )
                ),
            )
        except (
            TypeError,
            ValueError,
        ):
            return float(
                ImageSearch.DEFAULT_TIMEOUT
            )

    # ============================================================
    # INITIALIZATION
    # ============================================================

    def _initialize(self) -> None:
        """
        Initialize DDGS lazily.

        Import failures do not propagate into the chatbot.
        """

        try:
            from ddgs import DDGS

            self._ddgs = DDGS(
                timeout=self.timeout,
            )

            self._available = True

            if self.backend == "auto":
                self._backend_name = "ddgs:auto"
            else:
                self._backend_name = (
                    f"ddgs:{self.backend}"
                )

        except Exception as exc:
            self._ddgs = None
            self._available = False
            self._backend_name = "unavailable"

            print(
                "[IMAGE SEARCH] Initialization failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

    # ============================================================
    # STATUS
    # ============================================================

    @property
    def available(self) -> bool:
        """
        Whether the image-search backend initialized successfully.
        """

        return bool(
            self._available
            and self._ddgs is not None
        )

    def backend_name(self) -> str:
        """
        Return a human-readable backend name.
        """

        return self._backend_name

    # ============================================================
    # RESULT NORMALIZATION
    # ============================================================

    def _normalize_result(
    self,
    item: Dict,
    query: str = "",
) -> Optional[Dict]:
        """
        Convert a DDGS image result into the stable AVARIX
        visual-result format.

        Direct image URLs are required.

        Basic quality filtering is performed here so malformed
        or obviously unusable results never reach the frontend.
        """

        if not isinstance(
            item,
            dict,
        ):
            return None

        # --------------------------------------------------------
        # Direct image URL
        # --------------------------------------------------------

        image_url = str(
            item.get("image")
            or ""
        ).strip()

        if not image_url:
            return None

        # --------------------------------------------------------
        # Basic URL validation
        # --------------------------------------------------------

        if not image_url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            return None

        # --------------------------------------------------------
        # Source page
        # --------------------------------------------------------

        source_url = str(
            item.get("url")
            or ""
        ).strip()

        if source_url and not source_url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            source_url = ""

        # --------------------------------------------------------
        # Thumbnail
        # --------------------------------------------------------

        thumbnail_url = str(
            item.get("thumbnail")
            or ""
        ).strip()

        if thumbnail_url and not thumbnail_url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            thumbnail_url = ""

        # --------------------------------------------------------
        # Metadata
        # --------------------------------------------------------

        title = str(
            item.get("title")
            or ""
        ).strip()

        source = str(
            item.get("source")
            or ""
        ).strip()

        # --------------------------------------------------------
        # Dimensions
        # --------------------------------------------------------

        width = item.get(
            "width"
        )

        height = item.get(
            "height"
        )

        try:
            width = int(width)

            if width <= 0:
                width = None

        except (
            TypeError,
            ValueError,
        ):
            width = None

        try:
            height = int(height)

            if height <= 0:
                height = None

        except (
            TypeError,
            ValueError,
        ):
            height = None

        # --------------------------------------------------------
        # Reject obviously tiny images when dimensions are known.
        #
        # This avoids many icons, buttons, avatars and thumbnails.
        # Do not reject images when dimensions are unavailable.
        # --------------------------------------------------------

        if (
            width is not None
            and height is not None
        ):
            if width < 200 or height < 150:
                return None

        # --------------------------------------------------------
        # Normalize whitespace in title.
        # --------------------------------------------------------

        title = " ".join(
            title.split()
        )

        # --------------------------------------------------------
        # Stable AVARIX visual object
        # --------------------------------------------------------

        result = {
            "title": title,
            "image_url": image_url,
            "thumbnail_url": thumbnail_url,
            "source_url": source_url,
            "source": source,
            "width": width,
            "height": height,
        }

        # Reject obvious junk before it reaches the caller.
        if self._is_blocked_visual(result):
            return None

        # Attach a relevance score so the search stage can rank
        # candidates instead of blindly accepting provider order.
        result["_relevance"] = self._visual_relevance_score(
            query,
            result,
        )

        return result

    # ============================================================
    # VISUAL QUALITY FILTERING
    # ============================================================

    @staticmethod
    def _clean_query(query: str) -> str:
        """
        Normalize the visual-search query.

        Removes question punctuation and common conversational
        scaffolding so the image provider receives a clean
        technical topic.
        """

        text = str(query or "").strip().lower()

        text = re.sub(
            r"\b(what is|what are|explain|define|tell me about)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(r"[?!.:,;]+", " ", text)

        text = re.sub(r"\s+", " ", text).strip()

        return text

    @staticmethod
    def _domain_from_url(url: str) -> str:
        """Return a normalized hostname."""

        try:
            hostname = urlparse(
                str(url or "")
            ).hostname or ""

            hostname = hostname.lower().strip()

            if hostname.startswith("www."):
                hostname = hostname[4:]

            return hostname

        except Exception:
            return ""

    @classmethod
    def _is_blocked_visual(cls, item: Dict) -> bool:
        """
        Reject clearly unsuitable visual results.

        This is intentionally conservative: it blocks obvious
        entertainment/adult/clipart material but does not require
        images to come from a fixed allow-list of websites.
        """

        title = str(
            item.get("title") or ""
        ).lower()

        image_url = str(
            item.get("image_url") or ""
        ).lower()

        source_url = str(
            item.get("source_url") or ""
        ).lower()

        source = str(
            item.get("source") or ""
        ).lower()

        combined = " ".join(
            (
                title,
                image_url,
                source_url,
                source,
            )
        )

        # --------------------------------------------------------
        # Domain blocking
        # --------------------------------------------------------

        for url in (
            image_url,
            source_url,
        ):
            domain = cls._domain_from_url(url)

            if not domain:
                continue

            if any(
                domain == blocked
                or domain.endswith("." + blocked)
                for blocked in cls.BLOCKED_DOMAINS
            ):
                return True

        # --------------------------------------------------------
        # File-type blocking
        # --------------------------------------------------------

        if re.search(
            r"\.(?:gif)(?:$|[?#])",
            image_url,
            flags=re.IGNORECASE,
        ):
            return True

        # --------------------------------------------------------
        # Content-term blocking
        # --------------------------------------------------------

        for term in cls.BLOCKED_TERMS:
            if term in combined:
                return True

        return False

    @classmethod
    def _visual_relevance_score(
        cls,
        query: str,
        item: Dict,
    ) -> float:
        """
        Score an image according to how closely its metadata
        matches the requested technical topic.

        Returns a value in [0, 1].
        """

        clean_query = cls._clean_query(query)

        if not clean_query:
            return 0.0

        title = str(
            item.get("title") or ""
        ).lower()

        source = str(
            item.get("source") or ""
        ).lower()

        source_url = str(
            item.get("source_url") or ""
        ).lower()

        metadata = " ".join(
            (
                title,
                source,
                source_url,
            )
        )

        # --------------------------------------------------------
        # Query terms
        # --------------------------------------------------------

        query_terms = [
            token
            for token in re.findall(
                r"[a-z0-9]+",
                clean_query,
            )
            if len(token) >= 3
            and token not in cls.STOP_WORDS
        ]

        if not query_terms:
            return 0.0

        # --------------------------------------------------------
        # Exact phrase matches are strong evidence.
        # --------------------------------------------------------

        phrase_score = 0.0

        phrases = []

        if "finite element analysis" in clean_query:
            phrases.append(
                "finite element analysis"
            )

        if "finite element method" in clean_query:
            phrases.append(
                "finite element method"
            )

        if "boundary layer" in clean_query:
            phrases.append(
                "boundary layer"
            )

        if "mach number" in clean_query:
            phrases.append(
                "mach number"
            )

        if "pitot tube" in clean_query:
            phrases.append(
                "pitot tube"
            )

        for phrase in phrases:
            if phrase in metadata:
                phrase_score = max(
                    phrase_score,
                    0.75,
                )

        # --------------------------------------------------------
        # Individual query-term overlap
        # --------------------------------------------------------

        matched = sum(
            1
            for term in query_terms
            if re.search(
                rf"\b{re.escape(term)}\b",
                metadata,
            )
        )

        term_score = (
            matched / len(query_terms)
            if query_terms
            else 0.0
        )

        # --------------------------------------------------------
        # Technical vocabulary bonus
        # --------------------------------------------------------

        technical_matches = sum(
            1
            for term in cls.TECHNICAL_TERMS
            if re.search(
                rf"\b{re.escape(term)}\b",
                metadata,
            )
        )

        technical_bonus = min(
            0.20,
            technical_matches * 0.04,
        )

        # --------------------------------------------------------
        # Combine scores.
        # --------------------------------------------------------

        score = max(
            phrase_score,
            0.65 * term_score
            + technical_bonus,
        )

        return max(
            0.0,
            min(
                1.0,
                score,
            ),
        )

    # ============================================================
    # WIKIMEDIA COMMONS FALLBACK
    # ============================================================

    def _search_commons(
        self,
        query: str,
        max_results: int,
    ) -> List[Dict]:
        """Retrieve and normalize Wikimedia Commons image candidates."""
        # Use the same focused subject query for Commons retrieval and
        # relevance scoring. Scoring against the augmented chatbot query
        # incorrectly penalizes valid titles that mention only the subject.
        commons_query = " ".join(
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) >= 3
            and token not in self.STOP_WORDS
            and token not in {
                "technical", "diagram", "image", "images",
                "engineering", "aerospace",
            }
        ) or query

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": commons_query,
            "gsrnamespace": 6,
            "gsrlimit": min(max_results * 3, 20),
            "prop": "imageinfo",
            "iiprop": "url|size",
            "iiurlwidth": 800,
            "format": "json",
        }
        url = self.COMMONS_API_URL + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AVARIX/1.0 (technical image retrieval)"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        pages = payload.get("query", {}).get("pages", {})
        candidates = []
        seen_urls = set()
        rejected_normalization = 0
        rejected_relevance = 0
        rejected_duplicate = 0
        rejected_missing_url = 0

        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            image_url = info.get("thumburl") or info.get("url")
            if not image_url:
                rejected_missing_url += 1
                continue

            title = page.get("title", "").replace("File:", "", 1)
            source_url = page.get("canonicalurl") or (
                "https://commons.wikimedia.org/wiki/"
                + urllib.parse.quote(page.get("title", "").replace(" ", "_"))
            )
            normalized = self._normalize_result(
                {
                    "image": image_url,
                    "thumbnail": info.get("thumburl") or image_url,
                    "url": source_url,
                    "title": title,
                    "source": "Wikimedia Commons",
                    "width": info.get("width"),
                    "height": info.get("height"),
                },
                query=commons_query,
            )
            if normalized is None:
                rejected_normalization += 1
                continue

            if normalized["image_url"] in seen_urls:
                rejected_duplicate += 1
                continue
            seen_urls.add(normalized["image_url"])

            if normalized.get("_relevance", 0.0) < 0.30:
                rejected_relevance += 1
                continue
            candidates.append(normalized)

        candidates.sort(
            key=lambda item: float(item.get("_relevance", 0.0)),
            reverse=True,
        )

        print(
            "[IMAGE SEARCH] provider=commons diagnostics "
            f"raw={len(pages)} accepted={len(candidates)} "
            f"missing_url={rejected_missing_url} "
            f"normalization_rejected={rejected_normalization} "
            f"duplicate={rejected_duplicate} "
            f"low_relevance={rejected_relevance} "
            f"query={query!r}",
            flush=True,
        )
        return candidates[:max_results]

    # ============================================================
    # IMAGE SEARCH
    # ============================================================

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> List[Dict]:
        """
        Search for technical images.

        Returns a normalized list. Any backend failure results
        in [] so image retrieval can never break the chatbot.
        """

        query = self._clean_query(query)

        if not query:
            return []

        # Continue even when DDGS is unavailable: Wikimedia Commons
        # is an independent fallback and does not require DDGS.
        try:
            requested = (
                max_results
                if max_results is not None
                else self.max_results
            )

            requested = max(
                1,
                min(
                    int(requested),
                    8,
                ),
            )

        except (
            TypeError,
            ValueError,
        ):
            requested = self.max_results

        t0 = time.perf_counter()

        try:
            # Retrieve more candidates than we ultimately display.
            # The quality filter needs enough candidates to discard
            # irrelevant provider results without ending up with
            # an empty visual rail.
            candidate_limit = min(
                max(
                    requested * 4,
                    requested + 4,
                ),
                16,
            )

            kwargs = {
                "max_results": candidate_limit,
            }

            # DDGS supports backend selection. For "auto", allow
            # DDGS to choose its available image backend.
            if self.backend != "auto":
                kwargs["backend"] = self.backend

            # --------------------------------------------------------
            # Image search is an optional enrichment step.
            #
            # If the provider hangs or fails, the main AVARIX answer
            # must still be returned without treating image retrieval
            # as a fatal error.
            # --------------------------------------------------------

            results = []

            # Primary provider: DDGS.
            try:
                raw_results = self._ddgs.images(query, **kwargs)
                candidates = []
                seen_urls = set()
                for item in raw_results or []:
                    normalized = self._normalize_result(item, query=query)
                    if normalized is None:
                        continue
                    image_url = normalized["image_url"]
                    if image_url in seen_urls:
                        continue
                    seen_urls.add(image_url)
                    if normalized.get("_relevance", 0.0) < 0.30:
                        continue
                    candidates.append(normalized)

                candidates.sort(
                    key=lambda item: float(item.get("_relevance", 0.0)),
                    reverse=True,
                )
                results = candidates[:requested]
            except Exception as exc:
                print(
                    "[IMAGE SEARCH] provider=ddgs status=FAILED "
                    f"error={type(exc).__name__}: {exc} fallback=commons",
                    flush=True,
                )

            # Use Commons only if DDGS failed or returned no usable images.
            if not results:
                try:
                    results = self._search_commons(query, requested)
                    print(
                        "[IMAGE SEARCH] provider=commons "
                        f"status={'SUCCESS' if results else 'EMPTY'} "
                        f"results={len(results)}",
                        flush=True,
                    )
                except Exception as exc:
                    print(
                        "[IMAGE SEARCH] provider=commons status=FAILED "
                        f"error={type(exc).__name__}: {exc}",
                        flush=True,
                    )

            # Internal ranking metadata should not reach the frontend.
            for result in results:
                result.pop("_relevance", None)

            elapsed = time.perf_counter() - t0
            print(
                "[IMAGE SEARCH] "
                f"query={query!r} results={len(results)} time={elapsed:.2f}s",
                flush=True,
            )
            return results

        except Exception as exc:

            elapsed = (
                time.perf_counter()
                - t0
            )

            print(
                "[IMAGE SEARCH] Search failed: "
                f"{type(exc).__name__}: {exc} "
                f"after {elapsed:.2f}s",
                flush=True,
            )

            return []

    # ============================================================
    # CLEANUP
    # ============================================================

    def close(self) -> None:
        """
        Close the underlying DDGS client when supported.
        """

        client = self._ddgs

        if client is None:
            return

        try:
            close = getattr(
                client,
                "close",
                None,
            )

            if callable(close):
                close()

        except Exception:
            pass

        finally:
            self._ddgs = None
            self._available = False
            self._backend_name = "unavailable"