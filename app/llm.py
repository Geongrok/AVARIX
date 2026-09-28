"""LLM answer generation.

Strategy (auto-detected):
  1. OpenRouter (OPENROUTER_API_KEY)      -> cloud LLM via OpenRouter (preferred).
  2. Ollama running locally               -> local model (free).
  3. OpenAI (OPENAI_API_KEY)              -> OpenAI chat completions.
  4. Extractive fallback                  -> works with zero keys.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Reuse the same stop-word set used by the knowledge-base retrieval layer.
# This keeps the DB relevance gate consistent with BM25/query processing.
from .knowledge_base import STOP_WORDS

try:
    from dotenv import load_dotenv
    # Load .env from the project root (two levels above this file).
    _ENV_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    load_dotenv(_ENV_PATH)
except Exception:
    pass


class LLMEngine:
    def __init__(self, ollama_model: str = "llama3.2", ollama_url: str = None):
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url or os.getenv(
            "OLLAMA_URL", "http://localhost:11434"
        )
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.mode = self._detect_mode()

        print(
            f"[OPENROUTER DEBUG] LLM key_loaded={bool(self.openrouter_api_key)} "
            f"length={len(self.openrouter_api_key)} "
            f"prefix={self.openrouter_api_key[:10]}",
            flush=True,
        )

    def _detect_mode(self) -> str:
        if self.openrouter_api_key:
            return "openrouter"
        if self._ollama_alive():
            return "ollama"
        if self.openai_api_key:
            return "openai"
        return "extractive"
    
    def _ollama_alive(self) -> bool:
        try:
            import urllib.request
            with urllib.request.urlopen(
                f"{self.ollama_url}/api/tags", timeout=2
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(
        self,
        question: str,
        db_chunks: List[Dict],
        web_results: List[Dict],
    ) -> Dict[str, Any]:
        """
        Produce a final AVARIX answer.

        The returned object is intentionally backward-compatible:
        - answer      -> visible answer text
        - structured  -> adaptive answer sections
        - visuals     -> optional related visual metadata

        Provider failures are allowed to fall back to the extractive
        answer path.
        """
        if self.mode == "openrouter":
            raw = self._generate_openrouter(
                question,
                db_chunks,
                web_results,
            )
        elif self.mode == "ollama":
            raw = self._generate_ollama(
                question,
                db_chunks,
                web_results,
            )
        elif self.mode == "openai":
            raw = self._generate_openai(
                question,
                db_chunks,
                web_results,
            )
        else:
            raw = self._generate_extractive(
                question,
                db_chunks,
                web_results,
            )

        return self._normalize_generated_output(
            raw,
            question=question,
            db_chunks=db_chunks,
            web_results=web_results,
        )

    # ------------------------------------------------------------------ #
    # AVARIX structured answer handling
    # ------------------------------------------------------------------ #

    @staticmethod
    def _empty_structured_answer() -> Dict[str, Any]:
        """Return the stable structured-answer schema used by AVARIX."""
        return {
            "answer": "",
            "explanation": "",
            "key_points": [],
            "formula": None,
            "applications": [],
            "examples": [],
        }

    @classmethod
    def _normalize_generated_output(
        cls,
        raw: Any,
        question: str = "",
        db_chunks: Optional[List[Dict]] = None,
        web_results: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Normalize provider output.

        Providers normally return plain text. If a provider/model returns
        JSON, parse it into AVARIX's structured schema.

        Plain-text output remains fully supported.
        """
        db_chunks = db_chunks or []
        web_results = web_results or []

        if isinstance(raw, dict):
            answer = str(raw.get("answer") or "").strip()

            structured = raw.get("structured")
            visuals = raw.get("visuals")

            if not isinstance(structured, dict):
                structured = cls._empty_structured_answer()

            structured = cls._sanitize_structured_answer(structured)

            if not answer:
                answer = str(
                    structured.get("answer") or ""
                ).strip()

            if not isinstance(visuals, list):
                visuals = []

            return {
                "answer": answer,
                "structured": structured,
                "visuals": visuals,
            }

        text = str(raw or "").strip()

        parsed = cls._parse_structured_json(text)

        if parsed is not None:
            structured = cls._sanitize_structured_answer(parsed)

            answer = str(
                structured.get("answer") or ""
            ).strip()

            if not answer:
                answer = text

            return {
                "answer": answer,
                "structured": structured,
                "visuals": [],
            }

        # Legacy/plain-text model output.
        structured = cls._structure_plain_text(
            question,
            text,
        )

        return {
            "answer": text,
            "structured": structured,
            "visuals": [],
        }

    @staticmethod
    def _parse_structured_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract a JSON object from an LLM response when possible."""
        if not text:
            return None

        import json

        candidate = text.strip()

        # Remove markdown code fences.
        candidate = re.sub(
            r"^```(?:json)?\s*",
            "",
            candidate,
            flags=re.I,
        )
        candidate = re.sub(
            r"\s*```$",
            "",
            candidate,
        ).strip()

        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else None
        except Exception:
            pass

        # Some models add a short sentence before the JSON.
        start = candidate.find("{")
        end = candidate.rfind("}")

        if start < 0 or end <= start:
            return None

        try:
            data = json.loads(candidate[start:end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @classmethod
    def _sanitize_structured_answer(
        cls,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Keep only the fields AVARIX expects and normalize list/string values.
        """
        result = cls._empty_structured_answer()

        result["answer"] = str(
            data.get("answer") or ""
        ).strip()

        result["explanation"] = str(
            data.get("explanation") or ""
        ).strip()

        for field in (
            "key_points",
            "applications",
            "examples",
        ):
            value = data.get(field, [])

            if isinstance(value, str):
                value = [
                    value.strip()
                ] if value.strip() else []

            if not isinstance(value, list):
                value = []

            cleaned = []

            for item in value:
                if isinstance(item, dict):
                    text = (
                        item.get("text")
                        or item.get("description")
                        or item.get("value")
                    )
                else:
                    text = item

                if text is None:
                    continue

                text = str(text).strip()

                if text:
                    cleaned.append(text)

            result[field] = cleaned[:8]

        formula = data.get("formula")

        if formula is not None:
            if isinstance(formula, dict):
                result["formula"] = formula
            else:
                formula = str(formula).strip()
                result["formula"] = formula or None

        return result

    @staticmethod
    def _structure_plain_text(
        question: str,
        answer: str,
    ) -> Dict[str, Any]:
        """
        Convert an existing plain-text answer into a lightweight structured
        representation.

        This is deliberately conservative. It does not invent engineering
        facts that the model did not provide.
        """
        structured = {
            "answer": answer.strip(),
            "explanation": "",
            "key_points": [],
            "formula": None,
            "applications": [],
            "examples": [],
        }

        if not answer:
            return structured

        # Preserve explicit "Key points" sections already generated.
        key_match = re.search(
            r"(?:^|\n)\s*\*\*Key points\*\*\s*\n(?P<body>.*)$",
            answer,
            flags=re.I | re.S,
        )

        if key_match:
            body = key_match.group("body")

            bullets = re.findall(
                r"(?:^|\n)\s*(?:[-•*])\s+(.+)",
                body,
            )

            structured["key_points"] = [
                b.strip()
                for b in bullets
                if b.strip()
            ][:8]

            main_answer = answer[:key_match.start()].strip()

            if main_answer:
                structured["answer"] = main_answer

        return structured

    def check_api_configuration(self):
        """
        Check whether the API configuration required for web/LLM
        functionality is available.
        """

        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        if not openrouter_key:
            return {
                "available": False,
                "provider": "OpenRouter",
                "message": (
                    "Web search is unavailable because the "
                    "OpenRouter API key is not configured."
                ),
            }

        return {
            "available": True,
            "provider": "OpenRouter",
            "message": "OpenRouter API configured.",
        }
    
    # ------------------------------------------------------------------ #
    # Prompt builder (shared)
    # ------------------------------------------------------------------ #

    def _build_prompt(
        self,
        question: str,
        db_chunks: List[Dict],
        web_results: List[Dict],
    ) -> str:

        lines = [
            (
                "You are AVARIX, an aerospace engineering intelligence "
                "and knowledge assistant."
            ),
            (
                "Answer the user's question using ONLY the supplied "
                "database and web context."
            ),
            "",
            "## DATABASE CONTEXT",
        ]

        if db_chunks:
            for i, c in enumerate(db_chunks, 1):
                lines.append(
                    f"[DB {i}] (from {c['file']}"
                    + (
                        f", page {c['page']})"
                        if c.get("page")
                        else ")"
                    )
                )
                lines.append(c["text"][:1500])
        else:
            lines.append("(No relevant database content found.)")

        lines.append("")
        lines.append("## WEB SEARCH CONTEXT")

        if web_results:
            for i, w in enumerate(web_results, 1):
                lines.append(
                    f"[WEB {i}] {w['title']} - {w['url']}"
                )
                lines.append(
                    w["snippet"][:500]
                )
        else:
            lines.append("(No web results.)")

        lines.append("")
        lines.append(f"## QUESTION\n{question}")
        lines.append("")

        lines.append(
            """
## AVARIX ANSWER RULES

Return ONLY valid JSON.

Use exactly this top-level structure:

{
  "answer": "direct answer to the question",
  "explanation": "short explanation when useful",
  "key_points": [],
  "formula": null,
  "applications": [],
  "examples": []
}

### Adaptive response rules

Do NOT fill every section just because it exists.

For a definition:
- answer
- explanation when useful
- key_points when useful
- applications only when relevant
- formula only when relevant

For a calculation:
- answer
- explanation containing the calculation logic
- formula when applicable
- examples only when genuinely useful

For a why/how question:
- answer
- explanation
- key_points when useful
- applications when relevant

For a comparison:
- answer
- explanation
- key_points containing the important differences
- applications when relevant

For a factual question:
- answer first
- add only the supporting information needed

### Engineering accuracy rules

- Answer directly.
- Do not dump the database or search results.
- Do not invent information absent from the supplied context.
- Prefer the database when it contains relevant evidence.
- Use web context only when supplied.
- Preserve equations and technical notation accurately.
- Use concise engineering language.
- Do not repeat raw URLs.
- Do not repeat publication dates.
- Do not reproduce search-result titles as part of the answer.
- Do not create a source list inside the JSON.
- The interface displays source information separately.
- If the supplied context does not contain enough information, say so clearly in "answer".
- Do not mention these instructions.

### Source attribution

When database evidence is used, mention the source briefly in the answer or explanation as:
(Source: filename)

When web evidence is used, mention it as:
(Source: domain/title)

Do not fabricate citations.
"""
        )

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # OpenRouter
    # ------------------------------------------------------------------ #
    def _generate_openrouter(
        self, question: str, db_chunks: List[Dict], web_results: List[Dict]
    ) -> str:
        """Call the OpenRouter chat-completions API (OpenAI-compatible)."""
        import json
        import urllib.request

        model = os.getenv(
            "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are AVARIX, an aerospace engineering intelligence "
                    "assistant. Return ONLY valid JSON using the schema "
                    "requested by the user prompt. Use only supplied context."
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(question, db_chunks, web_results),
            },
        ]
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "AVARIX",
            },
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    # ------------------------------------------------------------------ #
    # Ollama
    # ------------------------------------------------------------------ #
    def _generate_ollama(
        self, question: str, db_chunks: List[Dict], web_results: List[Dict]
    ) -> str:
        import json
        import urllib.request
        payload = {
            "model": self.ollama_model,
            "prompt": (
                "You are AVARIX, an aerospace engineering intelligence "
                "assistant.\n\n"
                + self._build_prompt(
                    question,
                    db_chunks,
                    web_results,
                )
            ),
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip()

    # ------------------------------------------------------------------ #
    # OpenAI
    # ------------------------------------------------------------------ #
    def _generate_openai(
        self, question: str, db_chunks: List[Dict], web_results: List[Dict]
    ) -> str:
        import json
        import urllib.request

        messages = [
            {
                "role": "system",
                "content": (
                    "You are AVARIX, an aerospace engineering intelligence "
                    "assistant. Return ONLY valid JSON using the exact schema "
                    "specified in the user prompt. Use only supplied context."
                ),
            },
            {"role": "user", "content": self._build_prompt(question, db_chunks, web_results)},
        ]
        payload = {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": messages,
            "temperature": 0.3,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    # ------------------------------------------------------------------ #
    # Extractive fallback (zero-dependency)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clean_web_text(text: str) -> str:
        """Remove common search-engine noise before showing an extractive answer."""
        text = re.sub(r"https?://\S+", "", text or "")
        text = re.sub(
            r"^\s*(?:\d+\s+(?:day|days|week|weeks|month|months|year|years)\s+ago|"
            r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4})\s*[-–—:]?\s*",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(r"\s+", " ", text).strip(" -–—")
        return text

    @staticmethod
    def _web_extractive_answer(question: str, web_results: List[Dict]) -> str:
        """Create a useful answer without an LLM by ranking sentences from web snippets."""
        if not web_results:
            return ""

        stop = {
            "what", "is", "are", "the", "a", "an", "of", "for", "to",
            "and", "or", "in", "on", "at", "how", "why", "does", "do",
            "can", "could", "would", "should", "from", "with", "about",
            "explain", "tell", "me", "please", "define", "meaning",
        }
        terms = set(re.findall(r"[a-zA-Z0-9]{3,}", question.lower())) - stop
        candidates = []

        for rank, result in enumerate(web_results[:5]):
            text = LLMEngine._clean_web_text(result.get("snippet", ""))
            if not text:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 35:
                    continue
                words = set(re.findall(r"[a-zA-Z0-9]{3,}", sentence.lower()))
                overlap = len(terms & words)
                # Prefer sentences matching the question and earlier search results.
                score = overlap * 4 + max(0, 3 - rank)
                candidates.append((score, sentence))

        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = []
        seen = set()
        for _, sentence in candidates:
            key = re.sub(r"\W+", " ", sentence.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            selected.append(sentence)
            if len(selected) >= 3:
                break

        if not selected:
            selected = [LLMEngine._clean_web_text(web_results[0].get("snippet", ""))]

        # Keep the fallback concise: direct answer first, then supporting points.
        answer = selected[0].strip()
        if len(selected) > 1:
            answer += "\n\n" + "\n".join(f"• {s}" for s in selected[1:])
        return answer

    @staticmethod
    def _db_extractive_answer(question: str, db_chunks: List[Dict]) -> str:
        """Produce a concise answer from already-validated DB evidence.

        This never uses the whole retrieved chunk as the answer. It selects
        answer-bearing sentences or a nearby explicit answer marker.
        """
        if not db_chunks:
            return ""

        intent = LLMEngine._question_intent(question)
        q_terms = LLMEngine._meaningful_terms(question)
        q_clean = re.sub(r"\s+", " ", question.lower()).strip(" ?.!:")

        # Be defensive: only use passages that pass the same answerability
        # gate used by retrieval. This prevents a future caller from passing
        # raw top-k chunks and accidentally exposing them as an answer.
        validated_chunks = [
            c for c in db_chunks[:5]
            if LLMEngine._lexical_db_relevance(question, c, min_score=0.45)
        ]
        if not validated_chunks:
            return ""

        evidence = []
        for rank, chunk in enumerate(validated_chunks):
            raw = re.sub(r"\s+", " ", chunk.get("text", "")).strip()
            if not raw:
                continue
            sentences = [
                s.strip(" -•")
                for s in re.split(r"(?<=[.!?])\s+|(?<=:)\s+", raw)
                if len(s.strip()) >= 25
            ]

            # For value/exam questions, locate the exact question first and
            # search only a local window for ANS/solution. This avoids taking
            # the answer to the next question in a dense question bank.
            if intent == "value" and q_clean:
                low = raw.lower()
                positions = [m.start() for m in re.finditer(re.escape(q_clean), low)]

                # If wording differs slightly, locate the first sentence that
                # contains most of the question's core entities.
                if not positions:
                    for m in re.finditer(r"[^.!?]{20,500}\?", raw):
                        st = {
                            LLMEngine._normalise_term(t)
                            for t in re.findall(r"[a-zA-Z0-9]{3,}", m.group(0).lower())
                        }
                        if len(q_terms & st) / len(q_terms) >= 0.67:
                            positions.append(m.start())

                for pos in positions[:3]:
                    window = raw[pos:pos + 1200]
                    m = re.search(
                        r"\b(?:ans|answer|correct\s+answer|solution)\s*[:=-]\s*"
                        r"(.{1,180}?)(?=\s+(?:what|which|how|why|maximum|minimum|"
                        r"in the given problem|in the above question|consider|for an aircraft)\b|$)",
                        window,
                        re.I,
                    )
                    if m:
                        ans = m.group(1).strip(" .;,")
                        ans = re.sub(
                            r"^(?:option\s*)?[a-d]\s*[\):.-]\s*",
                            "", ans, flags=re.I
                        )
                        # Never return the question itself as the answer.
                        if ans and not ans.rstrip().endswith("?"):
                            return f"The answer is **{ans}**."

            # Score individual evidence sentences rather than the whole chunk.
            for sidx, s in enumerate(sentences[:120]):
                st = {
                    LLMEngine._normalise_term(t)
                    for t in re.findall(r"[a-zA-Z0-9]{3,}", s.lower())
                }
                overlap = len(q_terms & st)
                coverage = overlap / len(q_terms) if q_terms else 0
                if coverage < 0.67:
                    continue

                # Parsed PDF/DOCX chunks can begin or end in the middle of a
                # sentence. Do not promote obvious sentence fragments to the
                # primary answer (e.g. "peed of an aircraft...").
                fragment_like = bool(
                    re.match(r"^[a-z][a-z0-9'\-]*\s", s.strip())
                    or re.match(r"^[,;:)\]]", s.strip())
                )

                score = coverage * 10 + max(0, 3 - rank) + max(0, 2 - sidx * 0.02)
                if fragment_like:
                    score -= 7

                if intent == "application":
                    # Application/use questions need an explicit application
                    # relationship. Topic overlap alone is not enough: a
                    # worked example such as "an aircraft is cruising at..."
                    # may mention Mach number but does not answer "where is it
                    # used?".
                    application_cue = re.search(
                        r"\b(?:used\s+(?:in|for|to)|use[s]?\s+(?:of|in|for|to)|"
                        r"application[s]?\s+(?:of|include|in)|applied\s+(?:in|to)|"
                        r"important\s+(?:in|for)|helps?\s+(?:to\s+)?(?:determine|"
                        r"analyze|analyse|predict)|used\s+to\s+(?:classify|"
                        r"characteri[sz]e|measure|determine|analyze|analyse))\b",
                        s, re.I,
                    )
                    if application_cue:
                        score += 18
                    else:
                        # Do not let a merely related technical/example sentence
                        # become the answer. It is still useful to retrieval, but
                        # not answer-bearing evidence for this intent.
                        continue

                    if re.search(
                        r"\b(?:aircraft|flight|wind\s+tunnel|nozzle|duct|"
                        r"shock\s+wave|compressible\s+flow|propulsion|rocket|"
                        r"jet\s+engine|supersonic|transonic|hypersonic)\b",
                        s, re.I,
                    ):
                        score += 2

                    if re.search(
                        r"\b(?:given|calculate|determine|find)\b|"
                        r"\b(?:cruising|flowing)\b.*\b(?:at|with)\s+\d|"
                        r"\b\d+\.?\d*\s*(?:kpa|pa|m/s|km/s|hz|kg|n|k|%)\b",
                        s, re.I,
                    ):
                        score -= 12

                # Definition answers should strongly prefer "X is..." style
                # statements and avoid equations/question-bank prompts.
                if intent == "definition":
                    if re.search(
                        r"\bis\b|\bare\b|\brefers?\s+to\b|\bdefined\s+as\b|"
                        r"\bmeans\b|\bknown\s+as\b|\bforce\b.*\bthat\b",
                        s, re.I,
                    ):
                        score += 8
                    if s.endswith("?") or re.search(r"\([a-d]\)", s, re.I):
                        score -= 8

                if re.search(r"\b(?:ans|answer|solution|therefore|hence|thus)\b", s, re.I):
                    score += 3

                evidence.append((score, s))

        if not evidence:
            return ""

        # For application questions, every candidate has already been required
        # to contain an explicit use/application cue. This means a DB response
        # is withheld when the retrieved material only contains examples or
        # formulas; the caller can then fall back to web research instead of
        # presenting related-but-nonresponsive text.
        evidence.sort(key=lambda x: x[0], reverse=True)
        selected = []
        seen = set()
        for _, sentence in evidence:
            key = re.sub(r"\W+", " ", sentence.lower()).strip()
            if key in seen:
                continue
            seen.add(key)

            # Prefer complete sentences for the visible answer. Fragment
            # candidates remain useful as retrieval evidence, but should not
            # become the first thing the user reads.
            if (
                selected == []
                and re.match(r"^[a-z][a-z0-9'\-]*\s", sentence.strip())
            ):
                continue

            selected.append(sentence)
            if len(selected) >= (2 if intent in {"definition", "explanation"} else 3):
                break

        if not selected:
            return ""

        answer = selected[0]
        if len(answer) > 500:
            answer = answer[:500].rsplit(" ", 1)[0] + "…"

        if len(selected) > 1:
            answer += "\n\n**Key points**\n"
            for sentence in selected[1:]:
                if len(sentence) > 280:
                    sentence = sentence[:280].rsplit(" ", 1)[0] + "…"
                answer += f"• {sentence}\n"
        return answer.strip()

    # ------------------------------------------------------------------ #
    # Database relevance validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def normalize_query(question: str) -> str:
        """Expand common aerospace abbreviations for retrieval.

        The original wording is preserved for the final response. The expanded
        query gives BM25/vector search extra vocabulary when a document spells
        out an abbreviation (or uses the abbreviation when the user spells it
        out). Only common aerospace notation is expanded here.
        """
        q = re.sub(r"\s+", " ", (question or "")).strip()
        if not q:
            return q

        aliases = [
            # Most specific forms first.
            (r"(?<![A-Za-z0-9])C[_\s]*[mM][_\s]?(?:0|[oO])(?![A-Za-z0-9])",
             "Cmo (Cm0, pitching moment coefficient at zero lift)"),
            (r"(?<![A-Za-z0-9])C[_\s]*[lL][_\s]?(?:a|alpha|α)(?![A-Za-z0-9])",
             "CLalpha (lift curve slope)"),
            (r"(?<![A-Za-z0-9])C[_\s]*[lL](?![A-Za-z0-9])",
             "CL (lift coefficient)"),
            (r"(?<![A-Za-z0-9])C[_\s]*[dD](?![A-Za-z0-9])",
             "CD (drag coefficient)"),
            (r"(?<![A-Za-z0-9])C[_\s]*[mM](?![A-Za-z0-9])",
             "Cm (pitching moment coefficient)"),
            (r"(?<![A-Za-z0-9])M[_\s]*(?:cr)(?![A-Za-z0-9])",
             "Mcr (critical Mach number)"),
            (r"(?<![A-Za-z0-9])M[_\s]*(?:dd)(?![A-Za-z0-9])",
             "Mdd (drag divergence Mach number)"),
            (r"(?<![A-Za-z0-9])AoA(?![A-Za-z0-9])",
             "AoA (angle of attack)"),
            (r"(?<![A-Za-z0-9])L\s*/\s*D(?![A-Za-z0-9])",
             "L/D (lift-to-drag ratio)"),
        ]

        expanded = q
        for pattern, replacement in aliases:
            expanded = re.sub(pattern, replacement, expanded, flags=re.I)
        return expanded

    @staticmethod
    def _normalise_term(term: str) -> str:
        """Lightweight morphology normalisation without an NLP dependency."""
        t = re.sub(r"[^a-z0-9]", "", term.lower())
        if len(t) <= 4:
            return t
        # Keep common aerospace terminology intact while matching simple
        # singular/plural/verb variants: aerodynamic/aerodynamics, forces/force.
        if t.endswith("ies") and len(t) > 5:
            t = t[:-3] + "y"
        else:
            for suffix in ("ing", "ed", "s"):
                if t.endswith(suffix) and len(t) - len(suffix) >= 4:
                    t = t[: -len(suffix)]
                    break
        return t

    @staticmethod
    def _question_intent(question: str) -> str:
        """Classify the question so topical similarity is not mistaken for an answer."""
        q = re.sub(r"\s+", " ", question.lower()).strip()
        if re.search(r"\bwhat\s+is\s+the\s+value\s+of\b|\bwhat\s+is\s+the\s+value\b|\bvalue\s+of\b|\bfind\s+the\s+value\b", q):
            return "value"
        if re.search(r"\b(calculate|compute|determine|find|derive|solve)\b", q):
            return "calculation"
        if re.search(r"\bwhere\s+(?:is|are)\b|\bwhere\s+.*\bused\b|\bhow\s+is\b.*\bused\b|\bhow\s+.*\bused\b|\bwhat\s+(?:are|is)\b.*\buses?\b|\bwhat\s+.*\bapplications?\b|\bapplications?\s+of\b|\buse[s]?\s+of\b|\bused\s+(?:in|for|to)\b", q):
            return "application"
        if re.search(r"\bwhat\s+is\b|\bwhat\s+are\b|\bdefine\b|\bdefinition\s+of\b|\bmeaning\s+of\b", q):
            return "definition"
        if re.search(r"\bwhy\b|\bhow\s+does\b|\bhow\s+do\b|\bhow\s+is\b|\bexplain\b", q):
            return "explanation"
        return "fact"

    @classmethod
    def _meaningful_terms(cls, question: str) -> set:
        stop = STOP_WORDS | {
            "how", "why", "does", "do", "can", "could", "would", "should",
            "explain", "tell", "please", "define", "definition", "meaning",
            "calculate", "find", "give", "value", "following", "using",
            "used", "use", "describe", "discuss", "state",
        }
        terms = {
            cls._normalise_term(t)
            for t in re.findall(r"[a-zA-Z0-9]{3,}", question.lower())
            if t not in stop
        }
        return {t for t in terms if t}

    @staticmethod
    def _looks_like_question_bank(text: str, filename: str = "") -> bool:
        """Detect MCQ/question-bank material so it cannot answer generic definitions.

        Intellex's corpus contains GATE papers and question banks where a single
        chunk can contain many unrelated MCQs. Those chunks are excellent evidence
        for an exact exam-question lookup, but they are poor evidence for a generic
        concept question such as "What is Mach number?".
        """
        t = re.sub(r"\s+", " ", text or "").strip().lower()
        f = (filename or "").lower()
        if not t:
            return False

        # Strong structural markers for exam/MCQ material.
        option_hits = len(re.findall(r"\([a-d]\)\s+", t))
        question_hits = len(re.findall(r"(?:^|\s)(?:q\.?\s*\d+|question\s*\d+|q\s*\d+)", t))
        ans_hits = len(re.findall(r"\b(?:ans|answer|correct answer|solution)\b\s*[:=-]", t))
        exam_name = any(k in f for k in ("gate", "question", "suggested", "exam", "paper"))

        if option_hits >= 2 or question_hits >= 2:
            return True
        if exam_name and option_hits >= 1:
            return True
        if exam_name and ans_hits >= 1 and question_hits >= 1:
            return True
        return False

    @classmethod
    def _concept_phrase_tokens(cls, question: str) -> list:
        """Return ordered concept tokens after removing question scaffolding."""
        stop = STOP_WORDS | {
            "how", "why", "does", "do", "can", "could", "would", "should",
            "explain", "tell", "please", "define", "definition", "meaning",
            "calculate", "compute", "determine", "find", "derive", "solve",
            "give", "value", "following", "using", "used", "use", "describe",
            "discuss", "state", "the", "following",
        }
        return [
            cls._normalise_term(t)
            for t in re.findall(r"[a-zA-Z0-9]{3,}", question.lower())
            if cls._normalise_term(t) not in stop
        ]

    @classmethod
    def _lexical_db_relevance(
        cls, question: str, chunk: Dict, min_score: float = 0.55
    ) -> bool:
        """Strict answerability gate, not a topical-similarity gate.

        A retrieved chunk is accepted only when a sentence in it contains the
        question's core concepts in an answer-like context. This is especially
        important for question banks where hundreds of unrelated questions can
        live in one chunk.
        """
        text = re.sub(r"\s+", " ", chunk.get("text", "")).strip()
        score = float(chunk.get("score", 0.0))
        if not text or score < max(0.45, min_score):
            return False

        q_terms = cls._meaningful_terms(question)
        if not q_terms:
            return False

        intent = cls._question_intent(question)
        low = text.lower()
        text_terms = {
            cls._normalise_term(t)
            for t in re.findall(r"[a-zA-Z0-9]{3,}", low)
        }
        hits = q_terms & text_terms
        coverage = len(hits) / len(q_terms)

        # Exact question phrase is strong evidence, but only for value/factual
        # questions. A definition question can occur as a question-bank item
        # followed by an unrelated answer, so phrase matching alone is unsafe.
        q_clean = re.sub(r"\s+", " ", question.lower()).strip(" ?.!:")
        exact_question = bool(q_clean and q_clean in low)

        # Split into reasonably sized evidence units. Do not accept a chunk
        # merely because terms occur in different questions inside the chunk.
        sentences = [
            s.strip(" -•")
            for s in re.split(r"(?<=[.!?])\s+|(?<=:)\s+", text)
            if len(s.strip()) >= 25
        ]

        def sentence_terms(sentence: str) -> set:
            return {
                cls._normalise_term(t)
                for t in re.findall(r"[a-zA-Z0-9]{3,}", sentence.lower())
            }

        def has_answer_marker(sentence: str) -> bool:
            return bool(re.search(
                r"\b(?:ans|answer|correct\s+answer|solution|therefore|hence|thus)\b\s*[:=-]?",
                sentence,
                re.I,
            ))

        # ---- Definition questions -------------------------------------
        # A definition query is concept-sensitive.  "Mach number" must not
        # accept a definition of "critical Mach number", "free-stream Mach
        # number", or "drag-divergence Mach number" merely because the words
        # Mach + number occur.  Likewise "aerodynamic lift" must not accept a
        # lift-curve-slope calculation.
        if intent == "definition":
            explicit_definition = re.compile(
                r"\b(?:refers?\s+to|defined\s+as|means|known\s+as|denotes?|describes?)\b",
                re.I,
            )
            q_words = [
                cls._normalise_term(t)
                for t in re.findall(r"[a-zA-Z0-9]{3,}", question.lower())
                if cls._normalise_term(t) not in STOP_WORDS
            ]
            q_words = [t for t in q_words if t]
            if not q_words:
                return False

            # A generic definition question must not be answered from an MCQ
            # merely because the MCQ mentions the requested term. The exact
            # failure seen with "What is Mach number?" came from a GATE question
            # asking about *critical* Mach number. Reject question-bank chunks
            # unless they contain a genuine standalone definition sentence.
            if cls._looks_like_question_bank(text, chunk.get("file", "")):
                standalone_definition = False
                for s in sentences[:120]:
                    st = sentence_terms(s)
                    if not q_words or not (set(q_words) & st):
                        continue
                    if re.search(
                        r"\b(?:is|are|refers?\s+to|defined\s+as|means|denotes?)\b",
                        s, re.I,
                    ) and not re.search(r"\([a-d]\)|\bq\.?\s*\d+\b", s, re.I):
                        # Require the queried concept to be the subject or exact
                        # concept phrase, not a more-specific sibling such as
                        # "critical Mach number".
                        if len(q_words) == 1:
                            standalone_definition = True
                            break
                        phrase = r"\b" + r"\s+".join(map(re.escape, q_words)) + r"\b"
                        reverse_phrase = r"\b" + r"\s+".join(map(re.escape, q_words[::-1])) + r"\b"
                        if re.search(phrase, s, re.I) or re.search(reverse_phrase, s, re.I):
                            standalone_definition = True
                            break
                if not standalone_definition:
                    return False

            head_term = q_words[-1]
            modifier_terms = set(q_words[:-1])

            # Words which may sit before a concept without changing its
            # identity.  Other words immediately before the queried concept
            # are treated as a more-specific variant.
            harmless_prefix = {
                "a", "an", "the", "of", "for", "to", "and", "or",
                "free",  # handled specially below when part of the query
            }

            for s in sentences[:120]:
                st = sentence_terms(s)
                if head_term not in st:
                    continue

                tokens = [
                    cls._normalise_term(t)
                    for t in re.findall(r"[a-zA-Z0-9]{3,}", s.lower())
                ]
                raw_tokens = re.findall(r"[a-zA-Z0-9]{2,}", s.lower())

                # Examine every occurrence of the queried head noun.
                for pos, tok in enumerate(tokens):
                    if tok != head_term:
                        continue

                    left = max(0, pos - 5)
                    right = min(len(tokens), pos + 8)
                    local_tokens = set(tokens[left:right])
                    local_coverage = len(q_words and (set(q_words) & local_tokens)) / len(q_words)

                    # The exact concept phrase is strongest evidence.  This
                    # handles "aerodynamic lift" even when the definition is
                    # phrased as "aerodynamic lift is ...".
                    phrase_match = False
                    phrase_start = None
                    if len(q_words) >= 2:
                        # Compare the ordered concept phrase token-by-token.
                        for j in range(0, max(0, len(tokens) - len(q_words) + 1)):
                            if tokens[j:j + len(q_words)] == q_words:
                                phrase_match = True
                                phrase_start = j
                                break

                    # Reject a more-specific sibling concept when the query is
                    # generic. Example:
                    #   query: "what is Mach number?"
                    #   text:  "free stream Mach number ... is defined as ..."
                    # The extra modifier immediately before "Mach number" means
                    # this is not the requested general concept.
                    preceding = tokens[max(0, pos - len(modifier_terms) - 3):pos]
                    specific_modifiers = {
                        x for x in preceding
                        if x not in modifier_terms
                        and x not in {"a", "an", "the", "of", "for", "to", "and", "or"}
                    }

                    # For a multi-word concept, require the expected modifier
                    # to occur immediately before the head in the local phrase.
                    expected_modifier_ok = True
                    if modifier_terms:
                        # At least one query modifier should be directly close
                        # to the head; otherwise this is likely a related concept.
                        expected_modifier_ok = bool(
                            modifier_terms & set(tokens[max(0, pos - 3):pos])
                        )

                    # If the exact queried phrase occurs, don't penalize
                    # harmless preceding words.  If it doesn't, a specific
                    # modifier immediately before the phrase is a strong
                    # indication of a sibling concept.  However, definitions
                    # such as "Lift is the aerodynamic force..." are valid for
                    # the query "aerodynamic lift" even though the modifier is
                    # on the predicate side rather than immediately before
                    # the head noun.
                    head_is_subject = bool(
                        re.search(
                            rf"(?:\b(?:an?|the)\s+)?{re.escape(head_term)}\s+(?:is|are)\b",
                            s, re.I,
                        )
                    )
                    if (
                        not phrase_match
                        and modifier_terms
                        and not expected_modifier_ok
                        and not head_is_subject
                    ):
                        continue

                    # Even when the generic phrase occurs inside a longer
                    # specific phrase ("free stream Mach number"), reject the
                    # candidate if an extra technical modifier immediately
                    # precedes the queried phrase.  Articles and harmless
                    # grammar words are allowed.
                    if phrase_match and phrase_start is not None:
                        prefix = tokens[max(0, phrase_start - 3):phrase_start]
                        extra_prefix = [
                            x for x in prefix
                            if x not in {"a", "an", "the", "of", "for", "to", "and", "or"}
                            and x not in modifier_terms
                        ]
                        if extra_prefix:
                            continue

                    # For a generic one-term concept such as "Mach number"
                    # represented by two tokens, q_words has both terms, so
                    # phrase_match/expected_modifier_ok protects us.  For
                    # "lift" or another one-term query, use the head-subject
                    # check below.
                    head_near_is = head_is_subject

                    # Definition cue must be tied to the same local concept,
                    # not an unrelated "is" later in the sentence.
                    local_text = " ".join(raw_tokens[left:right])
                    local_definition = bool(
                        explicit_definition.search(local_text)
                        or re.search(r"\b(?:is|are)\b", local_text, re.I)
                    )

                    # A definition of a concept normally has the head term as
                    # the subject ("Mach number is...", "Lift is..."), or the
                    # exact concept phrase followed by a definition cue.
                    subject_definition = bool(head_near_is and local_definition)

                    if (
                        local_coverage >= 0.67
                        and (phrase_match or subject_definition or explicit_definition.search(local_text))
                    ):
                        if s.endswith("?") and not re.search(
                            r"\b(is|are|refers|defined|means)\b", s, re.I
                        ):
                            continue
                        return True

            return False

        # ---- Value / exam questions -----------------------------------
        # Question banks often put the exact question and ANS marker in one
        # chunk. Accept those even when the surrounding chunk contains many
        # unrelated questions.
        if intent == "value":
            # In question banks the wording may differ slightly ("what is
            # value of Cmo" vs "what is the value of Cmo"). Require the core
            # entities plus an answer marker in the same local chunk.
            if len(hits) / len(q_terms) >= 0.67:
                marker = re.search(
                    r"\b(?:ans|answer|correct\s+answer|solution)\b\s*[:=-]?",
                    low,
                    re.I,
                )
                if marker:
                    # Keep the marker reasonably close to the query concepts.
                    first_hit = min(
                        (low.find(term) for term in q_terms if low.find(term) >= 0),
                        default=0,
                    )
                    if abs(marker.start() - first_hit) <= 1800:
                        return True
            for s in sentences[:120]:
                st = sentence_terms(s)
                if len(q_terms & st) / len(q_terms) >= 0.67 and (
                    has_answer_marker(s)
                    or re.search(r"\([a-d]\)|\b\d+(?:\.\d+)?\b", s, re.I)
                ):
                    return True
            return False

        # ---- Calculation questions ------------------------------------
        # A database may contain a worked solution. Require the calculation
        # concepts to co-occur with a result/solution cue.
        if intent == "calculation":
            for s in sentences[:120]:
                st = sentence_terms(s)
                local_coverage = len(q_terms & st) / len(q_terms)
                if local_coverage >= 0.67 and (
                    has_answer_marker(s)
                    or re.search(r"=\s*[-+]?\d|(?:therefore|hence|solution|result)", s, re.I)
                ):
                    return True
            return False

        # ---- Explanations / general factual questions ----------------
        # Require the meaningful concepts to occur together in one evidence
        # sentence. Broad "aerodynamics" similarity is not enough.
        for s in sentences[:120]:
            st = sentence_terms(s)
            local_coverage = len(q_terms & st) / len(q_terms)
            if local_coverage >= 0.75:
                if intent == "explanation":
                    if re.search(
                        r"\bbecause\b|\bdue\s+to\b|\bcaused\s+by\b|\boccurs?\b|"
                        r"\bwhen\b|\bresults?\b|\ballows?\b|\benables?\b",
                        s, re.I,
                    ):
                        return True
                else:
                    return True

        # For a single concrete concept, require the concept plus an answer-like
        # sentence. This prevents "lift" alone from accepting a random lift-slope
        # calculation.
        if len(q_terms) == 1 and hits:
            for s in sentences[:120]:
                if cls._normalise_term(next(iter(q_terms))) in sentence_terms(s):
                    if re.search(r"\bis\b|\bare\b|\brefers?\b|\bdefined\b|\banswer\b|\bans\b", s, re.I):
                        return True

        return False

    @classmethod
    def attach_evidence_excerpts(cls, question: str, chunks: List[Dict]) -> List[Dict]:
        """Attach only the best evidence sentence to each DB source card."""
        out = []
        q_terms = cls._meaningful_terms(question)
        for chunk in chunks:
            c = dict(chunk)
            text = re.sub(r"\s+", " ", c.get("text", "")).strip()
            sentences = [
                s.strip(" -•")
                for s in re.split(r"(?<=[.!?])\s+|(?<=:)\s+", text)
                if len(s.strip()) >= 25
            ]
            best, best_score = "", -1.0
            for sentence in sentences[:120]:
                st = {cls._normalise_term(t) for t in re.findall(r"[a-zA-Z0-9]{3,}", sentence.lower())}
                coverage = len(q_terms & st) / len(q_terms) if q_terms else 0.0
                if coverage > best_score:
                    best_score, best = coverage, sentence
            c["evidence"] = best or text[:320]
            out.append(c)
        return out
    def assess_db_sufficiency(
        self,
        question: str,
        db_chunks: List[Dict],
    ) -> str:

        """
            Decide whether the retrieved database evidence is sufficient to
            answer the user's question by itself.

            Returns:
            "complete" -> DB can answer the question on its own.
            "partial"  -> DB contains related/useful information but not enough.
            "missing"  -> DB does not contain a usable answer.
            """

        if not db_chunks:
            return "missing"

        # -------------------------------------------------------------- #
        # LLM-based completeness judge
        # -------------------------------------------------------------- #
        if self.mode in {"openrouter", "openai", "ollama"}:
            try:
                result = self._llm_db_sufficiency_judge(
                    question,
                    db_chunks,
                )

                if result in {"complete", "partial", "missing"}:
                    return result

            except Exception as exc:
                print(f"[LLM] DB sufficiency judge unavailable: {exc}")

        # -------------------------------------------------------------- #
        # Conservative fallback when no LLM is available
        # -------------------------------------------------------------- #

        answer = self._db_extractive_answer(question, db_chunks)

        if not answer:
            return "partial"

        intent = self._question_intent(question)

        # A real definition should normally contain a definition cue.
        if intent == "definition":
            if re.search(
                r"\b(?:is|are|refers?\s+to|defined\s+as|means|denotes?)\b",
                answer,
                re.I,
            ):
                return "complete"
            return "partial"

        # Explanations should contain explanatory language.
        if intent == "explanation":
            if re.search(
                r"\bbecause\b|\bdue\s+to\b|\bcaused\s+by\b|\boccurs?\b|"
                r"\bresults?\b|\ballows?\b|\benables?\b",
                answer,
                re.I,
            ):
                return "complete"
            return "partial"

        # Calculations / values are considered complete only when a result
        # or explicit answer is present.
        if intent in {"calculation", "value"}:
            if re.search(
                r"\b(?:ans|answer|solution|result|therefore|hence|thus)\b|"
                r"=\s*[-+]?\d",
                answer,
                re.I,
            ):
                return "complete"
            return "partial"

        # General factual questions: a reasonably substantial answer is
        # acceptable, but stay conservative.
        if len(answer.strip()) >= 80:
            return "complete"

        return "partial"


    def _llm_db_sufficiency_judge(
        self,
        question: str,
        db_chunks: List[Dict],
    ) -> str:
        """
        Ask the configured model whether the DB evidence is complete,
        partial, or missing for the exact user question.
        """

        import json
        import urllib.request

        passages = []

        for i, c in enumerate(db_chunks[:5]):
            passages.append(
                f"[{i}] {c.get('file', 'document')}"
                + (
                    f", page {c.get('page')}"
                    if c.get("page")
                    else ""
                )
                + f"\n{c.get('text', '')[:1800]}"
            )

        prompt = (
            "You are a strict evidence-completeness judge for an aerospace "
            "research assistant.\n\n"

            "Determine whether the DATABASE passages alone are sufficient "
            "to answer the user's exact question.\n\n"

            "Return exactly one of:\n"
            "complete\n"
            "partial\n"
            "missing\n\n"

            "Definitions:\n"
            "- complete: The database contains a direct answer, definition, "
            "equation, explanation, or requested value. A reasonable answer "
            "can be produced without outside information.\n"
            "- partial: The database contains information related to the "
            "question, but important information needed to answer it is "
            "missing. Web search should supplement it.\n"
            "- missing: The database does not contain useful answer evidence. "
            "The retrieved passages are merely topical or incidental matches.\n\n"

            "IMPORTANT:\n"
            "- Do NOT mark a passage complete merely because it contains the "
            "same keyword as the question.\n"
            "- A document mentioning 'satellite' is NOT sufficient to answer "
            "'What is a satellite?' unless it actually defines or explains "
            "what a satellite is.\n"
            "- A question-bank item mentioning a concept is not sufficient "
            "for a generic definition unless it provides the actual answer.\n"
            "- For an equation question, the actual equation and enough "
            "context to explain it must be present.\n"
            "- Do not use general knowledge. Judge only the supplied DB text.\n\n"

            f"QUESTION:\n{question}\n\n"
            "DATABASE PASSAGES:\n"
            + "\n\n".join(passages)
            + "\n\nCLASSIFICATION:"
        )

        if self.mode == "openrouter":
            model = os.getenv(
                "OPENROUTER_MODEL",
                "meta-llama/llama-3.3-70b-instruct",
            )

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a strict evidence classifier. "
                            "Return only complete, partial, or missing."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0,
                "max_tokens": 10,
            }

            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Intellex",
                },
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"]

        elif self.mode == "openai":
            model = os.getenv(
                "OPENAI_MODEL",
                "gpt-4o-mini",
            )

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return only complete, partial, or missing."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0,
                "max_tokens": 10,
            }

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openai_api_key}",
                },
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"]

        else:
            # Ollama
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                },
            }

            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data.get("response", "")

        result = content.strip().lower()

        # Be tolerant of accidental surrounding text.
        if "complete" in result:
            return "complete"

        if "partial" in result:
            return "partial"

        if "missing" in result:
            return "missing"

        raise ValueError(
            f"Invalid DB sufficiency classification: {content!r}"
        )

    def filter_relevant_db_chunks(
        self, question: str, db_chunks: List[Dict], min_score: float = 0.55
    ) -> List[Dict]:
        """Return only DB passages that can credibly answer the question.

        When an LLM is available, use it as a small relevance judge. If no LLM
        key/model is available, use the conservative lexical gate above.
        The final answer generator only receives validated passages.
        """
        if not db_chunks:
            return []

        # First remove obviously weak retrievals.
        candidates = [
            c for c in db_chunks
            if float(c.get("score", 0.0)) >= max(0.35, min_score * 0.80)
        ][:8]

        # For generic definition/explanation queries, question-bank chunks are
        # retrieval candidates only, never answer evidence. This prevents an
        # MCQ such as "The critical Mach number..." from being selected for
        # the broader question "What is Mach number?". Exact exam-question
        # lookups are handled by the value/calculation paths below.
        intent = self._question_intent(question)
        if intent in {"definition", "explanation"}:
            candidates = [
                c for c in candidates
                if not self._looks_like_question_bank(
                    c.get("text", ""), c.get("file", "")
                )
            ]

        if not candidates:
            return []

        # LLM validation gives much better judgement for natural-language
        # questions and prevents "aerodynamics" question-bank neighbours from
        # being mistaken for an answer about a specific concept.
        if self.mode in {"openrouter", "openai", "ollama"}:
            try:
                indices = self._llm_relevance_judge(question, candidates)
                judged = [candidates[i] for i in indices if 0 <= i < len(candidates)]
                # The model is a semantic judge, but keep a deterministic
                # answerability gate as a second lock. This prevents a model
                # from accepting a merely topical aerodynamics passage.
                validated = [
                    c for c in judged
                    if self._lexical_db_relevance(question, c, min_score=min_score)
                ]
                if validated:
                    return validated[:5]
                # A successful judge returning no indices means there is no
                # credible DB answer; do not fall back to the bad candidates.
                return []
            except Exception as exc:
                print(f"[LLM] DB relevance judge unavailable: {exc}")

        validated = [
            c for c in candidates
            if self._lexical_db_relevance(question, c, min_score=min_score)
        ]
        return validated[:5]

    def _llm_relevance_judge(
        self, question: str, candidates: List[Dict]
    ) -> List[int]:
        """Ask the configured model which retrieved passages truly answer Q."""
        import json
        import urllib.request

        passages = []
        for i, c in enumerate(candidates):
            passages.append(
                f"[{i}] {c.get('file', 'document')}"
                + (f", page {c.get('page')}" if c.get("page") else "")
                + f"\n{c.get('text', '')[:1800]}"
            )

        prompt = (
            "You are a strict retrieval evaluator for a personal research "
            "assistant. Determine which database passages actually contain "
            "information that can answer the user's exact question. "
            "Do NOT select a passage merely because it is from the same broad "
            "subject. An unrelated aerodynamics question, equation, or MCQ is "
            "NOT relevant to a definition question. For 'what is/define' questions, "
            "select only passages containing an actual definition/explanation of the "
            "concept, not a calculation or another question that merely mentions it. "
            "For value/calculation questions, require the actual requested value, "
            "solution, or answer marker. Return ONLY JSON in the "
            'form {"relevant":[0,2]}. Return an empty list if none answers it.\n\n'
            f"QUESTION:\n{question}\n\nPASSAGES:\n"
            + "\n\n".join(passages)
        )

        if self.mode == "openrouter":
            model = os.getenv(
                "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"
            )
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a strict database retrieval judge. Output JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 120,
            }
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Intellex",
                },
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]

        elif self.mode == "openai":
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": "Output JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 120,
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openai_api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]

        else:  # Ollama
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            }
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data.get("response", "")

        # Be tolerant of a model wrapping JSON in markdown.
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            raise ValueError("relevance judge returned non-JSON")
        parsed = json.loads(match.group(0))
        indices = parsed.get("relevant", [])
        if not isinstance(indices, list):
            raise ValueError("relevance judge returned invalid indices")
        return [int(i) for i in indices if str(i).lstrip("-").isdigit()]

    def _generate_extractive(
        self, question: str, db_chunks: List[Dict], web_results: List[Dict]
    ) -> str:
        if db_chunks:
            return self._db_extractive_answer(question, db_chunks)

        if web_results:
            answer = self._web_extractive_answer(question, web_results)
            if answer:
                return answer + "\n\n*Based on the available web sources; open the sources below for details.*"

        return (
            "I couldn't find an answer in your database or on the web. "
            "Try rephrasing your question."
        )
