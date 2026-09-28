"""Structures and composites: stress analysis, stability, laminates and fatigue."""

from __future__ import annotations

import math

import numpy as np

from .. import plotting as P
from ..core import CalculationError, Result, choice, integer, num, text, toggle
from ..numeric import linspace, solve

CATEGORY = "Structures & Composites"

MATERIALS = {
    # key: (label, E [Pa], nu, yield [Pa], ultimate [Pa], density [kg/m3])
    "al2024": ("Aluminium 2024-T3", 73.1e9, 0.33, 345e6, 483e6, 2780),
    "al7075": ("Aluminium 7075-T6", 71.7e9, 0.33, 503e6, 572e6, 2810),
    "al6061": ("Aluminium 6061-T6", 68.9e9, 0.33, 276e6, 310e6, 2700),
    "ti64": ("Titanium Ti-6Al-4V", 113.8e9, 0.342, 880e6, 950e6, 4430),
    "steel4340": ("Steel AISI 4340", 205e9, 0.29, 862e6, 1080e6, 7850),
    "steel304": ("Stainless steel 304", 193e9, 0.29, 215e6, 505e6, 8000),
    "mg": ("Magnesium AZ31B", 45e9, 0.35, 200e6, 260e6, 1770),
    "inconel": ("Inconel 718", 200e9, 0.29, 1030e6, 1240e6, 8190),
    "custom": ("Custom material", 0, 0, 0, 0, 0),
}

MATERIAL_OPTIONS = [(k, v[0]) for k, v in MATERIALS.items()]


def _material(inp, prefix=""):
    key = inp.get(prefix + "material", "al2024")
    if key == "custom":
        E = inp[prefix + "E"] * 1e9
        nu = inp[prefix + "nu"]
        sy = inp[prefix + "sy"] * 1e6
        return E, nu, sy, sy, inp.get(prefix + "rho", 2700.0), "Custom material"
    label, E, nu, sy, su, rho = MATERIALS[key]
    return E, nu, sy, su, rho, label


def _mat_fields(section="Material"):
    return [
        choice("material", "Material", MATERIAL_OPTIONS, "al2024", section=section),
        num("E", "Young's modulus", 73.1, "GPa", minimum=0.001, section=section,
            show_if={"key": "material", "in": ["custom"]}),
        num("nu", "Poisson's ratio", 0.33, minimum=0.0, maximum=0.5, section=section,
            show_if={"key": "material", "in": ["custom"]}),
        num("sy", "Yield strength", 345.0, "MPa", minimum=0.001, section=section,
            show_if={"key": "material", "in": ["custom"]}),
        num("rho", "Density", 2780.0, "kg/m\u00b3", minimum=0.001, section=section,
            show_if={"key": "material", "in": ["custom"]}),
    ]


# ---------------------------------------------------------------------------
# Section properties
# ---------------------------------------------------------------------------


def _section_props(inp):
    kind = inp["section"]
    if kind == "rect":
        b, h = inp["b"], inp["h"]
        A = b * h
        I = b * h ** 3 / 12
        c = h / 2
        Q = b * h ** 2 / 8
        t_web = b
        J = b * h ** 3 * (1 / 3 - 0.21 * (h / b) * (1 - h ** 4 / (12 * b ** 4))) \
            if b >= h else h * b ** 3 * (1 / 3 - 0.21 * (b / h) * (1 - b ** 4 / (12 * h ** 4)))
        I_min = min(I, h * b ** 3 / 12)
        label = f"Rectangle {b * 1000:g}\u00d7{h * 1000:g} mm"
    elif kind == "circle":
        d = inp["d"]
        A = math.pi * d ** 2 / 4
        I = math.pi * d ** 4 / 64
        c = d / 2
        Q = d ** 3 / 12
        t_web = d
        J = math.pi * d ** 4 / 32
        I_min = I
        label = f"Solid circle \u00f8{d * 1000:g} mm"
    elif kind == "tube":
        do, di = inp["do"], inp["di"]
        if di >= do:
            raise CalculationError("The inner diameter must be smaller than the outer.")
        A = math.pi * (do ** 2 - di ** 2) / 4
        I = math.pi * (do ** 4 - di ** 4) / 64
        c = do / 2
        Q = (do ** 3 - di ** 3) / 12
        t_web = do - di
        J = math.pi * (do ** 4 - di ** 4) / 32
        I_min = I
        label = f"Tube \u00f8{do * 1000:g}/{di * 1000:g} mm"
    else:  # I-beam
        bf, tf, hw, tw = inp["bf"], inp["tf"], inp["hw"], inp["tw"]
        h = hw + 2 * tf
        A = 2 * bf * tf + hw * tw
        I = (bf * h ** 3 - (bf - tw) * hw ** 3) / 12
        c = h / 2
        Q = bf * tf * (h - tf) / 2 + tw * hw ** 2 / 8
        t_web = tw
        J = (2 * bf * tf ** 3 + hw * tw ** 3) / 3
        I_min = min(I, (2 * tf * bf ** 3 + hw * tw ** 3) / 12)
        label = f"I-section {bf * 1000:g}\u00d7{h * 1000:g} mm"
    return {"A": A, "I": I, "I_min": I_min, "c": c, "Q": Q, "t": t_web,
            "J": J, "label": label}


_SECTION_FIELDS = [
    choice("section", "Cross-section", [("rect", "Rectangle"), ("circle", "Solid circle"),
                                        ("tube", "Circular tube"), ("ibeam", "I-section")],
           "rect", section="Cross-section"),
    num("b", "Width b", 0.05, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["rect"]}),
    num("h", "Height h", 0.1, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["rect"]}),
    num("d", "Diameter", 0.05, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["circle"]}),
    num("do", "Outer diameter", 0.06, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["tube"]}),
    num("di", "Inner diameter", 0.05, "m", minimum=0.0, section="Cross-section",
        show_if={"key": "section", "in": ["tube"]}),
    num("bf", "Flange width", 0.08, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["ibeam"]}),
    num("tf", "Flange thickness", 0.008, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["ibeam"]}),
    num("hw", "Web height", 0.12, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["ibeam"]}),
    num("tw", "Web thickness", 0.005, "m", minimum=1e-6, section="Cross-section",
        show_if={"key": "section", "in": ["ibeam"]}),
]


# ---------------------------------------------------------------------------
# 1. Beam bending
# ---------------------------------------------------------------------------

_BEAM_CASES = [
    ("cant_point", "Cantilever, point load at the free end"),
    ("cant_udl", "Cantilever, uniformly distributed load"),
    ("ss_point", "Simply supported, point load at mid-span"),
    ("ss_udl", "Simply supported, uniformly distributed load"),
    ("fixed_udl", "Both ends fixed, uniformly distributed load"),
]


def _beam(inp):
    sec = _section_props(inp)
    E, nu, sy, su, rho, mat = _material(inp)
    L = inp["L"]
    case = inp["case"]
    P_load, w = inp["P"], inp["w"]

    n = 300
    xs = linspace(0, L, n)
    if case == "cant_point":
        M_max, x_M = P_load * L, 0.0
        V_max = P_load
        delta = P_load * L ** 3 / (3 * E * sec["I"])
        theta = P_load * L ** 2 / (2 * E * sec["I"])
        V = [P_load] * n
        M = [-P_load * (L - x) for x in xs]
        y = [-P_load * x ** 2 * (3 * L - x) / (6 * E * sec["I"]) for x in xs]
    elif case == "cant_udl":
        M_max, x_M = w * L ** 2 / 2, 0.0
        V_max = w * L
        delta = w * L ** 4 / (8 * E * sec["I"])
        theta = w * L ** 3 / (6 * E * sec["I"])
        V = [w * (L - x) for x in xs]
        M = [-w * (L - x) ** 2 / 2 for x in xs]
        y = [-w * x ** 2 * (6 * L ** 2 - 4 * L * x + x ** 2) / (24 * E * sec["I"]) for x in xs]
    elif case == "ss_point":
        M_max, x_M = P_load * L / 4, L / 2
        V_max = P_load / 2
        delta = P_load * L ** 3 / (48 * E * sec["I"])
        theta = P_load * L ** 2 / (16 * E * sec["I"])
        V = [P_load / 2 if x < L / 2 else -P_load / 2 for x in xs]
        M = [P_load * x / 2 if x < L / 2 else P_load * (L - x) / 2 for x in xs]
        y = [-P_load * x * (3 * L ** 2 - 4 * x ** 2) / (48 * E * sec["I"])
             if x <= L / 2 else
             -P_load * (L - x) * (3 * L ** 2 - 4 * (L - x) ** 2) / (48 * E * sec["I"])
             for x in xs]
    elif case == "ss_udl":
        M_max, x_M = w * L ** 2 / 8, L / 2
        V_max = w * L / 2
        delta = 5 * w * L ** 4 / (384 * E * sec["I"])
        theta = w * L ** 3 / (24 * E * sec["I"])
        V = [w * (L / 2 - x) for x in xs]
        M = [w * x * (L - x) / 2 for x in xs]
        y = [-w * x * (L ** 3 - 2 * L * x ** 2 + x ** 3) / (24 * E * sec["I"]) for x in xs]
    else:
        M_max, x_M = w * L ** 2 / 12, 0.0
        V_max = w * L / 2
        delta = w * L ** 4 / (384 * E * sec["I"])
        theta = 0.0
        V = [w * (L / 2 - x) for x in xs]
        M = [w * (6 * L * x - 6 * x ** 2 - L ** 2) / 12 for x in xs]
        y = [-w * x ** 2 * (L - x) ** 2 / (24 * E * sec["I"]) for x in xs]

    sigma = M_max * sec["c"] / sec["I"]
    tau = V_max * sec["Q"] / (sec["I"] * sec["t"])

    r = Result()
    r.group("Section", f"{sec['label']} in {mat}")
    r.out("Cross-sectional area", sec["A"] * 1e4, "cm\u00b2", symbol="A")
    r.headline("Second moment of area", sec["I"] * 1e12, "mm\u2074", symbol="I")
    r.out("Section modulus", sec["I"] / sec["c"] * 1e9, "mm\u00b3", symbol="Z = I/c")
    r.out("Radius of gyration", math.sqrt(sec["I"] / sec["A"]) * 1000, "mm", symbol="k")
    r.out("Distance to extreme fibre", sec["c"] * 1000, "mm", symbol="c")
    r.out("Mass per metre", sec["A"] * rho, "kg/m")
    r.out("Flexural rigidity", E * sec["I"], "N\u00b7m\u00b2", symbol="EI")

    r.group("Loading", dict(_BEAM_CASES)[case])
    r.headline("Maximum bending moment", M_max, "N\u00b7m", symbol="M_max")
    r.out("Maximum shear force", V_max, "N", symbol="V_max")
    r.headline("Maximum bending stress", sigma / 1e6, "MPa", symbol="\u03c3_max")
    r.out("Maximum transverse shear stress", tau / 1e6, "MPa", symbol="\u03c4_max")
    r.headline("Maximum deflection", delta * 1000, "mm", symbol="\u03b4_max")
    r.out("Deflection as a fraction of span", delta / L, symbol="\u03b4/L",
          note="L/360 is a common serviceability limit")
    r.out("Maximum slope", math.degrees(theta), "\u00b0", symbol="\u03b8")

    r.group("Margins", f"Yield strength {sy / 1e6:g} MPa")
    r.headline("Factor of safety on yield", sy / sigma if sigma else float("inf"),
               symbol="FoS")
    r.out("Margin of safety", sy / sigma - 1 if sigma else float("inf"), symbol="MS")
    r.out("Stress ratio", sigma / sy if sy else float("nan"))
    r.out("Maximum load at yield",
          (P_load if case in ("cant_point", "ss_point") else w) * sy / sigma
          if sigma else float("inf"),
          "N" if case in ("cant_point", "ss_point") else "N/m")
    if sigma > sy:
        r.note("The bending stress exceeds the yield strength — this section will "
               "yield under the stated load. Increase the depth (which raises I "
               "with the cube of height) before adding width.")

    r.plot(**P.stack([
        {"series": [{"x": xs, "y": V, "label": "shear"}],
         "xlabel": "x  [m]", "ylabel": "Shear force  V  [N]", "title": "Shear"},
        {"series": [{"x": xs, "y": M, "label": "moment", "color": P.SERIES[1]}],
         "xlabel": "x  [m]", "ylabel": "Bending moment  M  [N\u00b7m]", "title": "Moment"},
        {"series": [{"x": xs, "y": [v * 1000 for v in y], "color": P.SERIES[2]}],
         "xlabel": "x  [m]", "ylabel": "Deflection  [mm]", "title": "Deflection"},
    ], title="Shear, moment and deflection diagrams",
        caption="Deflection is drawn to true scale in millimetres; note that the "
                "maximum moment and maximum deflection do not always coincide."))

    zs = linspace(-sec["c"], sec["c"], 100)
    r.plot(**P.chart(
        [{"x": [M_max * z / sec["I"] / 1e6 for z in zs], "y": [z * 1000 for z in zs],
          "label": "bending stress"}],
        xlabel="Bending stress  \u03c3  [MPa]", ylabel="Distance from neutral axis  [mm]",
        title="Stress distribution through the depth",
        vlines=[{"value": sy / 1e6, "label": "yield", "color": "#B3242B"},
                {"value": -sy / 1e6, "color": "#B3242B"}],
        caption="Bending stress varies linearly through the depth, which is why "
                "material near the neutral axis contributes so little."))
    return r


# ---------------------------------------------------------------------------
# 2. Column buckling
# ---------------------------------------------------------------------------

_END_CONDITIONS = [
    ("pinned", "Pinned-pinned (K = 1.0)"),
    ("fixed_free", "Fixed-free / cantilever (K = 2.0)"),
    ("fixed_fixed", "Fixed-fixed (K = 0.5)"),
    ("fixed_pinned", "Fixed-pinned (K = 0.7)"),
]
_K_VALUES = {"pinned": 1.0, "fixed_free": 2.0, "fixed_fixed": 0.5, "fixed_pinned": 0.699}


def _buckling(inp):
    sec = _section_props(inp)
    E, nu, sy, su, rho, mat = _material(inp)
    L = inp["L"]
    I_b = sec["I_min"]
    K = inp["K"] if inp["custom_K"] else _K_VALUES[inp["ends"]]
    Le = K * L
    k = math.sqrt(I_b / sec["A"])
    slender = Le / k

    P_euler = math.pi ** 2 * E * I_b / Le ** 2
    sigma_euler = P_euler / sec["A"]
    slender_crit = math.sqrt(2 * math.pi ** 2 * E / sy)

    if slender >= slender_crit:
        P_cr = P_euler
        mode = "Euler (long column) \u2014 elastic buckling"
        sigma_cr = sigma_euler
    else:
        sigma_cr = sy - (sy ** 2 / (4 * math.pi ** 2 * E)) * slender ** 2
        P_cr = sigma_cr * sec["A"]
        mode = "Johnson (intermediate column) \u2014 inelastic buckling"

    P_applied = inp["P"]

    r = Result()
    r.group("Column", f"{sec['label']} in {mat}, L = {L:g} m")
    r.out("Effective length factor", K, symbol="K")
    r.out("Effective length", Le, "m", symbol="L_e = KL")
    r.out("Radius of gyration", k * 1000, "mm", symbol="k = \u221a(I/A)")
    r.headline("Slenderness ratio", slender, symbol="L_e/k")
    r.out("Critical slenderness ratio", slender_crit, symbol="(L_e/k)_crit",
          note="the transition between Euler and Johnson behaviour")
    r.out("Cross-sectional area", sec["A"] * 1e4, "cm\u00b2")
    r.out("Second moment of area (minimum)", I_b * 1e12, "mm\u2074",
          note="buckling always occurs about the weaker axis"
          if abs(I_b - sec["I"]) > 1e-15 * sec["I"] else "")

    r.group("Buckling", mode)
    r.headline("Critical buckling load", P_cr / 1000, "kN", symbol="P_cr")
    r.headline("Critical stress", sigma_cr / 1e6, "MPa", symbol="\u03c3_cr")
    r.out("Euler load (regardless of regime)", P_euler / 1000, "kN", symbol="P_E")
    r.out("Euler stress", sigma_euler / 1e6, "MPa")
    r.out("Squash load (pure yield)", sy * sec["A"] / 1000, "kN", symbol="P_y")
    r.out("Ratio of critical to squash load", P_cr / (sy * sec["A"]))

    r.group("Applied load", f"P = {P_applied / 1000:g} kN")
    r.headline("Factor of safety on buckling",
               P_cr / P_applied if P_applied else float("inf"), symbol="FoS")
    r.out("Margin of safety", P_cr / P_applied - 1 if P_applied else float("inf"))
    r.out("Applied stress", P_applied / sec["A"] / 1e6, "MPa")
    r.out("Axial shortening before buckling",
          P_applied * L / (sec["A"] * E) * 1000, "mm")
    if P_applied > P_cr:
        r.note("The applied load exceeds the critical load — this column will "
               "buckle. Buckling failure is sudden and gives no warning, so "
               "columns are normally sized with a larger factor of safety than "
               "tension members.")

    sl = linspace(5, max(250.0, slender * 1.4), 400)
    euler = [math.pi ** 2 * E / s ** 2 / 1e6 for s in sl]
    johnson = [(sy - (sy ** 2 / (4 * math.pi ** 2 * E)) * s ** 2) / 1e6 for s in sl]
    envelope = [min(euler[i], johnson[i]) if sl[i] < slender_crit else euler[i]
                for i in range(len(sl))]
    r.plot(**P.chart(
        [{"x": sl, "y": envelope, "label": "design curve", "width": 2.4},
         {"x": sl, "y": euler, "label": "Euler", "style": "--", "width": 1.2,
          "color": P.MUTED},
         {"x": sl, "y": johnson, "label": "Johnson parabola", "style": ":",
          "width": 1.2, "color": P.SERIES[1]}],
        xlabel="Slenderness ratio  L_e/k", ylabel="Critical stress  [MPa]",
        title="Column design curve", ylim=(0, sy / 1e6 * 1.2),
        hlines=[{"value": sy / 1e6, "label": "yield strength", "color": "#B3242B"}],
        vlines=[{"value": slender_crit, "label": "transition"}],
        points=[{"x": slender, "y": sigma_cr / 1e6, "label": "your column"}],
        caption="Euler theory alone would predict stresses above yield for short "
                "columns, which is why the Johnson parabola caps it."))
    return r


# ---------------------------------------------------------------------------
# 3. Pressure vessel
# ---------------------------------------------------------------------------


def _pressure_vessel(inp):
    E, nu, sy, su, rho, mat = _material(inp)
    p = inp["p"]
    r_i, t = inp["r"], inp["t"]
    shape = inp["shape"]
    ratio = r_i / t

    thin = ratio >= 10
    if shape == "cylinder":
        s_hoop = p * r_i / t
        s_long = p * r_i / (2 * t)
        s_radial = -p
        if not thin:
            r_o = r_i + t
            s_hoop = p * (r_i ** 2) * (1 + r_o ** 2 / r_i ** 2) / (r_o ** 2 - r_i ** 2)
            s_long = p * r_i ** 2 / (r_o ** 2 - r_i ** 2)
    else:
        s_hoop = s_long = p * r_i / (2 * t)
        s_radial = -p

    s1, s2, s3 = s_hoop, s_long, s_radial
    vm = math.sqrt(0.5 * ((s1 - s2) ** 2 + (s2 - s3) ** 2 + (s3 - s1) ** 2))
    tresca = max(s1, s2, s3) - min(s1, s2, s3)
    tau_max = tresca / 2

    r = Result()
    r.group("Vessel",
            f"{'Cylinder' if shape == 'cylinder' else 'Sphere'}, {mat}, "
            f"r/t = {ratio:.4g}")
    r.out("Wall classification", "thin-walled" if thin else "thick-walled",
          note="thin-wall theory applies above r/t \u2248 10")
    r.headline("Hoop (circumferential) stress", s_hoop / 1e6, "MPa",
               symbol="\u03c3_\u03b8")
    r.headline("Longitudinal (axial) stress", s_long / 1e6, "MPa", symbol="\u03c3_z")
    r.out("Radial stress at the inner surface", s_radial / 1e6, "MPa", symbol="\u03c3_r")
    r.out("Ratio of hoop to longitudinal stress", s_hoop / s_long if s_long else float("nan"),
          note="2.0 for a cylinder \u2014 which is why cylinders split along their length")
    r.out("Maximum shear stress", tau_max / 1e6, "MPa", symbol="\u03c4_max")

    r.group("Failure criteria", f"Yield strength {sy / 1e6:g} MPa")
    r.headline("von Mises stress", vm / 1e6, "MPa", symbol="\u03c3_vm")
    r.out("Tresca (maximum shear) stress", tresca / 1e6, "MPa")
    r.headline("Factor of safety, von Mises", sy / vm if vm else float("inf"),
               symbol="FoS")
    r.out("Factor of safety, Tresca", sy / tresca if tresca else float("inf"),
          note="Tresca is always the more conservative of the two")
    r.out("Margin of safety", sy / vm - 1 if vm else float("inf"))
    r.out("Burst pressure estimate", su * t / r_i / 1e6, "MPa",
          note="thin-wall hoop failure at the ultimate strength")
    r.out("Yield pressure", p * sy / vm / 1e6 if vm else float("inf"), "MPa")

    r.group("Deformation and sizing")
    r.out("Hoop strain", (s_hoop - nu * (s_long + s_radial)) / E, symbol="\u03b5_\u03b8")
    r.out("Radial growth", r_i * (s_hoop - nu * (s_long + s_radial)) / E * 1000, "mm")
    r.out("Longitudinal strain", (s_long - nu * (s_hoop + s_radial)) / E)
    r.out("Minimum thickness for FoS 1.5",
          1.5 * vm / sy * t * 1000, "mm",
          note="scaled from the current design")
    if inp["length"] > 0:
        L = inp["length"]
        V = math.pi * r_i ** 2 * L if shape == "cylinder" else 4 / 3 * math.pi * r_i ** 3
        A_wall = 2 * math.pi * r_i * L if shape == "cylinder" else 4 * math.pi * r_i ** 2
        mass = A_wall * t * rho
        r.out("Internal volume", V * 1000, "L", symbol="V")
        r.out("Wall mass", mass, "kg")
        r.out("Pressure-volume per unit mass", p * V / mass / 1000, "kJ/kg",
              note="the performance index that drives tank material choice")

    ratios = linspace(2, max(60.0, ratio * 1.25), 300)
    r.plot(**P.chart(
        [{"x": ratios, "y": [p * x / 1e6 for x in ratios], "label": "hoop stress"},
         {"x": ratios, "y": [p * x / 2 / 1e6 for x in ratios],
          "label": "longitudinal stress", "color": P.SERIES[1]}],
        xlabel="Radius-to-thickness ratio  r/t", ylabel="Stress  [MPa]",
        title="Stress against wall slenderness",
        hlines=[{"value": sy / 1e6, "label": "yield", "color": "#B3242B"}],
        points=[{"x": ratio, "y": s_hoop / 1e6, "label": "your vessel"}],
        caption="Stress rises linearly with r/t, so a thin, large tank is always "
                "the harder structural problem."))
    return r


# ---------------------------------------------------------------------------
# 4. Stress transformation and Mohr's circle
# ---------------------------------------------------------------------------


def _mohr(inp):
    sx, sy_, txy = inp["sx"] * 1e6, inp["sy"] * 1e6, inp["txy"] * 1e6
    sz = inp["sz"] * 1e6 if inp["triaxial"] else 0.0

    avg = (sx + sy_) / 2
    R = math.sqrt(((sx - sy_) / 2) ** 2 + txy ** 2)
    s1, s2 = avg + R, avg - R
    theta_p = 0.5 * math.atan2(2 * txy, sx - sy_)
    theta_s = theta_p - math.pi / 4

    principals = sorted([s1, s2, sz], reverse=True)
    p1, p2, p3 = principals
    vm = math.sqrt(0.5 * ((p1 - p2) ** 2 + (p2 - p3) ** 2 + (p3 - p1) ** 2))
    tresca = p1 - p3

    ang = math.radians(inp["angle"])
    sx_r = avg + (sx - sy_) / 2 * math.cos(2 * ang) + txy * math.sin(2 * ang)
    sy_r = avg - (sx - sy_) / 2 * math.cos(2 * ang) - txy * math.sin(2 * ang)
    txy_r = -(sx - sy_) / 2 * math.sin(2 * ang) + txy * math.cos(2 * ang)

    r = Result()
    r.group("Principal stresses")
    r.headline("Maximum principal stress", s1 / 1e6, "MPa", symbol="\u03c3\u2081")
    r.headline("Minimum principal stress", s2 / 1e6, "MPa", symbol="\u03c3\u2082")
    if inp["triaxial"]:
        r.out("Out-of-plane principal stress", sz / 1e6, "MPa", symbol="\u03c3\u2083")
    r.out("Principal angle", math.degrees(theta_p), "\u00b0", symbol="\u03b8_p",
          note="rotate the element by this much to remove all shear")
    r.headline("Maximum in-plane shear stress", R / 1e6, "MPa", symbol="\u03c4_max")
    r.out("Angle of maximum shear", math.degrees(theta_s), "\u00b0", symbol="\u03b8_s",
          note="always 45\u00b0 from the principal directions")
    r.out("Mean (hydrostatic) stress", (p1 + p2 + p3) / 3 / 1e6, "MPa",
          symbol="\u03c3_h")
    r.out("Absolute maximum shear stress", tresca / 2 / 1e6, "MPa")

    r.group("Yield criteria")
    r.headline("von Mises equivalent stress", vm / 1e6, "MPa", symbol="\u03c3_vm")
    r.out("Tresca equivalent stress", tresca / 1e6, "MPa")
    if inp["sy_mat"] > 0:
        sy_mat = inp["sy_mat"] * 1e6
        r.out("Factor of safety, von Mises", sy_mat / vm if vm else float("inf"))
        r.out("Factor of safety, Tresca", sy_mat / tresca if tresca else float("inf"))
        r.out("Yields?", "yes" if vm > sy_mat else "no",
              note="by the von Mises criterion")

    r.group("Rotated element", f"Rotated {inp['angle']:g}\u00b0")
    r.out("Normal stress on the x face", sx_r / 1e6, "MPa", symbol="\u03c3_x'")
    r.out("Normal stress on the y face", sy_r / 1e6, "MPa", symbol="\u03c3_y'")
    r.out("Shear stress", txy_r / 1e6, "MPa", symbol="\u03c4_x'y'")
    r.out("Sum of normal stresses", (sx_r + sy_r) / 1e6, "MPa",
          note="invariant \u2014 equals \u03c3_x + \u03c3_y at any rotation")

    th = linspace(0, 2 * math.pi, 400)
    fig, ax = P.new_axes(figsize=(6.6, 5.4))
    ax.plot([avg / 1e6 + R / 1e6 * math.cos(t) for t in th],
            [R / 1e6 * math.sin(t) for t in th], color=P.SERIES[0], lw=2.0,
            label="in-plane circle")
    if inp["triaxial"]:
        for a, b, c in ((p1, p3, P.SERIES[1]), (p2, p3, P.SERIES[2])):
            ca, ra = (a + b) / 2, abs(a - b) / 2
            ax.plot([ca / 1e6 + ra / 1e6 * math.cos(t) for t in th],
                    [ra / 1e6 * math.sin(t) for t in th], color=c, lw=1.2,
                    linestyle="--")
    ax.plot([sx / 1e6, sy_ / 1e6], [txy / 1e6, -txy / 1e6], color=P.MUTED,
            lw=1.0, ls=":")
    ax.plot([sx / 1e6], [txy / 1e6], "o", ms=7, color="#B3242B",
            markeredgecolor="white", zorder=6)
    ax.annotate("(\u03c3_x, \u03c4_xy)", (sx / 1e6, txy / 1e6),
                xytext=(8, 6), textcoords="offset points", fontsize=8.5)
    ax.plot([s1 / 1e6, s2 / 1e6], [0, 0], "o", ms=6, color="#0E7C6B",
            markeredgecolor="white", zorder=6)
    ax.axhline(0, color=P.MUTED, lw=0.8)
    ax.set_aspect("equal", adjustable="datalim")
    P.style_axes(ax, xlabel="Normal stress  \u03c3  [MPa]",
                 ylabel="Shear stress  \u03c4  [MPa]", title="Mohr's circle",
                 legend=True)
    r.plot(P.render(fig), "Mohr's circle",
           "Principal stresses are where the circle crosses the \u03c3 axis; the "
           "radius is the maximum in-plane shear stress.")

    angles = linspace(0, 180, 300)
    r.plot(**P.chart(
        [{"x": angles, "y": [(avg + (sx - sy_) / 2 * math.cos(2 * math.radians(a))
                              + txy * math.sin(2 * math.radians(a))) / 1e6 for a in angles],
          "label": "\u03c3_x'"},
         {"x": angles, "y": [(-(sx - sy_) / 2 * math.sin(2 * math.radians(a))
                              + txy * math.cos(2 * math.radians(a))) / 1e6 for a in angles],
          "label": "\u03c4_x'y'", "color": P.SERIES[1]}],
        xlabel="Rotation angle  \u03b8  [\u00b0]", ylabel="Stress  [MPa]",
        title="Stress components against element rotation",
        vlines=[{"value": math.degrees(theta_p) % 180, "label": "principal plane",
                 "color": "#0E7C6B"}],
        caption="Shear passes through zero exactly at the principal planes."))
    return r


# ---------------------------------------------------------------------------
# 5. Torsion
# ---------------------------------------------------------------------------


def _torsion(inp):
    E, nu, sy, su, rho, mat = _material(inp)
    G = E / (2 * (1 + nu))
    T, L = inp["T"], inp["L"]
    kind = inp["kind"]

    if kind == "solid":
        d = inp["d"]
        J = math.pi * d ** 4 / 32
        c = d / 2
        A_shear = math.pi * d ** 2 / 4
        label = f"Solid shaft \u00f8{d * 1000:g} mm"
    elif kind == "hollow":
        do, di = inp["do"], inp["di"]
        if di >= do:
            raise CalculationError("The inner diameter must be smaller than the outer.")
        J = math.pi * (do ** 4 - di ** 4) / 32
        c = do / 2
        A_shear = math.pi * (do ** 2 - di ** 2) / 4
        label = f"Hollow shaft \u00f8{do * 1000:g}/{di * 1000:g} mm"
    else:  # thin-walled closed section, Bredt-Batho
        Am, t_w, s_peri = inp["Am"], inp["t_wall"], inp["perimeter"]
        tau = T / (2 * Am * t_w)
        J = 4 * Am ** 2 * t_w / s_peri
        phi = T * L / (G * J)
        r = Result()
        r.group("Thin-walled closed section (Bredt-Batho)", mat)
        r.headline("Shear stress in the wall", tau / 1e6, "MPa", symbol="\u03c4")
        r.out("Shear flow", T / (2 * Am), "N/m", symbol="q = T/(2A_m)",
              note="constant around a single closed cell")
        r.headline("Angle of twist", math.degrees(phi), "\u00b0", symbol="\u03d5")
        r.out("Torsion constant", J * 1e12, "mm\u2074", symbol="J")
        r.out("Torsional rigidity", G * J, "N\u00b7m\u00b2", symbol="GJ")
        r.out("Twist per unit length", math.degrees(phi / L), "\u00b0/m")
        r.out("Shear modulus", G / 1e9, "GPa", symbol="G")
        r.out("Factor of safety on shear yield",
              0.577 * sy / tau if tau else float("inf"),
              note="von Mises shear yield is 0.577 \u00d7 tensile yield")
        r.note("Bredt-Batho assumes a single closed cell with thin walls and no "
               "warping restraint. An open section of the same size would be "
               "orders of magnitude less stiff in torsion.")
        return r

    tau_max = T * c / J
    phi = T * L / (G * J)

    r = Result()
    r.group("Shaft", f"{label} in {mat}, L = {L:g} m")
    r.headline("Maximum shear stress", tau_max / 1e6, "MPa", symbol="\u03c4_max")
    r.headline("Angle of twist", math.degrees(phi), "\u00b0", symbol="\u03d5")
    r.out("Polar second moment of area", J * 1e12, "mm\u2074", symbol="J")
    r.out("Polar section modulus", J / c * 1e9, "mm\u00b3", symbol="J/c")
    r.out("Torsional rigidity", G * J, "N\u00b7m\u00b2", symbol="GJ")
    r.out("Shear modulus", G / 1e9, "GPa", symbol="G")
    r.out("Twist per unit length", math.degrees(phi / L), "\u00b0/m")
    r.out("Maximum shear strain", tau_max / G, symbol="\u03b3_max")

    r.group("Margins")
    tau_yield = 0.577 * sy
    r.headline("Factor of safety on shear yield",
               tau_yield / tau_max if tau_max else float("inf"), symbol="FoS")
    r.out("Shear yield strength", tau_yield / 1e6, "MPa",
          note="von Mises: \u03c4_y = \u03c3_y/\u221a3")
    r.out("Maximum torque at yield", tau_yield * J / c, "N\u00b7m")
    r.out("Principal stresses under pure torsion",
          f"\u00b1{tau_max / 1e6:.4g} MPa at \u00b145\u00b0",
          note="which is why brittle shafts fail on a 45\u00b0 helix")
    r.out("Mass per metre", A_shear * rho, "kg/m")
    r.out("Torque per unit mass", T / (A_shear * rho * L) if A_shear else float("nan"),
          "N\u00b7m/(kg/m)")

    if inp["rpm"] > 0:
        omega = 2 * math.pi * inp["rpm"] / 60
        r.out("Transmitted power", T * omega / 1000, "kW", symbol="P = T\u03c9")

    radii = linspace(0, c, 100)
    inner = inp["di"] / 2 if kind == "hollow" else 0.0
    r.plot(**P.chart(
        [{"x": [r_ * 1000 for r_ in radii],
          "y": [T * r_ / J / 1e6 if r_ >= inner else float("nan") for r_ in radii],
          "label": "shear stress"}],
        xlabel="Radius  [mm]", ylabel="Shear stress  \u03c4  [MPa]",
        title="Shear stress distribution",
        hlines=[{"value": tau_yield / 1e6, "label": "shear yield", "color": "#B3242B"}],
        caption="Torsional shear rises linearly with radius, so material near the "
                "centre carries almost nothing \u2014 the argument for hollow shafts."))
    return r


# ---------------------------------------------------------------------------
# 6. Classical lamination theory
# ---------------------------------------------------------------------------

PLY_MATERIALS = {
    "cfrp_hs": ("Carbon/epoxy, high strength (AS4/3501-6)",
                147e9, 10.3e9, 7.0e9, 0.27, 1600, 2280e6, 1725e6, 57e6, 228e6, 76e6),
    "cfrp_hm": ("Carbon/epoxy, high modulus",
                220e9, 6.9e9, 4.8e9, 0.25, 1600, 1400e6, 1100e6, 39e6, 130e6, 62e6),
    "gfrp": ("E-glass/epoxy",
             45e9, 12e9, 5.5e9, 0.28, 2000, 1100e6, 675e6, 27e6, 120e6, 41e6),
    "aramid": ("Aramid/epoxy (Kevlar 49)",
               76e9, 5.5e9, 2.3e9, 0.34, 1460, 1400e6, 235e6, 12e6, 53e6, 34e6),
    "boron": ("Boron/epoxy",
              204e9, 18.5e9, 5.6e9, 0.23, 2000, 1260e6, 2500e6, 61e6, 202e6, 67e6),
    "custom": ("Custom ply", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
}


def _ply_props(inp):
    key = inp["ply"]
    if key == "custom":
        return (inp["E1"] * 1e9, inp["E2"] * 1e9, inp["G12"] * 1e9, inp["nu12"],
                inp["rho_ply"], inp["Xt"] * 1e6, inp["Xc"] * 1e6, inp["Yt"] * 1e6,
                inp["Yc"] * 1e6, inp["S12"] * 1e6, "Custom ply")
    v = PLY_MATERIALS[key]
    return v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10], v[0]


def _q_matrix(E1, E2, G12, nu12):
    nu21 = nu12 * E2 / E1
    d = 1 - nu12 * nu21
    return np.array([[E1 / d, nu12 * E2 / d, 0],
                     [nu12 * E2 / d, E2 / d, 0],
                     [0, 0, G12]])


def _qbar(Q, theta):
    c, s = math.cos(theta), math.sin(theta)
    T = np.array([[c ** 2, s ** 2, 2 * c * s],
                  [s ** 2, c ** 2, -2 * c * s],
                  [-c * s, c * s, c ** 2 - s ** 2]])
    R = np.diag([1.0, 1.0, 2.0])
    return np.linalg.inv(T) @ Q @ R @ T @ np.linalg.inv(R)


def _parse_layup(s: str) -> list[float]:
    s = str(s).replace("[", "").replace("]", "").replace(" ", "")
    parts = [p for p in s.replace(",", "/").split("/") if p]
    angles = []
    for p in parts:
        try:
            angles.append(float(p))
        except ValueError:
            raise CalculationError(
                f"Could not read '{p}' as a ply angle. Enter angles in degrees "
                "separated by slashes, for example 0/45/-45/90.")
    if not angles:
        raise CalculationError("Enter at least one ply angle.")
    if len(angles) > 100:
        raise CalculationError("A maximum of 100 plies is supported.")
    return angles


def _laminate(inp):
    E1, E2, G12, nu12, rho, Xt, Xc, Yt, Yc, S12, ply_label = _ply_props(inp)
    angles = _parse_layup(inp["layup"])
    if inp["symmetric"]:
        angles = angles + angles[::-1]
    t_ply = inp["t_ply"] / 1000
    n = len(angles)
    h = n * t_ply
    z = [-h / 2 + i * t_ply for i in range(n + 1)]

    Q = _q_matrix(E1, E2, G12, nu12)
    A = np.zeros((3, 3))
    B = np.zeros((3, 3))
    D = np.zeros((3, 3))
    qbars = []
    for k, ang in enumerate(angles):
        Qb = _qbar(Q, math.radians(ang))
        qbars.append(Qb)
        A += Qb * (z[k + 1] - z[k])
        B += 0.5 * Qb * (z[k + 1] ** 2 - z[k] ** 2)
        D += (1 / 3) * Qb * (z[k + 1] ** 3 - z[k] ** 3)

    a = np.linalg.inv(A)
    Ex = 1 / (h * a[0, 0])
    Ey = 1 / (h * a[1, 1])
    Gxy = 1 / (h * a[2, 2])
    nuxy = -a[0, 1] / a[0, 0]
    nuyx = -a[0, 1] / a[1, 1]

    r = Result()
    r.group("Laminate", f"{ply_label} \u2014 [{'/'.join(f'{x:g}' for x in angles)}]")
    r.out("Number of plies", n)
    r.out("Ply thickness", t_ply * 1000, "mm")
    r.headline("Laminate thickness", h * 1000, "mm", symbol="h")
    r.out("Areal mass", rho * h, "kg/m\u00b2")
    r.out("Symmetric?", "yes" if np.allclose(B, 0, atol=1.0) else "no",
          note="a symmetric stack has B = 0, so in-plane loads cause no bending")
    r.out("Balanced?",
          "yes" if abs(A[0, 2]) < 1e-3 * abs(A[0, 0]) and abs(A[1, 2]) < 1e-3 * abs(A[0, 0])
          else "no",
          note="a balanced stack has A16 = A26 = 0, so tension causes no shear")

    r.group("Effective in-plane properties")
    r.headline("Longitudinal modulus", Ex / 1e9, "GPa", symbol="E_x")
    r.headline("Transverse modulus", Ey / 1e9, "GPa", symbol="E_y")
    r.out("Shear modulus", Gxy / 1e9, "GPa", symbol="G_xy")
    r.out("Major Poisson's ratio", nuxy, symbol="\u03bd_xy")
    r.out("Minor Poisson's ratio", nuyx, symbol="\u03bd_yx")
    r.out("Specific stiffness E_x/\u03c1", Ex / rho / 1e6, "MN\u00b7m/kg")
    r.out("Ply longitudinal modulus", E1 / 1e9, "GPa", symbol="E\u2081",
          note="the ceiling a unidirectional laminate would reach")

    r.table("A matrix — extensional stiffness [N/m]",
            ["", "1", "2", "6"],
            [[lbl] + [A[ri, j] for j in range(3)] for ri, lbl in ((0, "1"), (1, "2"), (2, "6"))],
            caption="Rows and columns follow the 1, 2, 6 convention.")
    r.table("D matrix — bending stiffness [N·m]",
            ["", "1", "2", "6"],
            [[lbl] + [D[ri, j] for j in range(3)] for ri, lbl in ((0, "1"), (1, "2"), (2, "6"))])
    if not np.allclose(B, 0, atol=1.0):
        r.table("B matrix — coupling stiffness [N]",
                ["", "1", "2", "6"],
                [[lbl] + [B[ri, j] for j in range(3)] for ri, lbl in ((0, "1"), (1, "2"), (2, "6"))],
                caption="Non-zero B couples stretching to bending — an unsymmetric "
                        "laminate warps when it cures or is loaded.")

    if inp["apply_load"]:
        N = np.array([inp["Nx"], inp["Ny"], inp["Nxy"]]) * 1000
        M = np.array([inp["Mx"], inp["My"], inp["Mxy"]])
        ABD = np.block([[A, B], [B, D]])
        try:
            sol = np.linalg.solve(ABD, np.concatenate([N, M]))
        except np.linalg.LinAlgError:
            raise CalculationError(
                "The ABD matrix is singular — check that the layup is physically "
                "meaningful.")
        eps0, kappa = sol[:3], sol[3:]

        r.group("Response to the applied load")
        r.out("Mid-plane strain \u03b5\u2093\u2070", eps0[0] * 1e6, "\u03bc\u03b5")
        r.out("Mid-plane strain \u03b5_y\u2070", eps0[1] * 1e6, "\u03bc\u03b5")
        r.out("Mid-plane shear strain \u03b3_xy\u2070", eps0[2] * 1e6, "\u03bc\u03b5")
        r.out("Curvature \u03ba_x", kappa[0], "1/m")
        r.out("Curvature \u03ba_y", kappa[1], "1/m")
        r.out("Twist \u03ba_xy", kappa[2], "1/m")

        rows = []
        worst_fi, worst_ply = 0.0, None
        stress_top, stress_bot, zs_plot = [], [], []
        for k, ang in enumerate(angles):
            th = math.radians(ang)
            c, s = math.cos(th), math.sin(th)
            T = np.array([[c ** 2, s ** 2, 2 * c * s],
                          [s ** 2, c ** 2, -2 * c * s],
                          [-c * s, c * s, c ** 2 - s ** 2]])
            for face, zf in (("bottom", z[k]), ("top", z[k + 1])):
                eps = eps0 + zf * kappa
                sig = qbars[k] @ eps
                sig12 = T @ sig
                fi = _tsai_wu(sig12, Xt, Xc, Yt, Yc, S12)
                if face == "top":
                    rows.append([f"{k + 1}", f"{ang:g}", zf * 1000,
                                 sig12[0] / 1e6, sig12[1] / 1e6, sig12[2] / 1e6, fi])
                    stress_top.append(sig12[0] / 1e6)
                else:
                    stress_bot.append(sig12[0] / 1e6)
                    zs_plot.append(zf * 1000)
                if fi > worst_fi:
                    worst_fi, worst_ply = fi, (k + 1, ang, face)

        r.out("Highest Tsai-Wu failure index", worst_fi, symbol="FI",
              note=f"ply {worst_ply[0]} at {worst_ply[1]:g}\u00b0 ({worst_ply[2]} face)"
              if worst_ply else "")
        r.out("First-ply-failure load factor",
              1 / worst_fi if worst_fi > 0 else float("inf"),
              note="multiply the applied load by this to reach first ply failure")
        r.out("First ply to fail",
              f"ply {worst_ply[0]} at {worst_ply[1]:g}\u00b0" if worst_ply else "\u2014")

        r.table("Ply stresses in material axes (top surface of each ply)",
                ["Ply", "Angle [\u00b0]", "z [mm]", "\u03c3\u2081 [MPa]",
                 "\u03c3\u2082 [MPa]", "\u03c4\u2081\u2082 [MPa]", "Tsai-Wu FI"],
                rows, sig=5,
                caption="A failure index of 1.0 means that ply has failed.")

        all_z, all_s = [], []
        for k in range(len(angles)):
            th = math.radians(angles[k])
            c, s = math.cos(th), math.sin(th)
            T = np.array([[c ** 2, s ** 2, 2 * c * s],
                          [s ** 2, c ** 2, -2 * c * s],
                          [-c * s, c * s, c ** 2 - s ** 2]])
            for zf in (z[k], z[k + 1]):
                sig12 = T @ (qbars[k] @ (eps0 + zf * kappa))
                all_z.append(zf * 1000)
                all_s.append(sig12[0] / 1e6)
        r.plot(**P.chart(
            [{"x": all_s, "y": all_z, "label": "\u03c3\u2081 in each ply"}],
            xlabel="Fibre-direction stress  \u03c3\u2081  [MPa]",
            ylabel="Through-thickness position  z  [mm]",
            title="Ply stress distribution",
            vlines=[{"value": Xt / 1e6, "label": "tensile strength", "color": "#B3242B"},
                    {"value": -Xc / 1e6, "label": "compressive strength",
                     "color": "#B3242B"}],
            caption="Stress jumps at every ply interface because each orientation "
                    "has a different stiffness in the load direction."))

    thetas = linspace(0, 90, 91)
    exs = []
    for t in thetas:
        Ai = np.zeros((3, 3))
        for ang in [t, -t] * (n // 2) if n >= 2 else [t]:
            Ai += _qbar(Q, math.radians(ang)) * t_ply
        try:
            exs.append(1 / (n * t_ply * np.linalg.inv(Ai)[0, 0]) / 1e9)
        except np.linalg.LinAlgError:
            exs.append(float("nan"))
    r.plot(**P.chart(
        [{"x": thetas, "y": P.safe(exs), "label": "[\u00b1\u03b8] laminate"}],
        xlabel="Ply angle  \u03b8  [\u00b0]", ylabel="E_x  [GPa]",
        title="Stiffness of an angle-ply laminate",
        points=[{"x": 0, "y": exs[0], "label": "all 0\u00b0"}],
        caption="Stiffness falls sharply off-axis, which is why real structures "
                "mix orientations rather than optimising for one load direction."))
    return r


def _tsai_wu(sig, Xt, Xc, Yt, Yc, S):
    s1, s2, t12 = sig
    F1 = 1 / Xt - 1 / Xc
    F2 = 1 / Yt - 1 / Yc
    F11 = 1 / (Xt * Xc)
    F22 = 1 / (Yt * Yc)
    F66 = 1 / S ** 2
    F12 = -0.5 * math.sqrt(F11 * F22)
    return (F1 * s1 + F2 * s2 + F11 * s1 ** 2 + F22 * s2 ** 2
            + F66 * t12 ** 2 + 2 * F12 * s1 * s2)


# ---------------------------------------------------------------------------
# 7. Composite micromechanics
# ---------------------------------------------------------------------------


def _micromechanics(inp):
    Ef, Em = inp["Ef"] * 1e9, inp["Em"] * 1e9
    nuf, num_ = inp["nuf"], inp["num"]
    Gf = inp["Gf"] * 1e9 if inp["custom_G"] else Ef / (2 * (1 + nuf))
    Gm = Em / (2 * (1 + num_))
    Vf = inp["Vf"]
    Vm = 1 - Vf
    if not 0 < Vf < 1:
        raise CalculationError("The fibre volume fraction must be between 0 and 1.")
    void = inp["void"]

    E1 = Ef * Vf + Em * Vm
    nu12 = nuf * Vf + num_ * Vm
    E2_rom = 1 / (Vf / Ef + Vm / Em)
    G12_rom = 1 / (Vf / Gf + Vm / Gm)

    xi_E, xi_G = inp["xi_E"], inp["xi_G"]
    eta_E = (Ef / Em - 1) / (Ef / Em + xi_E)
    E2_ht = Em * (1 + xi_E * eta_E * Vf) / (1 - eta_E * Vf)
    eta_G = (Gf / Gm - 1) / (Gf / Gm + xi_G)
    G12_ht = Gm * (1 + xi_G * eta_G * Vf) / (1 - eta_G * Vf)

    rho = inp["rho_f"] * Vf + inp["rho_m"] * Vm
    rho *= (1 - void)

    r = Result()
    r.group("Constituents", f"V_f = {Vf:g}, V_m = {Vm:.4g}")
    r.out("Fibre modulus", Ef / 1e9, "GPa", symbol="E_f")
    r.out("Matrix modulus", Em / 1e9, "GPa", symbol="E_m")
    r.out("Fibre shear modulus", Gf / 1e9, "GPa", symbol="G_f")
    r.out("Matrix shear modulus", Gm / 1e9, "GPa", symbol="G_m")
    r.out("Modulus ratio", Ef / Em, symbol="E_f/E_m")

    r.group("Predicted lamina properties")
    r.headline("Longitudinal modulus", E1 / 1e9, "GPa", symbol="E\u2081",
               note="rule of mixtures — reliable, since the fibres dominate")
    r.headline("Transverse modulus (Halpin-Tsai)", E2_ht / 1e9, "GPa", symbol="E\u2082")
    r.out("Transverse modulus (inverse rule of mixtures)", E2_rom / 1e9, "GPa",
          note="this lower bound underpredicts real data by 10 to 30 %")
    r.out("Shear modulus (Halpin-Tsai)", G12_ht / 1e9, "GPa", symbol="G\u2081\u2082")
    r.out("Shear modulus (inverse rule of mixtures)", G12_rom / 1e9, "GPa")
    r.out("Major Poisson's ratio", nu12, symbol="\u03bd\u2081\u2082")
    r.out("Minor Poisson's ratio", nu12 * E2_ht / E1, symbol="\u03bd\u2082\u2081")
    r.out("Anisotropy ratio", E1 / E2_ht, symbol="E\u2081/E\u2082")

    r.group("Physical properties")
    r.out("Density", rho, "kg/m\u00b3", symbol="\u03c1")
    if void > 0:
        r.out("Void content", void * 100, "%",
              note="above 2 % voids, strength drops noticeably")
    r.out("Specific longitudinal modulus", E1 / rho / 1e6, "MN\u00b7m/kg")
    r.out("Fibre weight fraction",
          inp["rho_f"] * Vf / (inp["rho_f"] * Vf + inp["rho_m"] * Vm) * 100, "%")

    if inp["strengths"]:
        sf, sm = inp["sigma_f"] * 1e6, inp["sigma_m"] * 1e6
        Vf_crit = (sm - Em / Ef * sf) / (sf - Em / Ef * sf + sm) if sf else float("nan")
        r.group("Strength")
        r.out("Longitudinal tensile strength", (sf * Vf + Em / Ef * sf * Vm) / 1e6, "MPa",
              symbol="X_t", note="fibre-dominated, at fibre failure strain")
        r.out("Critical fibre volume fraction", Vf_crit,
              note="below this the composite is weaker than neat matrix")
        r.out("Matrix contribution", Em / Ef * sf * Vm / 1e6, "MPa")

    vfs = linspace(0.01, 0.9, 200)
    r.plot(**P.chart(
        [{"x": vfs, "y": [(Ef * v + Em * (1 - v)) / 1e9 for v in vfs], "label": "E\u2081"},
         {"x": vfs, "y": [Em * (1 + xi_E * ((Ef / Em - 1) / (Ef / Em + xi_E)) * v)
                          / (1 - ((Ef / Em - 1) / (Ef / Em + xi_E)) * v) / 1e9
                          for v in vfs], "label": "E\u2082 (Halpin-Tsai)",
          "color": P.SERIES[1]},
         {"x": vfs, "y": [1 / (v / Ef + (1 - v) / Em) / 1e9 for v in vfs],
          "label": "E\u2082 (inverse ROM)", "style": "--", "color": P.MUTED}],
        xlabel="Fibre volume fraction  V_f", ylabel="Modulus  [GPa]",
        title="Stiffness against fibre content", ylog=True,
        points=[{"x": Vf, "y": E1 / 1e9, "label": "your lamina"}],
        vlines=[{"value": 0.65, "label": "practical packing limit"}],
        caption="Longitudinal stiffness scales linearly with fibre content; "
                "transverse stiffness barely moves until V_f is high."))
    return r


# ---------------------------------------------------------------------------
# 8. Fatigue and fracture
# ---------------------------------------------------------------------------


def _fatigue(inp):
    su = inp["su"] * 1e6
    sy = inp["sy"] * 1e6
    s_max, s_min = inp["s_max"] * 1e6, inp["s_min"] * 1e6
    s_a = (s_max - s_min) / 2
    s_m = (s_max + s_min) / 2
    R_ratio = s_min / s_max if s_max else float("nan")

    Se = inp["Se"] * 1e6 if inp["custom_Se"] else 0.5 * su
    Se_corrected = Se * inp["ka"] * inp["kb"] * inp["kc"]

    goodman = s_a / Se_corrected + s_m / su if su else float("inf")
    soderberg = s_a / Se_corrected + s_m / sy if sy else float("inf")
    gerber = s_a / Se_corrected + (s_m / su) ** 2 if su else float("inf")
    s_ar = s_a / (1 - s_m / su) if s_m < su else float("inf")

    r = Result()
    r.group("Stress cycle")
    r.out("Maximum stress", s_max / 1e6, "MPa", symbol="\u03c3_max")
    r.out("Minimum stress", s_min / 1e6, "MPa", symbol="\u03c3_min")
    r.headline("Alternating stress", s_a / 1e6, "MPa", symbol="\u03c3_a")
    r.headline("Mean stress", s_m / 1e6, "MPa", symbol="\u03c3_m")
    r.out("Stress ratio", R_ratio, symbol="R = \u03c3_min/\u03c3_max")
    r.out("Stress range", (s_max - s_min) / 1e6, "MPa", symbol="\u0394\u03c3")
    r.out("Amplitude ratio", s_a / s_m if s_m else float("inf"), symbol="A")

    r.group("Endurance limit")
    r.out("Uncorrected endurance limit", Se / 1e6, "MPa", symbol="S_e'")
    r.headline("Corrected endurance limit", Se_corrected / 1e6, "MPa", symbol="S_e")
    r.out("Equivalent fully reversed stress (Goodman)", s_ar / 1e6, "MPa",
          symbol="\u03c3_ar")

    r.group("Mean stress criteria", "Values below 1.0 mean infinite life")
    r.headline("Goodman criterion", goodman)
    r.out("Factor of safety, Goodman", 1 / goodman if goodman else float("inf"))
    r.out("Soderberg criterion", soderberg, note="the most conservative")
    r.out("Gerber criterion", gerber, note="the least conservative, best fit to data")
    r.out("Verdict", "infinite life predicted" if goodman < 1 else "finite life")
    r.out("Yield check on first cycle", (s_a + s_m) / sy if sy else float("nan"),
          note="fatigue analysis is meaningless if the part yields on load one")

    if goodman >= 1:
        # Basquin S-N estimate
        f = 0.9
        a_b = (f * su) ** 2 / Se_corrected
        b_b = -(1 / 3) * math.log10(f * su / Se_corrected)
        try:
            N = (s_ar / a_b) ** (1 / b_b)
        except (ValueError, ZeroDivisionError):
            N = float("nan")
        r.group("Finite life estimate", "Basquin fit through 10\u00b3 and 10\u2076 cycles")
        r.headline("Cycles to failure", N, symbol="N_f")
        r.out("Basquin coefficient a", a_b / 1e6, "MPa")
        r.out("Basquin exponent b", b_b)
        if inp["cycles_per_hour"] > 0:
            r.out("Life", N / inp["cycles_per_hour"], "hours")

    if inp["fracture"]:
        Kic = inp["Kic"] * 1e6
        a_crack = inp["a"] / 1000
        Y = inp["Y"]
        K = Y * s_max * math.sqrt(math.pi * a_crack)
        a_crit = (Kic / (Y * s_max)) ** 2 / math.pi
        r_plastic = (1 / (2 * math.pi)) * (Kic / sy) ** 2 if sy else float("nan")

        r.group("Fracture mechanics")
        r.headline("Stress intensity factor", K / 1e6, "MPa\u00b7\u221am", symbol="K_I")
        r.out("Fracture toughness", Kic / 1e6, "MPa\u00b7\u221am", symbol="K_Ic")
        r.headline("Critical crack length", a_crit * 1000, "mm", symbol="a_c")
        r.out("Current crack length", a_crack * 1000, "mm", symbol="a")
        r.out("Factor of safety on fracture", Kic / K if K else float("inf"))
        r.out("Fracture stress at this crack length",
              Kic / (Y * math.sqrt(math.pi * a_crack)) / 1e6, "MPa")
        r.out("Plastic zone size", r_plastic * 1000, "mm",
              note="linear elastic fracture mechanics needs this to be small "
                   "compared with the crack and the thickness")
        r.out("Minimum thickness for plane strain",
              2.5 * (Kic / sy) ** 2 * 1000 if sy else float("nan"), "mm")
        if K >= Kic:
            r.note("The stress intensity already exceeds the fracture toughness — "
                   "this crack would run unstably right now.")

        C, m_paris = inp["C"], inp["m_paris"]
        dK = Y * (s_max - s_min) * math.sqrt(math.pi * a_crack)
        dadN = C * (dK / 1e6) ** m_paris
        if a_crack < a_crit and m_paris != 2:
            Nf = ((a_crit ** (1 - m_paris / 2) - a_crack ** (1 - m_paris / 2))
                  / (C * (Y * (s_max - s_min) / 1e6 * math.sqrt(math.pi)) ** m_paris
                     * (1 - m_paris / 2)))
        else:
            Nf = float("nan")
        r.group("Crack growth (Paris law)")
        r.out("Stress intensity range", dK / 1e6, "MPa\u00b7\u221am", symbol="\u0394K")
        r.out("Growth rate", dadN, "m/cycle", symbol="da/dN")
        r.out("Growth rate", dadN * 1e6, "\u03bcm/cycle")
        r.headline("Cycles to reach the critical crack length", Nf, symbol="N_f")
        if inp["cycles_per_hour"] > 0 and Nf == Nf:
            r.out("Remaining life", Nf / inp["cycles_per_hour"], "hours")

        avals = linspace(a_crack * 0.2, a_crit * 1.2, 300)
        r.plot(**P.chart(
            [{"x": [x * 1000 for x in avals],
              "y": [Y * s_max * math.sqrt(math.pi * x) / 1e6 for x in avals],
              "label": "K_I at this stress"}],
            xlabel="Crack length  a  [mm]",
            ylabel="Stress intensity  K_I  [MPa\u00b7\u221am]",
            title="Stress intensity against crack length",
            hlines=[{"value": Kic / 1e6, "label": "K_Ic", "color": "#B3242B"}],
            points=[{"x": a_crack * 1000, "y": K / 1e6, "label": "current crack"}],
            caption="K rises with \u221aa, so crack growth accelerates as the crack "
                    "lengthens \u2014 the last few millimetres take almost no time."))

    sms = linspace(0, su / 1e6, 200)
    r.plot(**P.chart(
        [{"x": sms, "y": [Se_corrected / 1e6 * (1 - x / (su / 1e6)) for x in sms],
          "label": "Goodman"},
         {"x": sms, "y": [Se_corrected / 1e6 * (1 - (x / (su / 1e6)) ** 2) for x in sms],
          "label": "Gerber", "color": P.SERIES[1]},
         {"x": sms, "y": [max(0, Se_corrected / 1e6 * (1 - x / (sy / 1e6))) for x in sms],
          "label": "Soderberg", "color": P.SERIES[2]}],
        xlabel="Mean stress  \u03c3_m  [MPa]", ylabel="Alternating stress  \u03c3_a  [MPa]",
        title="Constant life diagram",
        points=[{"x": s_m / 1e6, "y": s_a / 1e6, "label": "your loading"}],
        caption="Anything inside a curve has infinite life by that criterion. "
                "Your point sits inside Goodman if the criterion value is below 1."))
    return r


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CALCULATORS = [
    {
        "id": "beam-bending",
        "name": "Beam bending",
        "category": CATEGORY,
        "summary": "Section properties, stresses and deflection with shear and moment diagrams.",
        "tags": ["beam", "bending stress", "deflection", "second moment", "shear diagram"],
        "inputs": _SECTION_FIELDS + _mat_fields() + [
            choice("case", "Load case", _BEAM_CASES, "cant_point", section="Loading"),
            num("L", "Span or length", 2.0, "m", minimum=1e-6, section="Loading"),
            num("P", "Point load", 5000.0, "N", section="Loading",
                show_if={"key": "case", "in": ["cant_point", "ss_point"]}),
            num("w", "Distributed load", 5000.0, "N/m", section="Loading",
                show_if={"key": "case", "in": ["cant_udl", "ss_udl", "fixed_udl"]}),
        ],
        "compute": _beam,
    },
    {
        "id": "column-buckling",
        "name": "Column buckling",
        "category": CATEGORY,
        "summary": "Euler and Johnson critical loads with the full design curve.",
        "tags": ["buckling", "Euler", "Johnson", "slenderness", "effective length"],
        "inputs": _SECTION_FIELDS + _mat_fields() + [
            num("L", "Column length", 1.0, "m", minimum=1e-6, section="Geometry"),
            choice("ends", "End conditions", _END_CONDITIONS, "pinned",
                   section="Geometry"),
            toggle("custom_K", "Enter the effective length factor", False,
                   section="Geometry"),
            num("K", "Effective length factor K", 1.0, minimum=0.1, maximum=4.0,
                section="Geometry", show_if={"key": "custom_K", "in": [True]}),
            num("P", "Applied compressive load", 50000.0, "N", minimum=0.0,
                section="Loading"),
        ],
        "compute": _buckling,
    },
    {
        "id": "pressure-vessel",
        "name": "Pressure vessel",
        "category": CATEGORY,
        "summary": "Hoop and longitudinal stresses, von Mises check and burst pressure.",
        "tags": ["hoop stress", "pressure vessel", "tank", "von Mises", "burst"],
        "inputs": [
            choice("shape", "Shape", [("cylinder", "Cylinder"), ("sphere", "Sphere")],
                   "cylinder", section="Geometry"),
            num("r", "Internal radius", 0.5, "m", minimum=1e-6, section="Geometry"),
            num("t", "Wall thickness", 0.005, "m", minimum=1e-9, section="Geometry"),
            num("length", "Cylinder length", 0.0, "m", minimum=0.0, section="Geometry",
                help="Set to 0 to skip volume and mass."),
            num("p", "Internal gauge pressure", 2000000.0, "Pa", minimum=0.0,
                section="Loading"),
        ] + _mat_fields(),
        "compute": _pressure_vessel,
    },
    {
        "id": "stress-transformation",
        "name": "Stress transformation and Mohr's circle",
        "category": CATEGORY,
        "summary": "Principal stresses, maximum shear, von Mises and Tresca with the circle drawn.",
        "tags": ["Mohr", "principal stress", "von Mises", "Tresca", "transformation"],
        "inputs": [
            num("sx", "Normal stress \u03c3_x", 100.0, "MPa", section="Stress state"),
            num("sy", "Normal stress \u03c3_y", -40.0, "MPa", section="Stress state"),
            num("txy", "Shear stress \u03c4_xy", 50.0, "MPa", section="Stress state"),
            toggle("triaxial", "Include an out-of-plane stress", False,
                   section="Stress state"),
            num("sz", "Normal stress \u03c3_z", 0.0, "MPa", section="Stress state",
                show_if={"key": "triaxial", "in": [True]}),
            num("angle", "Rotation angle to evaluate", 30.0, "\u00b0", section="Rotation"),
            num("sy_mat", "Material yield strength", 345.0, "MPa", minimum=0.0,
                section="Material", help="Set to 0 to skip the safety factors."),
        ],
        "compute": _mohr,
    },
    {
        "id": "torsion",
        "name": "Torsion of shafts and closed sections",
        "category": CATEGORY,
        "summary": "Shear stress and twist for solid, hollow and thin-walled closed sections.",
        "tags": ["torsion", "shaft", "Bredt-Batho", "shear flow", "angle of twist"],
        "inputs": [
            choice("kind", "Member", [("solid", "Solid circular shaft"),
                                      ("hollow", "Hollow circular shaft"),
                                      ("thin", "Thin-walled closed section")],
                   "solid", section="Geometry"),
            num("d", "Diameter", 0.05, "m", minimum=1e-6, section="Geometry",
                show_if={"key": "kind", "in": ["solid"]}),
            num("do", "Outer diameter", 0.06, "m", minimum=1e-6, section="Geometry",
                show_if={"key": "kind", "in": ["hollow"]}),
            num("di", "Inner diameter", 0.05, "m", minimum=0.0, section="Geometry",
                show_if={"key": "kind", "in": ["hollow"]}),
            num("Am", "Enclosed median area A_m", 0.02, "m\u00b2", minimum=1e-9,
                section="Geometry", show_if={"key": "kind", "in": ["thin"]}),
            num("t_wall", "Wall thickness", 0.002, "m", minimum=1e-9, section="Geometry",
                show_if={"key": "kind", "in": ["thin"]}),
            num("perimeter", "Median perimeter", 0.6, "m", minimum=1e-9,
                section="Geometry", show_if={"key": "kind", "in": ["thin"]}),
            num("L", "Length", 1.0, "m", minimum=1e-9, section="Geometry"),
            num("T", "Applied torque", 1000.0, "N\u00b7m", section="Loading"),
            num("rpm", "Rotational speed", 0.0, "rpm", minimum=0.0, section="Loading",
                help="Set to 0 to skip the power calculation."),
        ] + _mat_fields(),
        "compute": _torsion,
    },
    {
        "id": "laminate-clt",
        "name": "Composite laminate (classical lamination theory)",
        "category": CATEGORY,
        "summary": "ABD matrices, effective properties, ply stresses and Tsai-Wu first-ply failure.",
        "description": "A full CLT solve: builds the transformed stiffness of every ply, "
                       "assembles A, B and D, and can apply a load case to find ply stresses "
                       "and the first ply to fail.",
        "tags": ["CLT", "ABD matrix", "laminate", "Tsai-Wu", "ply stress", "layup"],
        "inputs": [
            choice("ply", "Ply material",
                   [(k, v[0]) for k, v in PLY_MATERIALS.items()], "cfrp_hs",
                   section="Ply material"),
            num("E1", "E\u2081", 147.0, "GPa", minimum=0.001, section="Ply material",
                show_if={"key": "ply", "in": ["custom"]}),
            num("E2", "E\u2082", 10.3, "GPa", minimum=0.001, section="Ply material",
                show_if={"key": "ply", "in": ["custom"]}),
            num("G12", "G\u2081\u2082", 7.0, "GPa", minimum=0.001, section="Ply material",
                show_if={"key": "ply", "in": ["custom"]}),
            num("nu12", "\u03bd\u2081\u2082", 0.27, minimum=0.0, maximum=0.6,
                section="Ply material", show_if={"key": "ply", "in": ["custom"]}),
            num("rho_ply", "Density", 1600.0, "kg/m\u00b3", minimum=1.0,
                section="Ply material", show_if={"key": "ply", "in": ["custom"]}),
            num("Xt", "Longitudinal tensile strength", 2280.0, "MPa", minimum=0.001,
                section="Ply material", show_if={"key": "ply", "in": ["custom"]}),
            num("Xc", "Longitudinal compressive strength", 1725.0, "MPa", minimum=0.001,
                section="Ply material", show_if={"key": "ply", "in": ["custom"]}),
            num("Yt", "Transverse tensile strength", 57.0, "MPa", minimum=0.001,
                section="Ply material", show_if={"key": "ply", "in": ["custom"]}),
            num("Yc", "Transverse compressive strength", 228.0, "MPa", minimum=0.001,
                section="Ply material", show_if={"key": "ply", "in": ["custom"]}),
            num("S12", "In-plane shear strength", 76.0, "MPa", minimum=0.001,
                section="Ply material", show_if={"key": "ply", "in": ["custom"]}),
            text("layup", "Stacking sequence", "0/45/-45/90", section="Layup",
                 placeholder="0/45/-45/90",
                 help="Ply angles in degrees, separated by slashes, listed from the "
                      "bottom surface upward."),
            toggle("symmetric", "Mirror the stack to make it symmetric", True,
                   section="Layup"),
            num("t_ply", "Ply thickness", 0.125, "mm", minimum=1e-6, section="Layup"),
            toggle("apply_load", "Apply a load case", True, section="Loading"),
            num("Nx", "N_x", 100.0, "kN/m", section="Loading",
                show_if={"key": "apply_load", "in": [True]}),
            num("Ny", "N_y", 0.0, "kN/m", section="Loading",
                show_if={"key": "apply_load", "in": [True]}),
            num("Nxy", "N_xy", 0.0, "kN/m", section="Loading",
                show_if={"key": "apply_load", "in": [True]}),
            num("Mx", "M_x", 0.0, "N\u00b7m/m", section="Loading",
                show_if={"key": "apply_load", "in": [True]}),
            num("My", "M_y", 0.0, "N\u00b7m/m", section="Loading",
                show_if={"key": "apply_load", "in": [True]}),
            num("Mxy", "M_xy", 0.0, "N\u00b7m/m", section="Loading",
                show_if={"key": "apply_load", "in": [True]}),
        ],
        "compute": _laminate,
    },
    {
        "id": "micromechanics",
        "name": "Composite micromechanics",
        "category": CATEGORY,
        "summary": "Lamina properties from fibre and matrix using rule of mixtures and Halpin-Tsai.",
        "tags": ["rule of mixtures", "Halpin-Tsai", "fibre volume fraction", "lamina"],
        "inputs": [
            num("Ef", "Fibre modulus", 230.0, "GPa", minimum=0.001, section="Fibre"),
            num("nuf", "Fibre Poisson's ratio", 0.2, minimum=0.0, maximum=0.5,
                section="Fibre"),
            toggle("custom_G", "Enter the fibre shear modulus", False, section="Fibre"),
            num("Gf", "Fibre shear modulus", 22.0, "GPa", minimum=0.001, section="Fibre",
                show_if={"key": "custom_G", "in": [True]}),
            num("rho_f", "Fibre density", 1800.0, "kg/m\u00b3", minimum=1.0,
                section="Fibre"),
            num("Em", "Matrix modulus", 3.45, "GPa", minimum=0.001, section="Matrix"),
            num("num", "Matrix Poisson's ratio", 0.35, minimum=0.0, maximum=0.5,
                section="Matrix"),
            num("rho_m", "Matrix density", 1200.0, "kg/m\u00b3", minimum=1.0,
                section="Matrix"),
            num("Vf", "Fibre volume fraction", 0.6, minimum=0.01, maximum=0.95,
                section="Composition"),
            num("void", "Void content", 0.0, minimum=0.0, maximum=0.1,
                section="Composition"),
            num("xi_E", "Halpin-Tsai \u03be for E\u2082", 2.0, minimum=0.0, maximum=20.0,
                section="Halpin-Tsai", help="2 for circular fibres in a square array."),
            num("xi_G", "Halpin-Tsai \u03be for G\u2081\u2082", 1.0, minimum=0.0,
                maximum=20.0, section="Halpin-Tsai"),
            toggle("strengths", "Estimate longitudinal strength", False,
                   section="Strength"),
            num("sigma_f", "Fibre tensile strength", 3500.0, "MPa", minimum=0.001,
                section="Strength", show_if={"key": "strengths", "in": [True]}),
            num("sigma_m", "Matrix tensile strength", 70.0, "MPa", minimum=0.001,
                section="Strength", show_if={"key": "strengths", "in": [True]}),
        ],
        "compute": _micromechanics,
    },
    {
        "id": "fatigue-fracture",
        "name": "Fatigue and fracture",
        "category": CATEGORY,
        "summary": "Goodman, Soderberg and Gerber criteria, S–N life, stress intensity and Paris law.",
        "tags": ["fatigue", "Goodman", "S-N", "fracture", "stress intensity", "Paris law"],
        "inputs": [
            num("s_max", "Maximum stress", 200.0, "MPa", section="Loading"),
            num("s_min", "Minimum stress", -50.0, "MPa", section="Loading"),
            num("cycles_per_hour", "Cycles per hour", 0.0, minimum=0.0, section="Loading",
                help="Set to 0 to report life in cycles only."),
            num("su", "Ultimate tensile strength", 483.0, "MPa", minimum=0.001,
                section="Material"),
            num("sy", "Yield strength", 345.0, "MPa", minimum=0.001, section="Material"),
            toggle("custom_Se", "Enter the endurance limit", False, section="Material"),
            num("Se", "Endurance limit", 240.0, "MPa", minimum=0.001, section="Material",
                show_if={"key": "custom_Se", "in": [True]},
                help="Left blank, it is estimated as 0.5 \u00d7 ultimate strength."),
            num("ka", "Surface finish factor k_a", 0.9, minimum=0.1, maximum=1.0,
                section="Marin factors"),
            num("kb", "Size factor k_b", 0.9, minimum=0.1, maximum=1.0,
                section="Marin factors"),
            num("kc", "Load type factor k_c", 1.0, minimum=0.1, maximum=1.0,
                section="Marin factors"),
            toggle("fracture", "Include fracture mechanics", False, section="Fracture"),
            num("Kic", "Fracture toughness K_Ic", 36.0, "MPa\u00b7\u221am", minimum=0.001,
                section="Fracture", show_if={"key": "fracture", "in": [True]}),
            num("a", "Crack length", 2.0, "mm", minimum=1e-6, section="Fracture",
                show_if={"key": "fracture", "in": [True]}),
            num("Y", "Geometry factor Y", 1.12, minimum=0.1, maximum=5.0,
                section="Fracture", show_if={"key": "fracture", "in": [True]},
                help="1.12 for an edge crack, 1.0 for a central crack."),
            num("C", "Paris coefficient C", 1e-11, section="Fracture",
                show_if={"key": "fracture", "in": [True]},
                help="For da/dN in m/cycle with \u0394K in MPa\u00b7\u221am."),
            num("m_paris", "Paris exponent m", 3.0, minimum=1.0, maximum=8.0,
                section="Fracture", show_if={"key": "fracture", "in": [True]}),
        ],
        "compute": _fatigue,
    },
]
