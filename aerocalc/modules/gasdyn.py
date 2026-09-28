"""Gas dynamics: compressible flow relations, shocks, ducts and gas tables."""

from __future__ import annotations

import math

from .. import compressible as cf
from .. import plotting as P
from ..core import CalculationError, Result, choice, integer, num, toggle
from ..numeric import linspace, solve
from ..physics import GAS_OPTIONS, gas_properties

CATEGORY = "Gas Dynamics"


def _gas_fields(section="Working gas"):
    return [
        choice("gas", "Working gas", GAS_OPTIONS, "air", section=section),
        num("gamma", "Specific heat ratio \u03b3", 1.4, minimum=1.001, maximum=2.0,
            section=section, show_if={"key": "gas", "in": ["custom"]}),
        num("R", "Gas constant R", 287.05287, "J/(kg\u00b7K)", minimum=1.0,
            section=section, show_if={"key": "gas", "in": ["custom"]}),
    ]


# ---------------------------------------------------------------------------
# 1. Isentropic flow
# ---------------------------------------------------------------------------

_ISEN_MODES = [
    ("M", "Mach number M"),
    ("p0p", "Total/static pressure p\u2080/p"),
    ("t0t", "Total/static temperature T\u2080/T"),
    ("r0r", "Total/static density \u03c1\u2080/\u03c1"),
    ("ar_sub", "Area ratio A/A* (subsonic branch)"),
    ("ar_sup", "Area ratio A/A* (supersonic branch)"),
    ("mu", "Mach angle \u03bc"),
    ("nu", "Prandtl-Meyer angle \u03bd"),
]


def _isentropic(inp):
    g, R, gas = gas_properties(inp)
    mode, v = inp["mode"], inp["value"]

    if mode == "M":
        M = v
    elif mode == "p0p":
        M = cf.mach_from_p0_ratio(v, g)
    elif mode == "t0t":
        M = cf.mach_from_t0_ratio(v, g)
    elif mode == "r0r":
        M = cf.mach_from_rho0_ratio(v, g)
    elif mode == "ar_sub":
        M = cf.mach_from_area_ratio(v, g, "subsonic")
    elif mode == "ar_sup":
        M = cf.mach_from_area_ratio(v, g, "supersonic")
    elif mode == "mu":
        M = cf.mach_from_mach_angle(v)
    else:
        M = cf.mach_from_nu(math.radians(v), g)

    if M <= 0:
        raise CalculationError("Mach number must be greater than zero.")

    t0t = cf.t0_ratio(M, g)
    p0p = cf.p0_ratio(M, g)
    r0r = cf.rho0_ratio(M, g)
    ar = cf.area_ratio(M, g)

    r = Result()
    r.group("Flow state").headline("Mach number", M, symbol="M")
    r.out("Regime", "subsonic" if M < 1 else ("sonic" if abs(M - 1) < 1e-9 else "supersonic"))

    r.group("Isentropic ratios", f"{gas} \u2014 \u03b3 = {g:g}, R = {R:g} J/(kg\u00b7K)")
    r.out("Total / static temperature", t0t, symbol="T\u2080/T")
    r.out("Total / static pressure", p0p, symbol="p\u2080/p")
    r.out("Total / static density", r0r, symbol="\u03c1\u2080/\u03c1")
    r.out("Static / total temperature", 1 / t0t, symbol="T/T\u2080")
    r.out("Static / total pressure", 1 / p0p, symbol="p/p\u2080")
    r.out("Static / total density", 1 / r0r, symbol="\u03c1/\u03c1\u2080")
    r.out("Area ratio", ar, symbol="A/A*")

    r.group("Sonic (starred) reference")
    tstar = 2.0 / (g + 1.0) * t0t
    r.out("T/T*", tstar, symbol="T/T*")
    r.out("p/p*", (2.0 / (g + 1.0) * t0t) ** (g / (g - 1.0)), symbol="p/p*")
    r.out("Characteristic Mach number", math.sqrt((g + 1.0) * M * M / (2.0 + (g - 1.0) * M * M)),
          symbol="M*")
    r.out("Corrected flow function", cf.mass_flow_parameter(M, g),
          symbol="\u1e41\u221a(RT\u2080)/(Ap\u2080)")

    if M >= 1:
        r.group("Supersonic angles")
        r.out("Mach angle", math.degrees(cf.mach_angle(M)), "\u00b0", symbol="\u03bc")
        r.out("Prandtl-Meyer angle", math.degrees(cf.prandtl_meyer(M, g)), "\u00b0", symbol="\u03bd")

    if inp["dimensional"]:
        p, T = inp["p"], inp["T"]
        a = math.sqrt(g * R * T)
        rho = p / (R * T)
        V = M * a
        r.group("Dimensional conditions", "From the static pressure and temperature you entered")
        r.out("Speed of sound", a, "m/s", symbol="a")
        r.out("Velocity", V, "m/s", symbol="V")
        r.out("Density", rho, "kg/m\u00b3", symbol="\u03c1")
        r.out("Dynamic pressure", 0.5 * rho * V * V, "Pa", symbol="q")
        r.out("Total pressure", p * p0p, "Pa", symbol="p\u2080")
        r.out("Total temperature", T * t0t, "K", symbol="T\u2080")
        r.out("Total density", rho * r0r, "kg/m\u00b3", symbol="\u03c1\u2080")
        r.out("Mass flux", rho * V, "kg/(s\u00b7m\u00b2)", symbol="\u03c1V")

    ms = linspace(0.02, max(4.0, M * 1.25), 400)
    r.plot(**P.chart(
        [{"x": ms, "y": [1 / cf.p0_ratio(m, g) for m in ms], "label": "p/p\u2080"},
         {"x": ms, "y": [1 / cf.t0_ratio(m, g) for m in ms], "label": "T/T\u2080"},
         {"x": ms, "y": [1 / cf.rho0_ratio(m, g) for m in ms], "label": "\u03c1/\u03c1\u2080"},
         {"x": ms, "y": [min(cf.area_ratio(m, g), 6) for m in ms], "label": "A/A*", "style": "--"}],
        xlabel="Mach number  M", ylabel="Ratio", ylim=(0, 3.2),
        title="Isentropic property ratios",
        points=[{"x": M, "y": 1 / p0p, "label": f"operating point, M = {M:.4g}"}],
        caption=f"Isentropic relations for \u03b3 = {g:g}. A/A* is clipped at 6 for readability."))
    return r


# ---------------------------------------------------------------------------
# 2. Normal shock
# ---------------------------------------------------------------------------

_NS_MODES = [
    ("M1", "Upstream Mach number M\u2081"),
    ("M2", "Downstream Mach number M\u2082"),
    ("p2p1", "Static pressure ratio p\u2082/p\u2081"),
    ("p02p01", "Total pressure ratio p\u2080\u2082/p\u2080\u2081"),
    ("pitot", "Pitot ratio p\u2080\u2082/p\u2081"),
]


def _normal_shock(inp):
    g, R, gas = gas_properties(inp)
    mode, v = inp["mode"], inp["value"]

    if mode == "M1":
        M1 = v
    elif mode == "M2":
        M1 = cf.mach_from_M2(v, g)
    elif mode == "p2p1":
        M1 = cf.mach_from_shock_p_ratio(v, g)
    elif mode == "p02p01":
        M1 = cf.mach_from_shock_p0_ratio(v, g)
    else:
        M1 = cf.mach_from_pitot(v, g)

    M2 = cf.shock_M2(M1, g)
    pr, rr = cf.shock_p_ratio(M1, g), cf.shock_rho_ratio(M1, g)
    tr, p0r = cf.shock_T_ratio(M1, g), cf.shock_p0_ratio(M1, g)

    r = Result()
    r.group("Shock strength", f"{gas} \u2014 \u03b3 = {g:g}")
    r.headline("Upstream Mach number", M1, symbol="M\u2081")
    r.headline("Downstream Mach number", M2, symbol="M\u2082")

    r.group("Jump conditions")
    r.out("Static pressure ratio", pr, symbol="p\u2082/p\u2081")
    r.out("Static temperature ratio", tr, symbol="T\u2082/T\u2081")
    r.out("Density ratio", rr, symbol="\u03c1\u2082/\u03c1\u2081")
    r.out("Velocity ratio", 1 / rr, symbol="V\u2082/V\u2081")
    r.out("Total pressure ratio", p0r, symbol="p\u2080\u2082/p\u2080\u2081")
    r.out("Total temperature ratio", 1.0, symbol="T\u2080\u2082/T\u2080\u2081",
          note="a normal shock is adiabatic")
    r.out("Pitot ratio", cf.rayleigh_pitot(M1, g), symbol="p\u2080\u2082/p\u2081")
    r.out("Entropy rise", cf.shock_entropy_rise(M1, g, R), "J/(kg\u00b7K)", symbol="\u0394s")
    r.out("Downstream A*/upstream A*", 1 / p0r, symbol="A\u2082*/A\u2081*")

    if inp["dimensional"]:
        p1, T1 = inp["p1"], inp["T1"]
        a1 = math.sqrt(g * R * T1)
        rho1 = p1 / (R * T1)
        V1 = M1 * a1
        T2, p2, rho2 = T1 * tr, p1 * pr, rho1 * rr
        V2 = V1 / rr
        r.group("Upstream conditions")
        r.out("Velocity", V1, "m/s", symbol="V\u2081")
        r.out("Density", rho1, "kg/m\u00b3", symbol="\u03c1\u2081")
        r.out("Total pressure", p1 * cf.p0_ratio(M1, g), "Pa", symbol="p\u2080\u2081")
        r.out("Total temperature", T1 * cf.t0_ratio(M1, g), "K", symbol="T\u2080\u2081")
        r.group("Downstream conditions")
        r.out("Static pressure", p2, "Pa", symbol="p\u2082")
        r.out("Static temperature", T2, "K", symbol="T\u2082")
        r.out("Density", rho2, "kg/m\u00b3", symbol="\u03c1\u2082")
        r.out("Velocity", V2, "m/s", symbol="V\u2082")
        r.out("Total pressure", p2 * cf.p0_ratio(M2, g), "Pa", symbol="p\u2080\u2082")

    ms = linspace(1.0, max(5.0, M1 * 1.2), 350)
    r.plot(**P.chart(
        [{"x": ms, "y": [cf.shock_p_ratio(m, g) for m in ms], "label": "p\u2082/p\u2081"},
         {"x": ms, "y": [cf.shock_T_ratio(m, g) for m in ms], "label": "T\u2082/T\u2081"},
         {"x": ms, "y": [cf.shock_rho_ratio(m, g) for m in ms], "label": "\u03c1\u2082/\u03c1\u2081"}],
        xlabel="Upstream Mach number  M\u2081", ylabel="Ratio", ylog=True,
        title="Normal shock jump conditions",
        points=[{"x": M1, "y": pr, "label": f"M\u2081 = {M1:.4g}"}],
        caption="Density ratio asymptotes to (\u03b3+1)/(\u03b3\u22121) "
                f"= {(g + 1) / (g - 1):.3f} as M\u2081 \u2192 \u221e."))
    r.plot(**P.chart(
        [{"x": ms, "y": [cf.shock_p0_ratio(m, g) for m in ms], "label": "p\u2080\u2082/p\u2080\u2081"},
         {"x": ms, "y": [cf.shock_M2(m, g) for m in ms], "label": "M\u2082", "color": P.SERIES[1]}],
        xlabel="Upstream Mach number  M\u2081", ylabel="Value", ylim=(0, 1.05),
        title="Total pressure recovery and downstream Mach number",
        points=[{"x": M1, "y": p0r}],
        caption="Total pressure loss is the irreversibility of the shock; "
                "M\u2082 asymptotes to \u221a((\u03b3\u22121)/2\u03b3)."))
    return r


# ---------------------------------------------------------------------------
# 3. Oblique shock
# ---------------------------------------------------------------------------


def _oblique_shock(inp):
    g, R, gas = gas_properties(inp)
    M1 = inp["M1"]
    if M1 <= 1:
        raise CalculationError("An oblique shock requires supersonic upstream flow (M\u2081 > 1).")

    theta_max, beta_at_max = cf.max_deflection(M1, g)
    theta_sonic = cf.sonic_deflection(M1, g)

    if inp["mode"] == "theta":
        theta = math.radians(inp["theta"])
        if theta < 0:
            raise CalculationError("The deflection angle must be positive.")
        beta = cf.beta_from_theta(M1, theta, g, strong=(inp["branch"] == "strong"))
    else:
        beta = math.radians(inp["beta"])
        mu = math.asin(1.0 / M1)
        if not mu - 1e-9 <= beta <= math.pi / 2 + 1e-9:
            raise CalculationError(
                f"The wave angle must lie between the Mach angle "
                f"({math.degrees(mu):.3f}\u00b0) and 90\u00b0 at M\u2081 = {M1:g}.")
        theta = cf.theta_from_beta(M1, beta, g)

    Mn1 = M1 * math.sin(beta)
    Mn2 = cf.shock_M2(Mn1, g)
    M2 = Mn2 / math.sin(beta - theta) if abs(beta - theta) > 1e-12 else Mn2
    pr, tr = cf.shock_p_ratio(Mn1, g), cf.shock_T_ratio(Mn1, g)
    rr, p0r = cf.shock_rho_ratio(Mn1, g), cf.shock_p0_ratio(Mn1, g)

    r = Result()
    r.group("Wave geometry", f"{gas} \u2014 \u03b3 = {g:g}")
    r.headline("Wave angle", math.degrees(beta), "\u00b0", symbol="\u03b2")
    r.headline("Flow deflection", math.degrees(theta), "\u00b0", symbol="\u03b8")
    r.out("Solution branch", "strong" if beta > beta_at_max else "weak")
    r.out("Maximum deflection at this M\u2081", math.degrees(theta_max), "\u00b0",
          symbol="\u03b8\u2098\u2090\u2093",
          note=f"at \u03b2 = {math.degrees(beta_at_max):.3f}\u00b0")
    r.out("Deflection for sonic downstream flow", math.degrees(theta_sonic), "\u00b0",
          symbol="\u03b8*")

    r.group("Mach numbers")
    r.out("Upstream normal component", Mn1, symbol="M\u2099\u2081")
    r.out("Downstream normal component", Mn2, symbol="M\u2099\u2082")
    r.out("Downstream Mach number", M2, symbol="M\u2082")
    r.out("Downstream flow", "subsonic" if M2 < 1 else "supersonic")

    r.group("Jump conditions")
    r.out("Static pressure ratio", pr, symbol="p\u2082/p\u2081")
    r.out("Static temperature ratio", tr, symbol="T\u2082/T\u2081")
    r.out("Density ratio", rr, symbol="\u03c1\u2082/\u03c1\u2081")
    r.out("Total pressure ratio", p0r, symbol="p\u2080\u2082/p\u2080\u2081")
    r.out("Entropy rise", cf.shock_entropy_rise(Mn1, g, R), "J/(kg\u00b7K)", symbol="\u0394s")

    if inp["dimensional"]:
        p1, T1 = inp["p1"], inp["T1"]
        a1 = math.sqrt(g * R * T1)
        r.group("Dimensional conditions")
        r.out("Upstream velocity", M1 * a1, "m/s", symbol="V\u2081")
        r.out("Downstream velocity", M2 * math.sqrt(g * R * T1 * tr), "m/s", symbol="V\u2082")
        r.out("Static pressure downstream", p1 * pr, "Pa", symbol="p\u2082")
        r.out("Static temperature downstream", T1 * tr, "K", symbol="T\u2082")

    # theta-beta-M diagram
    series = []
    for i, m in enumerate(sorted({1.5, 2.0, 3.0, 5.0, round(M1, 4)})):
        if m <= 1:
            continue
        mu = math.degrees(math.asin(1.0 / m))
        bs = linspace(mu + 1e-6, 90.0, 400)
        ths = [math.degrees(cf.theta_from_beta(m, math.radians(b), g)) for b in bs]
        is_current = abs(m - M1) < 1e-9
        series.append({"x": ths, "y": bs, "label": f"M\u2081 = {m:g}",
                       "width": 2.4 if is_current else 1.3,
                       "color": "#B3242B" if is_current else None})
    for i, s in enumerate(series):
        if s["color"] is None:
            s["color"] = P.SERIES[i % len(P.SERIES)]

    tmax_line_x, tmax_line_y = [], []
    for m in linspace(1.02, 8.0, 200):
        tm, bm = cf.max_deflection(m, g)
        tmax_line_x.append(math.degrees(tm))
        tmax_line_y.append(math.degrees(bm))
    series.append({"x": tmax_line_x, "y": tmax_line_y, "label": "\u03b8\u2098\u2090\u2093 locus",
                   "style": "--", "color": P.MUTED, "width": 1.2})

    r.plot(**P.chart(
        series, xlabel="Deflection angle  \u03b8  [\u00b0]",
        ylabel="Wave angle  \u03b2  [\u00b0]", xlim=(0, 50), ylim=(0, 90),
        title="\u03b8\u2013\u03b2\u2013M diagram",
        points=[{"x": math.degrees(theta), "y": math.degrees(beta),
                 "label": "your solution"}],
        caption="Below the dashed locus the shock stays attached: the lower "
                "intersection is the weak solution, the upper one is the strong "
                "solution. Beyond it the shock detaches."))

    # Wedge sketch
    fig, ax = P.polar_orbit_figure(figsize=(6.6, 3.6))
    L = 1.0
    ax.plot([-0.7, 0], [0, 0], color=P.MUTED, lw=1.2)
    ax.plot([0, L * math.cos(theta)], [0, L * math.sin(theta)], color=P.INK, lw=2.4)
    ax.plot([0, L * 1.15 * math.cos(beta)], [0, L * 1.15 * math.sin(beta)],
            color="#B3242B", lw=2.0, linestyle="--")
    # Angle arcs mark theta against the wedge and beta against the shock. Every
    # label then goes in a region that is empty for any valid solution: theta
    # below the wedge with a leader, beta at the end of the shock, M2 below the
    # wedge tip. Small deflections squeeze the wedge angle to nothing, so no
    # text is ever placed inside it.
    def arc(angle, radius, color):
        ts = [angle * i / 48 for i in range(49)]
        ax.plot([radius * math.cos(t) for t in ts],
                [radius * math.sin(t) for t in ts],
                color=color, lw=1.0, zorder=3)

    arc(theta, 0.30, P.INK)
    arc(beta, 0.55, "#B3242B")

    ax_, ay = 0.30 * math.cos(theta / 2), 0.30 * math.sin(theta / 2)
    tx, ty = ax_ + 0.16, ay - 0.19
    ax.plot([ax_, tx - 0.01], [ay, ty + 0.02], color=P.MUTED, lw=0.8, zorder=3)
    ax.annotate(f"\u03b8 = {math.degrees(theta):.2f}\u00b0", (tx, ty),
                fontsize=9, color=P.INK, ha="left", va="center")

    ax.annotate(f"shock\n\u03b2 = {math.degrees(beta):.2f}\u00b0",
                (L * 1.15 * math.cos(beta), L * 1.15 * math.sin(beta)),
                xytext=(6, 2), textcoords="offset points",
                color="#B3242B", fontsize=9, ha="left", va="bottom")

    ax.annotate(f"M\u2081 = {M1:.4g}", (-0.66, 0.06), fontsize=9.5, color=P.INK)
    ax.annotate(f"M\u2082 = {M2:.4g}", (L * math.cos(theta), L * math.sin(theta)),
                xytext=(9, -5), textcoords="offset points",
                fontsize=9.5, color=P.INK, ha="left", va="top")

    top = max(L * 1.15 * math.sin(beta), L * math.sin(theta)) + 0.34
    ax.set_xlim(-0.75, 1.7)
    ax.set_ylim(-0.34, max(top, 0.8))
    ax.set_xticks([])
    ax.set_yticks([])
    r.plot(P.render(fig), "Flow geometry",
           "Wedge surface in black, shock wave dashed in red.")
    return r


# ---------------------------------------------------------------------------
# 4. Prandtl-Meyer expansion
# ---------------------------------------------------------------------------


def _expansion(inp):
    g, R, gas = gas_properties(inp)
    M1 = inp["M1"]
    if M1 < 1:
        raise CalculationError("An expansion fan requires supersonic flow (M\u2081 \u2265 1).")
    turn = math.radians(inp["turn"])
    nu1 = cf.prandtl_meyer(M1, g)
    nu2 = nu1 + turn
    M2 = cf.mach_from_nu(nu2, g)

    t_ratio = cf.t0_ratio(M1, g) / cf.t0_ratio(M2, g)
    p_ratio = cf.p0_ratio(M1, g) / cf.p0_ratio(M2, g)
    rho_ratio = cf.rho0_ratio(M1, g) / cf.rho0_ratio(M2, g)

    r = Result()
    r.group("Expansion", f"{gas} \u2014 \u03b3 = {g:g}")
    r.headline("Downstream Mach number", M2, symbol="M\u2082")
    r.out("Upstream Prandtl-Meyer angle", math.degrees(nu1), "\u00b0", symbol="\u03bd\u2081")
    r.out("Downstream Prandtl-Meyer angle", math.degrees(nu2), "\u00b0", symbol="\u03bd\u2082")
    r.out("Turn angle", math.degrees(turn), "\u00b0", symbol="\u0394\u03b8")
    r.out("Maximum possible turn from M\u2081",
          math.degrees(cf.nu_max(g) - nu1), "\u00b0",
          note="expansion into a vacuum")

    r.group("Fan geometry")
    r.out("Leading Mach line angle", math.degrees(cf.mach_angle(M1)), "\u00b0", symbol="\u03bc\u2081")
    r.out("Trailing Mach line angle", math.degrees(cf.mach_angle(M2)), "\u00b0", symbol="\u03bc\u2082")
    r.out("Fan included angle",
          math.degrees(cf.mach_angle(M1) - cf.mach_angle(M2) + turn), "\u00b0")

    r.group("Property changes", "The expansion is isentropic, so p\u2080, T\u2080 and \u03c1\u2080 are unchanged")
    r.out("Static pressure ratio", p_ratio, symbol="p\u2082/p\u2081")
    r.out("Static temperature ratio", t_ratio, symbol="T\u2082/T\u2081")
    r.out("Density ratio", rho_ratio, symbol="\u03c1\u2082/\u03c1\u2081")
    r.out("Velocity ratio", M2 / M1 * math.sqrt(t_ratio), symbol="V\u2082/V\u2081")
    r.out("Total pressure ratio", 1.0, symbol="p\u2080\u2082/p\u2080\u2081")

    if inp["dimensional"]:
        p1, T1 = inp["p1"], inp["T1"]
        r.group("Dimensional conditions")
        r.out("Downstream static pressure", p1 * p_ratio, "Pa", symbol="p\u2082")
        r.out("Downstream static temperature", T1 * t_ratio, "K", symbol="T\u2082")
        r.out("Upstream velocity", M1 * math.sqrt(g * R * T1), "m/s", symbol="V\u2081")
        r.out("Downstream velocity", M2 * math.sqrt(g * R * T1 * t_ratio), "m/s", symbol="V\u2082")

    ms = linspace(1.0, 12.0, 500)
    r.plot(**P.chart(
        [{"x": ms, "y": [math.degrees(cf.prandtl_meyer(m, g)) for m in ms],
          "label": "\u03bd(M)"},
         {"x": ms, "y": [math.degrees(cf.mach_angle(m)) for m in ms],
          "label": "\u03bc(M)", "color": P.SERIES[1]}],
        xlabel="Mach number  M", ylabel="Angle  [\u00b0]",
        title="Prandtl-Meyer function and Mach angle",
        hlines=[{"value": math.degrees(cf.nu_max(g)),
                 "label": f"\u03bd\u2098\u2090\u2093 = {math.degrees(cf.nu_max(g)):.2f}\u00b0"}],
        points=[{"x": M1, "y": math.degrees(nu1), "label": "upstream"},
                {"x": M2, "y": math.degrees(nu2), "label": "downstream",
                 "color": "#0E7C6B"}],
        caption="The turn angle is simply the vertical distance between the "
                "two points on the \u03bd curve."))
    return r


# ---------------------------------------------------------------------------
# 5. Fanno flow
# ---------------------------------------------------------------------------


def _fanno(inp):
    g, R, gas = gas_properties(inp)
    branch = inp["branch"]
    if inp["mode"] == "M":
        M1 = inp["value"]
        if M1 <= 0:
            raise CalculationError("Mach number must be positive.")
    else:
        M1 = cf.mach_from_fanno_fld(inp["value"], g, branch)

    fld1 = cf.fanno_fld(M1, g)
    r = Result()
    r.group("Inlet station", f"{gas} \u2014 \u03b3 = {g:g}")
    r.headline("Inlet Mach number", M1, symbol="M\u2081")
    r.out("Friction parameter to choking", fld1, symbol="4fL*/D")
    r.out("T\u2081/T*", cf.fanno_T(M1, g))
    r.out("p\u2081/p*", cf.fanno_p(M1, g))
    r.out("\u03c1\u2081/\u03c1*", cf.fanno_rho(M1, g))
    r.out("p\u2080\u2081/p\u2080*", cf.fanno_p0(M1, g))
    r.out("V\u2081/V*", cf.fanno_V(M1, g))
    r.out("(s* \u2212 s\u2081)/R", math.log(cf.fanno_p0(M1, g)))

    if inp["duct"]:
        f, L, D = inp["f"], inp["L"], inp["D"]
        if D <= 0:
            raise CalculationError("Duct diameter must be positive.")
        fld_duct = 4.0 * f * L / D
        r.group("Duct", f"4fL/D = {fld_duct:.6g} with Fanning f = {f:g}")
        r.out("Applied friction parameter", fld_duct, symbol="4fL/D")
        r.out("Maximum duct length before choking", fld1 * D / (4.0 * f), "m",
              symbol="L*")
        fld2 = fld1 - fld_duct
        if fld2 < -1e-12:
            r.note("The duct is longer than L*, so the flow chokes before the exit. "
                   "For subsonic flow the inlet Mach number would reduce (the duct "
                   "back-pressures the supply); for supersonic flow a shock appears "
                   "inside the duct.")
            r.out("Choked?", "yes \u2014 flow cannot pass this duct at the stated inlet Mach number")
        else:
            M2 = cf.mach_from_fanno_fld(fld2, g, branch)
            r.group("Exit station")
            r.headline("Exit Mach number", M2, symbol="M\u2082")
            r.out("p\u2082/p\u2081", cf.fanno_p(M2, g) / cf.fanno_p(M1, g))
            r.out("T\u2082/T\u2081", cf.fanno_T(M2, g) / cf.fanno_T(M1, g))
            r.out("\u03c1\u2082/\u03c1\u2081", cf.fanno_rho(M2, g) / cf.fanno_rho(M1, g))
            r.out("p\u2080\u2082/p\u2080\u2081", cf.fanno_p0(M2, g) / cf.fanno_p0(M1, g))
            r.out("Remaining length to choking", fld2 * D / (4.0 * f), "m")
            r.out("Entropy rise", -R * math.log(cf.fanno_p0(M2, g) / cf.fanno_p0(M1, g)),
                  "J/(kg\u00b7K)", symbol="\u0394s")

    sub = linspace(0.02, 0.999, 220)
    sup = linspace(1.001, 4.0, 220)
    r.plot(**P.chart(
        [{"x": sub, "y": [cf.fanno_fld(m, g) for m in sub], "label": "subsonic branch"},
         {"x": sup, "y": [cf.fanno_fld(m, g) for m in sup], "label": "supersonic branch",
          "color": P.SERIES[1]}],
        xlabel="Mach number  M", ylabel="4fL*/D", ylim=(0, 3),
        title="Fanno line: friction parameter to choking",
        points=[{"x": M1, "y": fld1, "label": "inlet"}],
        caption="Friction always drives the flow toward M = 1 from either branch."))

    # T-s Fanno line
    ms = linspace(0.05, 3.5, 400)
    ss = [math.log(cf.fanno_p0(m, g)) * -1 for m in ms]
    ts = [cf.fanno_T(m, g) for m in ms]
    r.plot(**P.chart(
        [{"x": ss, "y": ts, "label": "Fanno line"}],
        xlabel="(s \u2212 s*)/R", ylabel="T/T*",
        title="Fanno line on the T\u2013s plane",
        points=[{"x": -math.log(cf.fanno_p0(M1, g)), "y": cf.fanno_T(M1, g),
                 "label": "inlet"}],
        caption="The nose of the curve is the sonic point, where entropy is a "
                "maximum \u2014 friction cannot push flow past it."))
    return r


# ---------------------------------------------------------------------------
# 6. Rayleigh flow
# ---------------------------------------------------------------------------


def _rayleigh(inp):
    g, R, gas = gas_properties(inp)
    branch = inp["branch"]
    if inp["mode"] == "M":
        M1 = inp["value"]
    else:
        M1 = cf.mach_from_rayleigh_T0(inp["value"], g, branch)
    if M1 <= 0:
        raise CalculationError("Mach number must be positive.")

    r = Result()
    r.group("Inlet station", f"{gas} \u2014 \u03b3 = {g:g}")
    r.headline("Inlet Mach number", M1, symbol="M\u2081")
    r.out("T\u2080\u2081/T\u2080*", cf.rayleigh_T0(M1, g))
    r.out("T\u2081/T*", cf.rayleigh_T(M1, g))
    r.out("p\u2081/p*", cf.rayleigh_p(M1, g))
    r.out("\u03c1\u2081/\u03c1*", cf.rayleigh_rho(M1, g))
    r.out("p\u2080\u2081/p\u2080*", cf.rayleigh_p0(M1, g))
    r.out("V\u2081/V*", cf.rayleigh_V(M1, g))

    if inp["heat"]:
        T01, q = inp["T01"], inp["q"]
        cp = g * R / (g - 1.0)
        T0star = T01 / cf.rayleigh_T0(M1, g)
        q_max = cp * (T0star - T01)
        r.group("Heat addition", f"cp = {cp:.5g} J/(kg\u00b7K)")
        r.out("Sonic total temperature", T0star, "K", symbol="T\u2080*")
        r.out("Heat to thermally choke the duct", q_max, "J/kg", symbol="q\u2098\u2090\u2093")
        T02 = T01 + q / cp
        if T02 > T0star + 1e-9:
            r.note("The heat input exceeds q\u2098\u2090\u2093, so the duct thermally "
                   "chokes. The inlet conditions must change \u2014 mass flow reduces "
                   "for subsonic flow, or a shock forms for supersonic flow.")
            r.out("Thermally choked?", "yes")
        else:
            M2 = cf.mach_from_rayleigh_T0(T02 / T0star, g, branch)
            r.group("Exit station")
            r.headline("Exit Mach number", M2, symbol="M\u2082")
            r.out("Exit total temperature", T02, "K", symbol="T\u2080\u2082")
            r.out("p\u2082/p\u2081", cf.rayleigh_p(M2, g) / cf.rayleigh_p(M1, g))
            r.out("T\u2082/T\u2081", cf.rayleigh_T(M2, g) / cf.rayleigh_T(M1, g))
            r.out("p\u2080\u2082/p\u2080\u2081", cf.rayleigh_p0(M2, g) / cf.rayleigh_p0(M1, g),
                  note="total pressure always falls when heat is added")
            r.out("Fraction of choking heat used", q / q_max if q_max else float("nan"))

    ms = linspace(0.05, 4.0, 400)
    r.plot(**P.chart(
        [{"x": ms, "y": [cf.rayleigh_T0(m, g) for m in ms], "label": "T\u2080/T\u2080*"},
         {"x": ms, "y": [cf.rayleigh_T(m, g) for m in ms], "label": "T/T*",
          "color": P.SERIES[1]},
         {"x": ms, "y": [cf.rayleigh_p(m, g) for m in ms], "label": "p/p*",
          "color": P.SERIES[2]}],
        xlabel="Mach number  M", ylabel="Ratio", ylim=(0, 2.5),
        title="Rayleigh flow ratios",
        points=[{"x": M1, "y": cf.rayleigh_T0(M1, g), "label": "inlet"}],
        caption=f"T/T* peaks at M = 1/\u221a\u03b3 = {1 / math.sqrt(g):.4f}, "
                "where heating still raises T\u2080 but lowers T."))

    ss = []
    ts = []
    for m in ms:
        ts.append(cf.rayleigh_T(m, g))
        ss.append(math.log(cf.rayleigh_T(m, g) ** (g / (g - 1.0)) / cf.rayleigh_p(m, g)) / (g / (g - 1.0)))
    r.plot(**P.chart(
        [{"x": ss, "y": ts, "label": "Rayleigh line"}],
        xlabel="(s \u2212 s*)/cp", ylabel="T/T*",
        title="Rayleigh line on the T\u2013s plane",
        points=[{"x": ss[min(range(len(ms)), key=lambda i: abs(ms[i] - M1))],
                 "y": cf.rayleigh_T(M1, g), "label": "inlet"}],
        caption="Heating moves the state to the right along the curve toward "
                "the sonic point at the nose."))
    return r


# ---------------------------------------------------------------------------
# 7. Converging-diverging nozzle operation
# ---------------------------------------------------------------------------


def _cd_nozzle(inp):
    g, R, gas = gas_properties(inp)
    p0, T0 = inp["p0"], inp["T0"]
    ae_at, At, pb = inp["ae_at"], inp["At"], inp["pb"]
    if ae_at < 1:
        raise CalculationError("The exit-to-throat area ratio must be at least 1.")

    Me_sup = cf.mach_from_area_ratio(ae_at, g, "supersonic")
    Me_sub = cf.mach_from_area_ratio(ae_at, g, "subsonic")
    pe_sup = p0 / cf.p0_ratio(Me_sup, g)          # design (fully supersonic)
    pe_sub = p0 / cf.p0_ratio(Me_sub, g)          # first critical: choked, subsonic exit
    pe_shock_exit = pe_sup * cf.shock_p_ratio(Me_sup, g)   # normal shock at exit plane
    p_choke = p0 * cf.critical_pressure_ratio(g)
    Ae = ae_at * At

    r = Result()
    r.group("Nozzle", f"{gas} \u2014 \u03b3 = {g:g}, A\u2091/A* = {ae_at:g}")
    r.out("Throat area", At, "m\u00b2", symbol="A\u209c")
    r.out("Exit area", Ae, "m\u00b2", symbol="A\u2091")
    r.out("Design exit Mach number", Me_sup, symbol="M\u2091,design")
    r.out("Critical pressure ratio", cf.critical_pressure_ratio(g), symbol="p*/p\u2080")

    r.group("Operating boundaries", "Back pressures that separate the regimes")
    r.out("Choking begins (subsonic exit)", pe_sub, "Pa",
          note="p_b above this and the nozzle is an unchoked venturi")
    r.out("Normal shock at the exit plane", pe_shock_exit, "Pa")
    r.out("Design back pressure", pe_sup, "Pa", note="perfectly expanded")

    choked = pb <= pe_sub
    mdot = (cf.choked_mass_flow(p0, T0, At, g, R) if choked else
            _venturi_mass_flow(p0, T0, At, pb, g, R))

    if not choked:
        regime = "Unchoked venturi flow"
        Me = cf.mach_from_p0_ratio(p0 / pb, g)
        pe, Te = pb, T0 / cf.t0_ratio(Me, g)
        detail = ("The back pressure is too high to choke the throat. The nozzle "
                  "behaves as a venturi: flow accelerates to the throat and "
                  "decelerates again, staying subsonic throughout.")
        shock_ar = None
    elif pb > pe_shock_exit:
        regime = "Normal shock inside the divergent section"
        shock_ar = _find_shock_station(ae_at, pb, p0, g)
        Ms = cf.mach_from_area_ratio(shock_ar, g, "supersonic")
        p0_ratio_shock = cf.shock_p0_ratio(Ms, g)
        Me = cf.mach_from_area_ratio(ae_at / p0_ratio_shock, g, "subsonic")
        pe = pb
        Te = T0 / cf.t0_ratio(Me, g)
        detail = (f"A normal shock stands where A/A\u209c = {shock_ar:.4f} "
                  f"(M = {Ms:.4f} just upstream). Downstream of it the flow is "
                  "subsonic and diffuses to the back pressure.")
        r.group("Shock inside the nozzle")
        r.out("Shock station area ratio", shock_ar, symbol="A\u209b/A\u209c")
        r.out("Mach number upstream of shock", Ms, symbol="M\u209b")
        r.out("Mach number downstream of shock", cf.shock_M2(Ms, g))
        r.out("Total pressure recovery", p0_ratio_shock, symbol="p\u2080\u2082/p\u2080\u2081")
    elif abs(pb - pe_shock_exit) / pe_shock_exit < 1e-9:
        regime = "Normal shock exactly at the exit plane"
        Me, pe, Te = Me_sup, pe_sup, T0 / cf.t0_ratio(Me_sup, g)
        detail = "The shock sits on the exit plane; the nozzle interior is fully supersonic."
        shock_ar = ae_at
    elif pb > pe_sup:
        regime = "Overexpanded \u2014 oblique shocks outside the nozzle"
        Me, pe, Te = Me_sup, pe_sup, T0 / cf.t0_ratio(Me_sup, g)
        detail = ("The jet leaves at a pressure below ambient, so oblique shocks "
                  "form outside the exit plane to compress it back. Real nozzles "
                  "may separate internally in this regime.")
        shock_ar = None
    elif abs(pb - pe_sup) / pe_sup < 1e-9:
        regime = "Perfectly expanded (design point)"
        Me, pe, Te = Me_sup, pe_sup, T0 / cf.t0_ratio(Me_sup, g)
        detail = "The exit pressure matches ambient exactly \u2014 maximum thrust for this area ratio."
        shock_ar = None
    else:
        regime = "Underexpanded \u2014 expansion fans outside the nozzle"
        Me, pe, Te = Me_sup, pe_sup, T0 / cf.t0_ratio(Me_sup, g)
        detail = ("The jet leaves above ambient pressure and continues to expand "
                  "through Prandtl-Meyer fans downstream of the exit.")
        shock_ar = None

    Ve = Me * math.sqrt(g * R * Te)
    thrust = mdot * Ve + (pe - pb) * Ae

    r.group("Operating point")
    r.headline("Regime", regime)
    r.out("Back pressure ratio", pb / p0, symbol="p_b/p\u2080")
    r.out("Choked?", "yes" if choked else "no")
    r.out("Mass flow rate", mdot, "kg/s", symbol="\u1e41")
    r.out("Exit Mach number", Me, symbol="M\u2091")
    r.out("Exit pressure", pe, "Pa", symbol="p\u2091")
    r.out("Exit temperature", Te, "K", symbol="T\u2091")
    r.out("Exit velocity", Ve, "m/s", symbol="V\u2091")
    r.out("Thrust", thrust, "N", symbol="F",
          note="momentum + pressure terms")
    r.note(detail)

    # Pressure distribution along the nozzle
    x_conv = linspace(0.0, 1.0, 60)
    ar_conv = [3.0 - 2.0 * t for t in x_conv]              # convergent: A/At 3 -> 1
    x_div = linspace(1.0, 3.0, 200)
    ar_div = [1.0 + (ae_at - 1.0) * (t - 1.0) / 2.0 for t in x_div]

    def p_along(ar_list, x_list):
        out = []
        for ar in ar_list:
            m = cf.mach_from_area_ratio(max(ar, 1.0), g, "subsonic")
            out.append(1.0 / cf.p0_ratio(m, g))
        return out

    p_conv = p_along(ar_conv, x_conv)
    ideal_sup = [1.0 / cf.p0_ratio(cf.mach_from_area_ratio(max(a, 1.0), g, "supersonic"), g)
                 for a in ar_div]
    ideal_sub = [1.0 / cf.p0_ratio(cf.mach_from_area_ratio(max(a, 1.0), g, "subsonic"), g)
                 for a in ar_div]

    series = [{"x": x_conv, "y": p_conv, "color": P.INK, "label": "convergent section"}]
    series.append({"x": x_div, "y": ideal_sup, "style": ":", "color": P.MUTED,
                   "label": "ideal supersonic branch", "width": 1.2})
    series.append({"x": x_div, "y": ideal_sub, "style": "--", "color": P.MUTED,
                   "label": "ideal subsonic branch", "width": 1.2})

    actual = []
    if not choked:
        for a in ar_div:
            m = cf.mach_from_area_ratio(max(a, 1.0), g, "subsonic")
            actual.append(1.0 / cf.p0_ratio(m, g))
        # rescale so the exit matches pb/p0
        k = (pb / p0) / actual[-1]
        actual = [v * k for v in actual]
    elif shock_ar is not None and shock_ar < ae_at:
        Ms = cf.mach_from_area_ratio(shock_ar, g, "supersonic")
        p0r = cf.shock_p0_ratio(Ms, g)
        for a in ar_div:
            if a <= shock_ar:
                m = cf.mach_from_area_ratio(max(a, 1.0), g, "supersonic")
                actual.append(1.0 / cf.p0_ratio(m, g))
            else:
                m = cf.mach_from_area_ratio(max(a / p0r, 1.0), g, "subsonic")
                actual.append(p0r / cf.p0_ratio(m, g))
    else:
        actual = ideal_sup

    series.append({"x": x_div, "y": actual, "color": "#B3242B",
                   "label": "actual", "width": 2.3})

    r.plot(**P.chart(
        series, xlabel="Station along nozzle (throat at 1.0)",
        ylabel="p / p\u2080", ylim=(0, 1.05),
        title="Pressure distribution",
        hlines=[{"value": pb / p0, "label": "back pressure", "color": "#0E7C6B"}],
        vlines=[{"value": 1.0, "label": "throat"}],
        caption="The divergent section is drawn with a linear area distribution; "
                "the pressure at each station depends only on the local area ratio."))
    return r


def _venturi_mass_flow(p0, T0, At, pb, g, R):
    """Unchoked mass flow through the throat when the back pressure is too high."""
    Mt = cf.mach_from_p0_ratio(p0 / pb, g)
    Tt = T0 / cf.t0_ratio(Mt, g)
    rho = pb / (R * Tt)
    return rho * Mt * math.sqrt(g * R * Tt) * At


def _find_shock_station(ae_at, pb, p0, g):
    """Area ratio A_shock/A_t that puts the exit static pressure at pb."""
    def f(ar):
        Ms = cf.mach_from_area_ratio(ar, g, "supersonic")
        p0r = cf.shock_p0_ratio(Ms, g)
        Me = cf.mach_from_area_ratio(ae_at / p0r, g, "subsonic")
        return p0r * p0 / cf.p0_ratio(Me, g) - pb
    return solve(f, 1.0 + 1e-10, ae_at, what="shock location")


# ---------------------------------------------------------------------------
# 8. Shock tube
# ---------------------------------------------------------------------------


def _shock_tube(inp):
    g1, R1, gas1 = gas_properties(inp, "driven_")
    g4, R4, gas4 = gas_properties(inp, "driver_")
    p1, T1, p4, T4 = inp["p1"], inp["T1"], inp["p4"], inp["T4"]
    if p4 <= p1:
        raise CalculationError("The driver pressure p\u2084 must exceed the driven pressure p\u2081.")

    a1 = math.sqrt(g1 * R1 * T1)
    a4 = math.sqrt(g4 * R4 * T4)

    def term(p21):
        return ((g4 - 1.0) * (a1 / a4) * (p21 - 1.0) / math.sqrt(
            2.0 * g1 * (2.0 * g1 + (g1 + 1.0) * (p21 - 1.0))))

    # The driver gas can only expand so far: term -> 1 is the limiting shock
    # strength this driver can ever produce, and p4/p1 -> infinity there.
    p21_limit = solve(lambda x: term(x) - 1.0, 1.0 + 1e-12, 1e6,
                      what="limiting shock strength", expand=True)
    p21 = solve(lambda x: x * (1.0 - term(x)) ** (-2.0 * g4 / (g4 - 1.0)) - p4 / p1,
                1.0 + 1e-12, p21_limit * (1.0 - 1e-12),
                what="shock pressure ratio")
    Ms = math.sqrt((g1 + 1.0) / (2.0 * g1) * (p21 - 1.0) + 1.0)
    T21 = p21 * (((g1 + 1.0) / (g1 - 1.0)) + p21) / (1.0 + ((g1 + 1.0) / (g1 - 1.0)) * p21)
    rho21 = (1.0 + ((g1 + 1.0) / (g1 - 1.0)) * p21) / (((g1 + 1.0) / (g1 - 1.0)) + p21)
    up = a1 / g1 * (p21 - 1.0) * math.sqrt(
        (2.0 * g1 / (g1 + 1.0)) / (p21 + (g1 - 1.0) / (g1 + 1.0)))
    Ws = Ms * a1

    # Region 3: isentropic expansion of the driver gas, p3 = p2
    p34 = p21 * p1 / p4
    T3 = T4 * p34 ** ((g4 - 1.0) / g4)
    a3 = math.sqrt(g4 * R4 * T3)

    # Reflected shock
    def fr(mr):
        return (mr / (mr * mr - 1.0)
                - Ms / (Ms * Ms - 1.0) * math.sqrt(1.0 + 2.0 * (g1 - 1.0) / (g1 + 1.0) ** 2
                                                   * (Ms * Ms - 1.0) * (g1 + 1.0 / (Ms * Ms))))
    Mr = solve(fr, 1.0 + 1e-9, 20.0, what="reflected shock Mach number", expand=True)
    p52 = cf.shock_p_ratio(Mr, g1)
    T52 = cf.shock_T_ratio(Mr, g1)

    r = Result()
    r.group("Incident shock", f"Driver {gas4} \u2192 driven {gas1}")
    r.headline("Incident shock Mach number", Ms, symbol="M\u209b")
    r.out("Shock speed", Ws, "m/s", symbol="W\u209b")
    r.out("Pressure ratio across shock", p21, symbol="p\u2082/p\u2081")
    r.out("Temperature ratio across shock", T21, symbol="T\u2082/T\u2081")
    r.out("Density ratio across shock", rho21, symbol="\u03c1\u2082/\u03c1\u2081")
    r.out("Diaphragm pressure ratio", p4 / p1, symbol="p\u2084/p\u2081")

    r.group("Region 2 \u2014 shocked test gas")
    r.out("Pressure", p1 * p21, "Pa", symbol="p\u2082")
    r.out("Temperature", T1 * T21, "K", symbol="T\u2082")
    r.out("Particle (contact surface) velocity", up, "m/s", symbol="u\u209a")
    r.out("Flow Mach number behind shock", up / math.sqrt(g1 * R1 * T1 * T21), "M\u2082")

    r.group("Region 3 \u2014 expanded driver gas")
    r.out("Pressure", p1 * p21, "Pa", symbol="p\u2083", note="p\u2083 = p\u2082 across the contact surface")
    r.out("Temperature", T3, "K", symbol="T\u2083")
    r.out("Expansion fan head speed", -a4, "m/s", note="travels into the driver")
    r.out("Expansion fan tail speed", up - a3, "m/s")

    r.group("Reflected shock (end wall)")
    r.out("Reflected shock Mach number", Mr, symbol="M_R")
    r.out("Pressure", p1 * p21 * p52, "Pa", symbol="p\u2085")
    r.out("Temperature", T1 * T21 * T52, "K", symbol="T\u2085",
          note="the stagnant, high-enthalpy test slug")

    # x-t wave diagram
    t = 1.0
    fig, ax = P.new_axes(figsize=(6.6, 4.4))
    ax.plot([0, Ws * t], [0, t], color="#B3242B", lw=2.2, label="incident shock")
    ax.plot([0, up * t], [0, t], color="#0E7C6B", lw=2.0, ls="--", label="contact surface")
    ax.plot([0, -a4 * t], [0, t], color="#16497E", lw=1.8, label="expansion head")
    ax.plot([0, (up - a3) * t], [0, t], color="#16497E", lw=1.4, ls=":",
            label="expansion tail")
    for frac in (0.25, 0.5, 0.75):
        sp = -a4 + frac * ((up - a3) + a4)
        ax.plot([0, sp * t], [0, t], color="#16497E", lw=0.6, alpha=0.45)
    ax.axhline(0, color=P.MUTED, lw=0.8)
    ax.axvline(0, color=P.MUTED, lw=0.8, ls="--")
    ax.annotate("4", (-a4 * 0.75, 0.35), fontsize=11, color=P.INK)
    ax.annotate("3", (up * 0.35 - a3 * 0.15, 0.72), fontsize=11, color=P.INK)
    ax.annotate("2", ((up + Ws) * 0.5 * 0.75, 0.72), fontsize=11, color=P.INK)
    ax.annotate("1", (Ws * 0.85, 0.25), fontsize=11, color=P.INK)
    P.style_axes(ax, xlabel="Distance from diaphragm  x  [m]", ylabel="Time  t  [s]",
                 title="Wave diagram", legend=True)
    r.plot(P.render(fig), "x\u2013t wave diagram",
           "Numbers mark the four classical shock-tube regions. Distances are "
           "shown for one second of travel.")
    return r


# ---------------------------------------------------------------------------
# 9. Gas tables
# ---------------------------------------------------------------------------

_TABLE_KINDS = [
    ("isentropic", "Isentropic flow"),
    ("shock", "Normal shock"),
    ("fanno", "Fanno flow (friction)"),
    ("rayleigh", "Rayleigh flow (heat addition)"),
    ("pm", "Prandtl-Meyer expansion"),
]


def _gas_tables(inp):
    g, R, gas = gas_properties(inp)
    m0, m1, step = inp["m_start"], inp["m_end"], inp["m_step"]
    kind = inp["kind"]
    if step <= 0:
        raise CalculationError("The Mach number step must be positive.")
    if m1 <= m0:
        raise CalculationError("The ending Mach number must exceed the starting value.")
    n = int(round((m1 - m0) / step)) + 1
    if n > 2000:
        raise CalculationError(
            f"That range and step would produce {n} rows. Use a coarser step "
            "or a narrower range (2000 rows maximum).")

    machs = [m0 + i * step for i in range(n)]
    r = Result()

    if kind == "isentropic":
        cols = ["M", "p/p\u2080", "\u03c1/\u03c1\u2080", "T/T\u2080", "A/A*", "p\u2080/p", "T\u2080/T", "M*"]
        rows = []
        for M in machs:
            if M <= 0:
                continue
            rows.append([M, 1 / cf.p0_ratio(M, g), 1 / cf.rho0_ratio(M, g),
                         1 / cf.t0_ratio(M, g), cf.area_ratio(M, g),
                         cf.p0_ratio(M, g), cf.t0_ratio(M, g),
                         math.sqrt((g + 1) * M * M / (2 + (g - 1) * M * M))])
        title = "Isentropic flow table"
    elif kind == "shock":
        cols = ["M\u2081", "M\u2082", "p\u2082/p\u2081", "\u03c1\u2082/\u03c1\u2081", "T\u2082/T\u2081",
                "p\u2080\u2082/p\u2080\u2081", "p\u2080\u2082/p\u2081"]
        rows = []
        for M in machs:
            if M < 1:
                continue
            rows.append([M, cf.shock_M2(M, g), cf.shock_p_ratio(M, g),
                         cf.shock_rho_ratio(M, g), cf.shock_T_ratio(M, g),
                         cf.shock_p0_ratio(M, g), cf.rayleigh_pitot(M, g)])
        title = "Normal shock table"
    elif kind == "fanno":
        cols = ["M", "T/T*", "p/p*", "\u03c1/\u03c1*", "p\u2080/p\u2080*", "V/V*", "4fL*/D"]
        rows = []
        for M in machs:
            if M <= 0:
                continue
            rows.append([M, cf.fanno_T(M, g), cf.fanno_p(M, g), cf.fanno_rho(M, g),
                         cf.fanno_p0(M, g), cf.fanno_V(M, g), cf.fanno_fld(M, g)])
        title = "Fanno flow table"
    elif kind == "rayleigh":
        cols = ["M", "T\u2080/T\u2080*", "T/T*", "p/p*", "\u03c1/\u03c1*", "p\u2080/p\u2080*", "V/V*"]
        rows = []
        for M in machs:
            if M <= 0:
                continue
            rows.append([M, cf.rayleigh_T0(M, g), cf.rayleigh_T(M, g),
                         cf.rayleigh_p(M, g), cf.rayleigh_rho(M, g),
                         cf.rayleigh_p0(M, g), cf.rayleigh_V(M, g)])
        title = "Rayleigh flow table"
    else:
        cols = ["M", "\u03bd [\u00b0]", "\u03bc [\u00b0]", "p/p\u2080", "T/T\u2080", "A/A*"]
        rows = []
        for M in machs:
            if M < 1:
                continue
            rows.append([M, math.degrees(cf.prandtl_meyer(M, g)),
                         math.degrees(cf.mach_angle(M)),
                         1 / cf.p0_ratio(M, g), 1 / cf.t0_ratio(M, g),
                         cf.area_ratio(M, g)])
        title = "Prandtl-Meyer expansion table"

    if not rows:
        raise CalculationError(
            "No rows fall inside the valid Mach range for this table "
            "(shock and expansion tables require M \u2265 1).")

    r.group("Table")
    r.out("Table type", title)
    r.out("Working gas", f"{gas} (\u03b3 = {g:g})")
    r.out("Rows generated", len(rows))
    r.out("Mach range", f"{rows[0][0]:g} to {rows[-1][0]:g}, step {step:g}")
    r.out("Significant figures", inp["sig"])
    r.table(f"{title} \u2014 \u03b3 = {g:g}", cols, rows, sig=int(inp["sig"]),
            caption="Use the download button to export this table as CSV.")
    return r


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

CALCULATORS = [
    {
        "id": "isentropic-flow",
        "name": "Isentropic flow relations",
        "category": CATEGORY,
        "summary": "Property ratios, area ratio and angles from any single flow variable.",
        "description": "Solves the full isentropic set from whichever variable you know — "
                       "Mach number, a pressure or temperature ratio, an area ratio on "
                       "either branch, or a wave angle.",
        "tags": ["isentropic", "stagnation", "area ratio", "nozzle", "Mach"],
        "inputs": _gas_fields() + [
            choice("mode", "Known variable", _ISEN_MODES, "M", section="Input"),
            num("value", "Value of the known variable", 2.0, minimum=0.0, section="Input",
                help="Angles are in degrees."),
            toggle("dimensional", "Also compute dimensional conditions", True,
                   section="Static conditions"),
            num("p", "Static pressure p", 101325.0, "Pa", minimum=1e-6,
                section="Static conditions", show_if={"key": "dimensional", "in": [True]}),
            num("T", "Static temperature T", 288.15, "K", minimum=1e-3,
                section="Static conditions", show_if={"key": "dimensional", "in": [True]}),
        ],
        "compute": _isentropic,
        "references": ["NACA Report 1135, Equations (44)–(48)",
                       "Anderson, Modern Compressible Flow, Ch. 3"],
    },
    {
        "id": "normal-shock",
        "name": "Normal shock",
        "category": CATEGORY,
        "summary": "Jump conditions, total pressure loss and entropy rise across a normal shock.",
        "tags": ["shock", "Rankine-Hugoniot", "pitot", "total pressure"],
        "inputs": _gas_fields() + [
            choice("mode", "Known variable", _NS_MODES, "M1", section="Input"),
            num("value", "Value of the known variable", 2.0, minimum=0.0, section="Input"),
            toggle("dimensional", "Also compute dimensional conditions", True,
                   section="Upstream conditions"),
            num("p1", "Upstream static pressure p\u2081", 101325.0, "Pa", minimum=1e-6,
                section="Upstream conditions", show_if={"key": "dimensional", "in": [True]}),
            num("T1", "Upstream static temperature T\u2081", 288.15, "K", minimum=1e-3,
                section="Upstream conditions", show_if={"key": "dimensional", "in": [True]}),
        ],
        "compute": _normal_shock,
        "references": ["NACA Report 1135, Equations (93)–(100)"],
    },
    {
        "id": "oblique-shock",
        "name": "Oblique shock",
        "category": CATEGORY,
        "summary": "Exact θ–β–M solution with weak/strong branches and detachment check.",
        "description": "Solves the theta-beta-Mach relation exactly rather than from a chart, "
                       "reports the maximum attached deflection, and draws the θ–β–M diagram "
                       "with your solution marked.",
        "tags": ["oblique", "wedge", "theta-beta-M", "detachment", "supersonic"],
        "inputs": _gas_fields() + [
            num("M1", "Upstream Mach number M\u2081", 3.0, minimum=1.0, section="Flow"),
            choice("mode", "Specify", [("theta", "Deflection angle \u03b8"),
                                       ("beta", "Wave angle \u03b2")], "theta",
                   section="Flow"),
            num("theta", "Deflection angle \u03b8", 20.0, "\u00b0", minimum=0.0, maximum=89.0,
                section="Flow", show_if={"key": "mode", "in": ["theta"]}),
            choice("branch", "Shock branch", [("weak", "Weak (usual case)"),
                                              ("strong", "Strong")], "weak",
                   section="Flow", show_if={"key": "mode", "in": ["theta"]}),
            num("beta", "Wave angle \u03b2", 40.0, "\u00b0", minimum=0.0, maximum=90.0,
                section="Flow", show_if={"key": "mode", "in": ["beta"]}),
            toggle("dimensional", "Also compute dimensional conditions", False,
                   section="Upstream conditions"),
            num("p1", "Upstream static pressure p\u2081", 101325.0, "Pa", minimum=1e-6,
                section="Upstream conditions", show_if={"key": "dimensional", "in": [True]}),
            num("T1", "Upstream static temperature T\u2081", 288.15, "K", minimum=1e-3,
                section="Upstream conditions", show_if={"key": "dimensional", "in": [True]}),
        ],
        "compute": _oblique_shock,
    },
    {
        "id": "prandtl-meyer",
        "name": "Prandtl-Meyer expansion",
        "category": CATEGORY,
        "summary": "Supersonic expansion around a corner: downstream Mach number and fan geometry.",
        "tags": ["expansion", "corner", "isentropic", "nu", "Mach angle"],
        "inputs": _gas_fields() + [
            num("M1", "Upstream Mach number M\u2081", 2.0, minimum=1.0, section="Flow"),
            num("turn", "Turn angle \u0394\u03b8", 15.0, "\u00b0", minimum=0.0, section="Flow",
                help="The angle through which the wall turns away from the flow."),
            toggle("dimensional", "Also compute dimensional conditions", False,
                   section="Upstream conditions"),
            num("p1", "Upstream static pressure p\u2081", 101325.0, "Pa", minimum=1e-6,
                section="Upstream conditions", show_if={"key": "dimensional", "in": [True]}),
            num("T1", "Upstream static temperature T\u2081", 288.15, "K", minimum=1e-3,
                section="Upstream conditions", show_if={"key": "dimensional", "in": [True]}),
        ],
        "compute": _expansion,
    },
    {
        "id": "fanno-flow",
        "name": "Fanno flow (friction in a duct)",
        "category": CATEGORY,
        "summary": "Adiabatic constant-area flow with wall friction, including duct sizing.",
        "tags": ["Fanno", "friction", "duct", "choking", "4fL/D"],
        "inputs": _gas_fields() + [
            choice("mode", "Known variable", [("M", "Mach number"),
                                              ("fld", "Friction parameter 4fL*/D")],
                   "M", section="Inlet"),
            num("value", "Value", 0.3, minimum=0.0, section="Inlet"),
            choice("branch", "Branch", [("subsonic", "Subsonic"),
                                        ("supersonic", "Supersonic")], "subsonic",
                   section="Inlet"),
            toggle("duct", "Solve a specific duct", True, section="Duct"),
            num("f", "Fanning friction factor f", 0.005, minimum=1e-6, section="Duct",
                show_if={"key": "duct", "in": [True]},
                help="Fanning f = Darcy f / 4."),
            num("L", "Duct length L", 10.0, "m", minimum=0.0, section="Duct",
                show_if={"key": "duct", "in": [True]}),
            num("D", "Hydraulic diameter D", 0.1, "m", minimum=1e-9, section="Duct",
                show_if={"key": "duct", "in": [True]}),
        ],
        "compute": _fanno,
    },
    {
        "id": "rayleigh-flow",
        "name": "Rayleigh flow (heat addition)",
        "category": CATEGORY,
        "summary": "Frictionless constant-area flow with heating, including thermal choking.",
        "tags": ["Rayleigh", "heat", "combustor", "thermal choking"],
        "inputs": _gas_fields() + [
            choice("mode", "Known variable", [("M", "Mach number"),
                                              ("t0", "Total temperature ratio T\u2080/T\u2080*")],
                   "M", section="Inlet"),
            num("value", "Value", 0.3, minimum=0.0, section="Inlet"),
            choice("branch", "Branch", [("subsonic", "Subsonic"),
                                        ("supersonic", "Supersonic")], "subsonic",
                   section="Inlet"),
            toggle("heat", "Add a specific heat input", True, section="Heat addition"),
            num("T01", "Inlet total temperature T\u2080\u2081", 300.0, "K", minimum=1.0,
                section="Heat addition", show_if={"key": "heat", "in": [True]}),
            num("q", "Heat added per unit mass q", 500000.0, "J/kg",
                section="Heat addition", show_if={"key": "heat", "in": [True]}),
        ],
        "compute": _rayleigh,
    },
    {
        "id": "cd-nozzle",
        "name": "Converging-diverging nozzle",
        "category": CATEGORY,
        "summary": "Operating regime, shock position, mass flow and thrust from the back pressure.",
        "description": "Classifies the nozzle operating regime, locates an internal normal "
                       "shock if one exists, and plots the pressure distribution against the "
                       "two ideal branches.",
        "tags": ["nozzle", "choking", "overexpanded", "underexpanded", "thrust"],
        "inputs": _gas_fields() + [
            num("p0", "Reservoir total pressure p\u2080", 1000000.0, "Pa", minimum=1.0,
                section="Reservoir"),
            num("T0", "Reservoir total temperature T\u2080", 800.0, "K", minimum=1.0,
                section="Reservoir"),
            num("At", "Throat area A\u209c", 0.01, "m\u00b2", minimum=1e-12, section="Geometry"),
            num("ae_at", "Exit / throat area ratio A\u2091/A\u209c", 4.0, minimum=1.0,
                section="Geometry"),
            num("pb", "Back (ambient) pressure p_b", 101325.0, "Pa", minimum=1e-6,
                section="Environment"),
        ],
        "compute": _cd_nozzle,
    },
    {
        "id": "shock-tube",
        "name": "Shock tube",
        "category": CATEGORY,
        "summary": "Incident and reflected shock strength, contact surface and expansion fan.",
        "description": "Solves the shock-tube equation for the diaphragm pressure ratio, "
                       "including different driver and driven gases, and draws the x–t wave diagram.",
        "tags": ["shock tube", "Riemann", "wave diagram", "reflected shock", "test gas"],
        "inputs": [
            choice("driver_gas", "Driver gas (region 4)", GAS_OPTIONS, "he",
                   section="Driver \u2014 high pressure"),
            num("driver_gamma", "Driver \u03b3", 1.667, minimum=1.001,
                section="Driver \u2014 high pressure",
                show_if={"key": "driver_gas", "in": ["custom"]}),
            num("driver_R", "Driver R", 2077.1, "J/(kg\u00b7K)", minimum=1.0,
                section="Driver \u2014 high pressure",
                show_if={"key": "driver_gas", "in": ["custom"]}),
            num("p4", "Driver pressure p\u2084", 2000000.0, "Pa", minimum=1.0,
                section="Driver \u2014 high pressure"),
            num("T4", "Driver temperature T\u2084", 300.0, "K", minimum=1.0,
                section="Driver \u2014 high pressure"),
            choice("driven_gas", "Driven gas (region 1)", GAS_OPTIONS, "air",
                   section="Driven \u2014 low pressure"),
            num("driven_gamma", "Driven \u03b3", 1.4, minimum=1.001,
                section="Driven \u2014 low pressure",
                show_if={"key": "driven_gas", "in": ["custom"]}),
            num("driven_R", "Driven R", 287.05287, "J/(kg\u00b7K)", minimum=1.0,
                section="Driven \u2014 low pressure",
                show_if={"key": "driven_gas", "in": ["custom"]}),
            num("p1", "Driven pressure p\u2081", 10000.0, "Pa", minimum=1e-6,
                section="Driven \u2014 low pressure"),
            num("T1", "Driven temperature T\u2081", 300.0, "K", minimum=1.0,
                section="Driven \u2014 low pressure"),
        ],
        "compute": _shock_tube,
    },
    {
        "id": "gas-tables",
        "name": "Gas tables",
        "category": CATEGORY,
        "summary": "Generate isentropic, shock, Fanno, Rayleigh or Prandtl-Meyer tables for any γ.",
        "description": "Builds the classical compressible-flow tables to your chosen Mach range, "
                       "step and precision, for any specific heat ratio. Export as CSV.",
        "tags": ["tables", "isentropic table", "shock table", "Fanno table",
                 "Rayleigh table", "CSV"],
        "inputs": _gas_fields() + [
            choice("kind", "Table", _TABLE_KINDS, "isentropic", section="Range"),
            num("m_start", "Starting Mach number", 0.0, minimum=0.0, section="Range"),
            num("m_end", "Ending Mach number", 5.0, minimum=0.0, section="Range"),
            num("m_step", "Step", 0.05, minimum=1e-6, section="Range"),
            integer("sig", "Significant figures", 6, minimum=3, maximum=12, section="Range"),
        ],
        "compute": _gas_tables,
    },
]
