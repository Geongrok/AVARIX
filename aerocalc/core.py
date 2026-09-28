"""Core framework: input field specs, result builder, and the calculator registry.

Every calculator in AeroCalc is a plain dict describing its inputs plus a
``compute(inputs) -> Result`` function.  The registry turns those dicts into the
JSON schema the frontend uses to render forms, so adding a calculator never
requires touching the frontend.
"""

from __future__ import annotations

import math
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Input field constructors
# ---------------------------------------------------------------------------


def num(key, label, default, unit="", *, minimum=None, maximum=None,
        step=None, help="", section=None, show_if=None):
    """A floating point input."""
    return {
        "key": key, "label": label, "type": "number", "default": default,
        "unit": unit, "min": minimum, "max": maximum, "step": step,
        "help": help, "section": section, "show_if": show_if,
    }


def integer(key, label, default, unit="", *, minimum=None, maximum=None,
            help="", section=None, show_if=None):
    return {
        "key": key, "label": label, "type": "integer", "default": default,
        "unit": unit, "min": minimum, "max": maximum, "step": 1,
        "help": help, "section": section, "show_if": show_if,
    }


def choice(key, label, options, default, *, help="", section=None, show_if=None):
    """``options`` is a list of ``(value, label)`` pairs."""
    return {
        "key": key, "label": label, "type": "choice",
        "options": [{"value": v, "label": t} for v, t in options],
        "default": default, "help": help, "section": section, "show_if": show_if,
    }


def toggle(key, label, default=False, *, help="", section=None, show_if=None):
    return {
        "key": key, "label": label, "type": "toggle", "default": bool(default),
        "help": help, "section": section, "show_if": show_if,
    }


def text(key, label, default="", *, help="", section=None, show_if=None,
         placeholder=""):
    return {
        "key": key, "label": label, "type": "text", "default": default,
        "help": help, "section": section, "show_if": show_if,
        "placeholder": placeholder,
    }


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------

def fmt(value, sig=6):
    """Format a number for display, keeping ``sig`` significant figures.

    Engineering readouts switch to scientific notation only where fixed
    notation would be unreadable, and integers stay clean.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)

    if math.isnan(v):
        return "NaN"
    if math.isinf(v):
        return "∞" if v > 0 else "−∞"
    if v == 0:
        return "0"

    a = abs(v)
    if a >= 1e7 or a < 1e-4:
        mant, exp = f"{v:.{sig - 1}e}".split("e")
        mant = mant.rstrip("0").rstrip(".")
        return f"{mant}\u00d710{_superscript(int(exp))}"

    # Decimal places needed to keep `sig` significant figures.
    dec = max(0, sig - 1 - int(math.floor(math.log10(a))))
    out = f"{v:.{dec}f}"
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out


_SUP = str.maketrans("-0123456789", "\u207b\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")


def _superscript(n: int) -> str:
    return str(n).translate(_SUP)


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


class Result:
    """Accumulates output rows, plots, tables and notes for one calculation."""

    def __init__(self):
        self.groups: list[dict] = []
        self.plots: list[dict] = []
        self.tables: list[dict] = []
        self.notes: list[str] = []
        self._current: dict | None = None

    # -- outputs ----------------------------------------------------------
    def group(self, title: str, subtitle: str = "") -> "Result":
        self._current = {"title": title, "subtitle": subtitle, "rows": []}
        self.groups.append(self._current)
        return self

    def out(self, label, value, unit="", *, note="", sig=6, symbol="",
            highlight=False) -> "Result":
        if self._current is None:
            self.group("Results")
        self._current["rows"].append({
            "label": label,
            "symbol": symbol,
            "value": _jsonable(value),
            "display": fmt(value, sig),
            "unit": unit,
            "note": note,
            "highlight": highlight,
        })
        return self

    def headline(self, label, value, unit="", *, note="", sig=6, symbol=""):
        """A single primary readout, rendered large by the frontend."""
        return self.out(label, value, unit, note=note, sig=sig,
                        symbol=symbol, highlight=True)

    # -- attachments ------------------------------------------------------
    def plot(self, image: str, title: str = "", caption: str = "") -> "Result":
        self.plots.append({"image": image, "title": title, "caption": caption})
        return self

    def table(self, title, columns, rows, *, caption="", sig=6) -> "Result":
        formatted = [[fmt(c, sig) if not isinstance(c, str) else c for c in row]
                     for row in rows]
        self.tables.append({
            "title": title, "columns": list(columns),
            "rows": formatted,
            "raw": [[_jsonable(c) for c in row] for row in rows],
            "caption": caption,
        })
        return self

    def note(self, message: str) -> "Result":
        self.notes.append(message)
        return self

    def to_dict(self) -> dict:
        return {
            "groups": self.groups,
            "plots": self.plots,
            "tables": self.tables,
            "notes": self.notes,
        }


def _jsonable(v):
    """NaN/Inf are not valid JSON, so send them as strings the UI understands."""
    if isinstance(v, (bool, str)) or v is None:
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


class CalculationError(ValueError):
    """Raised when inputs are physically inadmissible.

    The message is shown to the user verbatim, so it must say what is wrong
    and what to change.
    """


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, dict] = {}
_ORDER: list[str] = []

CATEGORY_ORDER = [
    "Aerodynamics",
    "Fluid Dynamics",
    "Gas Dynamics",
    "Thermodynamics",
    "Propulsion",
    "Flight Mechanics",
    "Structures & Composites",
    "Space & Satellites",
    "Avionics & Electronics",
]

CATEGORY_BLURB = {
    "Aerodynamics": "Atmosphere, airspeeds, airfoil and wing theory, boundary layers.",
    "Fluid Dynamics": "Internal flow, similarity, viscous profiles and flow measurement.",
    "Gas Dynamics": "Compressible flow relations, shocks, expansions and gas tables.",
    "Thermodynamics": "States, processes, power and refrigeration cycles, heat transfer.",
    "Propulsion": "Air-breathing and rocket engine cycles, nozzles, propellers.",
    "Flight Mechanics": "Performance, manoeuvring, stability and control.",
    "Structures & Composites": "Stress analysis, stability, laminates and fatigue.",
    "Space & Satellites": "Orbits, transfers, perturbations and mission budgets.",
    "Avionics & Electronics": "Links, radar, navigation, sampling and power budgets.",
}


def register(spec: dict) -> dict:
    """Validate and add one calculator to the registry."""
    required = {"id", "name", "category", "summary", "inputs", "compute"}
    missing = required - spec.keys()
    if missing:
        raise ValueError(f"calculator {spec.get('id')!r} is missing {sorted(missing)}")
    if spec["id"] in _REGISTRY:
        raise ValueError(f"duplicate calculator id {spec['id']!r}")
    spec.setdefault("tags", [])
    spec.setdefault("references", [])
    spec.setdefault("description", "")
    from . import references as _refs        # local import avoids a cycle
    _refs.attach(spec)
    _REGISTRY[spec["id"]] = spec
    _ORDER.append(spec["id"])
    return spec


def register_all(specs: list[dict]) -> None:
    for s in specs:
        register(s)


def get(calc_id: str) -> dict | None:
    return _REGISTRY.get(calc_id)


def all_calculators() -> list[dict]:
    return [_REGISTRY[i] for i in _ORDER]


def public_spec(spec: dict) -> dict:
    """The registry entry minus the Python callable, ready to serialise."""
    return {k: v for k, v in spec.items() if k != "compute"}


def catalog() -> list[dict]:
    """Calculators grouped by category, in curriculum order."""
    buckets: dict[str, list[dict]] = {}
    for spec in all_calculators():
        buckets.setdefault(spec["category"], []).append({
            "id": spec["id"],
            "name": spec["name"],
            "summary": spec["summary"],
            "tags": spec["tags"],
        })
    ordered = []
    for cat in CATEGORY_ORDER:
        if cat in buckets:
            ordered.append({
                "category": cat,
                "blurb": CATEGORY_BLURB.get(cat, ""),
                "calculators": buckets.pop(cat),
            })
    for cat, items in buckets.items():  # anything added outside the known order
        ordered.append({"category": cat, "blurb": "", "calculators": items})
    return ordered


# ---------------------------------------------------------------------------
# Input coercion
# ---------------------------------------------------------------------------


def coerce_inputs(spec: dict, payload: dict) -> dict:
    """Validate a raw JSON payload against a calculator's field list."""
    values: dict[str, Any] = {}
    for f in spec["inputs"]:
        key = f["key"]
        raw = payload.get(key, f.get("default"))
        kind = f["type"]

        if kind in ("number", "integer"):
            if raw is None or raw == "":
                raise CalculationError(f"{f['label']} is required.")
            try:
                v = float(raw)
            except (TypeError, ValueError):
                raise CalculationError(f"{f['label']} must be a number.")
            if math.isnan(v) or math.isinf(v):
                raise CalculationError(f"{f['label']} must be a finite number.")
            if kind == "integer":
                v = int(round(v))
            lo, hi = f.get("min"), f.get("max")
            if lo is not None and v < lo:
                raise CalculationError(
                    f"{f['label']} must be at least {fmt(lo)}{_u(f)}.")
            if hi is not None and v > hi:
                raise CalculationError(
                    f"{f['label']} must be at most {fmt(hi)}{_u(f)}.")
            values[key] = v

        elif kind == "choice":
            allowed = [o["value"] for o in f["options"]]
            v = raw if raw in allowed else f["default"]
            values[key] = v

        elif kind == "toggle":
            values[key] = bool(raw) if not isinstance(raw, str) else raw.lower() in ("1", "true", "yes", "on")

        else:  # text
            values[key] = "" if raw is None else str(raw)

    return values


def _u(f):
    return f" {f['unit']}" if f.get("unit") else ""
