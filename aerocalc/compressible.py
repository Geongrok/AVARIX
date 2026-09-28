"""Exact compressible-flow relations for a calorically perfect gas.

Every function here is the closed-form relation; inverses are solved with a
bracketed Brent root-finder to machine precision rather than curve fits, so
results match NACA Report 1135 to all printed digits.
"""

from __future__ import annotations

import math

from .core import CalculationError
from .numeric import solve

# ---------------------------------------------------------------------------
# Isentropic relations
# ---------------------------------------------------------------------------


def t0_ratio(M: float, g: float) -> float:
    """T0/T."""
    return 1.0 + 0.5 * (g - 1.0) * M * M


def p0_ratio(M: float, g: float) -> float:
    """p0/p."""
    return t0_ratio(M, g) ** (g / (g - 1.0))


def rho0_ratio(M: float, g: float) -> float:
    """rho0/rho."""
    return t0_ratio(M, g) ** (1.0 / (g - 1.0))


def area_ratio(M: float, g: float) -> float:
    """A/A* for isentropic flow."""
    if M <= 0:
        raise CalculationError("Mach number must be greater than zero.")
    return (1.0 / M) * ((2.0 / (g + 1.0)) * t0_ratio(M, g)) ** ((g + 1.0) / (2.0 * (g - 1.0)))


def mach_angle(M: float) -> float:
    """Mach angle mu [rad]; only defined for supersonic flow."""
    if M < 1.0:
        raise CalculationError("The Mach angle is defined only for M \u2265 1.")
    return math.asin(1.0 / M)


def mach_from_area_ratio(ar: float, g: float, branch: str = "subsonic") -> float:
    """Invert A/A*.  ``branch`` selects the subsonic or supersonic root."""
    if ar < 1.0:
        raise CalculationError(
            "A/A* cannot be less than 1 — the throat is the minimum area.")
    if abs(ar - 1.0) < 1e-12:
        return 1.0
    f = lambda M: area_ratio(M, g) - ar
    if branch == "subsonic":
        return solve(f, 1e-9, 1.0, what="subsonic Mach number")
    return solve(f, 1.0, 60.0, what="supersonic Mach number", expand=True)


def mach_from_p0_ratio(ratio: float, g: float) -> float:
    """Invert p0/p."""
    if ratio < 1.0:
        raise CalculationError("p0/p cannot be less than 1.")
    return math.sqrt(2.0 * (ratio ** ((g - 1.0) / g) - 1.0) / (g - 1.0))


def mach_from_t0_ratio(ratio: float, g: float) -> float:
    if ratio < 1.0:
        raise CalculationError("T0/T cannot be less than 1.")
    return math.sqrt(2.0 * (ratio - 1.0) / (g - 1.0))


def mach_from_rho0_ratio(ratio: float, g: float) -> float:
    if ratio < 1.0:
        raise CalculationError("\u03c10/\u03c1 cannot be less than 1.")
    return math.sqrt(2.0 * (ratio ** (g - 1.0) - 1.0) / (g - 1.0))


def mach_from_mach_angle(mu_deg: float) -> float:
    mu = math.radians(mu_deg)
    if not 0 < mu <= math.pi / 2:
        raise CalculationError("The Mach angle must be between 0\u00b0 and 90\u00b0.")
    return 1.0 / math.sin(mu)


def critical_pressure_ratio(g: float) -> float:
    """p*/p0 — the back-pressure ratio that chokes a nozzle."""
    return (2.0 / (g + 1.0)) ** (g / (g - 1.0))


# ---------------------------------------------------------------------------
# Normal shock
# ---------------------------------------------------------------------------


def shock_M2(M1: float, g: float) -> float:
    _check_supersonic(M1)
    num = 1.0 + 0.5 * (g - 1.0) * M1 * M1
    den = g * M1 * M1 - 0.5 * (g - 1.0)
    return math.sqrt(num / den)


def shock_p_ratio(M1: float, g: float) -> float:
    """p2/p1."""
    _check_supersonic(M1)
    return 1.0 + 2.0 * g / (g + 1.0) * (M1 * M1 - 1.0)


def shock_rho_ratio(M1: float, g: float) -> float:
    _check_supersonic(M1)
    return (g + 1.0) * M1 * M1 / ((g - 1.0) * M1 * M1 + 2.0)


def shock_T_ratio(M1: float, g: float) -> float:
    return shock_p_ratio(M1, g) / shock_rho_ratio(M1, g)


def shock_p0_ratio(M1: float, g: float) -> float:
    """p02/p01 — the total-pressure recovery across the shock."""
    _check_supersonic(M1)
    a = ((g + 1.0) * M1 * M1 / ((g - 1.0) * M1 * M1 + 2.0)) ** (g / (g - 1.0))
    b = ((g + 1.0) / (2.0 * g * M1 * M1 - (g - 1.0))) ** (1.0 / (g - 1.0))
    return a * b


def shock_p1_over_p02(M1: float, g: float) -> float:
    """p1/p02 — the pitot-probe (Rayleigh) relation."""
    return 1.0 / (shock_p0_ratio(M1, g) * p0_ratio(M1, g))


def shock_entropy_rise(M1: float, g: float, R: float) -> float:
    """Delta s across the shock [J/(kg*K)]."""
    return -R * math.log(shock_p0_ratio(M1, g))


def mach_from_shock_p_ratio(pr: float, g: float) -> float:
    if pr < 1.0:
        raise CalculationError("p2/p1 across a shock cannot be less than 1.")
    return math.sqrt((pr - 1.0) * (g + 1.0) / (2.0 * g) + 1.0)


def mach_from_M2(M2: float, g: float) -> float:
    """Upstream Mach number given the subsonic downstream Mach number."""
    m2_min = math.sqrt((g - 1.0) / (2.0 * g))
    if not m2_min < M2 < 1.0:
        raise CalculationError(
            f"The downstream Mach number must lie between {m2_min:.4f} and 1.")
    return solve(lambda m: shock_M2(m, g) - M2, 1.0 + 1e-12, 60.0,
                 what="upstream Mach number", expand=True)


def mach_from_shock_p0_ratio(pr: float, g: float) -> float:
    if not 0 < pr <= 1.0:
        raise CalculationError("p02/p01 must be between 0 and 1.")
    return solve(lambda m: shock_p0_ratio(m, g) - pr, 1.0, 60.0,
                 what="shock Mach number", expand=True)


def _check_supersonic(M1):
    if M1 < 1.0:
        raise CalculationError(
            "A normal shock requires supersonic upstream flow (M\u2081 \u2265 1).")


# ---------------------------------------------------------------------------
# Oblique shock
# ---------------------------------------------------------------------------


def theta_from_beta(M1: float, beta: float, g: float) -> float:
    """theta-beta-M relation.  Angles in radians."""
    s = math.sin(beta)
    num = 2.0 / math.tan(beta) * (M1 * M1 * s * s - 1.0)
    den = M1 * M1 * (g + math.cos(2.0 * beta)) + 2.0
    return math.atan(num / den)


def max_deflection(M1: float, g: float) -> tuple[float, float]:
    """Maximum deflection angle and the wave angle at which it occurs [rad]."""
    lo = math.asin(1.0 / M1) + 1e-9
    hi = math.pi / 2 - 1e-9
    # theta(beta) is unimodal on this interval: golden-section search.
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    for _ in range(200):
        if theta_from_beta(M1, c, g) < theta_from_beta(M1, d, g):
            a = c
        else:
            b = d
        c, d = b - phi * (b - a), a + phi * (b - a)
        if b - a < 1e-13:
            break
    beta = 0.5 * (a + b)
    return theta_from_beta(M1, beta, g), beta


def beta_from_theta(M1: float, theta: float, g: float,
                    strong: bool = False) -> float:
    """Wave angle for a given deflection.  Angles in radians."""
    if M1 <= 1.0:
        raise CalculationError("An oblique shock requires M\u2081 > 1.")
    theta_max, beta_at_max = max_deflection(M1, g)
    if theta > theta_max + 1e-12:
        raise CalculationError(
            f"The flow cannot turn {math.degrees(theta):.3f}\u00b0 at M\u2081 = {M1:g}. "
            f"The maximum attached deflection is {math.degrees(theta_max):.3f}\u00b0, "
            "so the shock detaches and stands off as a bow shock.")
    mu = math.asin(1.0 / M1)
    if strong:
        return solve(lambda b: theta_from_beta(M1, b, g) - theta,
                     beta_at_max, math.pi / 2 - 1e-12, what="strong-shock wave angle")
    return solve(lambda b: theta_from_beta(M1, b, g) - theta,
                 mu + 1e-12, beta_at_max, what="weak-shock wave angle")


def sonic_deflection(M1: float, g: float) -> float:
    """Deflection at which the downstream flow is exactly sonic [rad]."""
    theta_max, beta_max = max_deflection(M1, g)

    def m2_of_beta(beta):
        mn1 = M1 * math.sin(beta)
        if mn1 <= 1.0:
            return 10.0
        mn2 = shock_M2(mn1, g)
        theta = theta_from_beta(M1, beta, g)
        return mn2 / math.sin(beta - theta)

    try:
        beta = solve(lambda b: m2_of_beta(b) - 1.0, beta_max,
                     math.pi / 2 - 1e-12, what="sonic wave angle")
    except CalculationError:
        return theta_max
    return theta_from_beta(M1, beta, g)


# ---------------------------------------------------------------------------
# Prandtl-Meyer expansion
# ---------------------------------------------------------------------------


def prandtl_meyer(M: float, g: float) -> float:
    """Prandtl-Meyer function nu(M) [rad]."""
    if M < 1.0:
        raise CalculationError(
            "The Prandtl-Meyer function is defined only for M \u2265 1.")
    if M == 1.0:
        return 0.0
    k = math.sqrt((g + 1.0) / (g - 1.0))
    b = math.sqrt(M * M - 1.0)
    return k * math.atan(b / k) - math.atan(b)


def nu_max(g: float) -> float:
    """The limiting turn angle as M -> infinity [rad]."""
    return 0.5 * math.pi * (math.sqrt((g + 1.0) / (g - 1.0)) - 1.0)


def mach_from_nu(nu: float, g: float) -> float:
    """Invert the Prandtl-Meyer function.  ``nu`` in radians."""
    limit = nu_max(g)
    if nu < 0:
        raise CalculationError("The turn angle cannot be negative.")
    if nu >= limit:
        raise CalculationError(
            f"\u03bd = {math.degrees(nu):.3f}\u00b0 exceeds the vacuum limit of "
            f"{math.degrees(limit):.3f}\u00b0 for \u03b3 = {g:g}. The flow would "
            "expand to zero pressure before turning that far.")
    if nu == 0:
        return 1.0
    return solve(lambda m: prandtl_meyer(m, g) - nu, 1.0, 60.0,
                 what="Mach number", expand=True)


# ---------------------------------------------------------------------------
# Fanno flow (adiabatic, with friction, constant area)
# ---------------------------------------------------------------------------


def fanno_T(M, g):
    return (g + 1.0) / (2.0 + (g - 1.0) * M * M)


def fanno_p(M, g):
    return (1.0 / M) * math.sqrt(fanno_T(M, g))


def fanno_rho(M, g):
    return (1.0 / M) * math.sqrt(1.0 / fanno_T(M, g))


def fanno_V(M, g):
    return M * math.sqrt(fanno_T(M, g))


def fanno_p0(M, g):
    return (1.0 / M) * ((2.0 + (g - 1.0) * M * M) / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))


def fanno_fld(M, g):
    """4 f L*/D — the friction parameter to choking (Fanning friction factor)."""
    if M <= 0:
        raise CalculationError("Mach number must be positive.")
    if abs(M - 1.0) < 1e-12:
        return 0.0
    m2 = M * M
    return ((1.0 - m2) / (g * m2)
            + (g + 1.0) / (2.0 * g) * math.log((g + 1.0) * m2 / (2.0 + (g - 1.0) * m2)))


def mach_from_fanno_fld(fld: float, g: float, branch: str = "subsonic") -> float:
    if fld < 0:
        raise CalculationError("4fL*/D cannot be negative.")
    if branch == "subsonic":
        return solve(lambda m: fanno_fld(m, g) - fld, 1e-6, 1.0,
                     what="subsonic Mach number")
    limit = fanno_fld(1e9, g)
    if fld > limit:
        raise CalculationError(
            f"For supersonic Fanno flow, 4fL*/D cannot exceed {limit:.5f} "
            f"at \u03b3 = {g:g}.")
    return solve(lambda m: fanno_fld(m, g) - fld, 1.0, 60.0,
                 what="supersonic Mach number", expand=True)


# ---------------------------------------------------------------------------
# Rayleigh flow (frictionless, with heat addition, constant area)
# ---------------------------------------------------------------------------


def rayleigh_p(M, g):
    return (1.0 + g) / (1.0 + g * M * M)


def rayleigh_T(M, g):
    return M * M * rayleigh_p(M, g) ** 2


def rayleigh_rho(M, g):
    return (1.0 + g * M * M) / ((1.0 + g) * M * M)


def rayleigh_T0(M, g):
    num = (g + 1.0) * M * M * (2.0 + (g - 1.0) * M * M)
    return num / (1.0 + g * M * M) ** 2


def rayleigh_p0(M, g):
    return rayleigh_p(M, g) * ((2.0 + (g - 1.0) * M * M) / (g + 1.0)) ** (g / (g - 1.0))


def rayleigh_V(M, g):
    return rayleigh_T(M, g) / rayleigh_p(M, g)


def mach_from_rayleigh_T0(t0: float, g: float, branch: str = "subsonic") -> float:
    if not 0 < t0 <= 1.0 + 1e-12:
        raise CalculationError(
            "T0/T0* must be between 0 and 1 — adding more heat than this "
            "thermally chokes the duct.")
    t0 = min(t0, 1.0)
    if branch == "subsonic":
        return solve(lambda m: rayleigh_T0(m, g) - t0, 1e-6, 1.0,
                     what="subsonic Mach number")
    return solve(lambda m: rayleigh_T0(m, g) - t0, 1.0, 60.0,
                 what="supersonic Mach number", expand=True)


# ---------------------------------------------------------------------------
# Derived quantities
# ---------------------------------------------------------------------------


def mass_flow_parameter(M: float, g: float) -> float:
    """Corrected mass flow  mdot*sqrt(R*T0)/(A*p0)  — dimensionless."""
    return (math.sqrt(g) * M
            * t0_ratio(M, g) ** (-(g + 1.0) / (2.0 * (g - 1.0))))


def choked_mass_flow(p0: float, T0: float, A: float, g: float, R: float) -> float:
    """Mass flow through a choked throat of area A [kg/s]."""
    return (A * p0 / math.sqrt(T0) * math.sqrt(g / R)
            * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0))))


def rayleigh_pitot(M1: float, g: float) -> float:
    """p02/p1 for a pitot probe in supersonic flow (Rayleigh pitot formula)."""
    _check_supersonic(M1)
    a = ((g + 1.0) ** 2 * M1 * M1 / (4.0 * g * M1 * M1 - 2.0 * (g - 1.0))) ** (g / (g - 1.0))
    b = (1.0 - g + 2.0 * g * M1 * M1) / (g + 1.0)
    return a * b


def mach_from_pitot(p02_over_p1: float, g: float) -> float:
    """Mach number from a supersonic pitot pressure ratio p02/p1."""
    if p02_over_p1 <= 1.0:
        raise CalculationError("p02/p1 must be greater than 1.")
    if p02_over_p1 < p0_ratio(1.0, g):
        raise CalculationError(
            "That pressure ratio corresponds to subsonic flow — use the "
            "isentropic relation instead.")
    return solve(lambda m: rayleigh_pitot(m, g) - p02_over_p1, 1.0, 60.0,
                 what="Mach number", expand=True)
