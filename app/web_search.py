"""
Intellex Web Search Module
==========================

Fast multi-backend web search with controlled fallbacks.

Priority:
    1. OpenRouter Web Search  - OPENROUTER_API_KEY
    2. Tavily                 - TAVILY_API_KEY
    3. Exa                    - EXA_API_KEY
    4. SerpAPI                - SERPAPI_API_KEY
    5. DuckDuckGo/DDGS        - free fallback

Important:
    - Web search is only used after the local Intellex knowledge base
      cannot answer the question.
    - We do NOT perform long serial searches across many DDGS engines.
    - Timeouts are deliberately short so a failed provider does not
      make Intellex appear frozen.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from typing import Dict, List


# ---------------------------------------------------------------------------
# Optional .env loading
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv

    _ENV_PATH = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        ),
        ".env",
    )

    load_dotenv(_ENV_PATH)

except Exception:
    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 6
DEFAULT_DDGS_TIMEOUT = 8


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return max(2, value)
    except Exception:
        return default


WEB_SEARCH_TIMEOUT = _env_int("WEB_SEARCH_TIMEOUT", DEFAULT_TIMEOUT)
DDGS_TIMEOUT = _env_int("DDGS_TIMEOUT", DEFAULT_DDGS_TIMEOUT)

# OpenRouter web search is a separate plugin from
# the normal OpenRouter LLM API.
ENABLE_OPENROUTER_WEB_SEARCH = (
    os.getenv(
        "ENABLE_OPENROUTER_WEB_SEARCH",
        "0",
    ).strip().lower()
    in {
        "1",
        "true",
        "yes",
        "on",
    }
)

# --------------------------------------------------------------
# Provider resilience / circuit breaker
# --------------------------------------------------------------

# Time a failed provider remains temporarily disabled.
# After this period the provider is automatically retried.
SEARCH_PROVIDER_COOLDOWN = _env_int(
    "SEARCH_PROVIDER_COOLDOWN",
    300,
)


# ---------------------------------------------------------------------------
# Web Search
# ---------------------------------------------------------------------------

class WebSearch:
    """Fast web search across multiple configurable backends."""

    def __init__(self, max_results: int = 5):

        self.max_results = max_results

        # API keys
        self.openrouter_key = os.getenv(
            "OPENROUTER_API_KEY",
            "",
        ).strip()
        
       

        self.tavily_key = os.getenv(
            "TAVILY_API_KEY",
            "",
        ).strip()

        self.exa_key = os.getenv(
            "EXA_API_KEY",
            "",
        ).strip()

        self.serpapi_key = os.getenv(
            "SERPAPI_API_KEY",
            "",
        ).strip()

        # DDGS availability
        self._ddgs_available = self._check_ddgs()

        # --------------------------------------------------------------
        # Provider resilience / circuit breaker
        # --------------------------------------------------------------
        #
        # Stores the timestamp of the most recent failure for each
        # provider. A failed provider is temporarily skipped and will
        # automatically become eligible again after the cooldown.
        #
        self._provider_failures = {}

        self._provider_cooldown = _env_int(
            "SEARCH_PROVIDER_COOLDOWN",
            300,
        )

        # Selected backend
        self._backend = self._detect_backend()

        print(
            f"[OPENROUTER DEBUG] WEB key_loaded={bool(self.openrouter_key)} "
            f"length={len(self.openrouter_key)} "
            f"prefix={self.openrouter_key[:10]}",
            flush=True,
        )
    # ------------------------------------------------------------------ #
    # Performance logging
    # ------------------------------------------------------------------ #

    @staticmethod
    def _perf(
        label: str,
        elapsed: float,
    ) -> None:

        enabled = os.getenv(
            "INTELLEX_PERF_LOG",
            "1",
        ).strip().lower()

        if enabled not in {
            "0",
            "false",
            "no",
            "off",
        }:

            print(
                f"[PERF] web.{label}: {elapsed:.3f}s",
                flush=True,
            )

    # ------------------------------------------------------------------ #
    # Backend detection
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_ddgs() -> bool:

        try:

            from ddgs import DDGS  # noqa: F401

            return True

        except Exception:

            return False

    def _detect_backend(self) -> str:
        forced = os.getenv(
            "WEB_SEARCH_BACKEND",
            "",
        ).strip().lower()

        # A forced OpenRouter backend is only valid when
        # OpenRouter web search is explicitly enabled.
        if forced == "openrouter":
            if (
                self.openrouter_key
                and ENABLE_OPENROUTER_WEB_SEARCH
            ):
                return "openrouter"

            print(
                "[SEARCH ROUTER] provider=openrouter "
                "status=DISABLED web_search_plugin "
                "fallback=automatic",
                flush=True,
            )

        elif forced:
            return forced

        # Automatic provider selection.
        if (
            self.openrouter_key
            and ENABLE_OPENROUTER_WEB_SEARCH
        ):
            return "openrouter"

        if self.tavily_key:
            return "tavily"

        if self.exa_key:
            return "exa"

        if self.serpapi_key:
            return "serpapi"

        if self._ddgs_available:
            return "duckduckgo"

        return "none"

    # ------------------------------------------------------------------ #
    # Backend availability
    # ------------------------------------------------------------------ #

    @property
    def available(self) -> bool:

        return (
            (
                bool(self.openrouter_key)
                and ENABLE_OPENROUTER_WEB_SEARCH
            )
            or bool(self.tavily_key)
            or bool(self.exa_key)
            or bool(self.serpapi_key)
            or self._ddgs_available
        )

    def backend_name(self) -> str:

        return self._backend

    # ------------------------------------------------------------------ #
    # Relevance helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokens(
        text: str,
    ) -> List[str]:

        stop = {
            "what",
            "is",
            "are",
            "the",
            "a",
            "an",
            "of",
            "for",
            "to",
            "and",
            "or",
            "in",
            "on",
            "at",
            "how",
            "why",
            "does",
            "do",
            "can",
            "could",
            "would",
            "should",
            "explain",
            "tell",
            "me",
            "please",
            "define",
            "definition",
            "meaning",
            "about",
            "from",
            "with",
            "give",
            "find",
            "value",
            "calculate",
            "show",
            "used",
            "use",
        }

        out = []

        for token in re.findall(
            r"[a-zA-Z0-9][a-zA-Z0-9_-]*",
            (text or "").lower(),
        ):

            token = token.strip("_- ")

            if len(token) < 3:
                continue

            if token in stop:
                continue

            if token.endswith("ies") and len(token) > 5:

                token = (
                    token[:-3]
                    + "y"
                )

            elif token.endswith("s") and len(token) > 4:

                token = token[:-1]

            out.append(token)

        return out

    @classmethod
    def _rank_relevant(
        cls,
        query: str,
        results: List[Dict],
        n: int,
    ) -> List[Dict]:

        if not results:
            return []

        # ---------------------------------------------------------------
        # Provider-ranked results
        #
        # OpenRouter/Tavily/Exa/etc. have already performed search
        # relevance ranking. Do NOT throw away their results just because
        # the title/snippet doesn't contain every query token.
        # ---------------------------------------------------------------

        provider_ranked = [
            item
            for item in results
            if isinstance(item, dict)
            and item.get("_provider_ranked")
        ]

        if provider_ranked:
            return provider_ranked[:n]

        # ---------------------------------------------------------------
        # Local relevance ranking for providers without provider ranking
        # ---------------------------------------------------------------

        q_terms = set(
            cls._tokens(query)
        )

        if not q_terms:
            return results[:n]

        scored = []

        for index, item in enumerate(results):

            if not isinstance(item, dict):
                continue

            haystack = " ".join(
                [
                    str(
                        item.get(
                            "title",
                            "",
                        )
                    ),
                    str(
                        item.get(
                            "snippet",
                            "",
                        )
                    ),
                    str(
                        item.get(
                            "url",
                            "",
                        )
                    ),
                ]
            )

            terms = set(
                cls._tokens(haystack)
            )

            overlap = q_terms & terms

            if not overlap:
                continue

            score = (
                len(overlap)
                / max(
                    1,
                    len(q_terms),
                )
            )

            # Exact concept phrase bonus
            phrase = " ".join(
                cls._tokens(query)
            ).lower()

            raw = (
                str(
                    item.get(
                        "title",
                        "",
                    )
                )
                + " "
                + str(
                    item.get(
                        "snippet",
                        "",
                    )
                )
            ).lower()

            if (
                phrase
                and len(q_terms) >= 2
                and phrase in raw
            ):
                score += 0.35

            # Technical authority bonus
            url = str(
                item.get(
                    "url",
                    "",
                )
            ).lower()

            authoritative_domains = (
                "nasa.gov",
                "faa.gov",
                "mit.edu",
                "nist.gov",
                "esa.int",
                "boeing.com",
                "airbus.com",
                "edu",
                "ac.uk",
            )

            if any(
                domain in url
                for domain in authoritative_domains
            ):
                score += 0.08

            scored.append(
                (
                    score,
                    -index,
                    item,
                )
            )

        scored.sort(
            reverse=True,
            key=lambda x: (
                x[0],
                x[1],
            ),
        )

        return [
            item
            for _, _, item
            in scored[:n]
        ]

    # ------------------------------------------------------------------ #
    # Aerospace context
    # ------------------------------------------------------------------ #

    @staticmethod
    def _needs_aerospace_context(
        query: str,
    ) -> bool:

        q = (
            query or ""
        ).lower()

        terms = (
            "mach",
            "airfoil",
            "aerofoil",
            "aerodynamic",
            "aircraft",
            "wing",
            "lift",
            "drag",
            "reynolds",
            "naca",
            "compressible",
            "shock wave",
            "pitot",
            "airspeed",
            "propulsion",
            "thrust",
            "rocket",
            "flight",
            "boundary layer",
            "fuselage",
            "tailplane",
            "stability",
            "fem",
            "finite element",
            "structural",
            "turbine",
            "compressor",
            "nozzle",
        )

        return any(
            term in q
            for term in terms
        )

    @classmethod
    def _web_query(
        cls,
        query: str,
    ) -> str:

        q = " ".join(
            (query or "").split()
        ).strip()

        if cls._needs_aerospace_context(q):

            return (
                f"{q} "
                "aerospace aerodynamics engineering"
            )

        return q
    
    # ------------------------------------------------------------------
    # Provider circuit breaker
    # ------------------------------------------------------------------

    def _provider_is_available(self, provider: str) -> bool:
        """
        Return True when a provider is healthy enough to be attempted.

        A provider that recently failed is temporarily skipped. Once the
        cooldown expires, it is automatically retried.
        """

        failed_at = self._provider_failures.get(provider)

        if failed_at is None:
            return True

        elapsed = time.time() - failed_at

        if elapsed >= self._provider_cooldown:
            print(
                f"[SEARCH ROUTER] provider={provider} "
                f"status=RETRY cooldown_expired",
                flush=True,
            )

            # Remove the failure state so the provider can be tried.
            self._provider_failures.pop(
                provider,
                None,
            )

            return True

        remaining = max(
            0,
            int(self._provider_cooldown - elapsed),
        )

        print(
            f"[SEARCH ROUTER] provider={provider} "
            f"status=COOLDOWN remaining={remaining}s",
            flush=True,
        )

        return False


    def _record_provider_failure(self, provider: str, error) -> None:
        self._provider_failures[provider] = time.time()
        print(
            f"[SEARCH ROUTER] provider={provider} status=FAILED "
            f"error={self._provider_error_label(error)} "
            f"cooldown={self._provider_cooldown}s",
            flush=True,
        )


    def _record_provider_success(
        self,
        provider: str,
    ) -> None:
        """
        Clear any previous failure state after a successful request.
        """

        if provider in self._provider_failures:
            self._provider_failures.pop(
                provider,
                None,
            )

        print(
            f"[SEARCH ROUTER] provider={provider} "
            f"status=SUCCESS",
            flush=True,
        )
    # ------------------------------------------------------------------ #
    # Public search API
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        max_results: int = None,
    ) -> List[Dict]:

        n = max_results or self.max_results

        if not query or not query.strip():

            return []

        search_query = self._web_query(
            query
        )

        errors = []

        # -------------------------------------------------------------- #
        # Build a SHORT fallback chain
        # -------------------------------------------------------------- #

        backends = []

        forced = os.getenv(
            "WEB_SEARCH_BACKEND",
            "",
        ).strip().lower()

        if (
            forced
            and not (
                forced == "openrouter"
                and not ENABLE_OPENROUTER_WEB_SEARCH
            )
        ):
            backends.append(forced)

        else:
            # Automatic fallback chain.
            # Prefer fast/free providers before consuming paid/limited
            # search-provider quota.
            if (
                self.openrouter_key
                and ENABLE_OPENROUTER_WEB_SEARCH
            ):
                backends.append("openrouter")

            if self.tavily_key:
                backends.append("tavily")

            if self.exa_key:
                backends.append("exa")

            if self._ddgs_available:
                backends.append("duckduckgo")

            if self.serpapi_key:
                backends.append("serpapi")

                # Remove duplicates
                backends = list(
                    dict.fromkeys(backends)
                )

                if not backends:

                    return [
                        self._error_result(
                            search_query,
                            "No web-search backend is configured or available.",
                        )
                    ]

        # -------------------------------------------------------------- #
        # Try configured providers
        # -------------------------------------------------------------- #

        for backend in backends:

            # Skip providers that recently failed.
            if not self._provider_is_available(backend):
                continue

            started = time.perf_counter()

            try:

                if backend == "openrouter":

                    if (
                        not self.openrouter_key
                        or not ENABLE_OPENROUTER_WEB_SEARCH
                    ):
                        continue

                    results = (
                        self._search_openrouter(
                            search_query,
                            n,
                        )
                    )

                elif backend == "tavily":

                    if not self.tavily_key:
                        continue

                    results = (
                        self._search_tavily(
                            search_query,
                            n,
                        )
                    )

                elif backend == "exa":

                    if not self.exa_key:
                        continue

                    results = (
                        self._search_exa(
                            search_query,
                            n,
                        )
                    )

                elif backend == "serpapi":

                    if not self.serpapi_key:
                        continue

                    results = (
                        self._search_serpapi(
                            search_query,
                            n,
                        )
                    )

                elif backend in {
                    "duckduckgo",
                    "ddgs",
                }:

                    if not self._ddgs_available:
                        continue

                    results = (
                        self._search_duckduckgo(
                            search_query,
                            n,
                        )
                    )

                else:

                    raise RuntimeError(
                        f"Unknown web backend: {backend}"
                    )

                elapsed = (
                    time.perf_counter()
                    - started
                )

                if results:
                    self._record_provider_success(
                        backend,
                    )

                if results:
                    print(
                        f"[SEARCH ROUTER] provider={backend} "
                        f"status=SUCCESS results={len(results)}",
                        flush=True,
                    )
                else:
                    print(
                        f"[SEARCH ROUTER] provider={backend} "
                        f"status=EMPTY results=0",
                        flush=True,
                    )

                self._perf(
                    f"primary[{backend}]",
                    elapsed,
                )

                # OpenRouter already ranked these results.
                # Local ranking is only needed for non-provider-ranked results.
                relevant = self._rank_relevant(
                    query,
                    results,
                    n,
                )

                if relevant:

                    self._backend = backend

                    return relevant[:n]

                errors.append(
                    f"{backend}: "
                    "no relevant results"
                )

            except Exception as exc:
                elapsed = time.perf_counter() - started

                if self._is_provider_failure(exc):
                    self._record_provider_failure(backend, exc)
                else:
                    print(
                        f"[SEARCH ROUTER] provider={backend} status=ERROR "
                        f"error={self._provider_error_label(exc)}",
                        flush=True,
                    )

                errors.append(
                    f"{backend}: {self._provider_error_label(exc)}"
                )

        # -------------------------------------------------------------- #
        # One exact-query DDGS fallback
        # -------------------------------------------------------------- #

        if (
            self._ddgs_available
            and search_query != query
            and self._provider_is_available("duckduckgo")
        ):

            started = time.perf_counter()

            try:

                results = (
                    self._search_duckduckgo(
                        query,
                        n,
                    )
                )

                if results:
                    self._record_provider_success(
                        "duckduckgo",
                    )

                self._perf(
                    "exact_ddgs_fallback",
                    time.perf_counter()
                    - started,
                )

                relevant = (
                    self._rank_relevant(
                        query,
                        results,
                        n,
                    )
                )

                if relevant:

                    self._backend = "duckduckgo"

                    return relevant[:n]

            except Exception as exc:
                if self._is_provider_failure(exc):
                    self._record_provider_failure(
                        "duckduckgo",
                        exc,
                    )
                else:
                    print(
                        "[SEARCH ROUTER] "
                        "provider=duckduckgo "
                        "status=ERROR "
                        f"error={self._provider_error_label(exc)}",
                        flush=True,
                    )

                errors.append(
                    f"duckduckgo exact: "
                    f"{self._provider_error_label(exc)}"
                )

    # ------------------------------------------------------------------
    # Provider failure classification
    # ------------------------------------------------------------------
    def _provider_error_label(self, exc: Exception) -> str:
        if isinstance(exc, HTTPError):
            reason = f": {exc.reason}" if exc.reason else ""
            return f"HTTP {exc.code}{reason}"

        if isinstance(exc, URLError):
            reason = exc.reason
            return f"network error: {reason}"

        if isinstance(exc, TimeoutError):
            return "timeout"

        return f"{type(exc).__name__}: {exc}"
    
    def _http_status_code(self, exc: Exception):
        if isinstance(exc, HTTPError):
            return exc.code
    
        return None
    
    def _is_provider_failure(self, exc: Exception) -> bool:
    # HTTP errors from urllib are definitive provider failures.
        if isinstance(exc, HTTPError):
            return True

        # Network/connection failures should also trip the circuit breaker.
        if isinstance(exc, URLError):
            return True

        if isinstance(exc, TimeoutError):
            return True

        error_text = str(exc).lower()

        failure_markers = (
            "401",
            "402",
            "403",
            "408",
            "429",
            "500",
            "502",
            "503",
            "504",
            "timeout",
            "timed out",
            "connection",
            "connecterror",
            "connectionerror",
            "network",
            "rate limit",
            "rate_limit",
            "payment required",
            "unauthorized",
            "forbidden",
            "service unavailable",
            "bad gateway",
            "gateway timeout",
        )

        return any(marker in error_text for marker in failure_markers)
        # -------------------------------------------------------------- #
        # Nothing worked
        # -------------------------------------------------------------- #

        detail = (
            errors[0][:220]
            if errors
            else "No relevant web results were returned."
        )

        return [
            self._error_result(
                search_query,
                detail,
            )
        ]

    # ------------------------------------------------------------------ #
    # Error result
    # ------------------------------------------------------------------ #

    @staticmethod
    def _error_result(
        query: str,
        detail: str,
    ) -> Dict:

        link = (
            "https://duckduckgo.com/?q="
            + urllib.parse.quote(query)
        )

        return {
            "title": "Open web search",
            "url": link,
            "snippet": (
                "Intellex could not retrieve "
                "relevant web results automatically. "
                + detail
            ),
            "_search_error": True,
        }

        # ------------------------------------------------------------------ #
    # OpenRouter Web Search
    # ------------------------------------------------------------------ #

    def _search_openrouter(
        self,
        query: str,
        n: int,
    ) -> List[Dict]:
        """
        Search the web using OpenRouter's web plugin.

        Extracts sources from:
        1. OpenRouter url_citation annotations
        2. Markdown links in assistant content
        3. Plain URLs in assistant content
        """

        model = os.getenv(
            "OPENROUTER_WEB_MODEL",
            "openrouter/auto",
        ).strip()

        if not model:
            model = "openrouter/auto"

        # Prevent model:online:online
        if model.endswith(":online"):
            model = model[:-7]

        configured_max = _env_int(
            "OPENROUTER_WEB_MAX_RESULTS",
            n,
        )

        max_results = max(
            2,
            min(
                n,
                configured_max,
                8,
            ),
        )

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Search the web for reliable information about "
                        "the following question.\n\n"
                        f"Question: {query}\n\n"
                        "Find several relevant sources. "
                        "Prefer authoritative aerospace, engineering, "
                        "educational, scientific, government, university, "
                        "or established technical sources. "
                        "Return a concise answer and cite the sources "
                        "using markdown links."
                    ),
                }
            ],
            "plugins": [
                {
                    "id": "web",
                    "max_results": max_results,
                }
            ],
            "temperature": 0.0,
        }

        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": (
                    f"Bearer {self.openrouter_key}"
                ),
                "HTTP-Referer": (
                    "https://intellex.app"
                ),
                "X-Title": "Intellex",
            },
            method="POST",
        )

        timeout = min(
            max(WEB_SEARCH_TIMEOUT, 10),
            30,
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read().decode(
                "utf-8"
            )

        data = json.loads(raw)

        if not isinstance(data, dict):
            raise RuntimeError(
                "OpenRouter returned an invalid response."
            )

        # ---------------------------------------------------------------
        # API error
        # ---------------------------------------------------------------

        if data.get("error"):

            error = data.get("error")

            if isinstance(error, dict):
                message = (
                    error.get("message")
                    or error.get("code")
                    or str(error)
                )
            else:
                message = str(error)

            raise RuntimeError(
                f"OpenRouter web search error: {message}"
            )

        choices = data.get("choices") or []

        if not choices:
            raise RuntimeError(
                "OpenRouter returned no choices."
            )

        results: List[Dict] = []

        # ---------------------------------------------------------------
        # Extract sources
        # ---------------------------------------------------------------

        for choice in choices:

            if not isinstance(choice, dict):
                continue

            message = (
                choice.get("message", {})
                or {}
            )

            # ===========================================================
            # 1. OpenRouter URL citation annotations
            # ===========================================================

            annotations = (
                message.get(
                    "annotations",
                    [],
                )
                or []
            )

            for annotation in annotations:

                if not isinstance(
                    annotation,
                    dict,
                ):
                    continue

                if annotation.get(
                    "type"
                ) != "url_citation":
                    continue

                citation = (
                    annotation.get(
                        "url_citation",
                        {},
                    )
                    or {}
                )

                if not isinstance(
                    citation,
                    dict,
                ):
                    continue

                url = str(
                    citation.get(
                        "url",
                        "",
                    )
                ).strip()

                if not url:
                    continue

                title = str(
                    citation.get(
                        "title",
                        "",
                    )
                ).strip()

                content = str(
                    citation.get(
                        "content",
                        "",
                    )
                ).strip()

                results.append(
                    {
                        "title": (
                            title
                            or url
                        ),
                        "url": url,
                        "snippet": content,
                        "_provider_ranked": True,
                        "_source": "openrouter",
                    }
                )

            # ===========================================================
            # 2. Markdown links from assistant content
            # ===========================================================

            content = message.get(
                "content",
                "",
            )

            if isinstance(
                content,
                list,
            ):

                parts = []

                for part in content:

                    if isinstance(
                        part,
                        dict,
                    ):
                        text_part = part.get(
                            "text",
                            "",
                        )

                        if text_part:
                            parts.append(
                                str(text_part)
                            )

                    elif isinstance(
                        part,
                        str,
                    ):
                        parts.append(part)

                content = "\n".join(parts)

            content = str(
                content or ""
            ).strip()

            if not content:
                continue

            # ---------------------------------------------------------------
            # Preserve the answer generated by OpenRouter Web Search.
            #
            # This allows chatbot.py to reuse the web-search answer directly
            # instead of making a SECOND OpenRouter/LLM request.
            # ---------------------------------------------------------------

            if content:
                for existing in results:
                    if existing.get("_source") == "openrouter":
                        existing["_web_answer"] = content
                        break
            markdown_links = re.findall(
                r"\[([^\]]+)\]\((https?://[^\s\)]+)\)",
                content,
                flags=re.I,
            )

            for title, url in markdown_links:

                title = title.strip()
                url = url.strip()

                if not url:
                    continue

                results.append(
                    {
                        "title": (
                            title
                            or url
                        ),
                        "url": url,
                        "snippet": content[:700],
                        "_provider_ranked": True,
                        "_source": "openrouter",
                    }
                )

            # ===========================================================
            # 3. Plain URLs
            # ===========================================================

            plain_urls = re.findall(
                r"https?://[^\s<>\]\)\"']+",
                content,
                flags=re.I,
            )

            for url in plain_urls:

                url = url.rstrip(
                    ".,;:!?)]}>\"'"
                )

                if not url:
                    continue

                results.append(
                    {
                        "title": url,
                        "url": url,
                        "snippet": content[:700],
                        "_provider_ranked": True,
                        "_source": "openrouter",
                    }
                )

        # ---------------------------------------------------------------
        # Deduplicate URLs
        # ---------------------------------------------------------------

        unique: Dict[str, Dict] = {}

        for result in results:

            url = str(
                result.get(
                    "url",
                    "",
                )
            ).strip()

            if not url:
                continue

            if url not in unique:
                unique[url] = result

            else:

                old = unique[url]

                old_snippet = str(
                    old.get(
                        "snippet",
                        "",
                    )
                )

                new_snippet = str(
                    result.get(
                        "snippet",
                        "",
                    )
                )

                if len(new_snippet) > len(
                    old_snippet
                ):
                    unique[url] = result

        results = list(
            unique.values()
        )

        # ---------------------------------------------------------------
        # Nothing extracted
        # ---------------------------------------------------------------

        if not results:

            print(
                "[WEB] OpenRouter returned no "
                "extractable web sources.",
                flush=True,
            )

            try:

                print(
                    "[WEB] Response keys:",
                    list(data.keys()),
                    flush=True,
                )

                print(
                    "[WEB] First choice:",
                    json.dumps(
                        choices[0],
                        ensure_ascii=False,
                    )[:3000],
                    flush=True,
                )

            except Exception:
                pass

            raise RuntimeError(
                "OpenRouter returned a response but "
                "no web source URLs could be extracted."
            )

        print(
            f"[WEB] OpenRouter returned "
            f"{len(results)} sources.",
            flush=True,
        )

        return results[:n]

    # ------------------------------------------------------------------ #
    # JSON parser
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_json_list(
        text: str,
    ) -> List[Dict]:

        if not text:

            return []

        text = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            text.strip(),
        )

        try:

            data = json.loads(
                text
            )

        except Exception:

            match = re.search(
                r"\[.*\]",
                text,
                re.S,
            )

            if not match:

                return []

            try:

                data = json.loads(
                    match.group(0)
                )

            except Exception:

                return []

        results = []

        if isinstance(
            data,
            list,
        ):

            for item in data:

                if (
                    isinstance(
                        item,
                        dict,
                    )
                    and item.get("url")
                ):

                    results.append(
                        {
                            "title": str(
                                item.get(
                                    "title",
                                    "",
                                )
                            ).strip(),

                            "url": str(
                                item.get(
                                    "url",
                                    "",
                                )
                            ).strip(),

                            "snippet": str(
                                item.get(
                                    "snippet",
                                    "",
                                )
                            ).strip(),
                        }
                    )

        return results

    # ------------------------------------------------------------------ #
    # Tavily
    # ------------------------------------------------------------------ #

    def _search_tavily(
        self,
        query: str,
        n: int,
    ) -> List[Dict]:

        payload = json.dumps(
            {
                "api_key": self.tavily_key,
                "query": query,
                "max_results": n,
                "search_depth": "basic",
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={
                "Content-Type": "application/json"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=min(
                WEB_SEARCH_TIMEOUT,
                15,
            ),
        ) as response:

            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        results = []

        for item in data.get(
            "results",
            [],
        )[:n]:

            results.append(
                {
                    "title": str(
                        item.get(
                            "title",
                            "",
                        )
                    ).strip(),

                    "url": str(
                        item.get(
                            "url",
                            "",
                        )
                    ).strip(),

                    "snippet": str(
                        item.get(
                            "content",
                            "",
                        )
                    ).strip(),
                }
            )

        return results

    # ------------------------------------------------------------------ #
    # Exa
    # ------------------------------------------------------------------ #

    def _search_exa(
        self,
        query: str,
        n: int,
    ) -> List[Dict]:

        payload = json.dumps(
            {
                "query": query,
                "numResults": n,
                "contents": {
                    "text": {
                        "maxCharacters": 400
                    }
                },
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            "https://api.exa.ai/search",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.exa_key,
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=min(
                WEB_SEARCH_TIMEOUT,
                15,
            ),
        ) as response:

            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        results = []

        for item in data.get(
            "results",
            [],
        )[:n]:

            results.append(
                {
                    "title": str(
                        item.get(
                            "title",
                            "",
                        )
                    ).strip(),

                    "url": str(
                        item.get(
                            "url",
                            "",
                        )
                    ).strip(),

                    "snippet": str(
                        item.get(
                            "text",
                            "",
                        )
                    ).strip()[:400],
                }
            )

        return results

    # ------------------------------------------------------------------ #
    # SerpAPI
    # ------------------------------------------------------------------ #

    def _search_serpapi(
        self,
        query: str,
        n: int,
    ) -> List[Dict]:

        params = urllib.parse.urlencode(
            {
                "engine": "google",
                "q": query,
                "api_key": self.serpapi_key,
                "num": n,
            }
        )

        request = urllib.request.Request(
            (
                "https://serpapi.com/search.json?"
                + params
            )
        )

        with urllib.request.urlopen(
            request,
            timeout=min(
                WEB_SEARCH_TIMEOUT,
                15,
            ),
        ) as response:

            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        results = []

        for item in data.get(
            "organic_results",
            [],
        )[:n]:

            results.append(
                {
                    "title": str(
                        item.get(
                            "title",
                            "",
                        )
                    ).strip(),

                    "url": str(
                        item.get(
                            "link",
                            "",
                        )
                    ).strip(),

                    "snippet": str(
                        item.get(
                            "snippet",
                            "",
                        )
                    ).strip(),
                }
            )

        return results

    # ------------------------------------------------------------------ #
    # DuckDuckGo / DDGS
    # ------------------------------------------------------------------ #

    def _search_duckduckgo(
        self,
        query: str,
        n: int,
    ) -> List[Dict]:

        from ddgs import DDGS

        results = []

        with DDGS(
            timeout=DDGS_TIMEOUT
        ) as ddgs:

            for item in ddgs.text(
                query,
                max_results=n,
            ):

                results.append(
                    {
                        "title": str(
                            item.get(
                                "title",
                                "",
                            )
                        ).strip(),

                        "url": str(
                            item.get(
                                "href",
                                item.get(
                                    "url",
                                    "",
                                ),
                            )
                        ).strip(),

                        "snippet": str(
                            item.get(
                                "body",
                                "",
                            )
                            or ""
                        ).strip(),
                    }
                )

        return results[:n]

    # ------------------------------------------------------------------ #
    # Individual DDGS engine
    #
    # Kept for compatibility with older Intellex code.
    # We intentionally do not loop through all engines anymore.
    # ------------------------------------------------------------------ #

    def _search_ddgs_engine(
        self,
        query: str,
        n: int,
        engine: str,
    ) -> List[Dict]:

        from ddgs import DDGS

        results = []

        with DDGS(
            timeout=DDGS_TIMEOUT
        ) as ddgs:

            for item in ddgs.text(
                query,
                max_results=n,
                backend=engine,
            ):

                results.append(
                    {
                        "title": str(
                            item.get(
                                "title",
                                "",
                            )
                        ).strip(),

                        "url": str(
                            item.get(
                                "href",
                                item.get(
                                    "url",
                                    "",
                                ),
                            )
                        ).strip(),

                        "snippet": str(
                            item.get(
                                "body",
                                "",
                            )
                            or ""
                        ).strip(),
                    }
                )

        return results[:n]