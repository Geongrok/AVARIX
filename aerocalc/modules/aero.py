"""Aerodynamics: atmosphere, airspeeds, airfoil and wing theory, boundary layers."""

from __future__ import annotations

import math

import numpy as np

from .. import compressible as cf
from .. import plotting as P
from ..core import CalculationError, Result, choice, integer, num, toggle
from ..numeric import linspace, logspace, solve
from ..physics import (A0_SL, GAMMA_AIR, P0_SL, R_AIR, RHO_SL, T0_SL,
                       atmosphere, pressure_altitude, sutherland)

CATEGORY = "Aerodynamics"

FT = 0.3048
KT = 0.514444444


def _alt_fields(default_m=0.0, section="Flight condition"):
    return [
        num("altitude", "Altitude", default_m, minimum=-5000, maximum=86000,
            section=section),
        choice("alt_unit", "Altitude unit", [("m", "metres"), ("ft", "feet")], "m",
               section=section),
        num("dT", "Temperature offset from ISA", 0.0, "K", minimum=-60, maximum=60,
            section=section),
    ]


def _altitude_m(inp):
    z = inp["altitude"] * (FT if inp["alt_unit"] == "ft" else 1.0)
    if z < -5000 or z > 86000:
        raise CalculationError(
            "Altitude must be between -5000 m and 86 000 m (-16 404 ft to 282 152 ft).")
    return z


# ---------------------------------------------------------------------------
# 1. Standard atmosphere
# ---------------------------------------------------------------------------


def _standard_atmosphere(inp):
    if inp["mode"] == "pressure":
        z = pressure_altitude(inp["pressure"])
    else:
        z = _altitude_m(inp)
    a = atmosphere(z, dT=inp["dT"])

    r = Result()
    r.group("Altitude")
    r.headline("Geometric altitude", z, "m", symbol="z")
    r.out("Geometric altitude", z / FT, "ft")
    r.out("Geopotential altitude", a["h"], "m", symbol="H")
    r.out("Layer", _layer_name(a["h"]))
    r.out("Local gravity", a["g"], "m/s\u00b2", symbol="g")

    r.group("Properties", "U.S. Standard Atmosphere 1976"
            + (f", ISA{inp['dT']:+g} K" if inp["dT"] else ""))
    r.headline("Temperature", a["T"], "K", symbol="T")
    r.out("Temperature", a["T"] - 273.15, "\u00b0C")
    r.headline("Pressure", a["p"], "Pa", symbol="p")
    r.out("Pressure", a["p"] / 100.0, "hPa")
    r.headline("Density", a["rho"], "kg/m\u00b3", symbol="\u03c1")
    r.out("Speed of sound", a["a"], "m/s", symbol="a")
    r.out("Speed of sound", a["a"] / KT, "kt")
    r.out("Dynamic viscosity", a["mu"], "Pa\u00b7s", symbol="\u03bc")
    r.out("Kinematic viscosity", a["nu"], "m\u00b2/s", symbol="\u03bd")

    r.group("Ratios to sea level")
    r.out("Temperature ratio", a["theta"], symbol="\u03b8 = T/T\u2080")
    r.out("Pressure ratio", a["delta"], symbol="\u03b4 = p/p\u2080")
    r.out("Density ratio", a["sigma"], symbol="\u03c3 = \u03c1/\u03c1\u2080")
    r.out("\u221a\u03c3", math.sqrt(a["sigma"]),
          note="EAS = TAS \u00d7 \u221a\u03c3")

    if inp["with_speed"]:
        V = inp["V"] * (KT if inp["v_unit"] == "kt" else 1.0)
        r.group("Derived flow quantities", f"at V = {V:.4g} m/s")
        r.out("Mach number", V / a["a"], symbol="M")
        r.out("Dynamic pressure", 0.5 * a["rho"] * V * V, "Pa", symbol="q")
        r.out("Equivalent airspeed", V * math.sqrt(a["sigma"]), "m/s", symbol="EAS")
        if inp["L_ref"] > 0:
            r.out("Reynolds number per metre", a["rho"] * V / a["mu"], "1/m")
            r.out("Reynolds number", a["rho"] * V * inp["L_ref"] / a["mu"],
                  symbol="Re", note=f"L = {inp['L_ref']:g} m")

    zs = linspace(0.0, 86000.0, 400)
    props = [atmosphere(zz) for zz in zs]
    km = [zz / 1000.0 for zz in zs]
    r.plot(**P.stack([
        {"series": [{"x": [q["T"] for q in props], "y": km}],
         "xlabel": "T  [K]", "ylabel": "Geometric altitude  [km]",
         "title": "Temperature", "points": [{"x": a["T"], "y": z / 1000.0}]},
        {"series": [{"x": [q["p"] for q in props], "y": km, "color": P.SERIES[1]}],
         "xlabel": "p  [Pa]", "title": "Pressure", "xlog": True,
         "points": [{"x": a["p"], "y": z / 1000.0}]},
        {"series": [{"x": [q["rho"] for q in props], "y": km, "color": P.SERIES[2]}],
         "xlabel": "\u03c1  [kg/m\u00b3]", "title": "Density", "xlog": True,
         "points": [{"x": a["rho"], "y": z / 1000.0}]},
        {"series": [{"x": [q["a"] for q in props], "y": km, "color": P.SERIES[3]}],
         "xlabel": "a  [m/s]", "title": "Speed of sound",
         "points": [{"x": a["a"], "y": z / 1000.0}]},
    ], title="Standard atmosphere profiles", sharey=True,
        caption="Red markers show your altitude. The kinks are the layer boundaries "
                "at 11, 20, 32, 47, 51 and 71 km geopotential."))
    return r


def _layer_name(h):
    if h < 11000:
        return "Troposphere (lapse \u22126.5 K/km)"
    if h < 20000:
        return "Tropopause (isothermal)"
    if h < 32000:
        return "Lower stratosphere (lapse +1.0 K/km)"
    if h < 47000:
        return "Upper stratosphere (lapse +2.8 K/km)"
    if h < 51000:
        return "Stratopause (isothermal)"
    if h < 71000:
        return "Lower mesosphere (lapse \u22122.8 K/km)"
    return "Upper mesosphere (lapse \u22122.0 K/km)"


# ---------------------------------------------------------------------------
# 2. Airspeed conversions
# ---------------------------------------------------------------------------


def _qc_from_mach(M, p):
    """Impact pressure qc = p0_total - p_static, subsonic or supersonic."""
    if M <= 1.0:
        return p * (cf.p0_ratio(M, GAMMA_AIR) - 1.0)
    return p * (cf.rayleigh_pitot(M, GAMMA_AIR) - 1.0)


def _mach_from_qc(qc, p):
    if qc <= 0:
        return 0.0
    ratio = qc / p + 1.0
    if ratio <= cf.p0_ratio(1.0, GAMMA_AIR):
        return cf.mach_from_p0_ratio(ratio, GAMMA_AIR)
    return cf.mach_from_pitot(ratio, GAMMA_AIR)


def _airspeed(inp):
    z = _altitude_m(inp)
    atm = atmosphere(z, dT=inp["dT"])
    p, rho, a, sigma = atm["p"], atm["rho"], atm["a"], atm["sigma"]
    unit = KT if inp["v_unit"] == "kt" else 1.0
    known, value = inp["known"], inp["value"]

    if known == "mach":
        M = value
        V = M * a
    elif known == "tas":
        V = value * unit
        M = V / a
    elif known == "eas":
        V = value * unit / math.sqrt(sigma)
        M = V / a
    else:  # cas
        Vc = value * unit
        qc = _qc_from_mach(Vc / A0_SL, P0_SL)
        M = _mach_from_qc(qc, p)
        V = M * a

    qc = _qc_from_mach(M, p)
    Mc = _mach_from_qc(qc, P0_SL)
    CAS = Mc * A0_SL
    EAS = V * math.sqrt(sigma)
    q_true = 0.5 * rho * V * V
    q_inc = 0.5 * RHO_SL * EAS * EAS

    r = Result()
    r.group("Airspeeds", f"at {z:.0f} m ({z / FT:.0f} ft)"
            + (f", ISA{inp['dT']:+g} K" if inp["dT"] else ""))
    r.headline("Mach number", M, symbol="M")
    r.headline("True airspeed", V, "m/s", symbol="TAS")
    r.out("True airspeed", V / KT, "kt")
    r.out("True airspeed", V * 3.6, "km/h")
    r.headline("Calibrated airspeed", CAS, "m/s", symbol="CAS")
    r.out("Calibrated airspeed", CAS / KT, "kt")
    r.out("Equivalent airspeed", EAS, "m/s", symbol="EAS")
    r.out("Equivalent airspeed", EAS / KT, "kt")

    r.group("Pressures")
    r.out("Impact pressure", qc, "Pa", symbol="q_c",
          note="what the pitot-static system senses")
    r.out("Dynamic pressure", q_true, "Pa", symbol="q = \u00bd\u03c1V\u00b2")
    r.out("Incompressible q from EAS", q_inc, "Pa",
          note="equals q by definition of EAS")
    r.out("Total pressure", p + qc, "Pa", symbol="p\u2080")
    r.out("Static pressure", p, "Pa", symbol="p")
    r.out("Compressibility correction", CAS - EAS, "m/s", symbol="\u0394V_c",
          note="CAS \u2212 EAS; grows with altitude and Mach number")

    r.group("Atmosphere")
    r.out("Density", rho, "kg/m\u00b3", symbol="\u03c1")
    r.out("Density ratio", sigma, symbol="\u03c3")
    r.out("Speed of sound", a, "m/s", symbol="a")
    r.out("Temperature", atm["T"], "K", symbol="T")
    r.out("Total air temperature", atm["T"] * cf.t0_ratio(M, GAMMA_AIR), "K",
          symbol="TAT", note="ram rise at recovery factor 1.0")

    zs = linspace(0, 15000, 200)
    tas_line, eas_line = [], []
    for zz in zs:
        aa = atmosphere(zz, dT=inp["dT"])
        qc_z = _qc_from_mach(CAS / A0_SL, P0_SL)
        m_z = _mach_from_qc(qc_z, aa["p"])
        tas_line.append(m_z * aa["a"] / KT)
        eas_line.append(m_z * aa["a"] * math.sqrt(aa["sigma"]) / KT)
    r.plot(**P.chart(
        [{"x": tas_line, "y": [zz / 1000 for zz in zs], "label": "TAS"},
         {"x": eas_line, "y": [zz / 1000 for zz in zs], "label": "EAS"},
         {"x": [CAS / KT] * len(zs), "y": [zz / 1000 for zz in zs],
          "label": "CAS (held constant)", "style": "--", "color": P.MUTED}],
        xlabel="Airspeed  [kt]", ylabel="Altitude  [km]",
        title="Climbing at constant CAS",
        points=[{"x": V / KT, "y": z / 1000, "label": "your condition"}],
        caption="At constant calibrated airspeed, true airspeed rises with "
                "altitude while dynamic pressure falls."))
    return r


# ---------------------------------------------------------------------------
# 3. Reynolds number and similarity
# ---------------------------------------------------------------------------


def _similarity(inp):
    if inp["source"] == "atmosphere":
        z = _altitude_m(inp)
        atm = atmosphere(z, dT=inp["dT"])
        rho, mu, T, a = atm["rho"], atm["mu"], atm["T"], atm["a"]
        label = f"ISA at {z:.0f} m"
    else:
        T, p = inp["T"], inp["p"]
        rho = p / (R_AIR * T)
        mu = sutherland(T)
        a = math.sqrt(GAMMA_AIR * R_AIR * T)
        label = f"custom: p = {p:g} Pa, T = {T:g} K"

    V, L = inp["V"], inp["L"]
    Re = rho * V * L / mu
    M = V / a

    r = Result()
    r.group("Flow condition", label)
    r.headline("Reynolds number", Re, symbol="Re")
    r.headline("Mach number", M, symbol="M")
    r.out("Reynolds number per metre", rho * V / mu, "1/m")
    r.out("Density", rho, "kg/m\u00b3", symbol="\u03c1")
    r.out("Dynamic viscosity", mu, "Pa\u00b7s", symbol="\u03bc")
    r.out("Kinematic viscosity", mu / rho, "m\u00b2/s", symbol="\u03bd")
    r.out("Dynamic pressure", 0.5 * rho * V * V, "Pa", symbol="q")
    r.out("Knudsen number", 1.26 * math.sqrt(GAMMA_AIR) * M / Re, symbol="Kn",
          note="continuum flow requires Kn \u226a 0.01")

    r.group("Regime")
    r.out("Flow speed regime", _speed_regime(M))
    r.out("Boundary layer state (flat plate)",
          "laminar" if Re < 5e5 else ("transitional" if Re < 3e6 else "turbulent"),
          note="transition near Re \u2248 5\u00d710\u2075 on a smooth flat plate")

    if inp["scale"]:
        Lm = inp["L_model"]
        if Lm <= 0:
            raise CalculationError("The model length must be positive.")
        scale = Lm / L
        r.group("Model testing", f"Geometric scale {scale:.4g}")
        r.out("Velocity for Reynolds matching in the same air", V / scale, "m/s",
              note="often impractically fast \u2014 this is why tunnels pressurise or cool")
        r.out("Pressure for Re matching at the same V and T", rho / scale * R_AIR * T, "Pa")
        r.out("Velocity for Mach matching", V, "m/s",
              note="Mach scaling is independent of model size")

    res = logspace(1e2, 1e8, 300)
    r.plot(**P.chart(
        [{"x": res, "y": [_sphere_cd(x) for x in res], "label": "sphere"},
         {"x": res, "y": [_cylinder_cd(x) for x in res], "label": "circular cylinder"},
         {"x": res, "y": [1.328 / math.sqrt(x) if x < 5e5 else 0.074 / x ** 0.2 for x in res],
          "label": "flat plate C_f", "style": "--"}],
        xlabel="Reynolds number  Re", ylabel="Drag coefficient  C_D",
        xlog=True, ylog=True, title="Drag coefficient against Reynolds number",
        vlines=[{"value": Re, "label": "your Re", "color": "#B3242B"}],
        caption="The sudden drop near Re \u2248 3\u00d710\u2075 is the drag crisis, where the "
                "boundary layer turns turbulent and separation moves aft."))
    return r


def _speed_regime(M):
    if M < 0.3:
        return "incompressible (M < 0.3)"
    if M < 0.8:
        return "subsonic"
    if M < 1.2:
        return "transonic"
    if M < 5:
        return "supersonic"
    return "hypersonic (M > 5)"


def _sphere_cd(Re):
    """Standard sphere drag curve (Morrison correlation)."""
    return (24 / Re + 2.6 * (Re / 5.0) / (1 + (Re / 5.0) ** 1.52)
            + 0.411 * (Re / 263000) ** -7.94 / (1 + (Re / 263000) ** -8.00)
            + 0.25 * (Re / 1e6) / (1 + (Re / 1e6)))


def _cylinder_cd(Re):
    """Engineering fit to the circular-cylinder drag curve."""
    if Re < 1:
        return 8 * math.pi / (Re * (2 - math.log(Re))) if Re > 0.01 else 100.0
    if Re < 2e5:
        return 1.0 + 10.0 * Re ** (-2.0 / 3.0)
    if Re < 5e5:
        return 0.35
    return 0.7


# ---------------------------------------------------------------------------
# 4. NACA 4-digit airfoil, thin airfoil theory
# ---------------------------------------------------------------------------


def _naca4_geometry(code, n=200):
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    t = int(code[2:4]) / 100.0
    beta = linspace(0.0, math.pi, n)
    x = [(1 - math.cos(b)) / 2 for b in beta]

    def camber(xc):
        if p == 0 or m == 0:
            return 0.0, 0.0
        if xc < p:
            return m / p ** 2 * (2 * p * xc - xc ** 2), 2 * m / p ** 2 * (p - xc)
        return (m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * xc - xc ** 2),
                2 * m / (1 - p) ** 2 * (p - xc))

    yt = [5 * t * (0.2969 * math.sqrt(max(xc, 0)) - 0.1260 * xc - 0.3516 * xc ** 2
                   + 0.2843 * xc ** 3 - 0.1015 * xc ** 4) for xc in x]
    yc, dyc = zip(*[camber(xc) for xc in x])
    theta = [math.atan(d) for d in dyc]
    xu = [x[i] - yt[i] * math.sin(theta[i]) for i in range(n)]
    yu = [yc[i] + yt[i] * math.cos(theta[i]) for i in range(n)]
    xl = [x[i] + yt[i] * math.sin(theta[i]) for i in range(n)]
    yl = [yc[i] - yt[i] * math.cos(theta[i]) for i in range(n)]
    return {"m": m, "p": p, "t": t, "x": x, "yc": list(yc), "dyc": list(dyc),
            "xu": xu, "yu": yu, "xl": xl, "yl": yl, "yt": yt}


def _thin_airfoil(inp):
    n = int(inp["code"])
    if not 0 <= n <= 9999:
        raise CalculationError(
            "Enter a four-digit NACA designation, for example 2412 or 0012.")
    code = str(n).zfill(4)
    if int(code[2:4]) == 0:
        raise CalculationError(
            "The last two digits are the thickness in per cent chord and must "
            "not be zero. Try 2412 or 0012.")
    geo = _naca4_geometry(code)
    m, p = geo["m"], geo["p"]

    # Fourier coefficients of the camber slope
    N = 4000
    th = np.linspace(1e-9, math.pi - 1e-9, N)
    xc = (1 - np.cos(th)) / 2

    def slope(xv):
        if m == 0 or p == 0:
            return np.zeros_like(xv)
        out = np.where(xv < p,
                       2 * m / p ** 2 * (p - xv),
                       2 * m / (1 - p) ** 2 * (p - xv))
        return out

    dz = slope(xc)
    A1 = 2 / math.pi * np.trapezoid(dz * np.cos(th), th)
    A2 = 2 / math.pi * np.trapezoid(dz * np.cos(2 * th), th)

    alpha_L0 = -(1 / math.pi) * float(np.trapezoid(dz * (np.cos(th) - 1), th))
    cm_c4 = math.pi / 4 * (A2 - A1)

    alpha = math.radians(inp["alpha"])
    cl = 2 * math.pi * (alpha - alpha_L0)
    cm_le = -(cl / 4 + math.pi / 4 * (A1 - A2))
    x_cp = 0.25 - cm_c4 / cl if abs(cl) > 1e-9 else float("nan")

    r = Result()
    r.group("Airfoil", f"NACA {code}")
    r.out("Maximum camber", m * 100, "% chord")
    r.out("Position of maximum camber", p * 100, "% chord")
    r.out("Maximum thickness", geo["t"] * 100, "% chord")

    r.group("Thin airfoil theory")
    r.headline("Lift coefficient", cl, symbol="c_l")
    r.out("Angle of attack", inp["alpha"], "\u00b0", symbol="\u03b1")
    r.out("Zero-lift angle of attack", math.degrees(alpha_L0), "\u00b0",
          symbol="\u03b1_L0")
    r.out("Lift-curve slope", 2 * math.pi, "per rad", symbol="a\u2080",
          note=f"= {2 * math.pi * math.pi / 180:.5f} per degree")
    r.out("Moment about quarter chord", cm_c4, symbol="c_m,c/4",
          note="independent of \u03b1 \u2014 the quarter chord is the aerodynamic centre")
    r.out("Moment about leading edge", cm_le, symbol="c_m,LE")
    r.out("Centre of pressure", x_cp, "x/c", symbol="x_cp")
    r.out("Fourier coefficient A\u2081", A1)
    r.out("Fourier coefficient A\u2082", A2)

    if inp["with_compressibility"] and inp["M"] > 0:
        M = inp["M"]
        if M >= 1:
            raise CalculationError(
                "The Prandtl-Glauert correction applies only to subsonic flow (M < 1).")
        beta_pg = math.sqrt(1 - M * M)
        r.group("Compressibility", f"M = {M:g}")
        r.out("Prandtl-Glauert factor", 1 / beta_pg, symbol="1/\u03b2")
        r.out("Compressible lift coefficient", cl / beta_pg, symbol="c_l,comp")
        r.out("Compressible lift-curve slope", 2 * math.pi / beta_pg, "per rad")

    fig, ax = P.new_axes(figsize=(7.4, 2.8))
    ax.plot(geo["xu"], geo["yu"], color=P.INK, lw=2.0)
    ax.plot(geo["xl"], geo["yl"], color=P.INK, lw=2.0)
    ax.plot(geo["x"], geo["yc"], color="#B3242B", lw=1.4, ls="--", label="camber line")
    ax.plot([0, 1], [0, 0], color=P.MUTED, lw=0.8, ls=":")
    ax.plot([0.25], [0], marker="o", ms=5, color="#0E7C6B")
    ax.annotate("c/4", (0.25, 0), xytext=(4, 6), textcoords="offset points",
                fontsize=8.5, color="#0E7C6B")
    ax.set_aspect("equal")
    P.style_axes(ax, xlabel="x/c", ylabel="y/c", title=f"NACA {code} section",
                 legend=True)
    r.plot(P.render(fig), f"NACA {code} geometry",
           "Generated from the standard four-digit thickness and camber definitions.")

    alphas = linspace(-10, 15, 100)
    r.plot(**P.chart(
        [{"x": alphas, "y": [2 * math.pi * (math.radians(al) - alpha_L0) for al in alphas],
          "label": "thin airfoil theory"},
         {"x": alphas, "y": [0.9 * 2 * math.pi * (math.radians(al) - alpha_L0) for al in alphas],
          "label": "typical viscous (0.9 a\u2080)", "style": "--", "color": P.MUTED}],
        xlabel="Angle of attack  \u03b1  [\u00b0]", ylabel="Lift coefficient  c_l",
        title="Lift curve",
        points=[{"x": inp["alpha"], "y": cl, "label": "your condition"}],
        hlines=[{"value": 0.0}],
        caption="Thin airfoil theory ignores thickness and viscosity, so it "
                "overpredicts the slope slightly and gives no stall."))
    return r


# ---------------------------------------------------------------------------
# 5. Finite wing / lifting line
# ---------------------------------------------------------------------------


def _lifting_line(inp):
    AR, taper = inp["AR"], inp["taper"]
    alpha = math.radians(inp["alpha"])
    aL0 = math.radians(inp["alpha_L0"])
    twist = math.radians(inp["twist"])
    a0 = inp["a0"]
    N = 40

    if not 0 < taper <= 1:
        raise CalculationError("The taper ratio must be greater than 0 and at most 1.")

    theta = np.array([(i + 1) * math.pi / (2 * N + 1) for i in range(N)])
    y = np.cos(theta)                     # y/(b/2)
    # Chord distribution normalised so that S = b^2/AR
    c_root = 2.0 / (AR * (1 + taper))     # c_root/b for a straight tapered wing
    chord = c_root * (1 - (1 - taper) * np.abs(y))
    alpha_local = alpha + twist * np.abs(y) - aL0

    n_odd = np.array([2 * i + 1 for i in range(N)])
    A = np.zeros((N, N))
    for i in range(N):
        # Glauert's mu = a0*c/(8*s) with s the semi-span; chord is c/b here
        mu = a0 * chord[i] / 4.0
        for j, n in enumerate(n_odd):
            A[i, j] = math.sin(n * theta[i]) * (math.sin(theta[i]) + n * mu)
    rhs = np.array([a0 * chord[i] / 4.0 * alpha_local[i] * math.sin(theta[i])
                    for i in range(N)])
    coeffs = np.linalg.solve(A, rhs)

    A1 = coeffs[0]
    CL = math.pi * AR * A1
    delta = float(sum(n * (coeffs[j] / A1) ** 2 for j, n in enumerate(n_odd) if j > 0)) \
        if abs(A1) > 1e-12 else 0.0
    e = 1.0 / (1.0 + delta)
    CDi = CL ** 2 / (math.pi * AR * e)

    # Spanwise distribution
    th_fine = np.linspace(1e-6, math.pi - 1e-6, 300)
    yy = np.cos(th_fine)
    gamma = np.zeros_like(th_fine)
    for j, n in enumerate(n_odd):
        gamma += coeffs[j] * np.sin(n * th_fine)
    chord_fine = c_root * (1 - (1 - taper) * np.abs(yy))
    cl_local = 4.0 * gamma / chord_fine
    alpha_i = np.zeros_like(th_fine)
    for j, n in enumerate(n_odd):
        alpha_i += n * coeffs[j] * np.sin(n * th_fine) / np.sin(th_fine)

    CL_alpha = a0 / (1 + a0 / (math.pi * AR) * (1 + delta))

    r = Result()
    r.group("Wing", f"AR = {AR:g}, taper \u03bb = {taper:g}")
    r.headline("Lift coefficient", CL, symbol="C_L")
    r.headline("Induced drag coefficient", CDi, symbol="C_Di")
    r.out("Span efficiency factor", e, symbol="e",
          note="1.0 for an elliptic distribution")
    r.out("Induced drag factor", delta, symbol="\u03b4")
    r.out("Lift-curve slope", CL_alpha, "per rad", symbol="dC_L/d\u03b1",
          note=f"= {CL_alpha * math.pi / 180:.5f} per degree")
    r.out("Section lift-curve slope used", a0, "per rad", symbol="a\u2080")
    r.out("Fourier coefficient A\u2081", A1)

    r.group("Induced flow")
    r.out("Induced angle at the root", math.degrees(float(alpha_i[len(th_fine) // 2])),
          "\u00b0", symbol="\u03b1_i")
    r.out("Mean induced angle", math.degrees(CL / (math.pi * AR) * (1 + delta)), "\u00b0")
    r.out("Effective angle at the root",
          math.degrees(alpha - aL0 - CL / (math.pi * AR) * (1 + delta)), "\u00b0")
    r.out("Lift-to-induced-drag ratio", CL / CDi if CDi else float("inf"),
          symbol="C_L/C_Di")

    if inp["dimensional"]:
        b, rho, V = inp["b"], inp["rho"], inp["V"]
        S = b * b / AR
        q = 0.5 * rho * V * V
        r.group("Dimensional", f"b = {b:g} m, V = {V:g} m/s")
        r.out("Wing area", S, "m\u00b2", symbol="S")
        r.out("Mean chord", S / b, "m", symbol="c\u0304")
        r.out("Root chord", 2 * S / (b * (1 + taper)), "m", symbol="c_r")
        r.out("Tip chord", 2 * S * taper / (b * (1 + taper)), "m", symbol="c_t")
        r.out("Dynamic pressure", q, "Pa", symbol="q")
        r.out("Lift", CL * q * S, "N", symbol="L")
        r.out("Induced drag", CDi * q * S, "N", symbol="D_i")

    ell = [math.sqrt(max(0.0, 1 - v ** 2)) for v in yy]
    ell_scale = float(np.max(gamma)) if np.max(gamma) > 0 else 1.0
    r.plot(**P.chart(
        [{"x": list(yy), "y": list(gamma / ell_scale), "label": "computed circulation"},
         {"x": list(yy), "y": ell, "label": "elliptic (reference)", "style": "--",
          "color": P.MUTED}],
        xlabel="Spanwise station  y/(b/2)", ylabel="\u0393 / \u0393\u2098\u2090\u2093",
        title="Spanwise circulation distribution", xlim=(-1, 1),
        caption=f"Solved from the monoplane equation with {N} odd Fourier terms. "
                f"The closer to elliptic, the closer e is to 1 (here e = {e:.4f})."))

    r.plot(**P.chart(
        [{"x": list(yy), "y": list(cl_local), "label": "local c_l"},
         {"x": list(yy), "y": [CL] * len(yy), "label": "wing C_L", "style": "--",
          "color": P.MUTED}],
        xlabel="Spanwise station  y/(b/2)", ylabel="Local lift coefficient  c_l",
        title="Section lift coefficient across the span", xlim=(-1, 1),
        caption="A highly tapered wing loads its tips harder relative to the root, "
                "which is what drives tip stall."))
    return r


# ---------------------------------------------------------------------------
# 6. Drag polar
# ---------------------------------------------------------------------------


def _drag_polar(inp):
    CD0, AR, e = inp["CD0"], inp["AR"], inp["e"]
    k = 1.0 / (math.pi * AR * e)
    CL_md = math.sqrt(CD0 / k)
    LD_max = 1.0 / (2 * math.sqrt(CD0 * k))
    CL = inp["CL"]
    CD = CD0 + k * CL ** 2

    r = Result()
    r.group("Polar", f"C_D = {CD0:g} + {k:.6g}\u00b7C_L\u00b2")
    r.headline("Drag coefficient at your C_L", CD, symbol="C_D")
    r.out("Lift-to-drag ratio", CL / CD if CD else float("inf"), symbol="L/D")
    r.out("Induced drag factor", k, symbol="k = 1/(\u03c0\u00b7AR\u00b7e)")
    r.out("Induced drag coefficient", k * CL ** 2, symbol="C_Di")
    r.out("Share of drag that is induced", 100 * k * CL ** 2 / CD, "%")

    r.group("Optimum points")
    r.headline("Maximum lift-to-drag ratio", LD_max, symbol="(L/D)\u2098\u2090\u2093")
    r.out("C_L for maximum L/D", CL_md, symbol="C_L,md",
          note="minimum drag: induced drag equals parasite drag")
    r.out("C_D at maximum L/D", 2 * CD0)
    r.out("C_L for maximum C_L^(3/2)/C_D", math.sqrt(3 * CD0 / k),
          note="minimum power required \u2014 best endurance for a propeller aircraft")
    r.out("Maximum C_L^(3/2)/C_D",
          (3 * CD0 / k) ** 0.75 / (4 * CD0), symbol="(C_L^1.5/C_D)\u2098\u2090\u2093")
    r.out("C_L for maximum C_L^(1/2)/C_D", math.sqrt(CD0 / (3 * k)),
          note="best range for a propeller aircraft at constant altitude")

    if inp["dimensional"]:
        W, S, rho = inp["W"], inp["S"], inp["rho"]
        V_md = math.sqrt(2 * W / (rho * S * CL_md))
        r.group("Speeds", f"W = {W:g} N, S = {S:g} m\u00b2")
        r.out("Wing loading", W / S, "N/m\u00b2", symbol="W/S")
        r.out("Speed for maximum L/D", V_md, "m/s", symbol="V_md")
        r.out("Minimum drag", W / LD_max, "N", symbol="D_min")
        r.out("Speed for minimum power", V_md / 3 ** 0.25, "m/s", symbol="V_mp")

    cls = linspace(0.0, max(2.0, CL * 1.3), 300)
    r.plot(**P.chart(
        [{"x": [CD0 + k * c ** 2 for c in cls], "y": cls, "label": "drag polar"},
         {"x": [CD0 for _ in cls], "y": cls, "label": "parasite only", "style": ":",
          "color": P.MUTED}],
        xlabel="Drag coefficient  C_D", ylabel="Lift coefficient  C_L",
        title="Drag polar",
        points=[{"x": CD, "y": CL, "label": "your point"},
                {"x": 2 * CD0, "y": CL_md, "label": "max L/D", "color": "#0E7C6B"}],
        caption="The tangent from the origin touches the polar at maximum L/D."))
    r.plot(**P.chart(
        [{"x": cls, "y": [c / (CD0 + k * c ** 2) for c in cls], "label": "L/D"},
         {"x": cls, "y": [c ** 1.5 / (CD0 + k * c ** 2) for c in cls],
          "label": "C_L^1.5/C_D", "color": P.SERIES[1]}],
        xlabel="Lift coefficient  C_L", ylabel="Efficiency parameter",
        title="Range and endurance parameters",
        points=[{"x": CL, "y": CL / CD}],
        caption="Different missions optimise different parameters, so the best "
                "cruise C_L is not the same for a jet and a propeller aircraft."))
    return r


# ---------------------------------------------------------------------------
# 7. Flat plate boundary layer
# ---------------------------------------------------------------------------


def _boundary_layer(inp):
    rho, mu, V, L = inp["rho"], inp["mu"], inp["V"], inp["L"]
    Re_L = rho * V * L / mu
    Re_tr = inp["Re_tr"]

    lam = Re_L < Re_tr
    r = Result()
    r.group("Plate", f"L = {L:g} m, V = {V:g} m/s")
    r.headline("Reynolds number at the trailing edge", Re_L, symbol="Re_L")
    r.out("State at the trailing edge", "laminar" if lam else "turbulent")
    if not lam:
        r.out("Transition location", Re_tr * mu / (rho * V), "m", symbol="x_tr")

    r.group("Laminar (Blasius) at x = L")
    d_lam = 5.0 * L / math.sqrt(Re_L)
    r.out("Boundary layer thickness", d_lam, "m", symbol="\u03b4",
          note="\u03b4/x = 5.0/\u221aRe_x")
    r.out("Displacement thickness", 1.7208 * L / math.sqrt(Re_L), "m", symbol="\u03b4*")
    r.out("Momentum thickness", 0.664 * L / math.sqrt(Re_L), "m", symbol="\u03b8")
    r.out("Shape factor", 2.59, symbol="H")
    r.out("Local skin friction coefficient", 0.664 / math.sqrt(Re_L), symbol="c_f")
    r.out("Average skin friction coefficient", 1.328 / math.sqrt(Re_L), symbol="C_F")

    r.group("Turbulent (1/7 power law) at x = L")
    d_turb = 0.37 * L / Re_L ** 0.2
    r.out("Boundary layer thickness", d_turb, "m", symbol="\u03b4",
          note="\u03b4/x = 0.37/Re_x^0.2")
    r.out("Displacement thickness", d_turb / 8.0, "m", symbol="\u03b4*")
    r.out("Momentum thickness", 7.0 * d_turb / 72.0, "m", symbol="\u03b8")
    r.out("Shape factor", 1.29, symbol="H")
    r.out("Local skin friction coefficient", 0.0592 / Re_L ** 0.2, symbol="c_f")
    r.out("Average skin friction coefficient", 0.074 / Re_L ** 0.2, symbol="C_F")

    CF = 1.328 / math.sqrt(Re_L) if lam else 0.074 / Re_L ** 0.2
    q = 0.5 * rho * V * V
    r.group("Drag", "One side of the plate, per metre of span")
    r.out("Average skin friction coefficient used", CF, symbol="C_F")
    r.out("Skin friction drag", CF * q * L, "N/m", symbol="D_f")
    r.out("Wall shear stress at x = L",
          (0.664 / math.sqrt(Re_L) if lam else 0.0592 / Re_L ** 0.2) * q, "Pa",
          symbol="\u03c4_w")

    xs = linspace(L * 0.005, L, 300)
    r.plot(**P.chart(
        [{"x": xs, "y": [5.0 * x / math.sqrt(rho * V * x / mu) * 1000 for x in xs],
          "label": "laminar (Blasius)"},
         {"x": xs, "y": [0.37 * x / (rho * V * x / mu) ** 0.2 * 1000 for x in xs],
          "label": "turbulent (1/7 power)", "color": P.SERIES[1]}],
        xlabel="Distance from leading edge  x  [m]",
        ylabel="Boundary layer thickness  \u03b4  [mm]",
        title="Boundary layer growth",
        vlines=[{"value": Re_tr * mu / (rho * V), "label": "transition",
                 "color": "#B3242B"}] if not lam else None,
        caption="A turbulent layer is thicker and produces several times the "
                "skin friction, but resists separation far better."))

    eta = linspace(0, 8, 200)
    blasius = [_blasius_u(e) for e in eta]
    r.plot(**P.chart(
        [{"x": blasius, "y": eta, "label": "Blasius (laminar)"},
         {"x": [min(1.0, (e / 5.0) ** (1 / 7)) for e in eta], "y": eta,
          "label": "1/7 power law (turbulent)", "color": P.SERIES[1]}],
        xlabel="u / U\u221e", ylabel="\u03b7 = y\u221a(U\u221e/\u03bdx)",
        title="Velocity profiles", ylim=(0, 8),
        caption="The turbulent profile is much fuller near the wall, which is why "
                "its wall shear \u2014 and therefore drag \u2014 is higher."))
    return r


_BLASIUS_TABLE = [
    (0.0, 0.0), (0.4, 0.13277), (0.8, 0.26471), (1.2, 0.39378), (1.6, 0.51676),
    (2.0, 0.62977), (2.4, 0.72899), (2.8, 0.81152), (3.2, 0.87609), (3.6, 0.92333),
    (4.0, 0.95552), (4.4, 0.97587), (4.8, 0.98779), (5.2, 0.99425), (5.6, 0.99748),
    (6.0, 0.99898), (6.4, 0.99961), (7.0, 0.99992), (8.0, 1.0),
]


def _blasius_u(eta):
    if eta >= 8:
        return 1.0
    for i in range(len(_BLASIUS_TABLE) - 1):
        e0, u0 = _BLASIUS_TABLE[i]
        e1, u1 = _BLASIUS_TABLE[i + 1]
        if e0 <= eta <= e1:
            return u0 + (u1 - u0) * (eta - e0) / (e1 - e0)
    return 1.0


# ---------------------------------------------------------------------------
# 8. Compressibility corrections and critical Mach number
# ---------------------------------------------------------------------------


def _compressibility(inp):
    cp0, M = inp["cp0"], inp["M"]
    g = GAMMA_AIR
    if M <= 0 or M >= 1:
        raise CalculationError("These corrections apply to subsonic flow, 0 < M < 1.")
    beta = math.sqrt(1 - M * M)

    pg = cp0 / beta
    kt = cp0 / (beta + (M * M / (1 + beta)) * cp0 / 2)
    lt = cp0 / (beta + M * M * (1 + (g - 1) / 2 * M * M) / (2 * beta) * cp0)

    r = Result()
    r.group("Corrected pressure coefficient", f"C_p0 = {cp0:g} at M = {M:g}")
    r.headline("Prandtl-Glauert", pg, symbol="C_p,PG")
    r.out("Karman-Tsien", kt, symbol="C_p,KT",
          note="usually the most accurate of the three")
    r.out("Laitone", lt, symbol="C_p,L")
    r.out("Prandtl-Glauert factor", 1 / beta, symbol="1/\u03b2")
    r.out("Compressible lift-curve slope", 2 * math.pi / beta, "per rad")

    cp_crit = _cp_critical(M, g)
    r.out("Critical pressure coefficient at this M", cp_crit, symbol="C_p,cr",
          note="the C_p at which the local flow first reaches M = 1")

    if inp["find_mcrit"]:
        try:
            Mcr = solve(lambda m: cp0 / math.sqrt(1 - m * m) - _cp_critical(m, g),
                        0.05, 0.999, what="critical Mach number")
            r.group("Critical Mach number")
            r.headline("Critical Mach number", Mcr, symbol="M_cr")
            r.out("Corrected C_p at M_cr", cp0 / math.sqrt(1 - Mcr ** 2))
            r.out("Drag-divergence Mach number (Korn estimate)", Mcr + 0.08, symbol="M_dd",
                  note="rule of thumb: M_dd \u2248 M_cr + 0.06 to 0.10")
        except CalculationError:
            r.note("No critical Mach number exists for this C_p0 below M = 1 — "
                   "the peak suction is too weak ever to reach sonic conditions.")

    ms = linspace(0.05, 0.95, 300)
    r.plot(**P.chart(
        [{"x": ms, "y": [cp0 / math.sqrt(1 - m * m) for m in ms],
          "label": "Prandtl-Glauert"},
         {"x": ms, "y": [cp0 / (math.sqrt(1 - m * m) + (m * m / (1 + math.sqrt(1 - m * m))) * cp0 / 2)
                         for m in ms], "label": "Karman-Tsien"},
         {"x": ms, "y": [_cp_critical(m, g) for m in ms], "label": "C_p,cr",
          "color": "#B3242B", "style": "--"}],
        xlabel="Free-stream Mach number  M\u221e", ylabel="Pressure coefficient  C_p",
        title="Critical Mach number construction", ylim=(min(-3, cp0 * 3), 0.2),
        points=[{"x": M, "y": pg, "label": "your condition"}],
        caption="Where the corrected C_p curve crosses the C_p,cr curve, the flow "
                "first goes sonic somewhere on the surface \u2014 that intersection is M_cr."))
    return r


def _cp_critical(M, g):
    return 2 / (g * M * M) * (((2 + (g - 1) * M * M) / (g + 1)) ** (g / (g - 1)) - 1)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CALCULATORS = [
    {
        "id": "standard-atmosphere",
        "name": "Standard atmosphere",
        "category": CATEGORY,
        "summary": "Full U.S. Standard Atmosphere 1976 properties from sea level to 86 km.",
        "description": "Implements all seven layers of the 1976 model, not just the "
                       "troposphere, with an optional ISA temperature offset.",
        "tags": ["ISA", "atmosphere", "density", "altitude", "1976"],
        "inputs": [
            choice("mode", "Specify by", [("altitude", "Altitude"),
                                          ("pressure", "Pressure")], "altitude",
                   section="Flight condition"),
            num("altitude", "Altitude", 11000.0, minimum=-5000, maximum=282000,
                section="Flight condition", show_if={"key": "mode", "in": ["altitude"]}),
            choice("alt_unit", "Altitude unit", [("m", "metres"), ("ft", "feet")], "m",
                   section="Flight condition", show_if={"key": "mode", "in": ["altitude"]}),
            num("pressure", "Pressure", 22632.0, "Pa", minimum=0.3,
                section="Flight condition", show_if={"key": "mode", "in": ["pressure"]}),
            num("dT", "Temperature offset from ISA", 0.0, "K", minimum=-60, maximum=60,
                section="Flight condition"),
            toggle("with_speed", "Add flow quantities for a given speed", False,
                   section="Optional speed"),
            num("V", "Speed", 250.0, section="Optional speed",
                show_if={"key": "with_speed", "in": [True]}),
            choice("v_unit", "Speed unit", [("m/s", "m/s"), ("kt", "knots")], "m/s",
                   section="Optional speed", show_if={"key": "with_speed", "in": [True]}),
            num("L_ref", "Reference length for Reynolds number", 1.0, "m", minimum=0.0,
                section="Optional speed", show_if={"key": "with_speed", "in": [True]}),
        ],
        "compute": _standard_atmosphere,
        "references": ["U.S. Standard Atmosphere, 1976 (NOAA/NASA/USAF)"],
    },
    {
        "id": "airspeed-conversion",
        "name": "Airspeed conversions",
        "category": CATEGORY,
        "summary": "Convert between TAS, EAS, CAS and Mach with the compressible relations.",
        "description": "Uses the full compressible pitot relations, including the Rayleigh "
                       "supersonic form, rather than the incompressible √σ shortcut.",
        "tags": ["TAS", "EAS", "CAS", "Mach", "pitot", "impact pressure"],
        "inputs": [
            choice("known", "Known speed", [("mach", "Mach number"),
                                            ("tas", "True airspeed"),
                                            ("eas", "Equivalent airspeed"),
                                            ("cas", "Calibrated airspeed")], "tas",
                   section="Speed"),
            num("value", "Value", 250.0, minimum=0.0, section="Speed"),
            choice("v_unit", "Unit", [("m/s", "m/s"), ("kt", "knots")], "m/s",
                   section="Speed", show_if={"key": "known",
                                             "in": ["tas", "eas", "cas"]}),
        ] + _alt_fields(8000.0),
        "compute": _airspeed,
    },
    {
        "id": "reynolds-similarity",
        "name": "Reynolds number and similarity",
        "category": CATEGORY,
        "summary": "Reynolds, Mach and Knudsen numbers, plus wind-tunnel scaling.",
        "tags": ["Reynolds", "similarity", "scaling", "wind tunnel", "Knudsen"],
        "inputs": [
            choice("source", "Flow properties from",
                   [("atmosphere", "Standard atmosphere"), ("custom", "Custom p and T")],
                   "atmosphere", section="Conditions"),
            num("altitude", "Altitude", 0.0, minimum=-5000, maximum=86000,
                section="Conditions", show_if={"key": "source", "in": ["atmosphere"]}),
            choice("alt_unit", "Altitude unit", [("m", "metres"), ("ft", "feet")], "m",
                   section="Conditions", show_if={"key": "source", "in": ["atmosphere"]}),
            num("dT", "Temperature offset from ISA", 0.0, "K", minimum=-60, maximum=60,
                section="Conditions", show_if={"key": "source", "in": ["atmosphere"]}),
            num("p", "Static pressure", 101325.0, "Pa", minimum=1e-6,
                section="Conditions", show_if={"key": "source", "in": ["custom"]}),
            num("T", "Static temperature", 288.15, "K", minimum=1.0,
                section="Conditions", show_if={"key": "source", "in": ["custom"]}),
            num("V", "Velocity", 50.0, "m/s", minimum=0.0, section="Geometry"),
            num("L", "Reference length", 1.0, "m", minimum=1e-12, section="Geometry"),
            toggle("scale", "Compare with a scale model", False, section="Model"),
            num("L_model", "Model reference length", 0.2, "m", minimum=1e-12,
                section="Model", show_if={"key": "scale", "in": [True]}),
        ],
        "compute": _similarity,
    },
    {
        "id": "thin-airfoil",
        "name": "NACA 4-digit airfoil (thin airfoil theory)",
        "category": CATEGORY,
        "summary": "Section geometry, zero-lift angle, lift and moment coefficients.",
        "description": "Builds the four-digit section from its definition and integrates "
                       "the camber slope numerically for the exact thin-airfoil results.",
        "tags": ["NACA", "airfoil", "camber", "thin airfoil", "aerodynamic centre"],
        "inputs": [
            integer("code", "NACA designation", 2412, minimum=1, maximum=9999,
                    section="Section", help="Four digits, e.g. 2412, 0012, 4415."),
            num("alpha", "Angle of attack \u03b1", 5.0, "\u00b0", minimum=-30, maximum=30,
                section="Condition"),
            toggle("with_compressibility", "Apply a Prandtl-Glauert correction", False,
                   section="Condition"),
            num("M", "Mach number", 0.5, minimum=0.0, maximum=0.99, section="Condition",
                show_if={"key": "with_compressibility", "in": [True]}),
        ],
        "compute": _thin_airfoil,
    },
    {
        "id": "lifting-line",
        "name": "Finite wing (Prandtl lifting line)",
        "category": CATEGORY,
        "summary": "Solves the monoplane equation for lift, induced drag and span efficiency.",
        "description": "A real lifting-line solution with 40 odd Fourier terms — not the "
                       "elliptic approximation — so taper and twist change the answer.",
        "tags": ["lifting line", "induced drag", "Oswald", "span efficiency", "taper"],
        "inputs": [
            num("AR", "Aspect ratio", 8.0, minimum=0.5, maximum=50, section="Planform"),
            num("taper", "Taper ratio \u03bb = c_t/c_r", 0.6, minimum=0.01, maximum=1.0,
                section="Planform"),
            num("twist", "Geometric washout at the tip", 0.0, "\u00b0",
                minimum=-15, maximum=15, section="Planform",
                help="Negative reduces tip incidence."),
            num("alpha", "Root angle of attack \u03b1", 5.0, "\u00b0", minimum=-20, maximum=25,
                section="Condition"),
            num("alpha_L0", "Section zero-lift angle \u03b1_L0", -2.0, "\u00b0",
                minimum=-15, maximum=10, section="Condition"),
            num("a0", "Section lift-curve slope a\u2080", 6.283185, "per rad",
                minimum=1.0, maximum=8.0, section="Condition"),
            toggle("dimensional", "Compute forces", False, section="Dimensional"),
            num("b", "Span", 10.0, "m", minimum=1e-6, section="Dimensional",
                show_if={"key": "dimensional", "in": [True]}),
            num("V", "Airspeed", 50.0, "m/s", minimum=0.0, section="Dimensional",
                show_if={"key": "dimensional", "in": [True]}),
            num("rho", "Density", 1.225, "kg/m\u00b3", minimum=1e-9,
                section="Dimensional", show_if={"key": "dimensional", "in": [True]}),
        ],
        "compute": _lifting_line,
    },
    {
        "id": "drag-polar",
        "name": "Drag polar and L/D",
        "category": CATEGORY,
        "summary": "Parabolic polar, maximum L/D, and the best range and endurance points.",
        "tags": ["drag polar", "L/D", "Oswald", "range", "endurance"],
        "inputs": [
            num("CD0", "Zero-lift drag coefficient C_D0", 0.02, minimum=1e-6,
                section="Polar"),
            num("AR", "Aspect ratio", 8.0, minimum=0.5, maximum=50, section="Polar"),
            num("e", "Oswald efficiency factor", 0.8, minimum=0.1, maximum=1.0,
                section="Polar"),
            num("CL", "Operating lift coefficient C_L", 0.5, minimum=0.0, maximum=4.0,
                section="Operating point"),
            toggle("dimensional", "Compute speeds and forces", False, section="Aircraft"),
            num("W", "Weight", 50000.0, "N", minimum=1.0, section="Aircraft",
                show_if={"key": "dimensional", "in": [True]}),
            num("S", "Wing area", 30.0, "m\u00b2", minimum=1e-6, section="Aircraft",
                show_if={"key": "dimensional", "in": [True]}),
            num("rho", "Density", 1.225, "kg/m\u00b3", minimum=1e-9, section="Aircraft",
                show_if={"key": "dimensional", "in": [True]}),
        ],
        "compute": _drag_polar,
    },
    {
        "id": "boundary-layer",
        "name": "Flat plate boundary layer",
        "category": CATEGORY,
        "summary": "Blasius and turbulent thicknesses, skin friction and profiles.",
        "tags": ["boundary layer", "Blasius", "skin friction", "transition", "displacement"],
        "inputs": [
            num("rho", "Density", 1.225, "kg/m\u00b3", minimum=1e-9, section="Fluid"),
            num("mu", "Dynamic viscosity", 1.7894e-5, "Pa\u00b7s", minimum=1e-12,
                section="Fluid"),
            num("V", "Free-stream velocity", 30.0, "m/s", minimum=1e-9, section="Flow"),
            num("L", "Plate length", 1.0, "m", minimum=1e-9, section="Flow"),
            num("Re_tr", "Transition Reynolds number", 500000.0, minimum=1000.0,
                section="Flow"),
        ],
        "compute": _boundary_layer,
    },
    {
        "id": "compressibility-correction",
        "name": "Compressibility corrections and M_crit",
        "category": CATEGORY,
        "summary": "Prandtl-Glauert, Kármán-Tsien and Laitone rules, plus critical Mach number.",
        "tags": ["Prandtl-Glauert", "Karman-Tsien", "critical Mach", "drag divergence"],
        "inputs": [
            num("cp0", "Incompressible peak pressure coefficient C_p0", -0.6,
                maximum=0.0, section="Section"),
            num("M", "Free-stream Mach number", 0.6, minimum=0.01, maximum=0.99,
                section="Condition"),
            toggle("find_mcrit", "Solve for the critical Mach number", True,
                   section="Condition"),
        ],
        "compute": _compressibility,
    },
]
