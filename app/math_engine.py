"""
AVARIX Math Engine
==================

General mathematical problem-solving engine for AVARIX.

Design goals
------------
1. Keep mathematical computation separate from the LLM.
2. Use SymPy for symbolic mathematics and SciPy for numerical roots when
   available.
3. Return structured, auditable results rather than only a formatted string.
4. Provide a small, controlled natural-language front end for common requests.
5. Allow the AVARIX router to call explicit operations directly in future.

This module is intentionally NOT an aerospace calculator. Aerospace-specific
calculations should continue to use AeroCalc. The MathEngine handles general
mathematics that AeroCalc should not need to know about.

Examples
--------
    engine = MathEngine()

    engine.solve("2*x + 5 = 17")
    engine.solve("x^2 - 5*x + 6 = 0")
    engine.solve("differentiate x^3 + 2*x")
    engine.solve("integrate 3*x^2 + 4")
    engine.solve("solve sin(x) = x/2 near 1")
    engine.solve("25 * (7 + 3) / 5")
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


try:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        implicit_multiplication_application,
        convert_xor,
        standard_transformations,
        parse_expr,
    )

    _SYMPY_AVAILABLE = True
    _TRANSFORMATIONS = standard_transformations + (
        convert_xor,
        implicit_multiplication_application,
    )
except Exception:  # pragma: no cover - handled at runtime
    sp = None
    parse_expr = None
    _TRANSFORMATIONS = ()
    _SYMPY_AVAILABLE = False


try:
    from scipy.optimize import root_scalar

    _SCIPY_AVAILABLE = True
except Exception:  # pragma: no cover - optional
    root_scalar = None
    _SCIPY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_DECIMAL_PLACES = 10

# Only these mathematical names are exposed to the parser.
# Do not add arbitrary Python names here.
_ALLOWED_FUNCTIONS = {
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "asin": "asin",
    "acos": "acos",
    "atan": "atan",
    "sinh": "sinh",
    "cosh": "cosh",
    "tanh": "tanh",
    "sqrt": "sqrt",
    "log": "log",
    "ln": "log",
    "exp": "exp",
    "abs": "Abs",
    "floor": "floor",
    "ceiling": "ceiling",
}

_ALLOWED_CONSTANTS = {
    "pi": "pi",
    "e": "E",
}

_ALLOWED_SYMBOLS = {
    # Common mathematical variables.
    "x", "y", "z",
    "a", "b", "c",
    "m", "n",
    "t",
    "u", "v", "w",
    "r",
    "theta", "phi",
    "alpha", "beta", "gamma",
    "lambda",
}

# Basic unit conversions are deliberately small in v1. AeroCalc remains the
# authoritative engineering/unit engine for aerospace-specific calculations.
_UNIT_FACTORS = {
    ("m", "cm"): 100.0,
    ("cm", "m"): 0.01,
    ("m", "mm"): 1000.0,
    ("mm", "m"): 0.001,
    ("km", "m"): 1000.0,
    ("m", "km"): 0.001,
    ("ft", "m"): 0.3048,
    ("m", "ft"): 3.280839895013123,
    ("in", "cm"): 2.54,
    ("cm", "in"): 1.0 / 2.54,
    ("in", "m"): 0.0254,
    ("m", "in"): 39.37007874015748,
    ("km/h", "m/s"): 1.0 / 3.6,
    ("m/s", "km/h"): 3.6,
    ("mph", "m/s"): 0.44704,
    ("m/s", "mph"): 2.2369362920544,
    ("kn", "m/s"): 0.5144444444444445,
    ("m/s", "kn"): 1.9438444924406048,
    ("deg", "rad"): math.pi / 180.0,
    ("rad", "deg"): 180.0 / math.pi,
}


class MathEngineError(ValueError):
    """Controlled error raised for invalid or unsupported math requests."""


@dataclass
class ParsedProblem:
    operation: str
    expression: Optional[str] = None
    equations: Optional[List[str]] = None
    variable: Optional[str] = None
    point: Optional[str] = None
    initial_guess: Optional[float] = None
    target_unit: Optional[str] = None


class MathEngine:
    """General mathematical computation engine used by AVARIX."""

    name = "AVARIX Math Engine"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return _SYMPY_AVAILABLE

    def capabilities(self) -> Dict[str, bool]:
        return {
            "symbolic": _SYMPY_AVAILABLE,
            "numerical": _SYMPY_AVAILABLE,
            "numerical_roots": _SCIPY_AVAILABLE,
            "unit_conversion": True,
        }

    def solve(
        self,
        question: str,
        *,
        operation: Optional[str] = None,
        expression: Optional[str] = None,
        equations: Optional[Sequence[str]] = None,
        variable: Optional[str] = None,
        point: Optional[str] = None,
        initial_guess: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Solve a mathematical request and return a structured result.

        The LLM/router may call this with an explicit operation and expression.
        If those are omitted, a conservative local parser handles common
        natural-language forms.
        """
        if not _SYMPY_AVAILABLE:
            return self._error(
                "SymPy is not installed. Add the 'sympy' package to the "
                "AVARIX deployment requirements."
            )

        question = str(question or "").strip()

        try:
            parsed = self._build_problem(
                question,
                operation=operation,
                expression=expression,
                equations=equations,
                variable=variable,
                point=point,
                initial_guess=initial_guess,
            )

            if parsed.operation == "evaluate":
                return self.evaluate(parsed.expression or "")

            if parsed.operation == "solve_equation":
                return self.solve_equation(
                    parsed.expression or "",
                    variable=parsed.variable,
                )

            if parsed.operation == "solve_system":
                return self.solve_system(parsed.equations or [])

            if parsed.operation == "differentiate":
                return self.differentiate(
                    parsed.expression or "",
                    variable=parsed.variable,
                )

            if parsed.operation == "integrate":
                return self.integrate(
                    parsed.expression or "",
                    variable=parsed.variable,
                )

            if parsed.operation == "limit":
                return self.limit(
                    parsed.expression or "",
                    variable=parsed.variable,
                    point=parsed.point,
                )

            if parsed.operation == "numerical_solve":
                return self.numerical_solve(
                    parsed.expression or "",
                    variable=parsed.variable,
                    initial_guess=parsed.initial_guess,
                )

            if parsed.operation == "convert_unit":
                return self.convert_unit(question)

            raise MathEngineError(
                f"Unsupported mathematical operation: {parsed.operation}"
            )

        except MathEngineError as exc:
            return self._error(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            return self._error(
                f"The mathematical calculation could not be completed: {exc}"
            )

    def evaluate(self, expression: str) -> Dict[str, Any]:
        """Evaluate a numerical/symbolic expression."""
        expr_text = self._clean_expression(expression)
        expr = self._parse_expression(expr_text)

        if expr.free_symbols:
            return self._success(
                operation="evaluate",
                expression=expr_text,
                steps=[expr_text],
                result=str(expr),
                numeric_result=None,
                notes=[
                    "The expression contains unresolved variables, so it was "
                    "simplified rather than reduced to a single number."
                ],
            )

        exact = sp.simplify(expr)
        numeric = self._numeric_value(exact)

        return self._success(
            operation="evaluate",
            expression=expr_text,
            steps=[
                expr_text,
                f"= {self._format_expr(exact)}",
            ],
            result=self._format_expr(exact),
            numeric_result=numeric,
            notes=[],
        )

    def solve_equation(
        self,
        equation: str,
        *,
        variable: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Solve one algebraic/transcendental equation symbolically."""
        eq_text = self._clean_equation(equation)
        lhs_text, rhs_text = self._split_equation(eq_text)

        lhs = self._parse_expression(lhs_text)
        rhs = self._parse_expression(rhs_text)

        expr = sp.expand(lhs - rhs)
        symbols = sorted(expr.free_symbols, key=lambda s: s.name)

        symbol = self._choose_variable(symbols, variable)
        if symbol is None:
            if sp.simplify(expr) == 0:
                return self._success(
                    operation="solve_equation",
                    expression=eq_text,
                    steps=[eq_text, "Both sides are identical."],
                    result="All values satisfy the equation.",
                    numeric_result=None,
                    notes=[],
                )
            return self._error(
                "No variable was found in the equation."
            )

        solutions = sp.solve(expr, symbol)

        formatted = [self._format_expr(value) for value in solutions]

        lhs_display = self._format_expr(lhs)
        rhs_display = self._format_expr(rhs)

        first_step = f"{lhs_display} = {rhs_display}"
        second_step = f"{self._format_expr(expr)} = 0"

        steps = [first_step]

        # Only show the rearranged equation if it is actually different.
        if second_step != first_step:
            steps.append(second_step)

        steps.append(
            (
                f"{symbol} = {formatted[0]}"
                if len(formatted) == 1
                else f"{symbol} = " + ", ".join(formatted)
            )
        )

        numeric = {
            symbol.name: [
                self._numeric_value(value)
                for value in solutions
                if self._numeric_value(value) is not None
            ]
        }

        return self._success(
            operation="solve_equation",
            expression=eq_text,
            variable=symbol.name,
            steps=steps,
            result={
                symbol.name: formatted,
            },
            numeric_result=numeric,
            notes=[],
        )

    @staticmethod
    def _clean_equation_text(text: str) -> str:
        """
        Extract the mathematical equation from a natural-language request.

        Examples:
            x^2 + 2x + 4 = 0 what is the value of x
            -> x^2 + 2x + 4 = 0

            solve 2x + 5 = 17
            -> 2x + 5 = 17

            find x: x^2 - 5x + 6 = 0
            -> x^2 - 5x + 6 = 0
        """
        q = re.sub(r"\s+", " ", (text or "")).strip()

        if "=" not in q:
            return q

        equation = self._clean_equation_text(equation)

        # Keep only the first equation.
        left, right = q.split("=", 1)

        lhs = self._parse_expression(left)
        rhs = self._parse_expression(right)

        # Remove common natural-language suffixes from the RHS.
        right = re.split(
            r"\b(?:what|find|solve|calculate|compute|determine|"
            r"evaluate|give|tell)\b",
            right,
            maxsplit=1,
            flags=re.I,
        )[0].strip()

        # Remove trailing punctuation.
        right = right.rstrip(" .,;:?")

        equation = f"{left.strip()} = {right}"

        # Remove common leading instructions from the LHS.
        equation = re.sub(
            r"^(?:solve|find|calculate|compute|determine|evaluate)"
            r"(?:\s+(?:for|the))?\s*",
            "",
            equation,
            flags=re.I,
        )

        return equation.strip()

    def solve_system(
        self,
        equations: Sequence[str],
    ) -> Dict[str, Any]:
        """Solve a system of simultaneous equations."""
        if not equations:
            raise MathEngineError("At least two equations are required.")

        parsed_equations = []
        for text in equations:
            cleaned = self._clean_equation(text)
            lhs_text, rhs_text = self._split_equation(cleaned)
            lhs = self._parse_expression(lhs_text)
            rhs = self._parse_expression(rhs_text)
            parsed_equations.append(sp.Eq(lhs, rhs))

        symbols = sorted(
            set().union(
                *(eq.free_symbols for eq in parsed_equations)
            ),
            key=lambda s: s.name,
        )

        if not symbols:
            raise MathEngineError(
                "No variables were found in the supplied equations."
            )

        solutions = sp.solve(
            parsed_equations,
            symbols,
            dict=True,
        )

        if not solutions:
            result_text = "No solution found."
            result = {}
        else:
            result = {
                symbol.name: self._format_expr(solution.get(symbol))
                for symbol in symbols
                for solution in solutions[:1]
                if symbol in solution
            }
            result_text = result

        steps = [
            f"{i + 1}. {self._format_expr(eq.lhs)} = "
            f"{self._format_expr(eq.rhs)}"
            for i, eq in enumerate(parsed_equations)
        ]

        if solutions:
            steps.append(
                "Solution: "
                + ", ".join(
                    f"{symbol} = {self._format_expr(solutions[0][symbol])}"
                    for symbol in symbols
                    if symbol in solutions[0]
                )
            )

        return self._success(
            operation="solve_system",
            expression=[str(eq) for eq in equations],
            variables=[s.name for s in symbols],
            steps=steps,
            result=result,
            numeric_result={
                symbol.name: self._numeric_value(solutions[0][symbol])
                for symbol in symbols
                if solutions and symbol in solutions[0]
            },
            notes=[] if solutions else ["The system has no symbolic solution."],
        )

    def differentiate(
        self,
        expression: str,
        *,
        variable: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Differentiate an expression."""
        expr_text = self._clean_expression(expression)
        expr = self._parse_expression(expr_text)

        symbol = self._choose_variable(
            sorted(expr.free_symbols, key=lambda s: s.name),
            variable,
        )

        if symbol is None:
            raise MathEngineError(
                "No differentiation variable was found."
            )

        derivative = sp.simplify(sp.diff(expr, symbol))

        return self._success(
            operation="differentiate",
            expression=expr_text,
            variable=symbol.name,
            steps=[
                f"f({symbol}) = {self._format_expr(expr)}",
                f"d/d{symbol} [f({symbol})]",
                f"= {self._format_expr(derivative)}",
            ],
            result=self._format_expr(derivative),
            numeric_result=None,
            notes=[],
        )

    def integrate(
        self,
        expression: str,
        *,
        variable: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute an indefinite integral."""
        expr_text = self._clean_expression(expression)
        expr = self._parse_expression(expr_text)

        symbol = self._choose_variable(
            sorted(expr.free_symbols, key=lambda s: s.name),
            variable,
        )

        if symbol is None:
            raise MathEngineError(
                "No integration variable was found."
            )

        integral = sp.integrate(expr, symbol)

        return self._success(
            operation="integrate",
            expression=expr_text,
            variable=symbol.name,
            steps=[
                f"∫ {self._format_expr(expr)} d{symbol}",
                f"= {self._format_expr(integral)} + C",
            ],
            result=f"{self._format_expr(integral)} + C",
            numeric_result=None,
            notes=[],
        )

    def limit(
        self,
        expression: str,
        *,
        variable: Optional[str] = None,
        point: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute a symbolic limit."""
        if point is None:
            raise MathEngineError(
                "A limit requires the point being approached."
            )

        expr_text = self._clean_expression(expression)
        expr = self._parse_expression(expr_text)

        symbol = self._choose_variable(
            sorted(expr.free_symbols, key=lambda s: s.name),
            variable,
        )

        if symbol is None:
            raise MathEngineError(
                "No limit variable was found."
            )

        point_expr = self._parse_expression(str(point))
        result = sp.limit(expr, symbol, point_expr)

        return self._success(
            operation="limit",
            expression=expr_text,
            variable=symbol.name,
            point=self._format_expr(point_expr),
            steps=[
                f"lim({symbol} → {self._format_expr(point_expr)}) "
                f"{self._format_expr(expr)}",
                f"= {self._format_expr(result)}",
            ],
            result=self._format_expr(result),
            numeric_result=self._numeric_value(result),
            notes=[],
        )

    def numerical_solve(
        self,
        equation: str,
        *,
        variable: Optional[str] = None,
        initial_guess: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Numerically solve an equation.

        Uses SymPy nsolve first. A SciPy root solver is retained as an optional
        fallback for future extension.
        """
        eq_text = self._clean_equation(equation)
        lhs_text, rhs_text = self._split_equation(eq_text)

        lhs = self._parse_expression(lhs_text)
        rhs = self._parse_expression(rhs_text)
        expr = lhs - rhs

        symbol = self._choose_variable(
            sorted(expr.free_symbols, key=lambda s: s.name),
            variable,
        )

        if symbol is None:
            raise MathEngineError("No numerical-solve variable was found.")

        if initial_guess is None:
            initial_guess = 1.0

        try:
            root = sp.nsolve(expr, symbol, initial_guess)
        except Exception as exc:
            raise MathEngineError(
                f"Numerical solving failed near x = {initial_guess}: {exc}"
            ) from exc

        root_value = float(root)

        return self._success(
            operation="numerical_solve",
            expression=eq_text,
            variable=symbol.name,
            steps=[
                f"{self._format_expr(lhs)} = {self._format_expr(rhs)}",
                f"Numerical solve near {initial_guess}",
                f"{symbol} ≈ {root_value:.10g}",
            ],
            result={symbol.name: f"{root_value:.10g}"},
            numeric_result={symbol.name: root_value},
            notes=[
                "The numerical result depends on the supplied initial guess."
            ],
        )

    def convert_unit(self, question: str) -> Dict[str, Any]:
        """Perform a small, deterministic set of unit conversions."""
        pattern = re.compile(
            r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*"
            r"(?P<from>[a-zA-Z/]+)\s*(?:to|in)\s*"
            r"(?P<to>[a-zA-Z/]+)",
            re.IGNORECASE,
        )

        match = pattern.search(question or "")
        if not match:
            raise MathEngineError(
                "Use a conversion such as '250 km/h to m/s'."
            )

        value = float(match.group("value"))
        from_unit = self._normalize_unit(match.group("from"))
        to_unit = self._normalize_unit(match.group("to"))

        if from_unit == to_unit:
            converted = value
        else:
            factor = _UNIT_FACTORS.get((from_unit, to_unit))
            if factor is None:
                raise MathEngineError(
                    f"I do not support conversion from {from_unit} to {to_unit}."
                )
            converted = value * factor

        return self._success(
            operation="convert_unit",
            expression=question,
            steps=[
                f"{value:g} {from_unit}",
                f"= {converted:.10g} {to_unit}",
            ],
            result=f"{converted:.10g} {to_unit}",
            numeric_result=converted,
            notes=[],
        )

    @staticmethod
    def _normalize_unicode_math(text: str) -> str:
        """
        Convert common Unicode mathematical notation into
        SymPy-compatible notation.

        Examples:
            x²       -> x^2
            x³       -> x^3
            x⁴       -> x^4
            x⁻¹      -> x^-1
            √(x)     -> sqrt(x)
            √x       -> sqrt(x)
            π        -> pi
            ×        -> *
            ÷        -> /
        """

        if not text:
            return ""

        text = str(text)

        # ------------------------------------------------------------
        # Unicode superscripts
        # ------------------------------------------------------------

        superscript_map = str.maketrans({
            "⁰": "0",
            "¹": "1",
            "²": "2",
            "³": "3",
            "⁴": "4",
            "⁵": "5",
            "⁶": "6",
            "⁷": "7",
            "⁸": "8",
            "⁹": "9",
            "⁺": "+",
            "⁻": "-",
            "⁽": "(",
            "⁾": ")",
        })

        # x² -> x^2
        text = re.sub(
            r"([A-Za-z0-9_)])([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾]+)",
            lambda m: (
                m.group(1)
                + "^"
                + m.group(2).translate(superscript_map)
            ),
            text,
        )

        # ------------------------------------------------------------
        # Unicode mathematical operators
        # ------------------------------------------------------------

        text = text.replace("×", "*")
        text = text.replace("÷", "/")
        text = text.replace("−", "-")
        text = text.replace("–", "-")
        text = text.replace("—", "-")

        # ------------------------------------------------------------
        # Greek symbols commonly used in mathematics
        # ------------------------------------------------------------

        text = text.replace("π", "pi")
        text = text.replace("Π", "pi")

        # ------------------------------------------------------------
        # Square root
        # ------------------------------------------------------------

        # √(x) -> sqrt(x)
        text = re.sub(
            r"√\s*\(([^()]*)\)",
            r"sqrt(\1)",
            text,
        )

        # √x -> sqrt(x)
        text = re.sub(
            r"√\s*([A-Za-z0-9.]+)",
            r"sqrt(\1)",
            text,
        )

        return text

    # ------------------------------------------------------------------
    # Parsing / routing
    # ------------------------------------------------------------------

    def _build_problem(
        self,
        question: str,
        *,
        operation: Optional[str],
        expression: Optional[str],
        equations: Optional[Sequence[str]],
        variable: Optional[str],
        point: Optional[str],
        initial_guess: Optional[float],
    ) -> ParsedProblem:
        if operation:
            op = self._normalize_operation(operation)
            return ParsedProblem(
                operation=op,
                expression=expression,
                equations=list(equations or []),
                variable=variable,
                point=point,
                initial_guess=initial_guess,
            )

        q = re.sub(r"\s+", " ", question).strip()
        q_lower = q.lower()

        # Unit conversion gets its own route before generic arithmetic.
        # Support both explicit wording ("convert 250 km/h to m/s") and the
        # compact calculator style ("250 km/h to m/s").
        if (
            re.search(r"\b(?:convert|conversion)\b", q_lower)
            or re.search(
                r"[-+]?\d+(?:\.\d+)?\s*[a-zA-Z/]+\s+"
                r"(?:to|in)\s+[a-zA-Z/]+\b",
                q,
                re.IGNORECASE,
            )
        ):
            return ParsedProblem(operation="convert_unit")

        # Natural-language calculus.
        derivative = re.match(
            r"^(?:differentiate|derivative of|find the derivative of)\s+(.+?)"
            r"(?:\s+with respect to\s+([a-zA-Z][a-zA-Z0-9_]*))?$",
            q,
            re.IGNORECASE,
        )
        if derivative:
            return ParsedProblem(
                operation="differentiate",
                expression=derivative.group(1),
                variable=derivative.group(2),
            )

        integral = re.match(
            r"^(?:integrate|integral of)\s+(.+?)"
            r"(?:\s+with respect to\s+([a-zA-Z][a-zA-Z0-9_]*))?$",
            q,
            re.IGNORECASE,
        )
        if integral:
            return ParsedProblem(
                operation="integrate",
                expression=integral.group(1),
                variable=integral.group(2),
            )

        limit = re.match(
            r"^(?:limit of)\s+(.+?)\s+as\s+([a-zA-Z][a-zA-Z0-9_]*)"
            r"\s*(?:approaches|->|→)\s*([^\s]+)$",
            q,
            re.IGNORECASE,
        )
        if limit:
            return ParsedProblem(
                operation="limit",
                expression=limit.group(1),
                variable=limit.group(2),
                point=limit.group(3),
            )

        numerical = re.match(
            r"^(?:numerically solve|find a numerical solution to|"
            r"solve numerically)\s+(.+?)"
            r"(?:\s+near\s+([-+]?\d+(?:\.\d+)?))?$",
            q,
            re.IGNORECASE,
        )
        if numerical:
            guess = (
                float(numerical.group(2))
                if numerical.group(2) is not None
                else None
            )
            return ParsedProblem(
                operation="numerical_solve",
                expression=numerical.group(1),
                initial_guess=guess,
            )

        # Explicit "solve ..." requests.
        solve_match = re.match(
            r"^(?:solve|find)\s+(.+)$",
            q,
            re.IGNORECASE,
        )
        if solve_match:
            body = solve_match.group(1).strip()

            # Two or more equality relations separated by comma/semicolon
            # are treated as a system.
            parts = [
                p.strip()
                for p in re.split(r"\s*(?:,|;)\s*", body)
                if p.strip()
            ]
            if len(parts) >= 2 and all("=" in p for p in parts):
                return ParsedProblem(
                    operation="solve_system",
                    equations=parts,
                )

            if "=" in body:
                return ParsedProblem(
                    operation="solve_equation",
                    expression=body,
                )

            # "solve x^2 - 4" is interpreted as solve expression = 0.
            return ParsedProblem(
                operation="solve_equation",
                expression=f"{body} = 0",
            )

        # Plain equation.
        if "=" in q:
            parts = [
                p.strip()
                for p in re.split(r"\s*(?:,|;)\s*", q)
                if p.strip()
            ]
            if len(parts) >= 2 and all("=" in p for p in parts):
                return ParsedProblem(
                    operation="solve_system",
                    equations=parts,
                )
            return ParsedProblem(
                operation="solve_equation",
                expression=q,
            )

        # Common arithmetic phrasing.
        arithmetic = q
        arithmetic = re.sub(
            r"^(?:calculate|compute|evaluate|what is|what's|find)\s+",
            "",
            arithmetic,
            flags=re.IGNORECASE,
        )
        arithmetic = arithmetic.rstrip(" ?.")
        arithmetic = self._translate_arithmetic_words(arithmetic)

        return ParsedProblem(
            operation="evaluate",
            expression=arithmetic,
        )

    @staticmethod
    def _normalize_operation(operation: str) -> str:
        op = re.sub(r"[\s-]+", "_", operation.strip().lower())
        aliases = {
            "calculate": "evaluate",
            "calculation": "evaluate",
            "eval": "evaluate",
            "differentiate": "differentiate",
            "derivative": "differentiate",
            "integral": "integrate",
            "integration": "integrate",
            "solve": "solve_equation",
            "equation": "solve_equation",
            "system": "solve_system",
            "numerical": "numerical_solve",
            "root": "numerical_solve",
            "roots": "numerical_solve",
            "convert": "convert_unit",
            "unit_conversion": "convert_unit",
        }
        return aliases.get(op, op)

    # ------------------------------------------------------------------
    # Safe expression handling
    # ------------------------------------------------------------------

    def _parse_expression(self, expression: str):
        cleaned = self._clean_expression(expression)

        if not cleaned:
            raise MathEngineError("No mathematical expression was supplied.")

        # Reject Python/object-access syntax before SymPy sees the string.
        if any(token in cleaned for token in ("__", "[", "]", "{", "}", ";")):
            raise MathEngineError("Unsupported expression syntax.")

        # Only mathematical characters/names are accepted.
        if not re.fullmatch(
            r"[0-9A-Za-z_+\-*/^().,=\s%]*",
            cleaned,
        ):
            raise MathEngineError(
                "The expression contains unsupported characters."
            )

        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", cleaned))

        unknown_names = []
        for name in names:
            lower = name.lower()
            if (
                lower not in _ALLOWED_FUNCTIONS
                and lower not in _ALLOWED_CONSTANTS
                and lower not in _ALLOWED_SYMBOLS
            ):
                unknown_names.append(name)

        if unknown_names:
            raise MathEngineError(
                "Unsupported mathematical name(s): "
                + ", ".join(sorted(unknown_names))
            )

        local_dict = {}
        for name, sympy_name in _ALLOWED_FUNCTIONS.items():
            local_dict[name] = getattr(sp, sympy_name)

        for name, sympy_name in _ALLOWED_CONSTANTS.items():
            local_dict[name] = getattr(sp, sympy_name)

        for name in _ALLOWED_SYMBOLS:
            local_dict[name] = sp.Symbol(name)

        try:
            return parse_expr(
                cleaned,
                local_dict=local_dict,
                transformations=_TRANSFORMATIONS,
                evaluate=True,
            )
        except Exception as exc:
            raise MathEngineError(
                f"Could not parse the mathematical expression '{cleaned}'."
            ) from exc

    @staticmethod
    def _clean_expression(expression: str) -> str:
        """
        Normalize human mathematical notation into SymPy-compatible syntax.

        This is the input boundary of MathEngine. User-friendly notation such
        as x², √x, × and ÷ is converted here before validation/parsing.

        Examples
        --------
        x² + 4x + 4       -> x^2 + 4x + 4
        x³                 -> x^3
        √25                -> sqrt(25)
        √(x + 1)           -> sqrt(x + 1)
        2 × x              -> 2 * x
        10 ÷ 2             -> 10 / 2
        """

        # Always start with a real string.
        text = str(expression or "").strip()

        if not text:
            return ""

        # ------------------------------------------------------------
        # Unicode operators
        # ------------------------------------------------------------

        text = text.replace("−", "-")
        text = text.replace("–", "-")
        text = text.replace("—", "-")
        text = text.replace("×", "*")
        text = text.replace("÷", "/")

        # ------------------------------------------------------------
        # Greek constants
        # ------------------------------------------------------------

        text = text.replace("π", "pi")
        text = text.replace("Π", "pi")

        # ------------------------------------------------------------
        # Unicode superscripts
        #
        # x²  -> x^2
        # x³  -> x^3
        # x⁴  -> x^4
        # x⁻² -> x^-2
        # ------------------------------------------------------------

        superscripts = {
            "⁰": "0",
            "¹": "1",
            "²": "2",
            "³": "3",
            "⁴": "4",
            "⁵": "5",
            "⁶": "6",
            "⁷": "7",
            "⁸": "8",
            "⁹": "9",
            "⁺": "+",
            "⁻": "-",
            "⁽": "(",
            "⁾": ")",
        }

        superscript_chars = "".join(
            re.escape(char)
            for char in superscripts
        )

        # Convert a superscript sequence attached to a base:
        #
        # x²      -> x^2
        # x¹²     -> x^12
        # (x+1)²  -> (x+1)^2
        #
        text = re.sub(
            rf"([A-Za-z0-9_)])([{superscript_chars}]+)",
            lambda match: (
                match.group(1)
                + "^"
                + "".join(
                    superscripts.get(char, char)
                    for char in match.group(2)
                )
            ),
            text,
        )

        # ------------------------------------------------------------
        # Square root
        # ------------------------------------------------------------

        # √(x + 1) -> sqrt(x + 1)
        text = re.sub(
            r"√\s*\(([^()]*)\)",
            r"sqrt(\1)",
            text,
        )

        # √x -> sqrt(x)
        # √25 -> sqrt(25)
        text = re.sub(
            r"√\s*([A-Za-z0-9_.]+)",
            r"sqrt(\1)",
            text,
        )

        # ------------------------------------------------------------
        # Whitespace
        # ------------------------------------------------------------

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return text

    @staticmethod
    def _clean_equation(equation: str) -> str:
        """
        Clean and extract an equation from natural-language input.

        Examples
        --------
        x^2 + 2x + 4 = 0
            -> x^2 + 2x + 4 = 0

        x^2 + 2x + 4 = 0 what is the value of x
            -> x^2 + 2x + 4 = 0

        solve x^2 - 5x + 6 = 0
            -> x^2 - 5x + 6 = 0

        find x: x^2 - 5x + 6 = 0
            -> x^2 - 5x + 6 = 0
        """

        text = MathEngine._clean_expression(equation)

        # Normalize equality.
        text = text.replace("==", "=")

        # ------------------------------------------------------------
        # Remove common leading instructions
        # ------------------------------------------------------------

        text = re.sub(
            r"^\s*(?:please\s+)?"
            r"(?:solve|find|calculate|compute|determine|evaluate)"
            r"(?:\s+(?:for|the\s+value\s+of|the\s+value\s+for))?"
            r"\s*[:\-]?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # ------------------------------------------------------------
        # If an equation exists, keep only the mathematical portion.
        # ------------------------------------------------------------

        if "=" in text:
            left, right = text.split("=", 1)

            # Remove natural-language text after the RHS.
            #
            # Examples:
            #   = 0 what is the value of x
            #   = 17 find x
            #   = 5 solve for x
            #   = 10 calculate the value
            right = re.split(
                r"\b(?:what\s+is|what's|find|solve|calculate|"
                r"compute|determine|evaluate|give|tell)\b",
                right,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]

            left = left.strip()
            right = right.strip()

            # Remove trailing punctuation.
            right = right.rstrip(" .,;:?")

            text = f"{left} = {right}"

        return text.strip()

    @staticmethod
    def _split_equation(equation: str) -> Tuple[str, str]:
        if equation.count("=") != 1:
            raise MathEngineError(
                "An equation must contain exactly one '='."
            )
        lhs, rhs = equation.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()

        if not lhs or not rhs:
            raise MathEngineError("Both sides of the equation are required.")

        return lhs, rhs

    @staticmethod
    def _choose_variable(
        symbols: Sequence[Any],
        variable: Optional[str],
    ):
        if variable:
            requested = variable.strip()
            for symbol in symbols:
                if symbol.name == requested:
                    return symbol
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", requested):
                return sp.Symbol(requested)
            raise MathEngineError(
                f"Invalid mathematical variable: {requested}"
            )

        if not symbols:
            return None

        # Prefer x for ordinary algebra when present.
        for preferred in ("x", "y", "z", "t"):
            for symbol in symbols:
                if symbol.name == preferred:
                    return symbol

        return symbols[0]

    @staticmethod
    def _normalize_unit(unit: str) -> str:
        """Normalize common unit spellings to the internal conversion keys."""
        value = re.sub(r"\s+", "", str(unit or "").strip().lower())

        aliases = {
            "meter": "m",
            "meters": "m",
            "metre": "m",
            "metres": "m",
            "centimeter": "cm",
            "centimeters": "cm",
            "centimetre": "cm",
            "centimetres": "cm",
            "millimeter": "mm",
            "millimeters": "mm",
            "millimetre": "mm",
            "millimetres": "mm",
            "kilometer": "km",
            "kilometers": "km",
            "kilometre": "km",
            "kilometres": "km",
            "feet": "ft",
            "foot": "ft",
            "inch": "in",
            "inches": "in",
            "kmph": "km/h",
            "kph": "km/h",
            "mps": "m/s",
            "mph": "mph",
            "knot": "kn",
            "knots": "kn",
            "degree": "deg",
            "degrees": "deg",
            "radian": "rad",
            "radians": "rad",
        }

        return aliases.get(value, value)

    @staticmethod
    def _translate_arithmetic_words(text: str) -> str:
        replacements = [
            (r"\bplus\b", "+"),
            (r"\bminus\b", "-"),
            (r"\bmultiplied\s+by\b", "*"),
            (r"\btimes\b", "*"),
            (r"\bdivided\s+by\b", "/"),
            (r"\bover\b", "/"),
            (r"\bto\s+the\s+power\s+of\b", "^"),
            (r"\bsquared\b", "^2"),
            (r"\bcubed\b", "^3"),
        ]

        result = text
        for pattern, replacement in replacements:
            result = re.sub(pattern, f" {replacement} ", result, flags=re.I)

        # Basic spoken-number forms are intentionally not attempted here.
        return re.sub(r"\s+", " ", result).strip()

    # ------------------------------------------------------------------
    # Formatting / result helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _numeric_value(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            if getattr(value, "is_real", None) is False:
                return None
            return float(sp.N(value))
        except Exception:
            return None

    @staticmethod
    def _format_expr(value: Any) -> str:
        """
        Convert SymPy expressions into readable mathematical notation.
        """
        try:
            expr = sp.simplify(value)

            # SymPy's Unicode-friendly LaTeX-style representation would be
            # ideal, but AVARIX currently renders plain text, so perform a
            # controlled conversion here.
            text = str(expr)

            # Imaginary unit
            text = re.sub(
                r"\bI\b",
                "i",
                text,
            )

            # Square roots
            text = re.sub(
                r"\bsqrt\(([^()]*)\)",
                r"√(\1)",
                text,
            )

            # Multiplication with i / sqrt
            text = re.sub(
                r"√\(([^()]*)\)\s*\*\s*i",
                r"i√(\1)",
                text,
            )

            text = re.sub(
                r"\bi\s*\*\s*√\(([^()]*)\)",
                r"i√(\1)",
                text,
            )

            # --------------------------------------------------------
            # Integer powers
            # --------------------------------------------------------

            superscript_map = str.maketrans(
                "0123456789+-",
                "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻",
            )

            def replace_power(match):
                base = match.group(1)
                exponent = match.group(2)

                if exponent.isdigit():
                    return (
                        base
                        + exponent.translate(superscript_map)
                    )

                return (
                    base
                    + "^("
                    + exponent
                    + ")"
                )

            text = re.sub(
                r"([A-Za-z0-9_)]+)\*\*(\d+)",
                replace_power,
                text,
            )

            # --------------------------------------------------------
            # Multiplication
            # --------------------------------------------------------

            text = text.replace("*", "·")

            # Remove multiplication dot where normal mathematical
            # implicit multiplication is clearer.
            text = re.sub(
                r"([0-9A-Za-z)])·([A-Za-z(])",
                r"\1\2",
                text,
            )

            return text

        except Exception:
            return str(value)

    @staticmethod
    def _success(
        *,
        operation: str,
        expression: Any,
        steps: List[str],
        result: Any,
        numeric_result: Any,
        notes: List[str],
        **extra: Any,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "engine": "math",
            "operation": operation,
            "expression": expression,
            "steps": steps,
            "result": result,
            "numeric_result": numeric_result,
            "notes": notes,
            **extra,
        }

    @staticmethod
    def _error(message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "engine": "math",
            "operation": None,
            "expression": None,
            "steps": [],
            "result": None,
            "numeric_result": None,
            "notes": [],
            "error": message,
        }


__all__ = [
    "MathEngine",
    "MathEngineError",
]
