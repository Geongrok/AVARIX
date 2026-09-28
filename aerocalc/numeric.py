"""Numerical helpers shared by the calculator modules.

Inverse problems (find M given A/A*, find the friction factor from Colebrook,
solve Kepler's equation) all funnel through these so the whole app has one
well-tested root-finder rather than a dozen hand-rolled loops.
"""

from __future__ import annotations

import math
from typing import Callable

from scipy.optimize import brentq

from .core import CalculationError


def solve(f: Callable[[float], float], lo: float, hi: float,
          *, what: str = "value", xtol: float = 1e-14, rtol: float = 8.9e-16,
          expand: bool = False) -> float:
    """Bracketed root of ``f`` on ``[lo, hi]``.

    ``expand`` widens the upper bound geometrically when the initial bracket
    does not straddle a sign change, which is what most "given a ratio, find
    the Mach number" problems need.
    """
    try:
        flo, fhi = f(lo), f(hi)
    except (ValueError, ZeroDivisionError, OverflowError):
        raise CalculationError(f"Could not evaluate the equation for {what}.")

    if expand:
        n = 0
        while flo * fhi > 0 and n < 60:
            hi *= 1.6
            try:
                fhi = f(hi)
            except (ValueError, ZeroDivisionError, OverflowError):
                break
            n += 1

    if flo * fhi > 0:
        raise CalculationError(
            f"No solution for {what} in the searched range — check that the "
            "inputs describe a physically possible flow or geometry.")

    return brentq(f, lo, hi, xtol=xtol, rtol=rtol, maxiter=200)


def newton(f: Callable[[float], float], df: Callable[[float], float],
           x0: float, *, tol: float = 1e-13, maxiter: int = 100,
           what: str = "value") -> float:
    """Newton-Raphson with a derivative, for smooth well-conditioned problems."""
    x = x0
    for _ in range(maxiter):
        fx = f(x)
        dfx = df(x)
        if dfx == 0:
            break
        step = fx / dfx
        x -= step
        if abs(step) < tol * max(1.0, abs(x)):
            return x
    if abs(f(x)) < 1e-8:
        return x
    raise CalculationError(f"Iteration for {what} did not converge.")


def linspace(a: float, b: float, n: int) -> list[float]:
    if n < 2:
        return [a]
    step = (b - a) / (n - 1)
    return [a + step * i for i in range(n)]


def logspace(a: float, b: float, n: int) -> list[float]:
    """``n`` points from ``a`` to ``b`` spaced logarithmically (both > 0)."""
    la, lb = math.log10(a), math.log10(b)
    return [10 ** v for v in linspace(la, lb, n)]


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
