"""Thermodynamics: states and processes, power cycles, heat transfer."""

from __future__ import annotations

import math

from .. import plotting as P
from ..core import CalculationError, Result, choice, num, toggle
from ..numeric import linspace, solve
from ..physics import (GAS_OPTIONS, STEFAN_BOLTZMANN, cp_from, cv_from,
                       gas_properties)

CATEGORY = "Thermodynamics"


def _gas_fields(section="Working gas", default="air"):
    return [
        choice("gas", "Working gas", GAS_OPTIONS, default, section=section),
        num("gamma", "Specific heat ratio \u03b3", 1.4, minimum=1.001, maximum=2.0,
            section=section, show_if={"key": "gas", "in": ["custom"]}),
        num("R", "Gas constant R", 287.05287, "J/(kg\u00b7K)", minimum=1.0,
            section=section, show_if={"key": "gas", "in": ["custom"]}),
    ]


# ---------------------------------------------------------------------------
# 1. Polytropic process
# ---------------------------------------------------------------------------


def _process(inp):
    g, R, gas = gas_properties(inp)
    cp, cv = cp_from(g, R), cv_from(g, R)
    p1, T1, m = inp["p1"], inp["T1"], inp["m"]
    v1 = R * T1 / p1
    V1 = m * v1

    kind = inp["process"]
    n = {"isothermal": 1.0, "isobaric": 0.0, "isochoric": math.inf,
         "isentropic": g}.get(kind, inp["n"])

    known, val = inp["known"], inp["value"]
    if kind == "isochoric":
        v2 = v1
        if known == "p2":
            p2 = val
            T2 = T1 * p2 / p1
        elif known == "T2":
            T2 = val
            p2 = p1 * T2 / T1
        else:
            raise CalculationError(
                "For a constant-volume process, specify the final pressure or "
                "temperature — the volume cannot change.")
    else:
        if known == "p2":
            p2 = val
            if kind == "isobaric":
                raise CalculationError(
                    "For a constant-pressure process, specify the final volume "
                    "or temperature instead.")
            v2 = v1 * (p1 / p2) ** (1.0 / n) if n != 0 else v1
            T2 = p2 * v2 / R
        elif known == "v2":
            v2 = val / m if inp["value_is_total"] else val
            p2 = p1 * (v1 / v2) ** n if n != math.inf else p1
            T2 = p2 * v2 / R
        else:
            T2 = val
            if kind == "isothermal":
                raise CalculationError(
                    "For an isothermal process the temperature cannot change. "
                    "Specify the final pressure or volume instead.")
            if kind == "isobaric":
                p2 = p1
                v2 = R * T2 / p2
            else:
                p2 = p1 * (T2 / T1) ** (n / (n - 1.0))
                v2 = R * T2 / p2
    V2 = m * v2

    du = m * cv * (T2 - T1)
    dh = m * cp * (T2 - T1)
    if kind == "isothermal":
        W = m * R * T1 * math.log(v2 / v1)
        Q = W
    elif kind == "isochoric":
        W = 0.0
        Q = du
    else:
        W = m * R * (T1 - T2) / (n - 1.0) if n != 1.0 else m * R * T1 * math.log(v2 / v1)
        Q = du + W
    ds = m * (cp * math.log(T2 / T1) - R * math.log(p2 / p1))

    r = Result()
    r.group("Process", f"{gas}, {_process_name(kind, n)}")
    r.out("Polytropic index", n if math.isfinite(n) else "\u221e", symbol="n")
    r.out("Specific heat at constant pressure", cp, "J/(kg\u00b7K)", symbol="c_p")
    r.out("Specific heat at constant volume", cv, "J/(kg\u00b7K)", symbol="c_v")
    r.out("Polytropic specific heat",
          cv * (n - g) / (n - 1.0) if math.isfinite(n) and n != 1 else float("nan"),
          "J/(kg\u00b7K)", symbol="c_n")

    r.group("State 1")
    r.out("Pressure", p1, "Pa", symbol="p\u2081")
    r.out("Temperature", T1, "K", symbol="T\u2081")
    r.out("Specific volume", v1, "m\u00b3/kg", symbol="v\u2081")
    r.out("Volume", V1, "m\u00b3", symbol="V\u2081")
    r.out("Density", 1 / v1, "kg/m\u00b3", symbol="\u03c1\u2081")

    r.group("State 2")
    r.out("Pressure", p2, "Pa", symbol="p\u2082")
    r.out("Temperature", T2, "K", symbol="T\u2082")
    r.out("Specific volume", v2, "m\u00b3/kg", symbol="v\u2082")
    r.out("Volume", V2, "m\u00b3", symbol="V\u2082")
    r.out("Compression ratio", v1 / v2, symbol="v\u2081/v\u2082")
    r.out("Pressure ratio", p2 / p1, symbol="p\u2082/p\u2081")

    r.group("Energy transfers", f"for {m:g} kg")
    r.headline("Boundary work", W, "J", symbol="W", note="positive means done by the gas")
    r.headline("Heat transfer", Q, "J", symbol="Q", note="positive means added to the gas")
    r.out("Change in internal energy", du, "J", symbol="\u0394U")
    r.out("Change in enthalpy", dh, "J", symbol="\u0394H")
    r.out("Change in entropy", ds, "J/K", symbol="\u0394S")
    r.out("Specific work", W / m, "J/kg", symbol="w")
    r.out("Specific heat transfer", Q / m, "J/kg", symbol="q")

    vs = linspace(min(v1, v2), max(v1, v2), 200)
    if kind == "isochoric":
        pv_x, pv_y = [v1, v1], [p1, p2]
    else:
        pv_x = vs
        pv_y = [p1 * (v1 / v) ** n for v in vs] if math.isfinite(n) else [p1] * len(vs)
    r.plot(**P.chart(
        [{"x": pv_x, "y": pv_y, "label": _process_name(kind, n), "fill": True}],
        xlabel="Specific volume  v  [m\u00b3/kg]", ylabel="Pressure  p  [Pa]",
        title="p\u2013v diagram",
        points=[{"x": v1, "y": p1, "annotate": "1", "color": "#16497E"},
                {"x": v2, "y": p2, "annotate": "2"}],
        caption="The shaded area is the boundary work \u222bp dv."))

    Ts = linspace(min(T1, T2), max(T1, T2), 200) if abs(T2 - T1) > 1e-9 else [T1, T1]
    if abs(T2 - T1) > 1e-9:
        ss = [cp * math.log(t / T1) - R * math.log(_p_at_T(t, T1, p1, kind, n) / p1)
              for t in Ts]
    else:
        ss = [0.0, ds / m]
        Ts = [T1, T2]

    # For a genuinely isentropic process the two logarithms cancel exactly in
    # exact arithmetic but leave ~1e-13 of rounding noise in floating point.
    # Plotted, that noise becomes a wild zigzag on a 1e-13 axis. Snap it flat
    # and give the axis a readable width instead.
    entropy_span = max(ss) - min(ss)
    ts_xlim = None
    if entropy_span < 1e-9 * cp:
        ss = [0.0 for _ in ss]
        ts_xlim = (-1.0, 1.0)

    r.plot(**P.chart(
        [{"x": ss, "y": Ts, "label": _process_name(kind, n)}],
        xlabel="Specific entropy change  s \u2212 s\u2081  [J/(kg\u00b7K)]",
        ylabel="Temperature  T  [K]", title="T\u2013s diagram", xlim=ts_xlim,
        points=[{"x": 0.0, "y": T1, "annotate": "1", "color": "#16497E"},
                {"x": 0.0 if ts_xlim else ds / m, "y": T2, "annotate": "2"}],
        caption="A vertical line would be isentropic; the slope here shows how "
                "much entropy the heat transfer carries."))
    return r


def _p_at_T(t, T1, p1, kind, n):
    if kind == "isobaric":
        return p1
    if kind == "isochoric":
        return p1 * t / T1
    if kind == "isothermal":
        return p1
    return p1 * (t / T1) ** (n / (n - 1.0))


def _process_name(kind, n):
    return {"isothermal": "isothermal (n = 1)", "isobaric": "isobaric (n = 0)",
            "isochoric": "isochoric (n \u2192 \u221e)",
            "isentropic": f"isentropic (n = \u03b3 = {n:g})"}.get(
        kind, f"polytropic, n = {n:g}")


# ---------------------------------------------------------------------------
# 2. Brayton cycle
# ---------------------------------------------------------------------------


def _brayton(inp):
    g, R, gas = gas_properties(inp)
    cp = cp_from(g, R)
    T1, p1, rp = inp["T1"], inp["p1"], inp["rp"]
    T3 = inp["T3"]
    eta_c, eta_t = inp["eta_c"], inp["eta_t"]
    if rp < 1:
        raise CalculationError("The pressure ratio must be at least 1.")
    if T3 <= T1:
        raise CalculationError(
            "The turbine inlet temperature must exceed the compressor inlet "
            "temperature for the cycle to produce work.")
    e = (g - 1.0) / g

    T2s = T1 * rp ** e
    T2 = T1 + (T2s - T1) / eta_c
    T4s = T3 * (1.0 / rp) ** e
    T4 = T3 - eta_t * (T3 - T4s)

    T2r = T2
    if inp["regen"]:
        eff = inp["eff_regen"]
        if T4 > T2:
            T2r = T2 + eff * (T4 - T2)
        else:
            T2r = T2

    w_c = cp * (T2 - T1)
    w_t = cp * (T3 - T4)
    w_net = w_t - w_c
    q_in = cp * (T3 - T2r)
    if q_in <= 0:
        raise CalculationError(
            "The compressor already delivers air hotter than the turbine inlet "
            "temperature — reduce the pressure ratio or raise T\u2083.")
    eta = w_net / q_in
    bwr = w_c / w_t
    q_out = q_in - w_net

    rp_opt = (T3 / T1) ** (1.0 / (2 * e))

    r = Result()
    r.group("Cycle", f"{gas} \u2014 pressure ratio {rp:g}, T\u2083 = {T3:g} K")
    r.headline("Thermal efficiency", eta * 100, "%", symbol="\u03b7_th")
    r.headline("Net specific work", w_net, "J/kg", symbol="w_net")
    r.out("Back work ratio", bwr, symbol="BWR",
          note="fraction of turbine work consumed by the compressor")
    r.out("Heat added", q_in, "J/kg", symbol="q_in")
    r.out("Heat rejected", q_out, "J/kg", symbol="q_out")
    r.out("Compressor specific work", w_c, "J/kg", symbol="w_c")
    r.out("Turbine specific work", w_t, "J/kg", symbol="w_t")
    r.out("Ideal (Carnot) efficiency for these temperatures", (1 - T1 / T3) * 100, "%")
    r.out("Ideal air-standard efficiency", (1 - rp ** -e) * 100, "%",
          note="with perfect components and no regeneration")

    r.group("Station temperatures")
    r.out("1 \u2014 compressor inlet", T1, "K")
    r.out("2s \u2014 ideal compressor exit", T2s, "K")
    r.out("2 \u2014 actual compressor exit", T2, "K")
    if inp["regen"]:
        r.out("2r \u2014 after regenerator", T2r, "K",
              note=f"effectiveness {inp['eff_regen']:g}")
    r.out("3 \u2014 turbine inlet", T3, "K")
    r.out("4s \u2014 ideal turbine exit", T4s, "K")
    r.out("4 \u2014 actual turbine exit", T4, "K")
    r.out("Compressor exit pressure", p1 * rp, "Pa", symbol="p\u2082")

    r.group("Design guidance")
    r.out("Pressure ratio for maximum specific work", rp_opt, symbol="rp_opt",
          note="ideal cycle: rp = (T\u2083/T\u2081)^(\u03b3/(2(\u03b3\u22121)))")
    r.out("Temperature ratio", T3 / T1, symbol="T\u2083/T\u2081")
    if inp["regen"] and T4 <= T2:
        r.note("Turbine exit temperature is below compressor exit temperature, so "
               "the regenerator cannot transfer heat in the useful direction. "
               "Regeneration only pays at low pressure ratios.")

    if inp["mass_flow"] > 0:
        mdot = inp["mass_flow"]
        r.group("Machine", f"\u1e41 = {mdot:g} kg/s")
        r.out("Net power output", w_net * mdot / 1000, "kW", symbol="P")
        r.out("Heat input rate", q_in * mdot / 1000, "kW")
        r.out("Compressor power", w_c * mdot / 1000, "kW")
        r.out("Turbine power", w_t * mdot / 1000, "kW")
        if inp["lhv"] > 0:
            f = q_in / (inp["lhv"] * 1e6)
            r.out("Fuel-air ratio", f, symbol="f")
            r.out("Fuel flow", f * mdot, "kg/s")
            r.out("Specific fuel consumption", f * mdot / (w_net * mdot / 1000) * 3.6e6,
                  "g/(kW\u00b7h)", symbol="SFC")

    rps = linspace(1.05, max(50.0, rp * 1.4), 300)

    def cycle_eff(x, regen):
        t2s = T1 * x ** e
        t2 = T1 + (t2s - T1) / eta_c
        t4s = T3 * x ** -e
        t4 = T3 - eta_t * (T3 - t4s)
        t2r = t2 + inp["eff_regen"] * (t4 - t2) if (regen and t4 > t2) else t2
        qin = cp * (T3 - t2r)
        wn = cp * (T3 - t4) - cp * (t2 - T1)
        return (wn / qin * 100 if qin > 0 else float("nan"), wn)

    series = [{"x": rps, "y": [cycle_eff(x, False)[0] for x in rps],
               "label": "no regeneration"}]
    if inp["regen"]:
        series.append({"x": rps, "y": [cycle_eff(x, True)[0] for x in rps],
                       "label": "with regeneration", "color": P.SERIES[1]})
    r.plot(**P.chart(
        series, xlabel="Pressure ratio  r_p", ylabel="Thermal efficiency  [%]",
        title="Efficiency against pressure ratio",
        points=[{"x": rp, "y": eta * 100, "label": "your design"}],
        caption="With real components efficiency peaks and then falls, unlike the "
                "ideal cycle which rises monotonically."))

    r.plot(**P.chart(
        [{"x": rps, "y": [cycle_eff(x, False)[1] / 1000 for x in rps],
          "label": "specific work", "color": P.SERIES[2]}],
        xlabel="Pressure ratio  r_p", ylabel="Net specific work  [kJ/kg]",
        title="Specific work against pressure ratio",
        points=[{"x": rp, "y": w_net / 1000, "label": "your design"}],
        vlines=[{"value": rp_opt, "label": "ideal optimum"}],
        caption="Maximum specific work and maximum efficiency occur at different "
                "pressure ratios \u2014 engine designers must choose between "
                "a compact engine and an economical one."))

    # T-s diagram
    def s_of(T, p):
        return cp * math.log(T / T1) - R * math.log(p / p1)

    p2 = p1 * rp
    ss, ts = [], []
    for T, p in ((T1, p1), (T2, p2), (T3, p2), (T4, p1), (T1, p1)):
        ss.append(s_of(T, p))
        ts.append(T)
    # smooth isobaric legs
    leg1_T = linspace(T2r, T3, 60)
    leg2_T = linspace(T4, T1, 60)
    r.plot(**P.chart(
        [{"x": [s_of(T1, p1), s_of(T2, p2)], "y": [T1, T2], "label": "compression",
          "color": P.SERIES[0]},
         {"x": [s_of(t, p2) for t in leg1_T], "y": list(leg1_T),
          "label": "heat addition", "color": "#B3242B"},
         {"x": [s_of(T3, p2), s_of(T4, p1)], "y": [T3, T4], "label": "expansion",
          "color": P.SERIES[2]},
         {"x": [s_of(t, p1) for t in leg2_T], "y": list(leg2_T),
          "label": "heat rejection", "color": P.SERIES[1]}],
        xlabel="Specific entropy  s \u2212 s\u2081  [J/(kg\u00b7K)]",
        ylabel="Temperature  T  [K]", title="T\u2013s diagram",
        points=[{"x": s_of(T1, p1), "y": T1, "annotate": "1"},
                {"x": s_of(T2, p2), "y": T2, "annotate": "2"},
                {"x": s_of(T3, p2), "y": T3, "annotate": "3"},
                {"x": s_of(T4, p1), "y": T4, "annotate": "4"}],
        caption="Compression and expansion lean to the right because the "
                "component efficiencies generate entropy."))
    return r


# ---------------------------------------------------------------------------
# 3. Piston cycles
# ---------------------------------------------------------------------------


def _piston_cycle(inp):
    g, R, gas = gas_properties(inp)
    cp, cv = cp_from(g, R), cv_from(g, R)
    kind = inp["cycle"]
    rc, T1, p1 = inp["rc"], inp["T1"], inp["p1"]
    if rc <= 1:
        raise CalculationError("The compression ratio must be greater than 1.")

    v1 = R * T1 / p1
    v2 = v1 / rc
    T2 = T1 * rc ** (g - 1)
    p2 = p1 * rc ** g

    if kind == "otto":
        q_in = inp["q_in"]
        T3 = T2 + q_in / cv
        p3 = p2 * T3 / T2
        v3 = v2
        T4 = T3 * (v3 / v1) ** (g - 1)
        eta_ideal = 1 - rc ** (1 - g)
        cutoff = 1.0
        states = [(v1, p1), (v2, p2), (v3, p3), (v1, p1 * T4 / T1)]
    elif kind == "diesel":
        q_in = inp["q_in"]
        T3 = T2 + q_in / cp
        cutoff = T3 / T2
        v3 = v2 * cutoff
        p3 = p2
        T4 = T3 * (v3 / v1) ** (g - 1)
        eta_ideal = 1 - (1 / rc ** (g - 1)) * (cutoff ** g - 1) / (g * (cutoff - 1))
        states = [(v1, p1), (v2, p2), (v3, p3), (v1, p1 * T4 / T1)]
    else:  # dual
        rp = inp["rp_dual"]
        T2a = T2 * rp
        p2a = p2 * rp
        q_v = cv * (T2a - T2)
        q_in_total = inp["q_in"]
        q_p = q_in_total - q_v
        if q_p < 0:
            raise CalculationError(
                "The constant-volume pressure rise alone already exceeds the heat "
                "input. Lower the pressure ratio or add more heat.")
        T3 = T2a + q_p / cp
        cutoff = T3 / T2a
        v3 = v2 * cutoff
        p3 = p2a
        T4 = T3 * (v3 / v1) ** (g - 1)
        eta_ideal = 1 - (1 / rc ** (g - 1)) * (rp * cutoff ** g - 1) / (
            (rp - 1) + g * rp * (cutoff - 1))
        q_in = q_in_total
        states = [(v1, p1), (v2, p2), (v2, p2a), (v3, p3), (v1, p1 * T4 / T1)]

    q_out = cv * (T4 - T1)
    w_net = q_in - q_out
    eta = w_net / q_in
    mep = w_net / (v1 - v2)

    r = Result()
    r.group("Cycle", f"{dict(otto='Otto', diesel='Diesel', dual='Dual')[kind]} cycle, "
            f"{gas}, r = {rc:g}")
    r.headline("Thermal efficiency", eta * 100, "%", symbol="\u03b7_th")
    r.headline("Net specific work", w_net, "J/kg", symbol="w_net")
    r.out("Air-standard efficiency (closed form)", eta_ideal * 100, "%")
    r.out("Mean effective pressure", mep, "Pa", symbol="MEP")
    r.out("Mean effective pressure", mep / 1e5, "bar")
    r.out("Heat added", q_in, "J/kg")
    r.out("Heat rejected", q_out, "J/kg")
    if kind != "otto":
        r.out("Cut-off ratio", cutoff, symbol="r_c")
    r.out("Otto efficiency at the same compression ratio", (1 - rc ** (1 - g)) * 100, "%",
          note="the ceiling for any cycle at this compression ratio")

    r.group("State points")
    r.out("T\u2081 \u2014 start of compression", T1, "K")
    r.out("T\u2082 \u2014 end of compression", T2, "K")
    r.out("p\u2082 \u2014 end of compression", p2, "Pa")
    r.out("T\u2083 \u2014 peak temperature", T3, "K")
    r.out("p\u2083 \u2014 peak pressure", p3, "Pa")
    r.out("T\u2084 \u2014 end of expansion", T4, "K")
    r.out("Peak pressure", p3 / 1e5, "bar")

    if inp["engine"]:
        Vd, N, ncyl = inp["Vd"] / 1e6, inp["rpm"], inp["cylinders"]
        strokes = 2 if inp["two_stroke"] else 4
        rho1 = p1 / (R * T1)
        m_cycle = rho1 * Vd * rc / (rc - 1) * (rc - 1) / rc  # displaced mass
        m_cycle = rho1 * Vd
        power = w_net * m_cycle * ncyl * (N / 60) / (strokes / 2) / 1000
        r.group("Engine", f"{ncyl} cylinders, {inp['Vd']:g} cm\u00b3 each, {N:g} rpm")
        r.out("Mass per cycle per cylinder", m_cycle * 1000, "g")
        r.out("Indicated power", power, "kW")
        r.out("Work per cycle per cylinder", w_net * m_cycle, "J")
        r.out("Torque", power * 1000 / (2 * math.pi * N / 60), "N\u00b7m")

    xs = [s[0] for s in states] + [states[0][0]]
    ys = [s[1] for s in states] + [states[0][1]]
    comp_v = linspace(v2, v1, 60)
    r.plot(**P.chart(
        [{"x": list(comp_v), "y": [p1 * (v1 / v) ** g for v in comp_v],
          "label": "isentropic compression"},
         {"x": list(comp_v), "y": [(p1 * T4 / T1) * (v1 / v) ** g for v in comp_v],
          "label": "isentropic expansion", "color": P.SERIES[2]},
         {"x": xs, "y": ys, "label": "cycle", "color": "#B3242B", "width": 1.4,
          "style": "--"}],
        xlabel="Specific volume  v  [m\u00b3/kg]", ylabel="Pressure  p  [Pa]",
        title="p\u2013v diagram", ylog=True,
        caption="Area enclosed by the cycle is the net work per unit mass."))

    rcs = linspace(2, 25, 200)
    r.plot(**P.chart(
        [{"x": rcs, "y": [(1 - x ** (1 - g)) * 100 for x in rcs], "label": "Otto"},
         {"x": rcs, "y": [(1 - (1 / x ** (g - 1)) * (2 ** g - 1) / (g * (2 - 1))) * 100
                          for x in rcs], "label": "Diesel, r_c = 2",
          "color": P.SERIES[1]}],
        xlabel="Compression ratio  r", ylabel="Air-standard efficiency  [%]",
        title="Efficiency against compression ratio",
        points=[{"x": rc, "y": eta * 100, "label": "your cycle"}],
        caption="At equal compression ratio the Otto cycle is more efficient, but "
                "diesels run at much higher r because they are not knock-limited."))
    return r


# ---------------------------------------------------------------------------
# 4. Heat transfer
# ---------------------------------------------------------------------------


def _heat_transfer(inp):
    r = Result()
    geom = inp["geometry"]
    Th, Tc = inp["Th"], inp["Tc"]
    h_in, h_out = inp["h_in"], inp["h_out"]

    if geom == "wall":
        A = inp["A"]
        layers = [(inp["L1"], inp["k1"]), (inp["L2"], inp["k2"]), (inp["L3"], inp["k3"])]
        R_conv_in = 1 / (h_in * A) if h_in > 0 else 0.0
        R_conv_out = 1 / (h_out * A) if h_out > 0 else 0.0
        R_cond = []
        for L, k in layers:
            if L > 0 and k > 0:
                R_cond.append(L / (k * A))
        R_total = R_conv_in + sum(R_cond) + R_conv_out
        area_label = f"A = {A:g} m\u00b2"
    else:
        L = inp["L_pipe"]
        r1, r2 = inp["r1"], inp["r2"]
        if r2 <= r1:
            raise CalculationError("The outer radius must exceed the inner radius.")
        R_conv_in = 1 / (h_in * 2 * math.pi * r1 * L) if h_in > 0 else 0.0
        R_conv_out = 1 / (h_out * 2 * math.pi * r2 * L) if h_out > 0 else 0.0
        R_cond = [math.log(r2 / r1) / (2 * math.pi * inp["k1"] * L)]
        if inp["L2"] > 0 and inp["k2"] > 0:
            r3 = r2 + inp["L2"]
            R_cond.append(math.log(r3 / r2) / (2 * math.pi * inp["k2"] * L))
            R_conv_out = 1 / (h_out * 2 * math.pi * r3 * L) if h_out > 0 else 0.0
        R_total = R_conv_in + sum(R_cond) + R_conv_out
        A = 2 * math.pi * r2 * L
        area_label = f"cylinder, L = {L:g} m"

    Q = (Th - Tc) / R_total if R_total > 0 else float("inf")

    r.group("Conduction and convection", area_label)
    r.headline("Heat transfer rate", Q, "W", symbol="Q\u0307")
    r.out("Total thermal resistance", R_total, "K/W", symbol="R_total")
    r.out("Overall heat transfer coefficient", 1 / (R_total * A), "W/(m\u00b2\u00b7K)",
          symbol="U")
    r.out("Temperature difference", Th - Tc, "K", symbol="\u0394T")
    r.out("Heat flux", Q / A, "W/m\u00b2", symbol="q\u2033")
    if h_in > 0:
        r.out("Inside convection resistance", R_conv_in, "K/W")
        r.out("Inside surface temperature", Th - Q * R_conv_in, "K")
    for i, Rc in enumerate(R_cond, 1):
        r.out(f"Conduction resistance, layer {i}", Rc, "K/W")
    if h_out > 0:
        r.out("Outside convection resistance", R_conv_out, "K/W")
        r.out("Outside surface temperature", Tc + Q * R_conv_out, "K")

    if inp["radiation"]:
        eps, Tsurr = inp["emissivity"], inp["T_surr"]
        Ts = Tc + Q * R_conv_out if h_out > 0 else Tc
        q_rad = eps * STEFAN_BOLTZMANN * A * (Ts ** 4 - Tsurr ** 4)
        h_rad = eps * STEFAN_BOLTZMANN * (Ts + Tsurr) * (Ts ** 2 + Tsurr ** 2)
        r.group("Radiation", f"\u03b5 = {eps:g}, surroundings at {Tsurr:g} K")
        r.out("Radiative heat transfer", q_rad, "W", symbol="Q\u0307_rad")
        r.out("Equivalent radiation coefficient", h_rad, "W/(m\u00b2\u00b7K)", symbol="h_rad")
        r.out("Radiation as a share of convection",
              h_rad / h_out * 100 if h_out > 0 else float("nan"), "%")
        r.out("Blackbody emissive power at the surface",
              STEFAN_BOLTZMANN * Ts ** 4, "W/m\u00b2", symbol="E_b")

    if inp["fin"]:
        kf, Lf, tf, wf = inp["k_fin"], inp["L_fin"], inp["t_fin"], inp["w_fin"]
        hf = h_out if h_out > 0 else h_in
        if hf <= 0:
            raise CalculationError(
                "A fin needs a convection coefficient — set the inside or outside "
                "coefficient to a positive value.")
        Ac = tf * wf
        Pp = 2 * (tf + wf)
        m = math.sqrt(hf * Pp / (kf * Ac))
        Lc = Lf + tf / 2
        eff = math.tanh(m * Lc) / (m * Lc)
        q_fin = eff * hf * Pp * Lc * (Th - Tc)
        r.group("Fin", f"{Lf * 1000:g} mm long, {tf * 1000:g} mm thick")
        r.out("Fin parameter", m, "1/m", symbol="m = \u221a(hP/kA_c)")
        r.out("Corrected length", Lc, "m", symbol="L_c")
        r.out("Fin efficiency", eff * 100, "%", symbol="\u03b7_fin")
        r.out("Fin effectiveness", q_fin / (hf * Ac * (Th - Tc)), symbol="\u03b5_fin",
              note="a fin is only worth fitting above about 2")
        r.out("Heat dissipated by one fin", q_fin, "W")
        r.out("Fin thermal resistance", (Th - Tc) / q_fin if q_fin else float("inf"), "K/W")

    ths = linspace(1.0, max(200.0, h_out * 2), 200)
    qs = []
    for hh in ths:
        Rt = R_conv_in + sum(R_cond) + (1 / (hh * A))
        qs.append((Th - Tc) / Rt)
    r.plot(**P.chart(
        [{"x": ths, "y": qs, "label": "heat transfer rate"}],
        xlabel="Outside convection coefficient  h  [W/(m\u00b2\u00b7K)]",
        ylabel="Heat transfer rate  [W]",
        title="Sensitivity to the outside coefficient",
        points=[{"x": h_out, "y": Q, "label": "your design"}] if h_out > 0 else None,
        caption="The curve flattens once conduction dominates \u2014 past that "
                "point, improving the air-side coefficient buys almost nothing."))
    return r


# ---------------------------------------------------------------------------
# 5. Heat exchanger
# ---------------------------------------------------------------------------


def _heat_exchanger(inp):
    mh, cph, Thi = inp["m_hot"], inp["cp_hot"], inp["T_hot_in"]
    mc, cpc, Tci = inp["m_cold"], inp["cp_cold"], inp["T_cold_in"]
    U, A = inp["U"], inp["A"]
    arrangement = inp["arrangement"]
    if Thi <= Tci:
        raise CalculationError(
            "The hot stream must enter hotter than the cold stream.")

    Ch, Cc = mh * cph, mc * cpc
    Cmin, Cmax = min(Ch, Cc), max(Ch, Cc)
    Cr = Cmin / Cmax
    NTU = U * A / Cmin
    q_max = Cmin * (Thi - Tci)

    if arrangement == "parallel":
        eff = (1 - math.exp(-NTU * (1 + Cr))) / (1 + Cr)
    elif arrangement == "counter":
        if abs(Cr - 1) < 1e-9:
            eff = NTU / (1 + NTU)
        else:
            eff = (1 - math.exp(-NTU * (1 - Cr))) / (1 - Cr * math.exp(-NTU * (1 - Cr)))
    else:  # crossflow, both unmixed (approximation)
        eff = 1 - math.exp((1 / Cr) * NTU ** 0.22 * (math.exp(-Cr * NTU ** 0.78) - 1))

    q = eff * q_max
    Tho = Thi - q / Ch
    Tco = Tci + q / Cc

    if arrangement == "parallel":
        dT1, dT2 = Thi - Tci, Tho - Tco
    else:
        dT1, dT2 = Thi - Tco, Tho - Tci
    lmtd = ((dT1 - dT2) / math.log(dT1 / dT2)
            if dT1 > 0 and dT2 > 0 and abs(dT1 - dT2) > 1e-9 else dT1)

    r = Result()
    r.group("Performance",
            {"parallel": "Parallel flow", "counter": "Counter flow",
             "cross": "Cross flow, both fluids unmixed"}[arrangement])
    r.headline("Heat transfer rate", q / 1000, "kW", symbol="Q\u0307")
    r.headline("Effectiveness", eff * 100, "%", symbol="\u03b5")
    r.out("Number of transfer units", NTU, symbol="NTU = UA/C_min")
    r.out("Capacity rate ratio", Cr, symbol="C_r = C_min/C_max")
    r.out("Maximum possible heat transfer", q_max / 1000, "kW", symbol="Q\u0307_max")
    r.out("Log mean temperature difference", lmtd, "K", symbol="LMTD")
    r.out("Heat transfer from LMTD method", U * A * lmtd / 1000, "kW",
          note="agrees with the \u03b5-NTU result, as it must")

    r.group("Outlet temperatures")
    r.out("Hot stream outlet", Tho, "K", symbol="T_h,out")
    r.out("Hot stream outlet", Tho - 273.15, "\u00b0C")
    r.out("Cold stream outlet", Tco, "K", symbol="T_c,out")
    r.out("Cold stream outlet", Tco - 273.15, "\u00b0C")
    r.out("Hot stream temperature drop", Thi - Tho, "K")
    r.out("Cold stream temperature rise", Tco - Tci, "K")
    r.out("Hot capacity rate", Ch / 1000, "kW/K", symbol="C_h")
    r.out("Cold capacity rate", Cc / 1000, "kW/K", symbol="C_c")
    r.out("Approach temperature", min(dT1, dT2), "K",
          note="the tightest temperature pinch in the exchanger")

    if arrangement == "parallel" and Tco > Tho:
        r.note("In parallel flow the cold outlet can never exceed the hot outlet. "
               "A counter-flow arrangement removes that limit and would transfer "
               "more heat for the same area.")

    ntus = linspace(0.05, max(6.0, NTU * 1.4), 300)

    def eps_of(n, mode):
        if mode == "parallel":
            return (1 - math.exp(-n * (1 + Cr))) / (1 + Cr)
        if abs(Cr - 1) < 1e-9:
            return n / (1 + n)
        return (1 - math.exp(-n * (1 - Cr))) / (1 - Cr * math.exp(-n * (1 - Cr)))

    r.plot(**P.chart(
        [{"x": ntus, "y": [eps_of(n, "counter") * 100 for n in ntus],
          "label": "counter flow"},
         {"x": ntus, "y": [eps_of(n, "parallel") * 100 for n in ntus],
          "label": "parallel flow", "color": P.SERIES[1]}],
        xlabel="NTU", ylabel="Effectiveness  \u03b5  [%]",
        title=f"Effectiveness against NTU at C_r = {Cr:.3f}",
        points=[{"x": NTU, "y": eff * 100, "label": "your design"}],
        caption="Beyond NTU \u2248 3 the curves flatten, so doubling the area "
                "again buys very little \u2014 this is where exchangers stop "
                "being worth enlarging."))

    x = linspace(0, 1, 100)
    if arrangement == "parallel":
        th = [Thi - (Thi - Tho) * xi for xi in x]
        tc = [Tci + (Tco - Tci) * xi for xi in x]
    else:
        th = [Thi - (Thi - Tho) * xi for xi in x]
        tc = [Tco - (Tco - Tci) * xi for xi in x]
    r.plot(**P.chart(
        [{"x": x, "y": th, "label": "hot stream", "color": "#B3242B"},
         {"x": x, "y": tc, "label": "cold stream", "color": P.SERIES[0]}],
        xlabel="Fractional distance along the exchanger", ylabel="Temperature  [K]",
        title="Temperature profiles",
        caption="Counter flow keeps the driving temperature difference roughly "
                "uniform, which is why it needs less area for the same duty."))
    return r


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CALCULATORS = [
    {
        "id": "polytropic-process",
        "name": "Ideal gas process",
        "category": CATEGORY,
        "summary": "Work, heat, entropy and state changes for any polytropic process.",
        "tags": ["polytropic", "isentropic", "work", "entropy", "p-v", "T-s"],
        "inputs": _gas_fields() + [
            choice("process", "Process", [("isentropic", "Isentropic (n = \u03b3)"),
                                          ("isothermal", "Isothermal (n = 1)"),
                                          ("isobaric", "Constant pressure (n = 0)"),
                                          ("isochoric", "Constant volume (n \u2192 \u221e)"),
                                          ("polytropic", "General polytropic")],
                   "isentropic", section="Process"),
            num("n", "Polytropic index n", 1.3, section="Process",
                show_if={"key": "process", "in": ["polytropic"]}),
            num("m", "Mass", 1.0, "kg", minimum=1e-12, section="Initial state"),
            num("p1", "Initial pressure p\u2081", 100000.0, "Pa", minimum=1e-9,
                section="Initial state"),
            num("T1", "Initial temperature T\u2081", 300.0, "K", minimum=1e-3,
                section="Initial state"),
            choice("known", "Final state given by", [("p2", "Pressure p\u2082"),
                                                     ("v2", "Specific volume v\u2082"),
                                                     ("T2", "Temperature T\u2082")],
                   "p2", section="Final state"),
            num("value", "Value", 1000000.0, section="Final state"),
            toggle("value_is_total", "Volume entered is total, not specific", False,
                   section="Final state", show_if={"key": "known", "in": ["v2"]}),
        ],
        "compute": _process,
    },
    {
        "id": "brayton-cycle",
        "name": "Brayton cycle",
        "category": CATEGORY,
        "summary": "Gas turbine cycle with real component efficiencies and regeneration.",
        "description": "Station-by-station analysis including isentropic efficiencies, "
                       "optional regeneration, and the trade between peak efficiency "
                       "and peak specific work.",
        "tags": ["Brayton", "gas turbine", "regeneration", "back work ratio", "T-s"],
        "inputs": _gas_fields() + [
            num("p1", "Inlet pressure p\u2081", 101325.0, "Pa", minimum=1.0,
                section="Cycle"),
            num("T1", "Inlet temperature T\u2081", 288.15, "K", minimum=1.0,
                section="Cycle"),
            num("rp", "Compressor pressure ratio", 12.0, minimum=1.0, section="Cycle"),
            num("T3", "Turbine inlet temperature T\u2083", 1400.0, "K", minimum=1.0,
                section="Cycle"),
            num("eta_c", "Compressor isentropic efficiency", 0.86, minimum=0.05,
                maximum=1.0, section="Components"),
            num("eta_t", "Turbine isentropic efficiency", 0.89, minimum=0.05,
                maximum=1.0, section="Components"),
            toggle("regen", "Include a regenerator", False, section="Components"),
            num("eff_regen", "Regenerator effectiveness", 0.75, minimum=0.0, maximum=1.0,
                section="Components", show_if={"key": "regen", "in": [True]}),
            num("mass_flow", "Mass flow rate", 0.0, "kg/s", minimum=0.0, section="Machine",
                help="Set to 0 for specific (per kilogram) results only."),
            num("lhv", "Fuel lower heating value", 43.0, "MJ/kg", minimum=0.0,
                section="Machine", help="Set to 0 to skip fuel calculations."),
        ],
        "compute": _brayton,
    },
    {
        "id": "piston-cycles",
        "name": "Otto, Diesel and Dual cycles",
        "category": CATEGORY,
        "summary": "Air-standard piston cycle analysis with p–v diagram and MEP.",
        "tags": ["Otto", "Diesel", "dual cycle", "compression ratio", "MEP"],
        "inputs": _gas_fields() + [
            choice("cycle", "Cycle", [("otto", "Otto (constant volume)"),
                                      ("diesel", "Diesel (constant pressure)"),
                                      ("dual", "Dual (limited pressure)")], "otto",
                   section="Cycle"),
            num("rc", "Compression ratio", 9.0, minimum=1.1, maximum=40, section="Cycle"),
            num("rp_dual", "Constant-volume pressure ratio", 1.5, minimum=1.0,
                section="Cycle", show_if={"key": "cycle", "in": ["dual"]}),
            num("q_in", "Heat added per unit mass", 1800000.0, "J/kg", minimum=1.0,
                section="Cycle"),
            num("p1", "Pressure at start of compression", 100000.0, "Pa", minimum=1.0,
                section="Initial state"),
            num("T1", "Temperature at start of compression", 300.0, "K", minimum=1.0,
                section="Initial state"),
            toggle("engine", "Size a real engine", False, section="Engine"),
            num("Vd", "Displacement per cylinder", 500.0, "cm\u00b3", minimum=1e-6,
                section="Engine", show_if={"key": "engine", "in": [True]}),
            num("cylinders", "Number of cylinders", 4, minimum=1, maximum=24,
                section="Engine", show_if={"key": "engine", "in": [True]}),
            num("rpm", "Engine speed", 3000.0, "rpm", minimum=1.0, section="Engine",
                show_if={"key": "engine", "in": [True]}),
            toggle("two_stroke", "Two-stroke", False, section="Engine",
                   show_if={"key": "engine", "in": [True]}),
        ],
        "compute": _piston_cycle,
    },
    {
        "id": "heat-transfer",
        "name": "Conduction, convection and radiation",
        "category": CATEGORY,
        "summary": "Thermal resistance networks for walls and pipes, with fins and radiation.",
        "tags": ["conduction", "convection", "radiation", "thermal resistance", "fin", "Biot"],
        "inputs": [
            choice("geometry", "Geometry", [("wall", "Plane wall"),
                                            ("cylinder", "Cylindrical pipe")], "wall",
                   section="Geometry"),
            num("A", "Surface area", 1.0, "m\u00b2", minimum=1e-9, section="Geometry",
                show_if={"key": "geometry", "in": ["wall"]}),
            num("L_pipe", "Pipe length", 1.0, "m", minimum=1e-9, section="Geometry",
                show_if={"key": "geometry", "in": ["cylinder"]}),
            num("r1", "Inner radius", 0.02, "m", minimum=1e-9, section="Geometry",
                show_if={"key": "geometry", "in": ["cylinder"]}),
            num("r2", "Outer radius", 0.025, "m", minimum=1e-9, section="Geometry",
                show_if={"key": "geometry", "in": ["cylinder"]}),
            num("L1", "Layer 1 thickness", 0.1, "m", minimum=0.0, section="Layers",
                show_if={"key": "geometry", "in": ["wall"]}),
            num("k1", "Layer 1 conductivity", 0.7, "W/(m\u00b7K)", minimum=1e-9,
                section="Layers"),
            num("L2", "Layer 2 thickness", 0.05, "m", minimum=0.0, section="Layers"),
            num("k2", "Layer 2 conductivity", 0.04, "W/(m\u00b7K)", minimum=0.0,
                section="Layers"),
            num("L3", "Layer 3 thickness", 0.0, "m", minimum=0.0, section="Layers",
                show_if={"key": "geometry", "in": ["wall"]}),
            num("k3", "Layer 3 conductivity", 0.0, "W/(m\u00b7K)", minimum=0.0,
                section="Layers", show_if={"key": "geometry", "in": ["wall"]}),
            num("Th", "Hot fluid temperature", 350.0, "K", minimum=1.0, section="Boundary"),
            num("Tc", "Cold fluid temperature", 280.0, "K", minimum=1.0, section="Boundary"),
            num("h_in", "Inside convection coefficient", 25.0, "W/(m\u00b2\u00b7K)",
                minimum=0.0, section="Boundary"),
            num("h_out", "Outside convection coefficient", 10.0, "W/(m\u00b2\u00b7K)",
                minimum=0.0, section="Boundary"),
            toggle("radiation", "Include surface radiation", False, section="Radiation"),
            num("emissivity", "Emissivity", 0.9, minimum=0.0, maximum=1.0,
                section="Radiation", show_if={"key": "radiation", "in": [True]}),
            num("T_surr", "Surroundings temperature", 280.0, "K", minimum=1.0,
                section="Radiation", show_if={"key": "radiation", "in": [True]}),
            toggle("fin", "Analyse a rectangular fin", False, section="Fin"),
            num("k_fin", "Fin conductivity", 180.0, "W/(m\u00b7K)", minimum=1e-9,
                section="Fin", show_if={"key": "fin", "in": [True]}),
            num("L_fin", "Fin length", 0.03, "m", minimum=1e-9, section="Fin",
                show_if={"key": "fin", "in": [True]}),
            num("t_fin", "Fin thickness", 0.002, "m", minimum=1e-9, section="Fin",
                show_if={"key": "fin", "in": [True]}),
            num("w_fin", "Fin width", 0.1, "m", minimum=1e-9, section="Fin",
                show_if={"key": "fin", "in": [True]}),
        ],
        "compute": _heat_transfer,
    },
    {
        "id": "heat-exchanger",
        "name": "Heat exchanger (ε–NTU and LMTD)",
        "category": CATEGORY,
        "summary": "Duty, effectiveness and outlet temperatures for the three arrangements.",
        "tags": ["heat exchanger", "NTU", "effectiveness", "LMTD", "counter flow"],
        "inputs": [
            choice("arrangement", "Arrangement", [("counter", "Counter flow"),
                                                  ("parallel", "Parallel flow"),
                                                  ("cross", "Cross flow, unmixed")],
                   "counter", section="Configuration"),
            num("U", "Overall heat transfer coefficient", 500.0, "W/(m\u00b2\u00b7K)",
                minimum=1e-9, section="Configuration"),
            num("A", "Heat transfer area", 10.0, "m\u00b2", minimum=1e-9,
                section="Configuration"),
            num("m_hot", "Hot stream mass flow", 2.0, "kg/s", minimum=1e-9,
                section="Hot stream"),
            num("cp_hot", "Hot stream specific heat", 4182.0, "J/(kg\u00b7K)",
                minimum=1e-9, section="Hot stream"),
            num("T_hot_in", "Hot stream inlet temperature", 360.0, "K", minimum=1.0,
                section="Hot stream"),
            num("m_cold", "Cold stream mass flow", 3.0, "kg/s", minimum=1e-9,
                section="Cold stream"),
            num("cp_cold", "Cold stream specific heat", 4182.0, "J/(kg\u00b7K)",
                minimum=1e-9, section="Cold stream"),
            num("T_cold_in", "Cold stream inlet temperature", 290.0, "K", minimum=1.0,
                section="Cold stream"),
        ],
        "compute": _heat_exchanger,
    },
]
