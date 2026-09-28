"""Fluid dynamics: internal flow, flow measurement, similarity and viscous profiles."""

from __future__ import annotations

import math

from .. import compressible as cf
from .. import plotting as P
from ..core import CalculationError, Result, choice, num, toggle
from ..numeric import linspace, logspace, solve
from ..physics import G0, GAMMA_AIR, R_AIR, atmosphere, sutherland

CATEGORY = "Fluid Dynamics"

FLUIDS = {
    # key: (label, density [kg/m3], dynamic viscosity [Pa*s])
    "water20": ("Water at 20 \u00b0C", 998.2, 1.002e-3),
    "water80": ("Water at 80 \u00b0C", 971.8, 3.55e-4),
    "air_sl": ("Air at sea level, 15 \u00b0C", 1.225, 1.7894e-5),
    "jeta": ("Jet A-1 at 15 \u00b0C", 804.0, 1.68e-3),
    "rp1": ("RP-1 kerosene", 810.0, 1.90e-3),
    "lox": ("Liquid oxygen at 90 K", 1141.0, 1.95e-4),
    "lh2": ("Liquid hydrogen at 20 K", 70.8, 1.32e-5),
    "hydoil": ("Hydraulic oil (ISO VG 46)", 870.0, 4.0e-2),
    "custom": ("Custom fluid", 0.0, 0.0),
}

FLUID_OPTIONS = [(k, v[0]) for k, v in FLUIDS.items()]

ROUGHNESS = {
    "drawn": ("Drawn tubing / smooth", 1.5e-6),
    "steel": ("Commercial steel", 4.5e-5),
    "galv": ("Galvanised iron", 1.5e-4),
    "cast": ("Cast iron", 2.6e-4),
    "concrete": ("Concrete", 1.2e-3),
    "custom": ("Custom roughness", 0.0),
}


def _fluid(inp):
    key = inp.get("fluid", "water20")
    if key == "custom":
        rho, mu = inp["rho"], inp["mu"]
        if rho <= 0 or mu <= 0:
            raise CalculationError("Density and viscosity must both be positive.")
        return rho, mu, "Custom fluid"
    label, rho, mu = FLUIDS[key]
    return rho, mu, label


def colebrook(Re: float, rel_rough: float) -> float:
    """Darcy friction factor from the Colebrook-White equation, solved exactly."""
    if Re <= 0:
        raise CalculationError("Reynolds number must be positive.")
    if Re < 2300:
        return 64.0 / Re
    def f(x):  # x = 1/sqrt(f)
        return x + 2.0 * math.log10(rel_rough / 3.7 + 2.51 * x / Re)
    x = solve(f, 0.5, 40.0, what="friction factor", expand=True)
    return 1.0 / x ** 2


def _pipe_flow(inp):
    rho, mu, fluid_label = _fluid(inp)
    D, L = inp["D"], inp["L"]
    if D <= 0:
        raise CalculationError("The pipe diameter must be positive.")
    eps = (inp["eps"] if inp["roughness"] == "custom"
           else ROUGHNESS[inp["roughness"]][1])
    A = math.pi * D ** 2 / 4.0

    if inp["known"] == "Q":
        Q = inp["Q"]
        V = Q / A
    else:
        V = inp["V"]
        Q = V * A

    Re = rho * V * D / mu
    rel = eps / D
    f = colebrook(Re, rel)
    hf = f * L / D * V ** 2 / (2 * G0)
    dp = rho * G0 * hf
    K_minor = inp["K"] if inp["minor"] else 0.0
    h_minor = K_minor * V ** 2 / (2 * G0)

    r = Result()
    r.group("Flow", f"{fluid_label} in a {D * 1000:.4g} mm pipe")
    r.headline("Reynolds number", Re, symbol="Re")
    r.out("Flow regime", "laminar" if Re < 2300 else
          ("transitional" if Re < 4000 else "turbulent"),
          note="transition band is roughly 2300 < Re < 4000")
    r.out("Mean velocity", V, "m/s", symbol="V")
    r.out("Volumetric flow rate", Q, "m\u00b3/s", symbol="Q")
    r.out("Volumetric flow rate", Q * 3600, "m\u00b3/h")
    r.out("Mass flow rate", rho * Q, "kg/s", symbol="\u1e41")
    r.out("Cross-sectional area", A, "m\u00b2", symbol="A")

    r.group("Friction")
    r.headline("Darcy friction factor", f, symbol="f")
    r.out("Fanning friction factor", f / 4.0, symbol="C_f")
    r.out("Relative roughness", rel, symbol="\u03b5/D")
    r.out("Absolute roughness", eps * 1000, "mm", symbol="\u03b5")
    r.out("Wall shear stress", f * rho * V ** 2 / 8.0, "Pa", symbol="\u03c4_w")
    r.out("Friction velocity", math.sqrt(f / 8.0) * V, "m/s", symbol="u\u03c4")

    r.group("Losses", f"over {L:g} m")
    r.headline("Major head loss", hf, "m", symbol="h_f")
    r.headline("Pressure drop", dp, "Pa", symbol="\u0394p")
    r.out("Pressure drop", dp / 1e5, "bar")
    r.out("Pressure gradient", dp / L, "Pa/m")
    if inp["minor"]:
        r.out("Minor loss head", h_minor, "m", symbol="h_m", note=f"K = {K_minor:g}")
        r.out("Total head loss", hf + h_minor, "m")
        r.out("Total pressure drop", rho * G0 * (hf + h_minor), "Pa")
        r.out("Equivalent length of the fittings", K_minor * D / f, "m")
    r.out("Pumping power required", dp * Q, "W", symbol="P",
          note="ideal, at 100 % pump efficiency")

    res = logspace(600, 1e8, 400)
    series = []
    for rr in (0.0, 1e-5, 1e-4, 1e-3, 5e-3, 2e-2):
        ys = []
        for R_ in res:
            ys.append(64.0 / R_ if R_ < 2300 else colebrook(R_, rr))
        series.append({"x": res, "y": ys,
                       "label": "smooth" if rr == 0 else f"\u03b5/D = {rr:g}",
                       "width": 1.4})
    r.plot(**P.chart(
        series, xlabel="Reynolds number  Re", ylabel="Darcy friction factor  f",
        xlog=True, ylog=True, title="Moody chart",
        points=[{"x": Re, "y": f, "label": "your operating point"}],
        bands=[{"x0": 2300, "x1": 4000, "label": "transition"}],
        caption="Generated by solving Colebrook-White at every point rather than "
                "read off a printed chart."))
    return r


# ---------------------------------------------------------------------------
# 2. Flow meters
# ---------------------------------------------------------------------------


def _flow_meter(inp):
    rho, mu, fluid_label = _fluid(inp)
    D, d, dp = inp["D"], inp["d"], inp["dp"]
    if d >= D:
        raise CalculationError("The throat diameter must be smaller than the pipe diameter.")
    beta = d / D
    A2 = math.pi * d ** 2 / 4.0
    A1 = math.pi * D ** 2 / 4.0

    kind = inp["kind"]
    if kind == "venturi":
        Cd = inp["Cd"] if inp["custom_cd"] else 0.984
        loss_frac = 0.10 + 0.05 * beta
    elif kind == "orifice":
        Cd = inp["Cd"] if inp["custom_cd"] else 0.61
        loss_frac = (1 - beta ** 1.9)
    else:
        Cd = inp["Cd"] if inp["custom_cd"] else 0.99
        loss_frac = 0.15

    E = 1.0 / math.sqrt(1 - beta ** 4)
    Q_ideal = A2 * E * math.sqrt(2 * dp / rho)
    Q = Cd * Q_ideal
    V2 = Q / A2
    V1 = Q / A1
    Re_D = rho * V1 * D / mu

    r = Result()
    r.group("Meter", f"{dict(venturi='Venturi', orifice='Orifice plate', nozzle='Flow nozzle')[kind]}"
            f" \u2014 {fluid_label}")
    r.headline("Volumetric flow rate", Q, "m\u00b3/s", symbol="Q")
    r.out("Volumetric flow rate", Q * 3600, "m\u00b3/h")
    r.headline("Mass flow rate", rho * Q, "kg/s", symbol="\u1e41")
    r.out("Diameter ratio", beta, symbol="\u03b2 = d/D")
    r.out("Velocity of approach factor", E, symbol="E")
    r.out("Discharge coefficient", Cd, symbol="C_d")
    r.out("Flow coefficient", Cd * E, symbol="K = C_d\u00b7E")
    r.out("Ideal (Bernoulli) flow rate", Q_ideal, "m\u00b3/s")

    r.group("Velocities and pressures")
    r.out("Upstream velocity", V1, "m/s", symbol="V\u2081")
    r.out("Throat velocity", V2, "m/s", symbol="V\u2082")
    r.out("Measured differential pressure", dp, "Pa", symbol="\u0394p")
    r.out("Differential head", dp / (rho * G0), "m of fluid")
    r.out("Pipe Reynolds number", Re_D, symbol="Re_D")
    r.out("Throat Reynolds number", rho * V2 * d / mu, symbol="Re_d")

    r.group("Permanent loss")
    r.out("Permanent pressure loss", loss_frac * dp, "Pa",
          note="a venturi recovers most of the differential; an orifice does not")
    r.out("Loss as a fraction of \u0394p", loss_frac * 100, "%")
    r.out("Power dissipated", loss_frac * dp * Q, "W")
    if Re_D < 1e4:
        r.note("The pipe Reynolds number is below about 10\u2074, where discharge "
               "coefficients depend strongly on Re. Use a calibration curve for "
               "the specific meter rather than the standard value.")

    dps = linspace(dp * 0.05, dp * 2.0, 200)
    r.plot(**P.chart(
        [{"x": dps, "y": [Cd * A2 * E * math.sqrt(2 * x / rho) for x in dps],
          "label": "this meter"}],
        xlabel="Differential pressure  \u0394p  [Pa]",
        ylabel="Volumetric flow rate  Q  [m\u00b3/s]",
        title="Meter characteristic",
        points=[{"x": dp, "y": Q, "label": "operating point"}],
        caption="Q varies as \u221a\u0394p, so the turndown ratio of a differential "
                "pressure meter is limited \u2014 halving the flow quarters the signal."))
    return r


# ---------------------------------------------------------------------------
# 3. Pitot-static
# ---------------------------------------------------------------------------


def _pitot(inp):
    r = Result()
    if inp["fluid_kind"] == "liquid":
        rho = inp["rho_l"]
        dp = inp["dp"]
        V = math.sqrt(2 * dp / rho)
        r.group("Incompressible pitot", f"\u03c1 = {rho:g} kg/m\u00b3")
        r.headline("Velocity", V, "m/s", symbol="V")
        r.out("Dynamic pressure", dp, "Pa", symbol="q = p\u2080 \u2212 p")
        r.out("Velocity head", dp / (rho * G0), "m of fluid")
        return r

    p, T = inp["p"], inp["T"]
    g = GAMMA_AIR
    a = math.sqrt(g * R_AIR * T)
    rho = p / (R_AIR * T)
    qc = inp["dp"]

    ratio = qc / p + 1.0
    subsonic_limit = cf.p0_ratio(1.0, g)
    if ratio <= subsonic_limit:
        M = cf.mach_from_p0_ratio(ratio, g)
        method = "Isentropic (subsonic) relation"
    else:
        M = cf.mach_from_pitot(ratio, g)
        method = "Rayleigh pitot formula \u2014 a bow shock stands ahead of the probe"
    V = M * a
    V_inc = math.sqrt(2 * qc / rho)

    r.group("Compressible pitot", method)
    r.headline("Mach number", M, symbol="M")
    r.headline("True airspeed", V, "m/s", symbol="V")
    r.out("True airspeed", V / 0.514444444, "kt")
    r.out("Impact pressure", qc, "Pa", symbol="q_c = p\u2080 \u2212 p")
    r.out("Total pressure", p + qc, "Pa", symbol="p\u2080")
    r.out("Density", rho, "kg/m\u00b3", symbol="\u03c1")
    r.out("Speed of sound", a, "m/s", symbol="a")
    r.out("Dynamic pressure", 0.5 * rho * V * V, "Pa", symbol="q = \u00bd\u03c1V\u00b2")

    r.group("Comparison with the incompressible formula")
    r.out("Incompressible V = \u221a(2q_c/\u03c1)", V_inc, "m/s")
    r.out("Error of the incompressible formula", (V_inc - V) / V * 100, "%",
          note="under 1 % below about M = 0.3, which is where that limit comes from")
    if M > 1:
        r.out("Total pressure loss across the bow shock",
              1 - cf.shock_p0_ratio(M, g), "fraction",
              note="the probe reads p\u2080 behind the shock, not free-stream p\u2080")

    ms = linspace(0.05, 3.0, 300)
    r.plot(**P.chart(
        [{"x": ms, "y": [_pitot_err(m, g) for m in ms],
          "label": "error of \u221a(2q_c/\u03c1)"}],
        xlabel="Mach number  M", ylabel="Velocity error  [%]",
        title="Why the incompressible pitot formula fails",
        points=[{"x": M, "y": _pitot_err(M, g), "label": "your condition"}],
        hlines=[{"value": 1.0, "label": "1 % error"}],
        vlines=[{"value": 1.0, "label": "sonic", "color": "#B3242B"}],
        caption="Beyond M = 1 the reading is taken behind a bow shock, which is "
                "why the curve changes character there."))
    return r


def _pitot_err(M, g):
    qc_p = (cf.p0_ratio(M, g) - 1.0) if M <= 1 else (cf.rayleigh_pitot(M, g) - 1.0)
    # V_inc/V = sqrt(2*qc/rho) / (M*a);  qc/p = qc_p, rho = p/(RT), a^2 = gRT
    return (math.sqrt(2 * qc_p / g) / M - 1.0) * 100


# ---------------------------------------------------------------------------
# 4. Dimensionless numbers
# ---------------------------------------------------------------------------


def _dimensionless(inp):
    rho, mu, label = _fluid(inp)
    V, L = inp["V"], inp["L"]
    r = Result()
    nu = mu / rho

    r.group("Fluid and scale", label)
    r.out("Density", rho, "kg/m\u00b3", symbol="\u03c1")
    r.out("Dynamic viscosity", mu, "Pa\u00b7s", symbol="\u03bc")
    r.out("Kinematic viscosity", nu, "m\u00b2/s", symbol="\u03bd")
    r.out("Velocity", V, "m/s", symbol="V")
    r.out("Length scale", L, "m", symbol="L")

    r.group("Kinematic and dynamic groups")
    Re = rho * V * L / mu
    r.headline("Reynolds number", Re, symbol="Re = \u03c1VL/\u03bc",
               note="inertia / viscous forces")
    r.out("Froude number", V / math.sqrt(G0 * L), symbol="Fr = V/\u221a(gL)",
          note="inertia / gravity \u2014 governs free-surface waves")
    r.out("Euler number", inp["dp"] / (rho * V ** 2), symbol="Eu = \u0394p/(\u03c1V\u00b2)")
    r.out("Pressure coefficient", inp["dp"] / (0.5 * rho * V ** 2), symbol="C_p")
    r.out("Strouhal number", inp["f"] * L / V, symbol="St = fL/V",
          note="vortex shedding; St \u2248 0.21 for a cylinder above Re \u2248 1000")
    if inp["sigma"] > 0:
        r.out("Weber number", rho * V ** 2 * L / inp["sigma"],
              symbol="We = \u03c1V\u00b2L/\u03c3", note="inertia / surface tension")
        r.out("Capillary number", mu * V / inp["sigma"], symbol="Ca = \u03bcV/\u03c3")
    if inp["a"] > 0:
        M = V / inp["a"]
        r.out("Mach number", M, symbol="M = V/a")
        r.out("Cauchy number", M * M, symbol="Ca = \u03c1V\u00b2/K")

    if inp["thermal"]:
        k, cp, dT = inp["k"], inp["cp"], inp["dT"]
        alpha = k / (rho * cp)
        Pr = mu * cp / k
        r.group("Thermal groups")
        r.out("Prandtl number", Pr, symbol="Pr = \u03bc\u00b7c_p/k",
              note="momentum / thermal diffusivity")
        r.out("Thermal diffusivity", alpha, "m\u00b2/s", symbol="\u03b1")
        r.out("Peclet number", Re * Pr, symbol="Pe = Re\u00b7Pr")
        if inp["h"] > 0:
            r.out("Nusselt number", inp["h"] * L / k, symbol="Nu = hL/k")
            r.out("Biot number", inp["h"] * L / inp["k_solid"], symbol="Bi",
                  note="Bi < 0.1 justifies a lumped-capacitance model")
        if dT != 0:
            Gr = G0 * inp["beta"] * abs(dT) * L ** 3 / nu ** 2
            r.out("Grashof number", Gr, symbol="Gr")
            r.out("Rayleigh number", Gr * Pr, symbol="Ra = Gr\u00b7Pr",
                  note="natural convection turns turbulent near Ra \u2248 10\u2079")
            r.out("Richardson number", Gr / Re ** 2, symbol="Ri = Gr/Re\u00b2",
                  note="Ri \u226b 1 means buoyancy dominates forced convection")
    return r


# ---------------------------------------------------------------------------
# 5. Viscous flow profiles
# ---------------------------------------------------------------------------


def _viscous_profile(inp):
    rho, mu, label = _fluid(inp)
    h, U, dpdx = inp["h"], inp["U"], inp["dpdx"]
    if h <= 0:
        raise CalculationError("The gap height must be positive.")

    ys = linspace(0.0, h, 200)
    Pnd = -dpdx * h ** 2 / (2 * mu * U) if U != 0 else 0.0

    def u(y):
        return U * y / h - dpdx / (2 * mu) * y * (h - y)

    # The profile is a parabola, so the peak is available in closed form.
    # Reading it off a sampled grid instead would miss the true maximum by
    # roughly (grid spacing)^2 — about 1 part in 10^5 at 200 points.
    G = -dpdx / (2 * mu)
    if G != 0:
        y_star = h / 2 + U / (2 * G * h)
        if 0.0 < y_star < h:
            u_max = u(y_star)
        else:
            u_max = max(u(0.0), u(h))
    else:                                   # pure Couette: linear profile
        y_star = h if U >= 0 else 0.0
        u_max = max(u(0.0), u(h))

    us = [u(y) for y in ys]
    Q = U * h / 2 - dpdx * h ** 3 / (12 * mu)
    u_mean = Q / h
    tau_bottom = mu * (U / h - dpdx * h / (2 * mu))
    tau_top = mu * (U / h + dpdx * h / (2 * mu))
    Re = rho * abs(u_mean) * h / mu

    r = Result()
    r.group("Channel", f"{label}, gap h = {h * 1000:.4g} mm")
    r.headline("Volumetric flow per unit width", Q, "m\u00b2/s", symbol="q")
    r.out("Mean velocity", u_mean, "m/s", symbol="\u016b")
    r.out("Maximum velocity", u_max, "m/s", symbol="u\u2098\u2090\u2093")
    r.out("Reynolds number", Re, symbol="Re = \u03c1\u016bh/\u03bc",
          note="laminar theory holds below Re \u2248 1400 for a channel")
    r.out("Non-dimensional pressure gradient", Pnd, symbol="P")

    r.group("Wall shear")
    r.out("Shear stress at the stationary wall", tau_bottom, "Pa", symbol="\u03c4\u2080")
    r.out("Shear stress at the moving wall", tau_top, "Pa", symbol="\u03c4_h")
    r.out("Force per unit area to drag the plate", tau_top, "Pa")
    r.out("Power per unit area to drag the plate", tau_top * U, "W/m\u00b2")
    r.out("Viscous dissipation per unit volume",
          mu * sum(((us[i + 1] - us[i]) / (ys[i + 1] - ys[i])) ** 2
                   for i in range(len(ys) - 1)) / (len(ys) - 1), "W/m\u00b3")

    r.group("Limiting cases")
    r.out("Pure Couette flow rate (dp/dx = 0)", U * h / 2, "m\u00b2/s")
    r.out("Pure Poiseuille flow rate (U = 0)", -dpdx * h ** 3 / (12 * mu), "m\u00b2/s")
    if dpdx > 0 and U > 0:
        r.note("The pressure gradient opposes the moving wall, so the profile has "
               "a reverse-flow region near the stationary wall when P < \u22121.")

    series = [{"x": us, "y": [y / h for y in ys], "label": "your profile", "width": 2.4}]
    for pnd, lab in ((0.0, "P = 0 (pure Couette)"), (1.0, "P = 1"), (-1.0, "P = \u22121"),
                     (3.0, "P = 3")):
        if U == 0:
            break
        prof = [U * (y / h) + pnd * U * (y / h) * (1 - y / h) for y in ys]
        series.append({"x": prof, "y": [y / h for y in ys], "label": lab,
                       "width": 1.1, "style": "--"})
    r.plot(**P.chart(
        series, xlabel="Velocity  u  [m/s]", ylabel="y / h",
        title="Couette-Poiseuille velocity profile",
        vlines=[{"value": 0.0}],
        caption="A favourable pressure gradient (P > 0) fattens the profile; an "
                "adverse one (P < \u22121) drives reverse flow at the fixed wall."))
    return r


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_FLUID_FIELDS = [
    choice("fluid", "Fluid", FLUID_OPTIONS, "water20", section="Fluid"),
    num("rho", "Density", 998.2, "kg/m\u00b3", minimum=1e-9, section="Fluid",
        show_if={"key": "fluid", "in": ["custom"]}),
    num("mu", "Dynamic viscosity", 1.002e-3, "Pa\u00b7s", minimum=1e-12, section="Fluid",
        show_if={"key": "fluid", "in": ["custom"]}),
]

CALCULATORS = [
    {
        "id": "pipe-flow",
        "name": "Pipe flow and head loss",
        "category": CATEGORY,
        "summary": "Darcy-Weisbach losses with an exact Colebrook friction factor and Moody chart.",
        "description": "Solves Colebrook-White numerically at every point, including for the "
                       "whole Moody chart, so nothing is read off an approximation.",
        "tags": ["Darcy", "Colebrook", "Moody", "head loss", "friction factor"],
        "inputs": _FLUID_FIELDS + [
            num("D", "Internal diameter", 0.05, "m", minimum=1e-9, section="Pipe"),
            num("L", "Length", 100.0, "m", minimum=0.0, section="Pipe"),
            choice("roughness", "Wall material",
                   [(k, v[0]) for k, v in ROUGHNESS.items()], "steel", section="Pipe"),
            num("eps", "Absolute roughness", 4.5e-5, "m", minimum=0.0, section="Pipe",
                show_if={"key": "roughness", "in": ["custom"]}),
            choice("known", "Known quantity", [("Q", "Volumetric flow rate"),
                                               ("V", "Mean velocity")], "Q",
                   section="Flow"),
            num("Q", "Volumetric flow rate", 0.004, "m\u00b3/s", minimum=0.0,
                section="Flow", show_if={"key": "known", "in": ["Q"]}),
            num("V", "Mean velocity", 2.0, "m/s", minimum=0.0, section="Flow",
                show_if={"key": "known", "in": ["V"]}),
            toggle("minor", "Include minor losses", False, section="Fittings"),
            num("K", "Total loss coefficient \u03a3K", 2.0, minimum=0.0,
                section="Fittings", show_if={"key": "minor", "in": [True]}),
        ],
        "compute": _pipe_flow,
    },
    {
        "id": "flow-meter",
        "name": "Venturi, orifice and nozzle meters",
        "category": CATEGORY,
        "summary": "Flow rate from a differential pressure, with permanent loss.",
        "tags": ["venturi", "orifice", "discharge coefficient", "beta ratio", "Bernoulli"],
        "inputs": _FLUID_FIELDS + [
            choice("kind", "Meter type", [("venturi", "Venturi tube"),
                                          ("orifice", "Orifice plate"),
                                          ("nozzle", "Flow nozzle")], "venturi",
                   section="Meter"),
            num("D", "Pipe diameter D", 0.1, "m", minimum=1e-9, section="Meter"),
            num("d", "Throat diameter d", 0.05, "m", minimum=1e-9, section="Meter"),
            toggle("custom_cd", "Use a measured discharge coefficient", False,
                   section="Meter"),
            num("Cd", "Discharge coefficient C_d", 0.98, minimum=0.1, maximum=1.0,
                section="Meter", show_if={"key": "custom_cd", "in": [True]}),
            num("dp", "Differential pressure \u0394p", 20000.0, "Pa", minimum=1e-9,
                section="Measurement"),
        ],
        "compute": _flow_meter,
    },
    {
        "id": "pitot-static",
        "name": "Pitot-static probe",
        "category": CATEGORY,
        "summary": "Velocity from impact pressure, incompressible through supersonic.",
        "tags": ["pitot", "impact pressure", "Rayleigh", "airspeed", "probe"],
        "inputs": [
            choice("fluid_kind", "Working fluid", [("gas", "Air (compressible)"),
                                                   ("liquid", "Liquid (incompressible)")],
                   "gas", section="Fluid"),
            num("rho_l", "Density", 998.2, "kg/m\u00b3", minimum=1e-9, section="Fluid",
                show_if={"key": "fluid_kind", "in": ["liquid"]}),
            num("p", "Static pressure", 101325.0, "Pa", minimum=1e-6, section="Fluid",
                show_if={"key": "fluid_kind", "in": ["gas"]}),
            num("T", "Static temperature", 288.15, "K", minimum=1.0, section="Fluid",
                show_if={"key": "fluid_kind", "in": ["gas"]}),
            num("dp", "Measured differential pressure  p\u2080 \u2212 p", 5000.0, "Pa",
                minimum=0.0, section="Measurement"),
        ],
        "compute": _pitot,
    },
    {
        "id": "dimensionless-numbers",
        "name": "Dimensionless groups",
        "category": CATEGORY,
        "summary": "Reynolds, Froude, Weber, Strouhal, Prandtl, Nusselt, Grashof and more.",
        "tags": ["Reynolds", "Froude", "Weber", "Prandtl", "Nusselt", "Grashof", "similarity"],
        "inputs": _FLUID_FIELDS + [
            num("V", "Velocity", 2.0, "m/s", minimum=0.0, section="Scales"),
            num("L", "Length scale", 0.1, "m", minimum=1e-12, section="Scales"),
            num("dp", "Pressure difference", 1000.0, "Pa", section="Scales"),
            num("f", "Characteristic frequency", 10.0, "Hz", minimum=0.0, section="Scales"),
            num("sigma", "Surface tension", 0.0728, "N/m", minimum=0.0, section="Scales",
                help="Set to 0 to skip Weber and capillary numbers."),
            num("a", "Speed of sound", 0.0, "m/s", minimum=0.0, section="Scales",
                help="Set to 0 to skip Mach and Cauchy numbers."),
            toggle("thermal", "Include thermal groups", False, section="Thermal"),
            num("k", "Fluid thermal conductivity", 0.6, "W/(m\u00b7K)", minimum=1e-9,
                section="Thermal", show_if={"key": "thermal", "in": [True]}),
            num("cp", "Specific heat", 4182.0, "J/(kg\u00b7K)", minimum=1e-9,
                section="Thermal", show_if={"key": "thermal", "in": [True]}),
            num("h", "Convective coefficient", 500.0, "W/(m\u00b2\u00b7K)", minimum=0.0,
                section="Thermal", show_if={"key": "thermal", "in": [True]}),
            num("k_solid", "Solid thermal conductivity", 50.0, "W/(m\u00b7K)", minimum=1e-9,
                section="Thermal", show_if={"key": "thermal", "in": [True]}),
            num("dT", "Temperature difference", 20.0, "K", section="Thermal",
                show_if={"key": "thermal", "in": [True]}),
            num("beta", "Thermal expansion coefficient", 0.000207, "1/K", minimum=0.0,
                section="Thermal", show_if={"key": "thermal", "in": [True]}),
        ],
        "compute": _dimensionless,
    },
    {
        "id": "couette-poiseuille",
        "name": "Couette-Poiseuille channel flow",
        "category": CATEGORY,
        "summary": "Exact laminar velocity profile between a moving and a fixed wall.",
        "tags": ["Couette", "Poiseuille", "viscous", "profile", "shear stress", "bearing"],
        "inputs": _FLUID_FIELDS + [
            num("h", "Gap height", 0.002, "m", minimum=1e-9, section="Geometry"),
            num("U", "Velocity of the moving wall", 1.0, "m/s", section="Driving"),
            num("dpdx", "Pressure gradient dp/dx", -50000.0, "Pa/m", section="Driving",
                help="Negative drives flow in the positive x direction."),
        ],
        "compute": _viscous_profile,
    },
]
