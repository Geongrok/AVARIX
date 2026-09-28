"""Bridge between Intellex and the AeroCalc aerospace calculation engine.

AeroCalc's 57 calculators are pure Python functions (the Flask layer is only a
thin JSON wrapper), so this module imports ``aerocalc.core`` directly into the
Intellex FastAPI process - no second server, no HTTP round-trip.

Responsibilities:

  * Match a user question to the best calculator (keyword/tag scoring plus a
    curated alias list for common phrasings).
  * Extract numeric inputs and choice/toggle values from the question text.
  * Run the calculation through AeroCalc's own validation and compute path, so
    every number shown to the user is produced by exactly the same code that
    the standalone AeroCalc app uses.
  * Produce a compact text summary of the headline results for the LLM, plus
    the full structured result for the frontend to render.

If AeroCalc is not importable (missing numpy/scipy/matplotlib, or the package
was moved), the bridge stays alive but reports ``available=False`` and the rest
of Intellex degrades gracefully to its normal database+web behaviour.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AEROCALC_PKG = os.path.join(_PROJECT_ROOT, "aerocalc")

try:
    if _AEROCALC_PKG not in os.sys.path:
        os.sys.path.insert(0, _AEROCALC_PKG)
    from aerocalc import core as _ac_core      # noqa: E402
    from aerocalc.modules import load_all      # noqa: E402

    load_all()
    _AVAILABLE = True
    _IMPORT_ERROR = None
except Exception as _exc:  # pragma: no cover - environment-specific
    _AVAILABLE = False
    _IMPORT_ERROR = _exc


# ---------------------------------------------------------------------------
# Curated aliases: concept phrases -> calculator id.
# ---------------------------------------------------------------------------

ALIASES: Dict[str, str] = {
    "speed of sound": "standard-atmosphere",
    "standard atmosphere": "standard-atmosphere",
    "atmosphere": "standard-atmosphere",
    "isa": "standard-atmosphere",
    "density of air": "standard-atmosphere",
    "air density": "standard-atmosphere",
    "air pressure": "standard-atmosphere",
    "pressure at altitude": "standard-atmosphere",
    "temperature at altitude": "standard-atmosphere",
    "airspeed": "airspeed-conversion",
    "true airspeed": "airspeed-conversion",
    "equivalent airspeed": "airspeed-conversion",
    "calibrated airspeed": "airspeed-conversion",
    "tas": "airspeed-conversion",
    "eas": "airspeed-conversion",
    "cas": "airspeed-conversion",
    "isentropic": "isentropic-flow",
    "isentropic flow": "isentropic-flow",
    "stagnation pressure": "isentropic-flow",
    "stagnation temperature": "isentropic-flow",
    "mach number": "isentropic-flow",
    "prandtl-meyer": "prandtl-meyer",
    "prandtl meyer": "prandtl-meyer",
    "expansion fan": "prandtl-meyer",
    "normal shock": "normal-shock",
    "shock wave": "normal-shock",
    "oblique shock": "oblique-shock",
    "theta-beta-m": "oblique-shock",
    "theta beta mach": "oblique-shock",
    "fanno": "fanno-flow",
    "fanno flow": "fanno-flow",
    "rayleigh": "rayleigh-flow",
    "rayleigh flow": "rayleigh-flow",
    "heat addition": "rayleigh-flow",
    "converging-diverging": "cd-nozzle",
    "converging diverging": "cd-nozzle",
    "nozzle": "cd-nozzle",
    "shock tube": "shock-tube",
    "gas tables": "gas-tables",
    "gas table": "gas-tables",
    "isentropic table": "gas-tables",
    "shock table": "gas-tables",
    "fanno table": "gas-tables",
    "rayleigh table": "gas-tables",
    "pipe flow": "pipe-flow",
    "pipe": "pipe-flow",
    "head loss": "pipe-flow",
    "darcy": "pipe-flow",
    "colebrook": "pipe-flow",
    "moody": "pipe-flow",
    "friction factor": "pipe-flow",
    "venturi": "flow-meter",
    "orifice": "flow-meter",
    "flow meter": "flow-meter",
    "flowmeter": "flow-meter",
    "pitot": "pitot-static",
    "pitot static": "pitot-static",
    "pitot-static": "pitot-static",
    "impact pressure": "pitot-static",
    "reynolds number": "reynolds-similarity",
    "reynolds": "reynolds-similarity",
    "knudsen": "reynolds-similarity",
    "wind tunnel": "reynolds-similarity",
    "dimensionless numbers": "dimensionless-numbers",
    "dimensionless": "dimensionless-numbers",
    "naca": "thin-airfoil",
    "airfoil": "thin-airfoil",
    "thin airfoil": "thin-airfoil",
    "lifting line": "lifting-line",
    "finite wing": "lifting-line",
    "induced drag": "lifting-line",
    "drag polar": "drag-polar",
    "lift to drag": "drag-polar",
    "l/d": "drag-polar",
    "boundary layer": "boundary-layer",
    "flat plate": "boundary-layer",
    "blasius": "boundary-layer",
    "compressibility correction": "compressibility-correction",
    "critical mach": "compressibility-correction",
    "prandtl glauert": "compressibility-correction",
    "karman tsien": "compressibility-correction",
    "orbital elements": "orbital-elements",
    "orbit": "orbital-elements",
    "orbital period": "orbital-elements",
    "satellite": "orbital-elements",
    "geostationary": "orbital-elements",
    "geosynchronous": "orbital-elements",
    "orbit transfer": "orbit-transfer",
    "hohmann": "orbit-transfer",
    "delta-v": "orbit-transfer",
    "delta v": "orbit-transfer",
    "plane change": "orbit-transfer",
    "kepler": "kepler-propagation",
    "kepler equation": "kepler-propagation",
    "true anomaly": "kepler-propagation",
    "rocket equation": "rocket-equation",
    "rocket": "rocket-equation",
    "tsiolkovsky": "rocket-equation",
    "staging": "rocket-equation",
    "ground track": "groundtrack-coverage",
    "groundtrack": "groundtrack-coverage",
    "swath": "groundtrack-coverage",
    "sun-synchronous": "groundtrack-coverage",
    "sun synchronous": "groundtrack-coverage",
    "escape velocity": "escape-hyperbolic",
    "escape": "escape-hyperbolic",
    "hyperbolic excess": "escape-hyperbolic",
    "gravity assist": "escape-hyperbolic",
    "oberth": "escape-hyperbolic",
    "c3": "escape-hyperbolic",
    "stagnation": "isentropic-flow",
    # Additional topics and calculators in the updated AeroCalc package.
    "couette-poiseuille": "couette-poiseuille",
    "couette poiseuille": "couette-poiseuille",
    "couette flow": "couette-poiseuille",
    "poiseuille flow": "couette-poiseuille",
    "channel flow": "couette-poiseuille",
    "polytropic process": "polytropic-process",
    "ideal gas process": "polytropic-process",
    "brayton cycle": "brayton-cycle",
    "otto cycle": "piston-cycles",
    "diesel cycle": "piston-cycles",
    "dual cycle": "piston-cycles",
    "piston cycle": "piston-cycles",
    "heat transfer": "heat-transfer",
    "conduction": "heat-transfer",
    "convection": "heat-transfer",
    "heat exchanger": "heat-exchanger",
    "effectiveness ntu": "heat-exchanger",
    "turbofan": "turbofan-cycle",
    "turbojet": "turbofan-cycle",
    "ramjet": "ramjet",
    "rocket nozzle": "rocket-nozzle",
    "propeller": "propeller-momentum",
    "rotor momentum": "propeller-momentum",
    "level flight": "level-flight",
    "range endurance": "range-endurance",
    "climb performance": "climb-performance",
    "rate of climb": "climb-performance",
    "turn performance": "turn-performance",
    "v-n diagram": "turn-performance",
    "takeoff": "takeoff-landing",
    "take-off": "takeoff-landing",
    "landing distance": "takeoff-landing",
    "static stability": "static-stability",
    "beam bending": "beam-bending",
    "column buckling": "column-buckling",
    "pressure vessel": "pressure-vessel",
    "stress transformation": "stress-transformation",
    "mohr circle": "stress-transformation",
    "torsion": "torsion",
    "laminate": "laminate-clt",
    "classical lamination": "laminate-clt",
    "micromechanics": "micromechanics",
    "fatigue": "fatigue-fracture",
    "fracture": "fatigue-fracture",
    "link budget": "link-budget",
    "radar range": "radar-range",
    "antenna gain": "antenna",
    "noise figure": "noise-cascade",
    "noise cascade": "noise-cascade",
    "control response": "control-response",
    "filter design": "filter-design",
    "scientific calculator": "scientific-calculator",
}

# Choice-mode inference: for calculators whose behaviour switches on a
# "mode"/"known"/"spec"/"kind" field, map question phrases to the choice value.
_MODE_HINTS: Dict[str, Dict[str, str]] = {
    "isentropic-flow": {
        "mach": "M", "pressure ratio": "p0p", "temperature ratio": "t0t",
        "density ratio": "r0r", "area ratio": "ar_sup", "area": "ar_sup",
        "mach angle": "mu", "prandtl": "nu", "meyer": "nu",
    },
    "normal-shock": {
        "mach": "M1", "pressure ratio": "p2p1", "total pressure": "p02p01",
        "pitot": "pitot",
    },
    "standard-atmosphere": {
        "pressure": "pressure", "altitude": "altitude", "density": "altitude",
    },
    "airspeed-conversion": {
        "mach": "mach", "true airspeed": "tas", "tas": "tas",
        "equivalent airspeed": "eas", "eas": "eas",
        "calibrated airspeed": "cas", "cas": "cas",
    },
    "orbital-elements": {
        "altitude": "alt", "altitudes": "alt", "perigee": "alt", "apogee": "alt",
        "semi-major": "ae", "eccentricity": "ae", "period": "period",
        "radius": "radii", "radii": "radii",
    },
    "orbit-transfer": {"altitude": "alt", "radius": "r"},
    "kepler-propagation": {"time": "time", "anomaly": "nu", "true anomaly": "nu"},
    "escape-hyperbolic": {
        "c3": "c3", "energy": "c3", "excess velocity": "vinf", "velocity": "vinf",
    },
    "oblique-shock": {
        "deflection": "theta", "theta": "theta", "wave": "beta", "beta": "beta",
    },
    "fanno-flow": {"mach": "M", "friction parameter": "fld", "4fld": "fld"},
    "rayleigh-flow": {"mach": "M", "total temperature": "t0", "temperature ratio": "t0"},
    "pipe-flow": {"flow rate": "Q", "flowrate": "Q", "velocity": "V"},
    "gas-tables": {
        "isentropic": "isentropic", "shock": "shock", "fanno": "fanno",
        "rayleigh": "rayleigh", "prandtl": "pm",
    },
}

_BODY_HINTS = ["earth", "moon", "mars", "venus", "jupiter", "sun"]


# ---------------------------------------------------------------------------
# Number/unit extraction
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*"
    r"((?:kg/m3|kg/m\u00b3|m3/s|m\u00b3/s|km/h|kmph|ft/s|m/s|kpa|hpa|mbar|psi|"
    r"atm|knots|knot|\u00b0\s?c|deg\s?c|\u00b0\s?f|deg\s?f|kelvin|"
    r"kilometers|kilometres|meters|metres|km|feet|ft|cm|mm|"
    r"m\u00b2|m2|km\u00b2|km2|cm\u00b2|"
    r"minutes|mins|min|seconds|secs|sec|hours|hrs|hr|days|day|"
    r"tonnes|tonne|tons|ton|kilograms|kg|grams|g|lbs|lb|"
    r"moles|mol|mmol|percent|percentage|%|"
    r"\u00b0|deg|degrees|radians|rad|"
    r"mhz|ghz|khz|hz|mj|kj|kcal|cal|mw|kw|w|kn|n|lbf|"
    r"m|s|h|d|k|pa|kt|j)?)"
    r"(?=\s|$|[;.,!?()])",
    re.IGNORECASE,
)

_UNIT_TO_SI = {
    "kpa": 1e3, "hpa": 1e2, "mbar": 1e2, "bar": 1e5, "psi": 6894.757,
    "atm": 101325.0,
    "km": 1e3, "kilometers": 1e3, "kilometres": 1e3,
    "kmph": 1.0 / 3.6, "km/h": 1.0 / 3.6,
    "m": 1.0, "meters": 1.0, "metres": 1.0,
    "ft": 0.3048, "feet": 0.3048, "cm": 0.01, "mm": 1e-3,
    "kt": 0.514444444, "knots": 0.514444444, "knot": 0.514444444,
    "mph": 0.44704, "ft/s": 0.3048,
    "sec": 1.0, "secs": 1.0, "second": 1.0, "seconds": 1.0, "s": 1.0,
    "min": 60.0, "mins": 60.0, "minute": 60.0, "minutes": 60.0,
    "hr": 3600.0, "hrs": 3600.0, "hour": 3600.0, "hours": 3600.0, "h": 3600.0,
    "day": 86400.0, "days": 86400.0, "d": 86400.0,
    "kg": 1.0, "kilograms": 1.0, "g": 1e-3, "grams": 1e-3,
    "tonne": 1000.0, "tonnes": 1000.0, "ton": 1000.0, "tons": 1000.0,
    "lb": 0.45359237, "lbs": 0.45359237,
    "kj": 1e3, "mj": 1e6, "kcal": 4184.0, "cal": 4.184,
    "kw": 1e3, "mw": 1e6, "hp": 745.7,
    "khz": 1e3, "mhz": 1e6, "ghz": 1e9,
    "kn": 1e3, "lbf": 4.448222,
}


class _NumToken:
    __slots__ = ("value", "unit", "raw")

    def __init__(self, value: float, unit: Optional[str], raw: str):
        self.value = value
        self.unit = unit
        self.raw = raw


def _tokenize_numbers(question: str) -> List[_NumToken]:
    tokens = []
    for match in _NUMBER_RE.finditer(question):
        num_str = match.group(1).replace(",", ".")
        try:
            value = float(num_str)
        except ValueError:
            continue
        unit = (match.group(2) or "").strip().lower()
        tokens.append(_NumToken(value, unit or None, match.group(0).strip()))
    return tokens


def _field_family(field: dict) -> Optional[str]:
    label = field.get("label", "").lower()
    unit = (field.get("unit") or "").lower()

    if "pressure" in label or unit in ("pa", "kpa", "hpa", "bar", "mbar", "psi", "atm"):
        return "pressure"
    if "temperature" in label or unit in ("k", "\u00b0c", "\u00b0f", "deg c", "deg f"):
        return "temperature"
    if any(w in label for w in ("angle", "deflection", "turn", "inclination",
                                "anomaly", "latitude", "elevation")):
        return "angle"
    if "mach" in label or unit == "mach":
        return "mach"
    if any(w in label for w in ("altitude", "height", "span", "radius", "diameter",
                                "length", "chord", "thickness")):
        return "length"
    if any(w in label for w in ("velocity", "airspeed", "speed")):
        return "velocity"
    if "density" in label or unit in ("kg/m\u00b3", "kg/m3"):
        return "density"
    if any(w in label for w in ("mass",)) or unit in ("kg", "grams", "g", "tonnes", "lb"):
        return "mass"
    if "flow rate" in label or unit in ("m\u00b3/s", "m3/s", "l/s", "gpm"):
        return "flow"
    if "area" in label or unit in ("m\u00b2", "m2", "km\u00b2", "km2", "cm\u00b2"):
        return "area"
    if any(w in label for w in ("time", "period", "duration")):
        return "time"
    if any(w in label for w in ("heat", "energy")) or unit in ("j", "kj", "mj", "cal", "kcal"):
        return "energy"
    if any(w in label for w in ("force", "thrust", "drag", "lift", "weight")):
        return "force"
    if "power" in label or unit in ("w", "kw", "mw", "hp"):
        return "power"
    if unit in ("hz", "khz", "mhz", "ghz"):
        return "frequency"
    return None


def _family_of_unit(unit: str) -> Optional[str]:
    if unit in ("pa", "kpa", "hpa", "mbar", "psi", "atm", "bar"):
        return "pressure"
    if unit in ("k", "kelvin", "\u00b0c", "deg c", "\u00b0f", "deg f"):
        return "temperature"
    if unit in ("\u00b0", "deg", "degrees", "rad", "radians"):
        return "angle"
    if unit in ("m", "meters", "metres", "km", "ft", "feet", "cm", "mm"):
        return "length"
    if unit in ("m/s", "km/h", "kmph", "kt", "knots", "knot", "mph", "ft/s"):
        return "velocity"
    if unit in ("kg/m\u00b3", "kg/m3"):
        return "density"
    if unit in ("kg", "kilograms", "g", "grams", "tonne", "tonnes", "ton", "tons", "lb", "lbs"):
        return "mass"
    if unit in ("m\u00b3/s", "m3/s", "l/s", "gpm"):
        return "flow"
    if unit in ("m\u00b2", "m2", "km\u00b2", "km2", "cm\u00b2"):
        return "area"
    if unit in ("s", "sec", "secs", "min", "mins", "h", "hr", "hrs", "day", "days"):
        return "time"
    if unit in ("j", "kj", "mj", "cal", "kcal"):
        return "energy"
    if unit in ("n", "kn", "lbf"):
        return "force"
    if unit in ("w", "kw", "mw", "hp"):
        return "power"
    if unit in ("hz", "khz", "mhz", "ghz"):
        return "frequency"
    return None


def _to_field_unit(value: float, unit: Optional[str], field: dict) -> float:
    """Scale a detected value so it is in the field's unit system."""
    if unit is None:
        return value
    scale = _UNIT_TO_SI.get(unit, 1.0)
    family = _field_family(field)
    field_unit = (field.get("unit") or "").lower()

    if family == "angle":
        if unit in ("rad", "radians"):
            import math
            return math.degrees(value)
        return value
    if family == "temperature":
        if unit in ("\u00b0c", "deg c", "c"):
            return value + 273.15
        if unit in ("\u00b0f", "deg f", "f"):
            return (value - 32) * 5.0 / 9.0 + 273.15
        return value
    if family == "pressure":
        if field_unit in ("kpa", "hpa", "mbar", "bar", "psi", "atm"):
            return value / scale * _UNIT_TO_SI.get(field_unit, 1.0)
        return value * scale
    if family == "length":
        if field_unit == "km":
            return value * scale / 1000.0
        return value * scale
    if family == "velocity":
        if field_unit == "kt":
            return value * scale / 0.514444444
        return value * scale
    if family == "time":
        if field_unit == "min":
            return value * scale / 60.0
        if field_unit == "h":
            return value * scale / 3600.0
        if field_unit == "d":
            return value * scale / 86400.0
        return value * scale
    return value * scale


def _visible(field: dict, payload: dict) -> bool:
    si = field.get("show_if")
    if not si:
        return True
    gate = payload.get(si["key"])
    if isinstance(gate, bool):
        return gate == si["in"][0]
    return gate in si.get("in", [])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def available() -> bool:
    return _AVAILABLE


def info() -> dict:
    if not _AVAILABLE:
        return {
            "available": False, "calculators": 0, "categories": 0,
            "error": str(_IMPORT_ERROR),
        }
    return {
        "available": True,
        "calculators": len(_ac_core.all_calculators()),
        "categories": len(_ac_core.catalog()),
    }


def catalog() -> List[dict]:
    """Simplified public spec of every calculator (no Python callables)."""
    if not _AVAILABLE:
        return []
    return [{
        "id": s["id"], "name": s["name"], "category": s["category"],
        "summary": s["summary"], "tags": s.get("tags", []),
    } for s in _ac_core.all_calculators()]


# Generic words that carry no topical signal; never use them for matching.
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "of", "to", "at", "in", "on", "is",
    "are", "was", "were", "what", "which", "how", "much", "many", "do", "does",
    "did", "can", "you", "me", "my", "i", "it", "its", "with", "from", "by",
    "please", "tell", "calculate", "computed", "compute", "give", "get", "find",
    "using", "use", "this", "that", "these", "those", "will", "would", "should",
    "about", "show", "need", "wanna", "want", "like", "value", "number",
}

_MATCH_WORD_RE = re.compile(r"[a-z0-9]+")

# AeroCalc is a calculation engine, not the general Intellex knowledge
# router.  Generic words such as "airfoil", "rocket", "orbit", or "naca"
# can describe an informational question, so they must not by themselves
# hijack the chatbot.  Only allow AeroCalc when the question contains a
# calculation intent (e.g. "calculate", "find", "solve") or a concrete
# numeric/units-bearing engineering input together with an AeroCalc concept.
_CALC_INTENT_WORDS = {
    "calculate", "calculation", "compute", "computed", "solve", "solution",
    "find", "determine", "evaluate", "estimate", "derive", "numerically",
}

_CALC_CONTEXT_PHRASES = {
    "speed of sound", "density of air", "air density", "air pressure",
    "pressure at altitude", "temperature at altitude", "true airspeed",
    "equivalent airspeed", "calibrated airspeed", "mach number",
    "isentropic flow", "normal shock", "oblique shock", "fanno flow",
    "rayleigh flow", "converging-diverging", "converging diverging",
    "pipe flow", "head loss", "friction factor", "flow meter", "pitot",
    "reynolds number", "dimensionless numbers", "thin airfoil", "naca", "airfoil",
    "lifting line", "induced drag", "drag polar", "boundary layer",
    "critical mach", "orbital elements", "orbital period", "orbit transfer",
    "hohmann", "delta-v", "delta v", "kepler equation", "true anomaly",
    "rocket equation", "ground track", "escape velocity", "c3",
    "couette", "poiseuille", "channel flow", "polytropic process",
    "ideal gas process", "brayton cycle", "otto cycle", "diesel cycle",
    "dual cycle", "piston cycle", "heat transfer", "conduction",
    "convection", "heat exchanger", "effectiveness ntu", "turbofan",
    "turbojet", "ramjet", "rocket nozzle", "propeller", "rotor momentum",
    "level flight", "range endurance", "climb performance", "rate of climb",
    "turn performance", "v-n diagram", "takeoff", "take-off",
    "landing distance", "static stability", "beam bending",
    "column buckling", "pressure vessel", "stress transformation",
    "mohr circle", "torsion", "laminate", "classical lamination",
    "micromechanics", "fatigue", "fracture", "link budget",
    "radar range", "antenna gain", "noise figure", "noise cascade",
    "control response", "filter design", "scientific calculator",
}

_NUMBER_IN_QUESTION_RE = re.compile(
    r"(?<![a-z])[-+]?\d+(?:[.,]\d+)?(?:\s*(?:%|km/h|kmph|m/s|ft/s|knots?|kg/m3|kg/m³|"
    r"kpa|hpa|mbar|psi|atm|km|m|ft|feet|cm|mm|deg(?:rees?)?|°|k|c|f|"
    r"seconds?|minutes?|mins?|hours?|hrs?|days?|n|kn|knm|pa|mpa))?\b",
    re.IGNORECASE,
)


def is_calculation_intent(question: str) -> bool:
    """Return True only when AeroCalc is appropriate for this question.

    This guard is deliberately conservative: Intellex should remain a
    general database/web chatbot, while AeroCalc should activate for actual
    numerical aerospace calculations.
    """
    q = (question or "").lower().strip()
    if not q:
        return False

    tokens = set(_MATCH_WORD_RE.findall(q))
    explicit = bool(tokens & _CALC_INTENT_WORDS)
    has_number = bool(_NUMBER_IN_QUESTION_RE.search(q))
    has_calc_context = any(phrase in q for phrase in _CALC_CONTEXT_PHRASES)

    # Generic concepts such as "airfoil"/"naca" need stronger evidence than
    # a bare number, otherwise an informational question like "What is NACA
    # 2412?" would be hijacked by the calculator.
    generic_context = {"airfoil", "naca"}
    matched_context = {p for p in _CALC_CONTEXT_PHRASES if p in q}
    only_generic = matched_context and matched_context.issubset(generic_context)
    specific_airfoil_input = any(
        p in q for p in ("angle of attack", "aoa", "alpha", "lift coefficient",
                         "aspect ratio", "camber", "thickness")
    )

    if explicit and has_calc_context:
        return True
    if has_number and has_calc_context:
        return (not only_generic) or specific_airfoil_input
    return False


def find_calculator(question: str) -> Optional[dict]:
    """Return the best matching calculator spec, or None."""
    if not _AVAILABLE:
        return None
    q = question.lower().strip()
    if not q:
        return None

    # Longest alias first so "rocket equation delta v" wins over "delta v".
    for phrase, calc_id in sorted(ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if phrase in q:
            spec = _ac_core.get(calc_id)
            if spec is not None:
                return spec

    q_tokens = {t for t in _MATCH_WORD_RE.findall(q) if t not in _STOP_WORDS}
    if not q_tokens:
        return None
    best_spec, best_score = None, 0.0
    for spec in _ac_core.all_calculators():
        haystack = " ".join(
            [spec["name"], spec["category"], spec["summary"],
             " ".join(spec.get("tags", [])),
             " ".join(f["label"] for f in spec["inputs"])]
        ).lower()
        tokens = set(_MATCH_WORD_RE.findall(haystack))
        overlap = len(q_tokens & tokens)
        if overlap > best_score:
            best_score = overlap
            best_spec = spec
    if best_score < 2:
        return None
    return best_spec


def _apply_choice(spec: dict, payload: dict, question: str) -> None:
    q = question.lower()
    for f in spec["inputs"]:
        if f["type"] != "choice":
            continue
        key = f["key"]
        options = [o["value"] for o in f.get("options", [])]
        if not options:
            continue

        if key == "body":
            for name in _BODY_HINTS:
                if name in q:
                    payload[key] = name
                    break
            continue

        if key in ("mode", "known", "spec", "kind"):
            hints = _MODE_HINTS.get(spec["id"])
            if hints:
                for phrase in sorted(hints, key=len, reverse=True):
                    if phrase in q:
                        payload[key] = hints[phrase]
                        break
            continue

        for opt in options:
            if opt == "custom":
                continue
            if opt.replace("_", " ") in q:
                payload[key] = opt
                break
        else:
            for o in f.get("options", []):
                label = (o.get("label") or "").lower()
                if label and label in q:
                    payload[key] = o["value"]
                    break


def _apply_toggles(spec: dict, payload: dict, question: str) -> None:
    q = question.lower()
    for f in spec["inputs"]:
        if f["type"] != "toggle":
            continue
        label = f.get("label", "").lower()
        if any(w in q for w in (label, "include", "compute", "solve", "add",
                                "compare", "with dimensional")):
            payload[f["key"]] = True
        elif any(w in q for w in ("no ", "without", "skip", "don't", "do not")):
            payload[f["key"]] = False


def _assign_numbers(
    spec: dict, payload: dict, tokens: List[_NumToken]
) -> set:
    """Fill numeric fields from extracted number tokens.

    Returns the set of field keys that actually received a number the user
    typed. Fields left untouched will be filled with their schema defaults
    afterwards by the caller, and those never count as "found inputs".
    """
    fields = [f for f in spec["inputs"] if f["type"] in ("number", "integer")]
    if not fields or not tokens:
        return set()

    assigned = set()

    # Pass 1: tokens carrying units match family fields first
    for tok in tokens:
        if tok.unit is None:
            continue
        fam = _family_of_unit(tok.unit)
        if fam is None:
            continue
        for f in fields:
            if f["key"] in assigned:
                continue
            if _field_family(f) == fam and _visible(f, payload):
                payload[f["key"]] = _to_field_unit(tok.value, tok.unit, f)
                assigned.add(f["key"])
                break

    # Pass 2: remaining unit-less tokens fill the first still-empty visible field
    for tok in tokens:
        if tok.unit is not None:
            continue
        for f in fields:
            if f["key"] in assigned:
                continue
            if not _visible(f, payload):
                continue
            payload[f["key"]] = _to_field_unit(tok.value, None, f)
            assigned.add(f["key"])
            break

    return assigned


def _has_confident_inputs(
    spec: dict, payload: dict, extracted_numeric: set
) -> bool:
    """A calculation only runs when the user actually supplied a number.

    ``extracted_numeric`` is the set of field keys that received a number
    token from the question. Defaults filled afterwards never count, so a
    question with no numbers at all ("what is the capital of france") is
    never silently computed on default inputs.
    """
    if not extracted_numeric:
        return False
    # The user-typed value must land on a field that is currently visible
    # (not hidden by a show_if gate).
    for key in extracted_numeric:
        for f in spec["inputs"]:
            if f["key"] == key and _visible(f, payload):
                return True
    return False


def _required_labels(spec: dict) -> List[str]:
    return [
        f["label"] for f in spec["inputs"]
        if f["type"] in ("number", "integer") and f.get("show_if") is None
    ]


def compute(question: str, calc_id: Optional[str] = None) -> Optional[dict]:
    """Try to run a calculation for the question.

    Returns a structured dict (see module docstring) or None when no calculator
    matched the question at all.
    """
    if not _AVAILABLE:
        print(
            "[AEROCALC] unavailable "
            f"import_error={_IMPORT_ERROR!r}",
            flush=True,
        )
        return None

    # The AVARIX chatbot already gates this call using its calculation
    # detector. Do not apply a second, independently maintained intent gate
    # here: mismatched phrase lists can make a valid request return None and
    # silently fall through to web search.
    spec = _ac_core.get(calc_id) if calc_id else None
    if spec is None:
        spec = find_calculator(question)
    if spec is None:
        print(
            f"[AEROCALC] no calculator match query={question!r}",
            flush=True,
        )
        return None

    print(
        f"[AEROCALC] matched id={spec.get('id')!r} "
        f"name={spec.get('name')!r} query={question!r}",
        flush=True,
    )

    payload: Dict[str, object] = {}
    tokens = _tokenize_numbers(question)

    _apply_choice(spec, payload, question)
    _apply_toggles(spec, payload, question)

    # Populate selector/toggle defaults BEFORE numeric extraction.  AeroCalc
    # uses these values in ``show_if`` gates, so a question such as
    # "speed of sound at 5000 feet" must activate the default ``altitude``
    # mode before the 5000 value can be assigned to the altitude field.
    for f in spec["inputs"]:
        if f["key"] not in payload and f["type"] in ("choice", "toggle"):
            payload[f["key"]] = f.get("default")

    extracted_numeric = _assign_numbers(spec, payload, tokens)

    # Fill defaults for all remaining fields (AeroCalc coerce needs them).
    for f in spec["inputs"]:
        if f["key"] not in payload:
            payload[f["key"]] = f.get("default")

    if not _has_confident_inputs(spec, payload, extracted_numeric):
        print(
            f"[AEROCALC] missing_inputs id={spec.get('id')!r} "
            f"extracted={sorted(extracted_numeric)!r}",
            flush=True,
        )
        return {
            "calculator": _public_spec(spec),
            "matched": True,
            "match_name": spec["name"],
            "payload": payload,
            "groups": [], "plots": [], "tables": [], "notes": [], "steps": [],
            "summary": "",
            "error": "",
            "suggestions": [
                f"Tell me the {', '.join(_required_labels(spec)[:3])}",
                f"Example: {_example_question(spec)}",
            ],
        }

    try:
        inputs = _ac_core.coerce_inputs(spec, payload)
        result_obj = spec["compute"](inputs)
        # Newer AeroCalc versions attach custom steps and can synthesize
        # concise educational steps for calculators that do not define them.
        ensure_steps = getattr(_ac_core, "ensure_steps", None)
        if callable(ensure_steps):
            ensure_steps(spec, inputs, result_obj)
        result = result_obj.to_dict()
    except _ac_core.CalculationError as exc:
        return {
            "calculator": _public_spec(spec),
            "matched": True,
            "match_name": spec["name"],
            "payload": payload,
            "groups": [], "plots": [], "tables": [], "notes": [], "steps": [],
            "summary": "",
            "error": str(exc),
            "suggestions": [],
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "calculator": _public_spec(spec),
            "matched": True,
            "match_name": spec["name"],
            "payload": payload,
            "groups": [], "plots": [], "tables": [], "notes": [], "steps": [],
            "summary": "",
            "error": f"The calculation failed unexpectedly: {exc}",
            "suggestions": [],
        }

    return {
        "calculator": _public_spec(spec),
        "matched": True,
        "match_name": spec["name"],
        "payload": dict(inputs),
        "groups": result.get("groups", []),
        "plots": result.get("plots", []),
        "tables": result.get("tables", []),
        "notes": result.get("notes", []),
        "steps": result.get("steps", []),
        "summary": _summarize(result),
        "error": "",
        "suggestions": [],
    }


def _public_spec(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k != "compute"}


def _summarize(result: dict) -> str:
    """A short readable text of the headline numbers, for the LLM to weave
    into a conversational answer."""
    lines = []
    for g in result.get("groups", []):
        heads = [r for r in g["rows"] if r.get("highlight")]
        for r in heads:
            unit = f" {r['unit']}" if r.get("unit") else ""
            extra = f" ({r['symbol']})" if r.get("symbol") else ""
            lines.append(f"{r['label']}{extra}: {r['display']}{unit}")
        if heads and len(g["rows"]) > len(heads):
            others = "; ".join(
                f"{r['label']} = {r['display']}{' ' + r['unit'] if r.get('unit') else ''}"
                for r in g["rows"] if not r.get("highlight")
            )
            lines.append("Other values: " + others[:900])
    if not lines:
        for g in result.get("groups", []):
            for r in g["rows"][:4]:
                unit = f" {r['unit']}" if r.get("unit") else ""
                lines.append(f"{r['label']}: {r['display']}{unit}")
    return " | ".join(lines)


def _example_question(spec: dict) -> str:
    examples = {
        "standard-atmosphere": "density at 11 000 m altitude",
        "airspeed-conversion": "true airspeed at Mach 0.8 at 8000 m",
        "isentropic-flow": "isentropic ratios at Mach 2",
        "normal-shock": "normal shock at Mach 2.5",
        "oblique-shock": "oblique shock at Mach 3 with 20 degree deflection",
        "prandtl-meyer": "Prandtl-Meyer expansion turning 15 degrees from Mach 2",
        "fanno-flow": "Fanno flow at Mach 0.3 in a 10 m duct",
        "rayleigh-flow": "Rayleigh flow at Mach 0.5 with 500 kJ/kg heat",
        "cd-nozzle": "converging-diverging nozzle at exit area ratio 4",
        "shock-tube": "shock tube with driver pressure 2 MPa",
        "gas-tables": "isentropic gas table from Mach 0 to 5",
        "pipe-flow": "head loss in a 100 m pipe at 0.004 m3/s",
        "flow-meter": "venturi flow at 20 kPa differential pressure",
        "pitot-static": "velocity from a pitot probe with 5000 Pa differential",
        "reynolds-similarity": "Reynolds number at 50 m/s over 1 m",
        "thin-airfoil": "NACA 2412 at 5 degrees angle of attack",
        "lifting-line": "lifting line for an aspect ratio 8 wing at 5 degrees",
        "drag-polar": "drag polar at lift coefficient 0.5",
        "boundary-layer": "boundary layer on a 1 m plate at 30 m/s",
        "compressibility-correction": "critical Mach number for C_p0 of -0.6",
        "orbital-elements": "orbit period at 400 km altitude",
        "orbit-transfer": "Hohmann transfer from 400 km to 35786 km",
        "kepler-propagation": "Kepler propagation at 60 minutes for e=0.74",
        "rocket-equation": "rocket delta-v for a 2 stage vehicle",
        "groundtrack-coverage": "ground track of a 700 km sun-synchronous orbit",
        "escape-hyperbolic": "escape velocity from a 200 km parking orbit",
    }
    return examples.get(spec["id"], spec["name"].lower())
