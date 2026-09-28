"""Core Intellex routing.

Priority:

    FAST DATABASE
        ↓
    SEMANTIC DATABASE
        ↓
    AeroCalc
        ↓
    WEB

The database is the primary source.

Routing contract:
- DB is checked first.
- A sufficiently answerable DB hit is terminal: answer from DB only.
- If DB misses and the request is a calculation, use AeroCalc.
- Otherwise use a reusable web-answer cache, then fresh web search.
- Fresh web answers may use the LLM for answer synthesis.
- Exactly one previous completed turn is retained per session for follow-ups.
- No global conversation history is used.
- DB answerability and enrichment are deterministic/local to keep the DB path
  fast and prevent an LLM from overruling curated evidence.
"""

import os
import re
import time

from typing import Dict, Optional

from .answer_cache import AnswerCache

from .knowledge_base import (
    KnowledgeBase,
)

from .web_search import (
    WebSearch,
)
from .image_search import (
    ImageSearch,
)
from .llm import (
    LLMEngine,
)
from .math_engine import (
    MathEngine,
)
from .problem_evidence import (
    ProblemEvidenceClassifier,
)

from . import aerocalc_bridge


# ================================================================
# Retrieval thresholds
# ================================================================

RELEVANCE_THRESHOLD = 0.55

SEMANTIC_THRESHOLD = 0.78

# When a validated DB hit is answerable but too thin, pull a small local
# context window from the same document. This enriches answers without
# rebuilding the index, calling OpenRouter, or weakening the answerability gate.
DB_CONTEXT_RADIUS = 2
DB_CONTEXT_MAX_CHUNKS = 8

# Routing contract:
#   1) DB (BM25, then semantic only if BM25 is weak)
#   2) persistent web-answer cache for non-calculation questions
#   3) AeroCalc for explicit calculations
#   4) fresh web search for everything else
#
# A sufficiently answerable DB hit is terminal: no web search and no OpenRouter
# generation. Thin/partial DB hits are expanded locally from nearby same-document
# chunks; if still insufficient, routing continues to cache/AeroCalc/web.
# Conversation memory is exactly one previous completed turn per session.


class ChatBot:

    def __init__(
        self,
        data_dir: Optional[str] = None,
        cache_dir: Optional[str] = None,
        web_results: int = 5,
        threshold: float = RELEVANCE_THRESHOLD,
    ):
        
        self.kb = KnowledgeBase(
            data_dir=data_dir,
            cache_dir=cache_dir,
        )

        self.web = WebSearch(
            max_results=web_results
        )

        self.images = ImageSearch(
            max_results=int(
                os.getenv(
                    "AVARIX_IMAGE_RESULTS",
                    "4",
                )
            ),
        )

        self.llm = LLMEngine()

        self.threshold = threshold

        self._index_ready = False

        # Persistent cache for successful, non-time-dependent web answers.
        # Curated database knowledge remains higher priority than this cache.
        self.answer_cache = AnswerCache(
            os.path.join(self.kb.cache_dir, "web_answers.json")
        )

        # One previous turn per session. Never use a global conversation history.
        self._memory = {}

        self.aerocalc = aerocalc_bridge
        self.math = MathEngine()
        self.problem_evidence = ProblemEvidenceClassifier()

    @staticmethod
    def _normalize_generation(generated):
        """
        Normalize the LLM generation result.

        Supports:
        - new structured dict output
        - legacy plain-string output
        """
        if isinstance(generated, dict):
            answer = str(
                generated.get("answer") or ""
            ).strip()

            structured = generated.get(
                "structured"
            )

            if not isinstance(
                structured,
                dict,
            ):
                structured = None

            visuals = (
                generated.get("visuals")
                or generated.get("images")
                or generated.get("related_visuals")
                or generated.get("relatedVisuals")
                or []
            )

            if not isinstance(
                visuals,
                list,
            ):
                visuals = []

            return (
                answer,
                structured,
                visuals,
            )

        answer = str(
            generated or ""
        ).strip()

        return (
            answer,
            None,
            [],
        )

    # ============================================================
    # PERFORMANCE
    # ============================================================

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
                f"[PERF] {label}: "
                f"{elapsed:.3f}s",
                flush=True,
            )

    # ============================================================
    # INDEX
    # ============================================================
    @staticmethod
    def get_configuration_status():
        """
        Return the current Intellex API configuration status.
            """

        key = os.getenv("OPENROUTER_API_KEY")

        return {
            "openrouter_configured": bool(key),
            "web_search_available": bool(key),
            "message": (
                "Web search available."
                if key
                else
                "Web search unavailable: OPENROUTER_API_KEY is missing."
            ),
        }

    # ============================================================
    # INDEX
    # ============================================================

    def ensure_index(self, force: bool = False) -> None:
        """Load or build the knowledge-base index once."""

        if self._index_ready and not force:
            return

        self.kb.build_index(force=force)
        self._index_ready = True

    # ============================================================
    # CALCULATION DETECTION
    # ============================================================

    @staticmethod
    def _is_explicit_calculation_request(
        question: str,
    ) -> bool:

        query = re.sub(
            r"\s+",
            " ",
            (question or "").lower(),
        ).strip()

        # Direct calculation verbs.

        if re.search(
            r"\b(?:calculate|compute|determine|solve|derive|"
            r"evaluate|work\s+out|find)\b",
            query,
        ):

            return True

        # Numerical input.

        has_number = bool(
            re.search(
                r"(?<![a-z])[-+]?\d+(?:[.,]\d+)?",
                query,
            )
        )

        if not has_number:

            return False

        # NACA identity question.

        if re.fullmatch(
            r"what\s+is\s+(?:the\s+)?naca\s+\d{4}\??",
            query,
        ):

            return False

        calculation_concepts = (
            "mach",
            "naca",
            "airfoil",
            "shock",
            "isentropic",
            "fanno",
            "rayleigh",
            "nozzle",
            "reynolds",
            "density",
            "pressure",
            "temperature",
            "airspeed",
            "velocity",
            "speed of sound",
            "l/d",
            "lift to drag",
            "orbital",
            "orbit",
            "hohmann",
            "delta-v",
            "delta v",
            "rocket equation",
            "escape velocity",
            "pipe flow",
            "friction factor",
            "pitot",
            # Topics added/expanded in the updated AeroCalc package.
            "couette",
            "poiseuille",
            "channel flow",
            "polytropic process",
            "ideal gas process",
            "brayton cycle",
            "otto cycle",
            "diesel cycle",
            "dual cycle",
            "piston cycle",
            "heat transfer",
            "conduction",
            "convection",
            "heat exchanger",
            "turbofan",
            "turbojet",
            "ramjet",
            "rocket nozzle",
            "propeller",
            "rotor momentum",
            "level flight",
            "range endurance",
            "climb performance",
            "rate of climb",
            "turn performance",
            "v-n diagram",
            "takeoff",
            "take-off",
            "landing distance",
            "static stability",
            "beam bending",
            "column buckling",
            "pressure vessel",
            "stress transformation",
            "mohr circle",
            "torsion",
            "laminate",
            "classical lamination",
            "micromechanics",
            "fatigue",
            "fracture",
            "link budget",
            "radar range",
            "antenna gain",
            "noise figure",
            "noise cascade",
            "control response",
            "filter design",
            "scientific calculator",
        )

        return any(
            term in query
            for term in calculation_concepts
        )

    # ============================================================
    # GENERAL MATHEMATICAL PROBLEM SOLVING
    # ============================================================

    @staticmethod
    def _is_general_math_request(question: str) -> bool:
        """Detect general mathematics without stealing AeroCalc requests.

        This is deliberately conservative. Aerospace-domain calculations are
        left for AeroCalc; obvious mathematical expressions, equations,
        calculus requests and unit conversions can use MathEngine.
        """
        q = re.sub(r"\s+", " ", (question or "").lower()).strip()
        if not q:
            return False

        # Calculus / symbolic-math language is a strong signal.
        if re.search(
            r"\b(?:differentiate|derivative|integrate|integral|limit|"
            r"factorize|factorise|simplify|expand|solve|equation|"
            r"simultaneous equations|quadratic)\b",
            q,
        ):
            return True

        # Explicit equations or mathematical operators. Avoid treating a
        # normal sentence containing a hyphen as a mathematical expression.
        if "=" in q and re.search(r"[0-9a-z]\s*=\s*[0-9a-z]", q):
            return True

        if re.search(
            r"[-+]?\d+(?:\.\d+)?\s*(?:[+*/^]|-|÷|×)\s*"
            r"[-+]?\d+(?:\.\d+)?",
            q,
        ):
            return True

        # Compact unit conversions such as 250 km/h to m/s.
        if re.search(
            r"[-+]?\d+(?:\.\d+)?\s*[a-zA-Z/]+\s+"
            r"(?:to|in)\s+[a-zA-Z/]+\b",
            q,
            re.IGNORECASE,
        ):
            return True

        # Explicit arithmetic wording.
        if re.search(
            r"\b(?:calculate|compute|evaluate|what is|what's)\b",
            q,
        ) and re.search(
            r"\b(?:plus|minus|times|multiplied by|divided by|over|"
            r"squared|cubed|square root|percentage|percent|power)\b",
            q,
        ):
            return True

        return False

    @staticmethod
    def _format_math_answer(math_result: Dict) -> str:
        """Turn MathEngine's structured result into a compact AVARIX answer."""
        if not math_result.get("success"):
            error = math_result.get("error") or "The mathematical calculation failed."
            return f"**Mathematical calculation**\n\n{error}"

        operation = math_result.get("operation") or "calculation"
        steps = math_result.get("steps") or []
        result = math_result.get("result")
        notes = math_result.get("notes") or []

        title = {
            "evaluate": "Calculation",
            "solve_equation": "Equation Solution",
            "solve_system": "System of Equations",
            "differentiate": "Differentiation",
            "integrate": "Integration",
            "limit": "Limit",
            "numerical_solve": "Numerical Solution",
            "convert_unit": "Unit Conversion",
        }.get(operation, "Mathematical Solution")

        lines = [f"**{title}**", ""]

        if steps:
            lines.append("**Solution**")
            for step in steps:
                lines.append(f"- {step}")
            lines.append("")

        if result is not None:
            if isinstance(result, dict):
                lines.append("**Result**")
                for key, value in result.items():
                    if isinstance(value, list) and len(value) == 1:
                        value = value[0]
                    lines.append(f"**{key} = {value}**")
            else:
                lines.append(f"**Result: {result}**")

        for note in notes:
            lines.append(f"\n*{note}*")

        return "\n".join(lines).strip()

    def _run_math_engine(self, question: str) -> Optional[Dict]:
        print(
            f"[MATH] checking request: {question}",
            flush=True,
        )

        print(
            f"[MATH] available = {self.math.available}",
            flush=True,
        )

        is_math = self._is_general_math_request(question)

        print(
            f"[MATH] detected = {is_math}",
            flush=True,
        )

        if not self.math.available:
            print(
                "[MATH] MathEngine unavailable",
                flush=True,
            )
            return None

        if not is_math:
            print(
                "[MATH] request was not detected as general math",
                flush=True,
            )
            return None

        t0 = time.perf_counter()

        result = self.math.solve(question)

        print(
            f"[MATH] result = {result}",
            flush=True,
        )

        self._perf(
            f"math_engine success={bool(result.get('success'))}",
            time.perf_counter() - t0,
        )

        return result

    # ============================================================
    # PROBLEM EVIDENCE
    # ============================================================

    def _classify_problem_evidence(
        self,
        question: str,
        db_results,
    ):
        """Classify already-accepted DB hits as problem evidence.

        This runs after the existing DB relevance/answerability gate. It does
        not replace that gate and does not perform any calculation.
        """
        try:
            return [
                item.to_dict()
                for item in self.problem_evidence.classify(
                    question,
                    db_results or [],
                )
            ]
        except Exception as exc:
            print(
                f"[PROBLEM_EVIDENCE] {type(exc).__name__}: {exc}",
                flush=True,
            )
            return []

    # ============================================================
    # RELATED VISUALS
    # ============================================================

    @staticmethod
    def _should_search_visuals(
        question: str,
        is_calculation: bool = False,
    ) -> bool:

        if is_calculation:
            return False

        q = re.sub(
            r"\s+",
            " ",
            (question or "").lower(),
        ).strip()

        if not q:
            return False

        # Provenance questions do not need visuals.
        if re.search(
            r"\b(?:source|sources|reference|references|"
            r"citation|cite|where did you get|"
            r"which page|which document)\b",
            q,
        ):
            return False

        # Avoid visuals for time-sensitive questions.
        if re.search(
            r"\b(?:latest|today|current|news|weather|"
            r"price|stock|recent)\b",
            q,
        ):
            return False

        conceptual_cues = (
            "what is",
            "what are",
            "explain",
            "how does",
            "how do",
            "how is",
            "why does",
            "why is",
            "where is it used",
            "where are",
            "application",
            "applications",
            "used for",
            "used in",
            "working principle",
            "principle of",
            "working of",
            "components",
            "component",
            "types of",
            "classification",
            "difference between",
            "compare",
            "comparison",
            "structure of",
            "diagram",
            "schematic",
            "example of",
        )

        if any(
            cue in q
            for cue in conceptual_cues
        ):
            return True

        aerospace_terms = (
            "mach",
            "airfoil",
            "wing",
            "lift",
            "drag",
            "boundary layer",
            "shock wave",
            "pitot",
            "reynolds",
            "compressible flow",
            "incompressible flow",
            "nozzle",
            "rocket",
            "propulsion",
            "turbine",
            "compressor",
            "aircraft",
            "uav",
            "stability",
            "fem",
            "finite element",
            "stress",
            "strain",
            "wind tunnel",
            "flight",
            "aerodynamics",
        )

        return any(
            term in q
            for term in aerospace_terms
        )
    
    @staticmethod
    def _visual_query(question: str) -> str:

        q = re.sub(
            r"\s+",
            " ",
            (question or "").strip(),
        )

        q = re.sub(
            r"^(?:what\s+is|what\s+are|explain|"
            r"describe|tell\s+me\s+about)\s+",
            "",
            q,
            flags=re.I,
        )

        q = re.sub(
            r"\b(?:where\s+is\s+it\s+used|"
            r"where\s+is\s+it\s+applied|"
            r"what\s+are\s+its\s+applications)\b",
            "applications",
            q,
            flags=re.I,
        )

        return (
            f"{q} aerospace engineering technical diagram"
        )[:320]

    # ============================================================
    # DATABASE SEARCH
    # ============================================================
    
    def _search_visuals(
        self,
        question: str,
        is_calculation: bool = False,
    ):

        if not self._should_search_visuals(
            question,
            is_calculation=is_calculation,
        ):
            return []

        if not self.images.available:
            return []

        query = self._visual_query(question)

        t0 = time.perf_counter()

        visuals = self.images.search(
            query,
            max_results=self.images.max_results,
        )

        self._perf(
            f"image_search ({len(visuals)} results)",
            time.perf_counter() - t0,
        )

        return visuals

    def _search_database(
        self,
        query: str,
        top_k: int = 8,
    ):

        # --------------------------------------------------------
        # STEP 1 — FAST BM25
        # --------------------------------------------------------

        keyword_results = (
            self.kb.search_keyword(
                query,
                top_k=top_k,
            )
        )

        if keyword_results:

            top_score = float(
                keyword_results[0].get(
                    "score",
                    0,
                )
            )

            # Strong keyword match:
            #
            # DO NOT create a vector embedding.

            if top_score >= self.threshold:

                return (
                    keyword_results,
                    "bm25",
                )

        # --------------------------------------------------------
        # STEP 2 — semantic search
        # --------------------------------------------------------

        semantic_results = (
            self.kb.search_semantic(
                query,
                top_k=top_k,
            )
        )

        fused = (
            self.kb.fuse_results(
                keyword_results,
                semantic_results,
                top_k=top_k,
            )
        )

        return (
            fused,
            "hybrid",
        )

    # ============================================================
    # DB ANSWER QUALITY + LOCAL CONTEXT EXPANSION
    # ============================================================

    @staticmethod
    def _db_answer_is_sufficient(question: str, answer: str) -> bool:
        """Check whether a local DB answer is informative enough to terminate.

        This is deliberately deterministic and local.  Retrieval relevance is
        not enough: a sentence such as "They are designed profiles to increase
        the drag divergence Mach number" is relevant to supercritical airfoils,
        but it is too thin to stand alone as the answer to "What is a
        supercritical airfoil?".
        """
        text = re.sub(r"\s+", " ", (answer or "")).strip()
        if not text:
            return False

        intent = LLMEngine._question_intent(question)

        if intent == "definition":
            # The definition cue must be tied to the queried concept.  Do not
            # treat a pronoun construction such as "Supercritical airfoil.
            # They are designed..." as a definition.
            q_terms = LLMEngine._concept_phrase_tokens(question)
            concept = " ".join(q_terms).strip()
            definition_cue = False
            if concept:
                concept_pattern = re.escape(concept)
                definition_cue = bool(re.search(
                    rf"\b{concept_pattern}\b\s+(?:is|are|refers?\s+to|"
                    rf"defined\s+as|means|denotes?|known\s+as|consists?\s+of|"
                    rf"characteri[sz]ed\s+by)\b",
                    text,
                    re.I,
                ))

                # Also accept a clear colon-style definition, e.g.
                # "Supercritical airfoil: a specialized profile..."
                if not definition_cue:
                    definition_cue = bool(re.search(
                        rf"\b{concept_pattern}\b\s*:\s*(?:a|an|the)\b",
                        text,
                        re.I,
                    ))

            if definition_cue:
                return True

            # If there is no concept-tied definition cue, require multiple
            # substantive sentences before accepting the answer. This keeps
            # thin purpose-only snippets from terminating DB routing.
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[.!?])\s+", text)
                if len(s.strip()) >= 35
            ]
            return len(sentences) >= 2 and len(text) >= 180

        if intent == "explanation":
            return bool(
                re.search(
                    r"\bbecause\b|\bdue\s+to\b|\bcaused\s+by\b|\boccurs?\b|"
                    r"\bresults?\b|\ballows?\b|\benables?\b|\bwhen\b",
                    text,
                    re.I,
                )
            )

        # Facts/value/calculation already have stricter answerability gates.
        return len(text) >= 45

    def _expand_db_context(self, seed_chunks, radius=DB_CONTEXT_RADIUS,
                           max_chunks=DB_CONTEXT_MAX_CHUNKS):
        """Return validated seeds plus nearby chunks from the same document.

        The compiled KB keeps chunks and metadata in matching list positions.
        We use those stable in-memory positions to retrieve adjacent chunks, so
        this costs only a tiny local scan and does not touch Chroma or the web.
        Neighbours are supporting context only; they can never replace a
        validated seed hit.
        """
        if not seed_chunks:
            return []

        chunks = getattr(self.kb, "chunks", None) or []
        meta = getattr(self.kb, "meta", None) or []
        if not chunks or len(chunks) != len(meta):
            return list(seed_chunks)

        # Exact lookup by the same fields emitted by KnowledgeBase search.
        positions = {}
        for idx, (text, metadata) in enumerate(zip(chunks, meta)):
            key = (
                str(metadata.get("file", "")),
                metadata.get("page"),
                str(text),
            )
            positions[key] = idx

        expanded = []
        seen = set()

        def add(item, source="seed", distance=0, parent_score=None):
            key = (
                item.get("file"),
                item.get("page"),
                item.get("text", ""),
            )
            if key in seen or len(expanded) >= max_chunks:
                return
            seen.add(key)
            copy = dict(item)
            copy["context_role"] = source
            if source == "context":
                base = float(parent_score if parent_score is not None else 0.55)
                # Keep the support chunk visible to local extractive logic,
                # while retaining its weaker provenance as metadata.
                copy["score"] = max(0.45, base - (0.05 * distance))
                copy["context_distance"] = distance
            expanded.append(copy)

        for seed in seed_chunks:
            if len(expanded) >= max_chunks:
                break

            add(seed, source="seed")
            key = (
                str(seed.get("file", "")),
                seed.get("page"),
                str(seed.get("text", "")),
            )
            idx = positions.get(key)
            if idx is None:
                continue

            seed_file = str(meta[idx].get("file", ""))
            seed_page = meta[idx].get("page")
            base_score = float(seed.get("score", 0.55))

            for distance in range(1, radius + 1):
                if len(expanded) >= max_chunks:
                    break
                for neighbour_idx in (idx - distance, idx + distance):
                    if len(expanded) >= max_chunks:
                        break
                    if neighbour_idx < 0 or neighbour_idx >= len(chunks):
                        continue

                    neighbour_meta = meta[neighbour_idx]
                    neighbour_file = str(neighbour_meta.get("file", ""))
                    neighbour_page = neighbour_meta.get("page")

                    # Never cross into another document.  Prefer the same page,
                    # but allow the immediately adjacent page because a section
                    # can be split at a page boundary.
                    if neighbour_file != seed_file:
                        continue
                    if seed_page is not None and neighbour_page is not None:
                        try:
                            if abs(int(neighbour_page) - int(seed_page)) > 1:
                                continue
                        except (TypeError, ValueError):
                            pass

                    add(
                        {
                            "text": chunks[neighbour_idx],
                            "file": neighbour_file,
                            "page": neighbour_page,
                        },
                        source="context",
                        distance=distance,
                        parent_score=base_score,
                    )

        return expanded

    @staticmethod
    def _db_enriched_answer(question: str, seed_chunks, context_chunks) -> str:
        """Build a richer extractive DB answer from validated + nearby evidence.

        The first answer-bearing sentence must come from a validated seed.
        Nearby chunks may contribute supporting sentences, but only from the
        same document and small context window established by the caller.
        No external model is called here.
        """
        if not seed_chunks:
            return ""

        base = LLMEngine._db_extractive_answer(question, seed_chunks)
        if not base:
            return ""

        intent = LLMEngine._question_intent(question)
        q_terms = LLMEngine._meaningful_terms(question)
        base_sentences = [
            s.strip(" -•")
            for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", base))
            if len(s.strip()) >= 25
        ]
        seen = {
            re.sub(r"\W+", " ", s.lower()).strip()
            for s in base_sentences
        }

        support = []
        for chunk in context_chunks:
            if chunk.get("context_role") != "context":
                continue
            raw = re.sub(r"\s+", " ", chunk.get("text", "")).strip()
            if not raw:
                continue
            if LLMEngine._looks_like_question_bank(raw, chunk.get("file", "")):
                continue

            for sidx, sentence in enumerate(
                re.split(r"(?<=[.!?])\s+|(?<=:)\s+", raw)
            ):
                sentence = sentence.strip(" -•")
                if len(sentence) < 35:
                    continue
                if re.match(r"^[a-z][a-z0-9'\-]*\s", sentence):
                    continue

                key = re.sub(r"\W+", " ", sentence.lower()).strip()
                if not key or key in seen:
                    continue

                st = {
                    LLMEngine._normalise_term(t)
                    for t in re.findall(r"[a-zA-Z0-9]{3,}", sentence.lower())
                }
                overlap = len(q_terms & st)
                coverage = overlap / len(q_terms) if q_terms else 0.0

                score = coverage * 8.0
                if re.search(
                    r"\b(?:is|are|refers?\s+to|defined\s+as|means|"
                    r"characteri[sz]ed|consists?\s+of|designed|features?|"
                    r"typically|includes?|provides?|allows?|reduces?|"
                    r"increases?|improves?|prevents?)\b",
                    sentence,
                    re.I,
                ):
                    score += 4.0
                score += max(0.0, 1.5 - 0.4 * float(chunk.get("context_distance", 1)))
                score -= min(sidx * 0.03, 0.6)

                support.append((score, sentence))

        support.sort(key=lambda item: item[0], reverse=True)

        # Add only a small amount of local context. The answer remains concise
        # and the UI can still expose the underlying source cards separately.
        target_support = 2 if intent in {"definition", "explanation"} else 1
        selected_support = []
        for _, sentence in support:
            key = re.sub(r"\W+", " ", sentence.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            selected_support.append(sentence)
            if len(selected_support) >= target_support:
                break

        if not selected_support:
            return base

        answer = base.rstrip()
        answer += "\n\n**Key points**\n"
        for sentence in selected_support:
            if len(sentence) > 280:
                sentence = sentence[:280].rsplit(" ", 1)[0] + "…"
            answer += f"• {sentence}\n"
        return answer.strip()

    # ============================================================
    # ANSWER
    # ============================================================

    # ============================================================
    # LOCAL INTENT + STRUCTURED CONVERSATIONAL MEMORY
    # ============================================================

    MAX_MEMORY_TURNS = 5

    @staticmethod
    def _is_time_dependent(question: str) -> bool:
        """Return True when an answer depends on a relative/current moment.

        Stable historical years such as 2016 or 2025 are NOT treated as
        time-dependent merely because they contain four digits.
        """
        q = re.sub(r"\s+", " ", (question or "").lower()).strip()
        if not q:
            return False

        temporal_terms = (
            r"\bcurrent(?:ly)?\b", r"\bnow\b", r"\btoday\b", r"\btonight\b",
            r"\byesterday\b", r"\btomorrow\b", r"\blatest\b", r"\brecent(?:ly)?\b",
            r"\bthis\s+(?:week|month|year|morning|afternoon|evening)\b",
            r"\blast\s+(?:week|month|year|night|few\s+days)\b",
            r"\bnext\s+(?:week|month|year|few\s+days)\b",
            r"\bat\s+the\s+moment\b", r"\bas\s+of\s+now\b", r"\bongoing\b",
            r"\blive\b", r"\bjust\s+happened\b", r"\bupdated?\b",
        )
        if any(re.search(pattern, q) for pattern in temporal_terms):
            return True

        live_subjects = (
            "stock price", "share price", "weather", "flight status",
            "launch schedule", "launch status", "mission status", "live score",
            "breaking news", "current chairman", "current ceo",
        )
        return any(term in q for term in live_subjects)

    @staticmethod
    def _is_followup_request(question: str) -> bool:
        """Detect likely contextual follow-ups locally.

        This is detection only. It does NOT itself answer the question.
        """
        q = re.sub(r"\s+", " ", (question or "").lower()).strip()
        if not q:
            return False

        patterns = (
            r"\bwhat did (?:you|it) say\b",
            r"\bprevious answer\b",
            r"\bwhat (?:were|are) (?:the )?(?:web )?(?:sources|results)\b",
            r"\b(?:show|give|list) (?:me )?(?:the )?(?:web )?(?:sources|results)\b",
            r"\bsource(?:s)? for (?:this|that|it|the above)\b",
            r"\bexplain (?:this|that|it)\b",
            r"\b(?:elaborate|expand) on (?:this|that|it)\b",
            r"\b(?:why|how|when|where|which|what) (?:does|did|is|was|are|were)\s+(?:this|that|it)\b",
        )
        if any(re.search(pattern, q) for pattern in patterns):
            return True

        # Short elliptical questions are usually contextual when memory exists.
        words = q.split()
        return len(words) <= 8 and bool(
            re.search(
                r"\b(?:it|this|that|these|those|its|they|them|above|previous|"
                r"same|former|latter|one|ones)\b",
                q,
            )
        )

    @staticmethod
    def _memory_topic(turn: Dict) -> str:
        """Extract a compact topic label from a completed turn."""
        topic = turn.get("topic")
        if topic:
            return str(topic)

        q = str(turn.get("question") or "").strip()
        if not q:
            return ""

        # Keep this deliberately local/deterministic.
        q = re.sub(r"\s+", " ", q)
        q = re.sub(
            r"^(?:what|why|how|when|where|which|who|can|could|is|are|"
            r"explain|define|calculate|compute|determine)\b",
            "",
            q,
            flags=re.I,
        ).strip(" ?:-")
        return q[:180]

    def _save_memory(self, session_id: str, result: Dict) -> None:
        """Keep a rolling window of at most five completed turns."""
        sid = str(session_id or "default").strip() or "default"

        history = self._memory.setdefault(sid, [])
        history.append({
            "question": result.get("_question", ""),
            "resolved_query": result.get("_resolved_query", result.get("_question", "")),
            "answer": result.get("answer", ""),
            "topic": result.get("_topic") or self._memory_topic(result),
            "source": result.get("source"),
            "db_results": result.get("db_results", []),
            "web_results": result.get("web_results", []),
            "aerocalc": result.get("aerocalc"),
            "structured": result.get("structured"),
            "visuals": result.get("visuals", []),
        })

        if len(history) > self.MAX_MEMORY_TURNS:
            del history[:-self.MAX_MEMORY_TURNS]

    def _get_memory(self, session_id: str):
        sid = str(session_id or "default").strip() or "default"
        return self._memory.get(sid, [])

    @staticmethod
    def _compact_memory(history):
        """Return only the context needed for query resolution."""
        compact = []
        for i, turn in enumerate(history[-ChatBot.MAX_MEMORY_TURNS:], 1):
            compact.append({
                "turn": i,
                "question": turn.get("question", ""),
                "resolved_query": turn.get("resolved_query", ""),
                "topic": turn.get("topic", ""),
                "source": turn.get("source"),
            })
        return compact

    def _llm_resolve_context(self, question: str, history):
        """Call the dedicated context resolver, if configured."""
        resolver = getattr(self.llm, "resolve_context", None)
        if not callable(resolver):
            return question
        candidate = resolver(
            question=question,
            memory=self._compact_memory(history),
        )
        return candidate.strip() if isinstance(candidate, str) and candidate.strip() else question

    def _resolve_context(self, question: str, history):
        """Resolve a follow-up into a standalone query.

        Uses the existing LLM only when necessary and only for rewriting/
        reference resolution. It never decides DB/AeroCalc/Web routing and
        never generates the final answer.
        """
        if not history or not self._is_followup_request(question):
            return question, None

        previous = history[-1]
        previous_topic = previous.get("topic") or previous.get("resolved_query") or previous.get("question", "")
        q = re.sub(r"\s+", " ", question).strip()

        # Deterministic handling for source/provenance requests.
        if re.search(r"\b(?:sources|source|results)\b", q, re.I):
            return q, previous_topic

        # Fast deterministic reference replacement for common pronouns.
        resolved = q
        if previous_topic:
            resolved = re.sub(
                r"\b(?:it|this|that|its)\b",
                previous_topic,
                resolved,
                flags=re.I,
            )

        # For genuinely ambiguous follow-ups, ask the existing local/remote
        # LLM to rewrite the question. It returns ONLY the rewritten query.
        # If that fails, the deterministic replacement above is retained.
        needs_resolution = bool(
            re.search(
                r"\b(?:these|those|they|them|one|ones|former|latter|above|"
                r"previous|same)\b",
                q,
                re.I,
            )
        )

        if needs_resolution:
            try:
                    candidate = self._llm_resolve_context(q, history)
                    if candidate and candidate.strip():
                        resolved = candidate.strip()
            except Exception as exc:
                print(
                    f"[CONTEXT] resolver failed: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )

        return resolved, previous_topic

    def _followup_answer(self, question: str, history):
        """Handle provenance/previous-answer follow-ups without new search."""
        if not history:
            return None

        q = re.sub(r"\s+", " ", (question or "").lower()).strip()
        previous = history[-1]
        previous_answer = previous.get("answer", "")
        previous_source = previous.get("source")
        web_results = previous.get("web_results") or []

        if re.search(r"\b(?:web )?(?:sources|results)\b", q):
            if web_results:
                return {
                    "answer": "Here are the web sources used for the previous answer.",
                    "case": 4,
                    "source": "memory",
                    "db_results": previous.get("db_results", []),
                    "web_results": web_results,
                    "aerocalc": previous.get("aerocalc"),
                    "structured": previous.get("structured"),
                    "visuals": previous.get("visuals", []),
                    "mode": self.llm.mode,
                }

            if previous_source == "database":
                return {
                    "answer": (
                        "No web sources were used for the previous answer. "
                        "It was answered from Intellex's database."
                    ),
                    "case": 2,
                    "source": "memory",
                    "db_results": previous.get("db_results", []),
                    "web_results": [],
                    "aerocalc": previous.get("aerocalc"),
                    "structured": previous.get("structured"),
                    "visuals": previous.get("visuals", []),
                    "mode": self.llm.mode,
                }

            return {
                "answer": "No web sources were stored for the previous answer.",
                "case": None,
                "source": "memory",
                "db_results": previous.get("db_results", []),
                "web_results": [],
                "aerocalc": previous.get("aerocalc"),
                "structured": previous.get("structured"),
                "visuals": previous.get("visuals", []),
                "mode": self.llm.mode,
            }

        if re.search(r"\bwhat did (?:you|it) say\b|\bprevious answer\b", q):
            return {
                "answer": previous_answer,
                "case": None,
                "source": "memory",
                "db_results": previous.get("db_results", []),
                "web_results": web_results,
                "aerocalc": previous.get("aerocalc"),
                "structured": previous.get("structured"),
                "visuals": previous.get("visuals", []),
                "mode": self.llm.mode,
            }

        return None
        
    # ============================================================
    # LLM OUTPUT NORMALIZATION
    # ============================================================

    @staticmethod
    def _normalize_generation(generated):
        """
        Normalize LLM output so chatbot.py can support both:

        1. Legacy string output:
           "Mach number is..."

        2. Structured output:
           {
               "answer": "...",
               "structured": {...},
               "visuals": [...]
           }

        This keeps chatbot.py backward-compatible while the LLM
        layer is upgraded.
        """
        if isinstance(generated, dict):
            answer = str(generated.get("answer") or "").strip()

            structured = generated.get("structured")
            if not isinstance(structured, dict):
                structured = None

            visuals = (
                generated.get("visuals")
                or generated.get("images")
                or generated.get("related_visuals")
                or generated.get("relatedVisuals")
                or []
            )

            if not isinstance(visuals, list):
                visuals = []

            return answer, structured, visuals

        answer = str(generated or "").strip()

        return answer, None, []

    def answer(
        self,
        question: str,
        rebuild_index: bool = False,
        session_id: str = "default",
    ) -> Dict:
        request_started = time.perf_counter()
        question = (question or "").strip()

        if not question:
            return {
                "answer": "Please ask a question.",
                "case": None,
                "db_results": [],
                "web_results": [],
                "aerocalc": None,
                "structured": None,
                "visuals": [],
                "mode": self.llm.mode,
            }

        # ---------------------------------------------------------------
        # 0. ONE-SESSION CONTEXT
        # ---------------------------------------------------------------
        history = self._get_memory(session_id)

        # Provenance/previous-answer requests can be answered immediately.
        if history and self._is_followup_request(question):
            followup = self._followup_answer(question, history)
            if followup is not None:
                self._perf("followup_memory", time.perf_counter() - request_started)
                return followup

        # Resolve contextual references before any retrieval.
        t0 = time.perf_counter()
        resolved_question, topic = self._resolve_context(question, history)
        self._perf("context_resolution", time.perf_counter() - t0)

        is_calculation = self._is_explicit_calculation_request(resolved_question)
        time_dependent = self._is_time_dependent(resolved_question)

        # ---------------------------------------------------------------
        # 1. KNOWLEDGE-BASE INDEX
        # ---------------------------------------------------------------
        self.ensure_index(force=rebuild_index)

        # normalize_query is local/static; it never calls an LLM.
        retrieval_question = LLMEngine.normalize_query(resolved_question)

        # ================================================================
        # GENERAL MATH — BEFORE KNOWLEDGE-BASE RETRIEVAL
        # ================================================================
        is_general_math = self._is_general_math_request(resolved_question)

        if is_general_math:
            math_result = self._run_math_engine(resolved_question)

            if math_result is not None:
                answer = self._format_math_answer(math_result)

                result = {
                    "answer": answer,
                    "case": 4,
                    "source": "math",
                    "db_results": [],
                    "problem_evidence": [],
                    "web_results": [],
                    "aerocalc": None,
                    "math": math_result,
                    "structured": None,
                    "visuals": [],
                    "mode": self.llm.mode,
                    "_question": question,
                    "_resolved_query": resolved_question,
                    "_topic": topic or self._memory_topic({
                        "question": resolved_question,
                    }),
                }

                self._save_memory(session_id, result)
                self._perf(
                    "TOTAL",
                    time.perf_counter() - request_started,
                )

                return {
                    k: v for k, v in result.items()
                    if not k.startswith("_")
                }

        # ================================================================
        # 2. CURATED DATABASE — HIGHEST AUTHORITY
        # ================================================================
        t0 = time.perf_counter()
        db_candidates, retrieval_mode = self._search_database(
            retrieval_question,
            top_k=8,
        )
        self._perf(
            f"db_search mode={retrieval_mode}",
            time.perf_counter() - t0,
        )

        relevant = []
        for result in db_candidates:
            score = float(result.get("score", 0.0))
            vector_score = float(result.get("vector_score", score))
            filename_match = bool(result.get("filename_match", False))

            if score >= self.threshold or filename_match:
                relevant.append(result)
            elif (
                retrieval_mode == "hybrid"
                and vector_score >= SEMANTIC_THRESHOLD
            ):
                relevant.append(result)

        unique = {}
        for result in relevant:
            key = (
                result.get("file"),
                result.get("page"),
                result.get("text", "")[:200],
            )
            unique[key] = result

        relevant = list(unique.values())
        relevant.sort(
            key=lambda item: float(item.get("score", 0.0)),
            reverse=True,
        )

        # DB HIT = DB ANSWER ONLY, but only after deterministic answerability
        # validation. A topical hit is not automatically an answer.
        # No sufficiency API call and no OpenRouter generation are used here.
        if relevant:
            t0 = time.perf_counter()

            answerable_db = [
                candidate
                for candidate in relevant[:8]
                if not (
                    LLMEngine._question_intent(resolved_question) == "definition"
                    and LLMEngine._looks_like_question_bank(
                        candidate.get("text", ""),
                        candidate.get("file", ""),
                    )
                )
                and self.llm._lexical_db_relevance(
                    resolved_question,
                    candidate,
                    min_score=max(0.45, self.threshold),
                )
            ]

            self._perf(
                "db_answerability_gate",
                time.perf_counter() - t0,
            )

            if answerable_db:
                t0 = time.perf_counter()

                # Pull a tiny same-document context window only when the
                # validated answer is too thin. This does NOT alter retrieval
                # scores or the database authority order.
                initial_answer = self.llm._db_extractive_answer(
                    resolved_question,
                    answerable_db,
                )

                if self._db_answer_is_sufficient(
                    resolved_question,
                    initial_answer,
                ):
                    answer_text = initial_answer
                    enriched_db = answerable_db
                else:
                    expanded_db = self._expand_db_context(answerable_db)
                    answer_text = self._db_enriched_answer(
                        resolved_question,
                        answerable_db,
                        expanded_db,
                    )

                    if self._db_answer_is_sufficient(
                        resolved_question,
                        answer_text,
                    ):
                        enriched_db = expanded_db
                    else:
                        # The DB has topical/partial evidence but still does
                        # not contain a sufficiently informative answer. Fall
                        # through to the existing answer-cache -> AeroCalc ->
                        # web route rather than returning a weak DB answer.
                        answer_text = ""
                        enriched_db = []

                self._perf(
                    "db_answer_local",
                    time.perf_counter() - t0,
                )

                if answer_text:

                    visuals = self._search_visuals(
                        resolved_question,
                        is_calculation=is_calculation,
                    )

                    problem_evidence = self._classify_problem_evidence(
                        resolved_question,
                        enriched_db,
                    )

                    result = {
                        "answer": answer_text,
                        "case": 2,
                        "source": "database",
                        "db_results": enriched_db,
                        "problem_evidence": problem_evidence,
                        "web_results": [],
                        "aerocalc": None,
                        "structured": None,
                        "visuals": visuals,
                        "mode": self.llm.mode,
                        "_question": question,
                        "_resolved_query": resolved_question,
                        "_topic": topic or self._memory_topic({
                            "question": resolved_question,
                        }),
                    }
                    self._save_memory(session_id, result)
                    self._perf(
                        "TOTAL",
                        time.perf_counter() - request_started,
                    )
                    return {
                        k: v for k, v in result.items()
                        if not k.startswith("_")
                    }

        # ================================================================
        # 3. PERSISTENT WEB ANSWER CACHE
        # ================================================================
        is_general_math = self._is_general_math_request(resolved_question)

        # Never serve a general web-answer cache entry for an engineering
        # calculation. Calculator inputs can change while the question remains
        # similar, so cached prose can silently return stale numeric results.
        if not time_dependent and not is_general_math and not is_calculation:
            cached = self.answer_cache.get(resolved_question)

            if cached:

                cached_visuals = cached.get(
                        "visuals",
                        [],
                    )

                if not isinstance(
                    cached_visuals,
                    list,
                ):
                    cached_visuals = []

                if not cached_visuals:

                    cached_visuals = self._search_visuals(
                        resolved_question,
                        is_calculation=is_calculation,
                    )

                    if cached_visuals:

                        self.answer_cache.put(
                            question=resolved_question,
                            answer=cached.get(
                                "answer",
                                "",
                            ),
                            web_results=cached.get(
                                "web_results",
                                [],
                            ),
                            structured=cached.get(
                                "structured"
                            ),
                            visuals=cached_visuals,
                        )

                result = {
                    "answer": cached.get("answer", ""),
                    "case": 6,
                    "source": "web_cache",
                    "db_results": [],
                    "problem_evidence": [],
                    "web_results": cached.get("web_results", []),
                    "aerocalc": None,
                    "structured": cached.get("structured"),
                    "visuals": cached_visuals,
                    "mode": self.llm.mode,
                    "_question": question,
                    "_resolved_query": resolved_question,
                    "_topic": topic or self._memory_topic({
                        "question": resolved_question,
                    }),
                }
                self._save_memory(session_id, result)
                self._perf(
                    "answer_cache HIT",
                    time.perf_counter() - request_started,
                )
                return {
                    k: v for k, v in result.items()
                    if not k.startswith("_")
                }

        # ================================================================
        # 4. AEROCALC — CALCULATION REQUESTS ONLY
        # ================================================================
        calc = None

        if is_calculation:
            t0 = time.perf_counter()
            calc = self.aerocalc.compute(resolved_question)
            self._perf(
                "aerocalc",
                time.perf_counter() - t0,
            )

        if calc is not None:
            # Any matched AeroCalc response is terminal, including requests
            # that need additional inputs. Do not send a matched engineering
            # calculation to web search merely because its summary is empty.
            if calc.get("matched") or calc.get("summary") or (
                calc.get("error") and not is_general_math
            ):
                if calc.get("error"):
                    answer = (
                        f"AeroCalc matched this as "
                        f"**{calc['match_name']}**, "
                        "but the calculation could not be completed."
                    )
                elif calc.get("summary"):
                    answer = (
                        f"**AeroCalc result — "
                        f"{calc['match_name']}**\n\n"
                        f"{calc['summary']}"
                    )
                else:
                    answer = (
                        f"**AeroCalc — {calc.get('match_name', 'Calculation')}**\n\n"
                        "I matched your request to this calculator, but need "
                        "more input values before I can calculate the result.\n\n"
                        + "\n".join(
                            f"- {item}" for item in calc.get("suggestions", [])
                        )
                    )

                result = {
                    "answer": answer,
                    "case": 3,
                    "source": "aerocalc",
                    "db_results": [],
                    "problem_evidence": [],
                    "web_results": [],
                    "aerocalc": calc,
                    "math": None,
                    "structured": None,
                    "visuals": [],
                    "mode": self.llm.mode,
                    "_question": question,
                    "_resolved_query": resolved_question,
                    "_topic": topic or self._memory_topic({
                        "question": resolved_question,
                    }),
                }
                self._save_memory(session_id, result)
                self._perf("TOTAL", time.perf_counter() - request_started)
                return {
                    k: v for k, v in result.items()
                    if not k.startswith("_")
                }

        # ================================================================
        # 5. FRESH WEB — LAST RESORT
        # ================================================================
        t0 = time.perf_counter()
        web_results = self.web.search(retrieval_question)
        self._perf(
            f"web_search ({len(web_results)} results)",
            time.perf_counter() - t0,
        )

        usable_web = [
            result
            for result in web_results
            if not result.get("_search_error")
        ]

        if not usable_web:
            result = {
                "answer": (
                    "I couldn't retrieve relevant web sources for this "
                    "question right now. The local knowledge base and "
                    "reusable answer cache did not contain a sufficient match."
                ),
                "case": 1,
                "source": "web_unavailable",
                "db_results": relevant,
                "web_results": web_results,
                "aerocalc": None,
                "structured": None,
                "visuals": [],
                "mode": self.llm.mode,
                "_question": question,
                "_resolved_query": resolved_question,
                "_topic": topic or self._memory_topic({
                    "question": resolved_question,
                }),
            }
            self._save_memory(session_id, result)
            self._perf(
                "TOTAL",
                time.perf_counter() - request_started,
            )
            return {
                k: v for k, v in result.items()
                if not k.startswith("_")
            }

                # Fresh web answer may use the existing LLM quality layer.
        t0 = time.perf_counter()

        structured = None
        visuals = []

        try:
            generated = self.llm.generate(
                resolved_question,
                [],
                usable_web,
            )

            (
                answer_text,
                structured,
                visuals,
            ) = self._normalize_generation(
                generated
            )

        except Exception as exc:
            print(
                f"[LLM] Generation failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

            answer_text = (
                self.llm._web_extractive_answer(
                    resolved_question,
                    usable_web,
                )
                or ""
            ).strip()

            structured = None
            visuals = []

        self._perf(
            f"web_answer_generation mode={self.llm.mode}",
            time.perf_counter() - t0,
        )

        if not answer_text:
            answer_text = (
                self.llm._web_extractive_answer(
                    resolved_question,
                    usable_web,
                )
                or ""
            ).strip()
            
        if not visuals:

            visuals = self._search_visuals(
                resolved_question,
                is_calculation=is_calculation,
            )

        # Persist only stable/non-relative web answers.
        if not time_dependent and answer_text:
            self.answer_cache.put(
                question=resolved_question,
                answer=answer_text,
                web_results=usable_web,
                structured=structured,
                visuals=visuals,
            )

        result = {
            "answer": answer_text,
            "case": 4,
            "source": "web",
            "db_results": relevant,
            "web_results": usable_web,
            "aerocalc": None,
            "mode": self.llm.mode,
            "structured": structured,
            "visuals": visuals,
            "_question": question,
            "_resolved_query": resolved_question,
            "_topic": topic or self._memory_topic({
                "question": resolved_question,
            }),
        }
        self._save_memory(session_id, result)

        self._perf(
            "TOTAL",
            time.perf_counter() - request_started,
        )
        return {
            k: v for k, v in result.items()
            if not k.startswith("_")
        }

    # ============================================================
    # STATUS
    # ============================================================

    def stats(self) -> Dict:

        return {
            "docs_loaded":
                self.kb.doc_count(),

            "files":
                self.kb.file_names(),

            "llm_mode":
                self.llm.mode,

            "web_search":
                self.web.available,

            "web_backend":
                self.web.backend_name(),

            "embedding":
                self.kb.vector.embedding.info(),

            "vector_docs":
                self.kb.vector.count(),

            "threshold":
                self.threshold,

            "aerocalc":
                self.aerocalc.info(),

            "math_engine":
                self.math.capabilities(),

            "data_dir":
                self.kb.data_dir,

            "cache_dir":
                self.kb.cache_dir,

            "answer_cache":
                os.path.join(
                    self.kb.cache_dir,
                    "web_answers.json",
                ),
        }

config = ChatBot.get_configuration_status()

if config["web_search_available"]:
    print("[CONFIG] OpenRouter API key detected")
    print("[CONFIG] Web search: AVAILABLE")
else:
    print("[CONFIG] OpenRouter API key: NOT FOUND")
    print(
        "[WARNING] Web search is unavailable. "
        "Add OPENROUTER_API_KEY to .env"
    )

