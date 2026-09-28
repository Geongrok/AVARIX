"""AVARIX problem-evidence classification layer.

This module classifies already-retrieved KB evidence. It does not calculate,
perform web search, or replace the existing DB relevance gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?(?![A-Za-z])")

FORMULA_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9_]*\s*(?:=|≈|~)\s*[^.;\n]+"
    r"|\b(?:formula|equation|relation)\b\s*[:\-]?\s*[^.;\n]+)", re.I)

PROBLEM_CUES = ("problem", "question", "calculate", "compute", "determine", "find", "solve", "evaluate", "given", "required")
SOLUTION_CUES = ("solution", "solved", "worked solution", "working", "steps", "therefore", "hence", "thus", "substituting", "substitute", "calculation", "answer", "final answer", "result")
FORMULA_CUES = ("formula", "equation", "relation", "expression", "defined as", "is given by", "given by")
CONCEPT_CUES = ("what is", "what are", "definition", "defined", "refers to", "means", "principle", "working principle", "application", "applications", "used for", "used in")


@dataclass
class Evidence:
    type: str
    confidence: float
    source: Dict[str, Any] = field(default_factory=dict)
    question: str = ""
    solution: str = ""
    formula: str = ""
    final_answer: str = ""
    query_numbers: List[str] = field(default_factory=list)
    evidence_numbers: List[str] = field(default_factory=list)
    shared_numbers: List[str] = field(default_factory=list)
    matched_terms: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "question": self.question,
            "solution": self.solution,
            "formula": self.formula,
            "final_answer": self.final_answer,
            "query_numbers": self.query_numbers,
            "evidence_numbers": self.evidence_numbers,
            "shared_numbers": self.shared_numbers,
            "matched_terms": self.matched_terms,
            "notes": self.notes,
        }


class ProblemEvidenceClassifier:
    """Classify retrieved KB records without performing calculations."""

    THRESHOLDS = {
        "exact_solution": 0.78,
        "similar_problem": 0.52,
        "formula_source": 0.50,
        "concept_source": 0.42,
    }

    def __init__(self, max_items: int = 8):
        self.max_items = max(1, int(max_items))

    def classify(self, query: str, results: Optional[Iterable[Dict[str, Any]]] = None) -> List[Evidence]:
        query = self._norm(query)
        if not query:
            return []
        output: List[Evidence] = []
        for item in list(results or [])[: self.max_items]:
            if isinstance(item, dict):
                record = self._classify_one(query, item)
                if record:
                    output.append(record)
        output.sort(key=lambda x: (self._priority(x.type), x.confidence), reverse=True)
        return output

    def best(self, query: str, results: Optional[Iterable[Dict[str, Any]]] = None) -> Optional[Evidence]:
        items = self.classify(query, results)
        return items[0] if items else None

    def _classify_one(self, query: str, item: Dict[str, Any]) -> Optional[Evidence]:
        text = self._item_text(item)
        if not text:
            return None

        q_tokens = set(self._tokens(query))
        e_tokens = set(self._tokens(text))
        overlap = sorted(q_tokens & e_tokens)
        lexical = len(overlap) / max(1, len(q_tokens))

        q_numbers = self._numbers(query)
        e_numbers = self._numbers(text)
        e_number_set = set(e_numbers)
        shared = [n for n in q_numbers if n in e_number_set]

        problem = self._cue_score(text, PROBLEM_CUES)
        solution = self._cue_score(text, SOLUTION_CUES)
        formula_signal = self._cue_score(text, FORMULA_CUES)
        concept_signal = self._cue_score(text, CONCEPT_CUES)

        # Structured problem records may store these concepts in dedicated
        # fields rather than literal words in the text. Treat those fields as
        # evidence signals without changing the underlying retrieval score.
        if any(item.get(k) for k in ("question", "problem")):
            problem = max(problem, 0.50)
        if any(item.get(k) for k in ("solution", "worked_solution", "steps", "answer", "final_answer", "result")):
            solution = max(solution, 0.50)
        if any(item.get(k) for k in ("formula", "equation")):
            formula_signal = max(formula_signal, 0.50)

        formula = self._formula(item, text)
        solved_text = self._solution(item, text)
        final_answer = self._final_answer(item, text)

        query_problem = (
            bool(q_numbers)
            or bool(re.search(
                r"\b(?:calculate|compute|determine|find|solve|evaluate|problem|question|given|required)\b",
                query,
                re.I,
            ))
        )
        looks_problem = query_problem and (
            problem >= 0.18
            or bool(q_numbers and e_numbers)
            or bool(re.search(r"\b(?:question|problem)\b", text, re.I))
        )
        looks_solution = solution >= 0.18 or bool(solved_text) or bool(final_answer)

        numeric_exact = (
            not q_numbers
            or (bool(e_numbers) and all(n in e_number_set for n in q_numbers))
        )

        exact = (
            0.34 * lexical + 0.22 * problem + 0.24 * solution
            + 0.12 * min(1.0, len(shared) / max(1, len(q_numbers)))
            + 0.08 * (1.0 if numeric_exact else 0.0)
        )
        similar = (
            0.44 * lexical + 0.20 * problem + 0.20 * solution
            + 0.10 * (1.0 if formula else 0.0)
            + 0.06 * min(1.0, len(shared) / max(1, len(q_numbers)))
        )
        formula_score = 0.48 * lexical + 0.30 * formula_signal + 0.22 * (1.0 if formula else 0.0)
        concept_score = 0.62 * lexical + 0.22 * concept_signal + 0.16 * (1.0 if not looks_problem else 0.0)

        explicit_solution_field = any(
            item.get(k)
            for k in ("solution", "worked_solution", "steps", "answer", "final_answer", "result")
        )
        exact_candidate = (
            looks_problem
            and looks_solution
            and numeric_exact
            and (lexical >= 0.90)
            and explicit_solution_field
        )

        if exact_candidate or (
            looks_problem
            and looks_solution
            and numeric_exact
            and exact >= self.THRESHOLDS["exact_solution"]
        ):
            kind, confidence = "exact_solution", max(exact, self.THRESHOLDS["exact_solution"])
        elif looks_problem and looks_solution and similar >= self.THRESHOLDS["similar_problem"]:
            kind, confidence = "similar_problem", similar
        elif formula and formula_score >= self.THRESHOLDS["formula_source"]:
            kind, confidence = "formula_source", formula_score
        elif concept_score >= self.THRESHOLDS["concept_source"]:
            kind, confidence = "concept_source", concept_score
        else:
            return None

        source = {k: item.get(k) for k in ("file", "filename", "source", "page", "title", "url", "chunk_id") if item.get(k) is not None}
        notes: List[str] = []
        if kind == "exact_solution":
            notes.append("Stored numerical inputs are compatible with the query.")
        elif kind == "similar_problem":
            notes.append("Use this as a solution method/template; recalculate when the user's values differ.")

        return Evidence(
            type=kind, confidence=confidence, source=source,
            question=self._question(item), solution=solved_text,
            formula=formula, final_answer=final_answer,
            query_numbers=q_numbers, evidence_numbers=e_numbers,
            shared_numbers=shared, matched_terms=overlap[:30], notes=notes,
        )

    @staticmethod
    def _item_text(item: Dict[str, Any]) -> str:
        parts = []
        for key in ("question", "problem", "query", "title", "text", "content", "chunk", "snippet", "answer", "solution", "formula"):
            value = item.get(key)
            if value is not None:
                parts.append(str(value))
        return " ".join(parts).strip()

    @staticmethod
    def _question(item: Dict[str, Any]) -> str:
        for key in ("question", "problem", "query"):
            if item.get(key):
                return str(item[key]).strip()
        return ""

    @staticmethod
    def _solution(item: Dict[str, Any], text: str) -> str:
        for key in ("solution", "worked_solution", "steps"):
            if item.get(key):
                return str(item[key]).strip()
        match = re.search(r"(?:solution|working|steps?)\s*[:\-]\s*(.+)", text, re.I | re.S)
        return match.group(1).strip() if match else str(item.get("answer") or "").strip()

    @staticmethod
    def _final_answer(item: Dict[str, Any], text: str) -> str:
        for key in ("final_answer", "result", "answer"):
            if item.get(key):
                return str(item[key]).strip()
        matches = re.findall(r"(?:final\s+answer|answer|result)\s*[:=]\s*([^\n.;]+)", text, re.I)
        return matches[-1].strip() if matches else ""

    @staticmethod
    def _formula(item: Dict[str, Any], text: str) -> str:
        for key in ("formula", "equation"):
            if item.get(key):
                return str(item[key]).strip()
        match = FORMULA_RE.search(text)
        return match.group(0).strip() if match else ""

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").lower()).strip()

    @staticmethod
    def _tokens(text: str) -> List[str]:
        stop = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "what", "which", "how", "why", "calculate", "compute", "determine", "find", "solve", "show", "using", "use", "me", "please", "can", "you", "give"}
        return [t for t in re.findall(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*", text.lower()) if t not in stop and len(t) > 1]

    @staticmethod
    def _numbers(text: str) -> List[str]:
        return [re.sub(r"\s+", "", value).replace(",", ".").lower() for value in NUMBER_RE.findall(text or "")]

    @staticmethod
    def _cue_score(text: str, cues) -> float:
        return min(1.0, sum(1 for cue in cues if cue in text.lower()) / 4.0)

    @staticmethod
    def _priority(kind: str) -> int:
        return {"exact_solution": 5, "similar_problem": 4, "formula_source": 3, "concept_source": 2, "irrelevant": 1}.get(kind, 0)


ProblemEvidence = ProblemEvidenceClassifier
