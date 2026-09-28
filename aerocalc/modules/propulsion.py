"""Propulsion: air-breathing engine cycles, rocket nozzles and propellers."""

from __future__ import annotations

import math

from .. import compressible as cf
from .. import plotting as P
from ..core import CalculationError, Result, choice, num, toggle
from ..numeric import linspace, solve
from ..physics import G0, GAMMA_AIR, R_AIR, atmosphere, cp_from

CATEGORY = "Propulsion"

FT = 0.3048


def _ram_recovery(M0):
    """MIL-E-5008B inlet total pressure recovery."""
    if M0 <= 1:
        return 1.0
    if M0 <= 5:
        return 1.0 - 0.075 * (M0 - 1.0) ** 1.35
    return 800.0 / (M0 ** 4 + 935.0)


# ---------------------------------------------------------------------------
# 1. Turbojet / turbofan
# ---------------------------------------------------------------------------


def _turbofan(inp):
    gc, gt = inp["gamma_c"], inp["gamma_t"]
    cpc, cpt = inp["cp_c"], inp["cp_t"]
    Rc = cpc * (gc - 1) / gc
    Rt = cpt * (gt - 1) / gt

    z = inp["altitude"] * (FT if inp["alt_unit"] == "ft" else 1.0)
    atm = atmosphere(z)
    T0, p0 = atm["T"], atm["p"]
    a0 = math.sqrt(gc * Rc * T0)
    M0 = inp["M0"]
    V0 = M0 * a0

    alpha = inp["bypass"]
    pi_c, pi_f = inp["pi_c"], inp["pi_f"]
    Tt4, hPR = inp["Tt4"], inp["hPR"] * 1e6

    tau_r = 1 + (gc - 1) / 2 * M0 ** 2
    pi_r = tau_r ** (gc / (gc - 1))
    eta_r = _ram_recovery(M0)
    pi_d = inp["pi_d"] * eta_r

    tau_c = 1 + (pi_c ** ((gc - 1) / gc) - 1) / inp["eta_c"]
    tau_f = 1 + (pi_f ** ((gc - 1) / gc) - 1) / inp["eta_f"] if alpha > 0 else 1.0
    tau_lambda = cpt * Tt4 / (cpc * T0)

    if tau_lambda <= tau_r * tau_c:
        raise CalculationError(
            "The compressor already delivers air hotter than the turbine inlet "
            "temperature. Reduce the pressure ratio, reduce the flight Mach "
            "number, or raise T_t4.")

    denom = inp["eta_b"] * hPR / (cpc * T0) - tau_lambda
    if denom <= 0:
        raise CalculationError(
            "The fuel heating value cannot reach the required turbine inlet "
            "temperature. Raise the heating value or lower T_t4.")
    f = (tau_lambda - tau_r * tau_c) / denom

    tau_t = 1 - (tau_r / (tau_lambda * inp["eta_m"] * (1 + f))) * (
        (tau_c - 1) + alpha * (tau_f - 1))
    if tau_t <= 0:
        raise CalculationError(
            "The turbine cannot extract enough work to drive the compressor and "
            "fan. Lower the bypass ratio or the pressure ratios.")
    pi_t = (1 - (1 - tau_t) / inp["eta_t"]) ** (gt / (gt - 1))

    # Core nozzle, perfectly expanded
    pt9_p9 = pi_r * pi_d * pi_c * inp["pi_b"] * pi_t * inp["pi_n"]
    if inp["afterburner"]:
        pt9_p9 *= inp["pi_ab"]
        Tt7 = inp["Tt7"]
        tau_lambda_ab = cpt * Tt7 / (cpc * T0)
        den_ab = inp["eta_ab"] * hPR / (cpc * T0) - tau_lambda_ab
        if den_ab <= 0:
            raise CalculationError(
                "The afterburner temperature exceeds what this fuel can deliver.")
        f_ab = (1 + f) * (tau_lambda_ab - tau_lambda * tau_t) / den_ab
        Tt9 = Tt7
        f_total = f + f_ab
    else:
        f_ab = 0.0
        Tt9 = Tt4 * tau_t
        f_total = f

    if pt9_p9 <= 1:
        raise CalculationError(
            "There is no pressure available across the nozzle — the cycle as "
            "specified cannot produce thrust.")
    M9 = math.sqrt(2 / (gt - 1) * (pt9_p9 ** ((gt - 1) / gt) - 1))
    T9 = Tt9 / (1 + (gt - 1) / 2 * M9 ** 2)
    V9 = M9 * math.sqrt(gt * Rt * T9)

    # Fan nozzle
    if alpha > 0:
        pt19_p19 = pi_r * pi_d * pi_f * inp["pi_fn"]
        M19 = math.sqrt(2 / (gc - 1) * (pt19_p19 ** ((gc - 1) / gc) - 1))
        T19 = T0 * tau_r * tau_f / (1 + (gc - 1) / 2 * M19 ** 2)
        V19 = M19 * math.sqrt(gc * Rc * T19)
    else:
        M19 = V19 = T19 = 0.0

    F_m0 = ((1 + f_total) * V9 - V0) / (1 + alpha) + alpha * (V19 - V0) / (1 + alpha)
    if F_m0 <= 0:
        raise CalculationError(
            "This cycle produces no net thrust at these conditions — the exhaust "
            "is slower than the flight speed.")
    S = f_total / ((1 + alpha) * F_m0)

    ke_out = ((1 + f_total) * V9 ** 2 + alpha * V19 ** 2 - (1 + alpha) * V0 ** 2) / 2
    eta_th = ke_out / (f_total * hPR)
    eta_p = F_m0 * V0 * (1 + alpha) / ke_out if ke_out > 0 else float("nan")
    eta_o = eta_th * eta_p

    r = Result()
    engine = "Turbojet" if alpha == 0 else f"Turbofan, bypass ratio {alpha:g}"
    if inp["afterburner"]:
        engine += " with afterburner"
    r.group("Performance", f"{engine} at M {M0:g}, {z:.0f} m")
    r.headline("Specific thrust", F_m0, "N\u00b7s/kg", symbol="F/\u1e41\u2080")
    r.headline("Thrust specific fuel consumption", S * 1e6, "mg/(N\u00b7s)", symbol="TSFC")
    r.out("Thrust specific fuel consumption", S * 3600 * 9.80665 * 1000 / 9.80665,
          "kg/(N\u00b7h)\u00d710\u00b3", note="equivalently " f"{S * 3.6e6:.4g} g/(kN\u00b7s)")
    r.out("Fuel-air ratio (burner)", f, symbol="f")
    if inp["afterburner"]:
        r.out("Fuel-air ratio (afterburner)", f_ab, symbol="f_AB")
        r.out("Total fuel-air ratio", f_total)
    r.out("Thermal efficiency", eta_th * 100, "%", symbol="\u03b7_th")
    r.out("Propulsive efficiency", eta_p * 100, "%", symbol="\u03b7_p")
    r.out("Overall efficiency", eta_o * 100, "%", symbol="\u03b7_o")

    r.group("Flight condition")
    r.out("Ambient temperature", T0, "K", symbol="T\u2080")
    r.out("Ambient pressure", p0, "Pa", symbol="p\u2080")
    r.out("Speed of sound", a0, "m/s", symbol="a\u2080")
    r.out("Flight velocity", V0, "m/s", symbol="V\u2080")
    r.out("Ram temperature ratio", tau_r, symbol="\u03c4_r")
    r.out("Ram pressure ratio", pi_r, symbol="\u03c0_r")
    r.out("Inlet pressure recovery", eta_r, symbol="\u03b7_r")

    r.group("Component ratios")
    r.out("Compressor temperature ratio", tau_c, symbol="\u03c4_c")
    r.out("Compressor exit total temperature", T0 * tau_r * tau_c, "K", symbol="T_t3")
    if alpha > 0:
        r.out("Fan temperature ratio", tau_f, symbol="\u03c4_f")
    r.out("Turbine temperature ratio", tau_t, symbol="\u03c4_t")
    r.out("Turbine pressure ratio", pi_t, symbol="\u03c0_t")
    r.out("Turbine exit total temperature", Tt4 * tau_t, "K", symbol="T_t5")
    r.out("Cycle temperature parameter", tau_lambda, symbol="\u03c4_\u03bb")
    r.out("Overall pressure ratio", pi_r * pi_d * pi_c, symbol="OPR")

    r.group("Exhaust")
    r.out("Core nozzle pressure ratio", pt9_p9, symbol="p_t9/p\u2089")
    r.out("Core exit Mach number", M9, symbol="M\u2089")
    r.out("Core exit temperature", T9, "K", symbol="T\u2089")
    r.out("Core exit velocity", V9, "m/s", symbol="V\u2089")
    r.out("Core jet velocity ratio", V9 / V0 if V0 else float("inf"), symbol="V\u2089/V\u2080")
    if alpha > 0:
        r.out("Fan exit Mach number", M19, symbol="M\u2081\u2089")
        r.out("Fan exit velocity", V19, "m/s", symbol="V\u2081\u2089")
        r.out("Jet velocity ratio", V9 / V19 if V19 else float("inf"),
              symbol="V\u2089/V\u2081\u2089",
              note="optimum bypass shares power to make these ratios similar")

    if inp["mdot"] > 0:
        m0 = inp["mdot"]
        r.group("Engine size", f"total inlet flow {m0:g} kg/s")
        r.out("Net thrust", F_m0 * m0 / 1000, "kN", symbol="F")
        r.out("Core mass flow", m0 / (1 + alpha), "kg/s")
        r.out("Bypass mass flow", m0 * alpha / (1 + alpha), "kg/s")
        r.out("Fuel flow", f_total * m0 / (1 + alpha), "kg/s")
        r.out("Fuel flow", f_total * m0 / (1 + alpha) * 3600, "kg/h")

    pis = linspace(2.0, 50.0, 200)
    st, sf = [], []
    for pc in pis:
        try:
            v = _turbofan_point(inp, pc, alpha, T0, p0, a0, gc, gt, Rc, Rt, cpc, cpt, hPR)
            st.append(v[0])
            sf.append(v[1] * 1e6)
        except CalculationError:
            st.append(float("nan"))
            sf.append(float("nan"))
    r.plot(**P.chart(
        [{"x": pis, "y": P.safe(st), "label": "specific thrust"}],
        xlabel="Compressor pressure ratio  \u03c0_c",
        ylabel="Specific thrust  [N\u00b7s/kg]",
        title="Specific thrust against compressor pressure ratio",
        points=[{"x": pi_c, "y": F_m0, "label": "your design"}],
        caption="For a fixed turbine inlet temperature, specific thrust peaks and "
                "then falls as the compressor absorbs too much of the turbine work."))
    r.plot(**P.chart(
        [{"x": pis, "y": P.safe(sf), "label": "TSFC", "color": P.SERIES[1]}],
        xlabel="Compressor pressure ratio  \u03c0_c",
        ylabel="TSFC  [mg/(N\u00b7s)]",
        title="Fuel consumption against compressor pressure ratio",
        points=[{"x": pi_c, "y": S * 1e6, "label": "your design"}],
        caption="Efficiency keeps improving with pressure ratio well past the "
                "point of maximum thrust \u2014 which is why airliners run higher "
                "OPR than fighters."))
    return r


def _turbofan_point(inp, pi_c, alpha, T0, p0, a0, gc, gt, Rc, Rt, cpc, cpt, hPR):
    """Recompute specific thrust and TSFC at a different compressor ratio."""
    M0 = inp["M0"]
    V0 = M0 * a0
    tau_r = 1 + (gc - 1) / 2 * M0 ** 2
    pi_r = tau_r ** (gc / (gc - 1))
    pi_d = inp["pi_d"] * _ram_recovery(M0)
    tau_c = 1 + (pi_c ** ((gc - 1) / gc) - 1) / inp["eta_c"]
    tau_f = 1 + (inp["pi_f"] ** ((gc - 1) / gc) - 1) / inp["eta_f"] if alpha > 0 else 1.0
    tau_lambda = cpt * inp["Tt4"] / (cpc * T0)
    if tau_lambda <= tau_r * tau_c:
        raise CalculationError("infeasible")
    f = (tau_lambda - tau_r * tau_c) / (inp["eta_b"] * hPR / (cpc * T0) - tau_lambda)
    tau_t = 1 - (tau_r / (tau_lambda * inp["eta_m"] * (1 + f))) * (
        (tau_c - 1) + alpha * (tau_f - 1))
    if tau_t <= 0:
        raise CalculationError("infeasible")
    pi_t = (1 - (1 - tau_t) / inp["eta_t"]) ** (gt / (gt - 1))
    pt9_p9 = pi_r * pi_d * pi_c * inp["pi_b"] * pi_t * inp["pi_n"]
    if pt9_p9 <= 1:
        raise CalculationError("infeasible")
    M9 = math.sqrt(2 / (gt - 1) * (pt9_p9 ** ((gt - 1) / gt) - 1))
    T9 = inp["Tt4"] * tau_t / (1 + (gt - 1) / 2 * M9 ** 2)
    V9 = M9 * math.sqrt(gt * Rt * T9)
    if alpha > 0:
        pt19 = pi_r * pi_d * inp["pi_f"] * inp["pi_fn"]
        M19 = math.sqrt(2 / (gc - 1) * (pt19 ** ((gc - 1) / gc) - 1))
        T19 = T0 * tau_r * tau_f / (1 + (gc - 1) / 2 * M19 ** 2)
        V19 = M19 * math.sqrt(gc * Rc * T19)
    else:
        V19 = 0.0
    F = ((1 + f) * V9 - V0) / (1 + alpha) + alpha * (V19 - V0) / (1 + alpha)
    if F <= 0:
        raise CalculationError("infeasible")
    return F, f / ((1 + alpha) * F)


# ---------------------------------------------------------------------------
# 2. Ramjet
# ---------------------------------------------------------------------------


def _ramjet(inp):
    g, cp = inp["gamma"], inp["cp"]
    R = cp * (g - 1) / g
    z = inp["altitude"] * (FT if inp["alt_unit"] == "ft" else 1.0)
    atm = atmosphere(z)
    T0, p0 = atm["T"], atm["p"]
    a0 = math.sqrt(g * R * T0)
    M0 = inp["M0"]
    if M0 <= 0:
        raise CalculationError(
            "A ramjet produces no thrust at rest — it needs forward speed to "
            "compress the incoming air.")
    V0 = M0 * a0

    tau_r = 1 + (g - 1) / 2 * M0 ** 2
    pi_r = tau_r ** (g / (g - 1))
    pi_d = inp["pi_d"] * _ram_recovery(M0)
    Tt4 = inp["Tt4"]
    tau_lambda = Tt4 / T0
    if tau_lambda <= tau_r:
        raise CalculationError(
            "Ram compression alone already heats the air above the combustor exit "
            "temperature. Lower the Mach number or raise T_t4.")
    hPR = inp["hPR"] * 1e6
    f = cp * T0 * (tau_lambda - tau_r) / (inp["eta_b"] * hPR - cp * Tt4)

    pt9_p9 = pi_r * pi_d * inp["pi_b"] * inp["pi_n"]
    M9 = math.sqrt(2 / (g - 1) * (pt9_p9 ** ((g - 1) / g) - 1))
    T9 = Tt4 / (1 + (g - 1) / 2 * M9 ** 2)
    V9 = M9 * math.sqrt(g * R * T9)

    F_m0 = (1 + f) * V9 - V0
    if F_m0 <= 0:
        raise CalculationError(
            "The exhaust is slower than the flight speed, so this ramjet produces "
            "drag rather than thrust at these conditions.")
    S = f / F_m0
    eta_th = (((1 + f) * V9 ** 2 - V0 ** 2) / 2) / (f * hPR)
    eta_p = F_m0 * V0 / (((1 + f) * V9 ** 2 - V0 ** 2) / 2)

    r = Result()
    r.group("Performance", f"Ramjet at M {M0:g}, {z:.0f} m")
    r.headline("Specific thrust", F_m0, "N\u00b7s/kg", symbol="F/\u1e41\u2080")
    r.headline("Thrust specific fuel consumption", S * 1e6, "mg/(N\u00b7s)", symbol="TSFC")
    r.out("Fuel-air ratio", f, symbol="f")
    r.out("Thermal efficiency", eta_th * 100, "%", symbol="\u03b7_th")
    r.out("Propulsive efficiency", eta_p * 100, "%", symbol="\u03b7_p")
    r.out("Overall efficiency", eta_th * eta_p * 100, "%", symbol="\u03b7_o")
    r.out("Ideal thermal efficiency", (1 - 1 / tau_r) * 100, "%",
          note="ram compression is the only compression a ramjet has")

    r.group("Stations")
    r.out("Free-stream velocity", V0, "m/s", symbol="V\u2080")
    r.out("Total temperature after the inlet", T0 * tau_r, "K", symbol="T_t2")
    r.out("Total pressure recovery", pi_d, symbol="\u03c0_d")
    r.out("Combustor exit total temperature", Tt4, "K", symbol="T_t4")
    r.out("Nozzle pressure ratio", pt9_p9, symbol="p_t9/p\u2089")
    r.out("Exit Mach number", M9, symbol="M\u2089")
    r.out("Exit velocity", V9, "m/s", symbol="V\u2089")
    r.out("Exit temperature", T9, "K", symbol="T\u2089")

    if inp["mdot"] > 0:
        r.group("Engine size", f"inlet flow {inp['mdot']:g} kg/s")
        r.out("Thrust", F_m0 * inp["mdot"] / 1000, "kN")
        r.out("Fuel flow", f * inp["mdot"] * 3600, "kg/h")
        r.out("Capture area required", inp["mdot"] / (atm["rho"] * V0), "m\u00b2")

    ms = linspace(0.3, 6.0, 300)
    st, sf = [], []
    for m in ms:
        try:
            tr = 1 + (g - 1) / 2 * m ** 2
            if tau_lambda <= tr:
                raise ValueError
            pid = inp["pi_d"] * _ram_recovery(m)
            ff = cp * T0 * (tau_lambda - tr) / (inp["eta_b"] * hPR - cp * Tt4)
            npr = tr ** (g / (g - 1)) * pid * inp["pi_b"] * inp["pi_n"]
            m9 = math.sqrt(2 / (g - 1) * (npr ** ((g - 1) / g) - 1))
            t9 = Tt4 / (1 + (g - 1) / 2 * m9 ** 2)
            v9 = m9 * math.sqrt(g * R * t9)
            fm = (1 + ff) * v9 - m * a0
            st.append(fm if fm > 0 else float("nan"))
            sf.append(ff / fm * 1e6 if fm > 0 else float("nan"))
        except (ValueError, ZeroDivisionError):
            st.append(float("nan"))
            sf.append(float("nan"))
    r.plot(**P.chart(
        [{"x": ms, "y": P.safe(st), "label": "specific thrust"}],
        xlabel="Flight Mach number  M\u2080", ylabel="Specific thrust  [N\u00b7s/kg]",
        title="Ramjet thrust against flight Mach number",
        points=[{"x": M0, "y": F_m0, "label": "your condition"}],
        caption="Thrust vanishes at both ends: at low Mach there is no ram "
                "compression, and at high Mach the ram temperature approaches the "
                "combustor limit so no heat can be added."))
    return r


# ---------------------------------------------------------------------------
# 3. Rocket nozzle
# ---------------------------------------------------------------------------


def _rocket_nozzle(inp):
    g = inp["gamma"]
    if inp["gas_spec"] == "molar":
        Mw = inp["Mw"]
        if Mw <= 0:
            raise CalculationError("Molar mass must be positive.")
        R = 8314.462618 / Mw
    else:
        R = inp["R"]
    pc, Tc = inp["pc"], inp["Tc"]
    pa = inp["pa"]

    if inp["expansion"] == "area":
        eps = inp["eps"]
        Me = cf.mach_from_area_ratio(eps, g, "supersonic")
        pe = pc / cf.p0_ratio(Me, g)
    else:
        pe = inp["pe"]
        if pe >= pc:
            raise CalculationError("The exit pressure must be below chamber pressure.")
        Me = cf.mach_from_p0_ratio(pc / pe, g)
        eps = cf.area_ratio(Me, g)

    Te = Tc / cf.t0_ratio(Me, g)
    Ve = Me * math.sqrt(g * R * Te)

    cstar = math.sqrt(R * Tc / g) * ((g + 1) / 2) ** ((g + 1) / (2 * (g - 1)))
    CF_mom = math.sqrt(2 * g ** 2 / (g - 1) * (2 / (g + 1)) ** ((g + 1) / (g - 1))
                       * (1 - (pe / pc) ** ((g - 1) / g)))
    CF = CF_mom + (pe - pa) / pc * eps
    CF_vac = CF_mom + pe / pc * eps
    Isp = CF * cstar / G0
    Isp_vac = CF_vac * cstar / G0

    eff = inp["eta_cstar"] * inp["eta_cf"] if inp["real"] else 1.0

    if inp["size_by"] == "throat":
        At = inp["At"]
        F = CF * pc * At
    else:
        F = inp["F"]
        At = F / (CF * pc)
    Ae = eps * At
    mdot = pc * At / cstar

    r = Result()
    r.group("Nozzle", f"\u03b3 = {g:g}, R = {R:.5g} J/(kg\u00b7K), "
            f"p_c = {pc / 1e5:g} bar")
    r.headline("Thrust", F / 1000, "kN", symbol="F")
    r.headline("Specific impulse", Isp, "s", symbol="I_sp")
    r.out("Vacuum specific impulse", Isp_vac, "s", symbol="I_sp,vac")
    r.out("Thrust coefficient", CF, symbol="C_F")
    r.out("Vacuum thrust coefficient", CF_vac, symbol="C_F,vac")
    r.out("Momentum term of C_F", CF_mom)
    r.out("Pressure term of C_F", (pe - pa) / pc * eps)
    r.out("Characteristic velocity", cstar, "m/s", symbol="c*")
    r.out("Effective exhaust velocity", Isp * G0, "m/s", symbol="c = I_sp\u00b7g\u2080")

    r.group("Geometry and flow")
    r.out("Expansion area ratio", eps, symbol="\u03b5 = A\u2091/A\u209c")
    r.out("Throat area", At, "m\u00b2", symbol="A\u209c")
    r.out("Throat diameter", 2 * math.sqrt(At / math.pi), "m")
    r.out("Exit area", Ae, "m\u00b2", symbol="A\u2091")
    r.out("Exit diameter", 2 * math.sqrt(Ae / math.pi), "m")
    r.out("Mass flow rate", mdot, "kg/s", symbol="\u1e41")
    r.out("Exit Mach number", Me, symbol="M\u2091")
    r.out("Exit velocity", Ve, "m/s", symbol="V\u2091")
    r.out("Exit pressure", pe, "Pa", symbol="p\u2091")
    r.out("Exit temperature", Te, "K", symbol="T\u2091")
    r.out("Throat pressure", pc * cf.critical_pressure_ratio(g), "Pa", symbol="p\u209c")
    r.out("Throat temperature", Tc * 2 / (g + 1), "K", symbol="T\u209c")

    r.group("Expansion state")
    if pa > 0:
        eps_opt = cf.area_ratio(cf.mach_from_p0_ratio(pc / pa, g), g)
        state = ("perfectly expanded" if abs(pe - pa) / pa < 0.01 else
                 ("overexpanded \u2014 shocks form in the exit plane" if pe < pa
                  else "underexpanded \u2014 the plume keeps expanding outside"))
        r.out("Expansion state", state)
        r.out("Exit-to-ambient pressure ratio", pe / pa, symbol="p\u2091/p_a")
        r.out("Optimum area ratio for this altitude", eps_opt, symbol="\u03b5_opt")
        r.out("Thrust at optimum expansion",
              (math.sqrt(2 * g ** 2 / (g - 1) * (2 / (g + 1)) ** ((g + 1) / (g - 1))
                         * (1 - (pa / pc) ** ((g - 1) / g)))) * pc * At / 1000, "kN")
        if pe < 0.4 * pa:
            r.note("The exit pressure is below about 40 % of ambient, which is the "
                   "usual flow-separation limit (Summerfield criterion). A real "
                   "nozzle would separate internally and the thrust would differ "
                   "from this ideal value.")
    else:
        r.out("Expansion state", "vacuum operation")

    if inp["real"]:
        r.group("With efficiency losses",
                f"\u03b7_c* = {inp['eta_cstar']:g}, \u03b7_CF = {inp['eta_cf']:g}")
        r.out("Delivered specific impulse", Isp * eff, "s")
        r.out("Delivered thrust", F * eff / 1000, "kN")
        r.out("Delivered c*", cstar * inp["eta_cstar"], "m/s")
        r.out("Overall nozzle efficiency", eff * 100, "%")

    eps_range = linspace(1.5, max(80.0, eps * 1.5), 300)
    series = []
    for pr, lab in ((0.0, "vacuum"), (pa / pc if pa > 0 else 0.001, "your ambient"),
                    (101325 / pc, "sea level")):
        ys = []
        for e_ in eps_range:
            m_ = cf.mach_from_area_ratio(e_, g, "supersonic")
            pe_ = 1 / cf.p0_ratio(m_, g)
            ys.append(CF_mom_of(g, pe_) + (pe_ - pr) * e_)
        series.append({"x": eps_range, "y": ys, "label": lab})
    r.plot(**P.chart(
        series, xlabel="Area ratio  \u03b5 = A\u2091/A\u209c",
        ylabel="Thrust coefficient  C_F",
        title="Thrust coefficient against area ratio",
        points=[{"x": eps, "y": CF, "label": "your nozzle"}],
        caption="In vacuum C_F rises without limit, but at any finite ambient "
                "pressure there is an optimum area ratio \u2014 which is why "
                "upper stages have far larger bells than boosters."))
    return r


def CF_mom_of(g, pe_pc):
    return math.sqrt(2 * g ** 2 / (g - 1) * (2 / (g + 1)) ** ((g + 1) / (g - 1))
                     * (1 - pe_pc ** ((g - 1) / g)))


# ---------------------------------------------------------------------------
# 4. Propeller / rotor momentum theory
# ---------------------------------------------------------------------------


def _propeller(inp):
    rho = inp["rho"]
    D = inp["D"]
    A = math.pi * D ** 2 / 4
    T = inp["T"]
    V = inp["V"]
    if D <= 0:
        raise CalculationError("The disk diameter must be positive.")

    vi = -V / 2 + math.sqrt((V / 2) ** 2 + T / (2 * rho * A))
    P_ideal = T * (V + vi)
    DL = T / A
    eta_ideal = V / (V + vi) if V > 0 else 0.0

    r = Result()
    r.group("Actuator disk", f"D = {D:g} m, disk area {A:.4g} m\u00b2")
    r.headline("Induced velocity", vi, "m/s", symbol="v_i")
    r.headline("Ideal induced power", P_ideal / 1000, "kW", symbol="P_i")
    r.out("Disk loading", DL, "N/m\u00b2", symbol="T/A")
    r.out("Slipstream velocity far downstream", V + 2 * vi, "m/s", symbol="w")
    r.out("Ideal propulsive efficiency", eta_ideal * 100, "%", symbol="\u03b7_i",
          note="Froude efficiency \u2014 the ceiling for any propeller at this loading")
    r.out("Power loading", T / P_ideal if P_ideal else float("inf"), "N/W",
          symbol="T/P")
    r.out("Thrust", T, "N", symbol="T")

    if V == 0:
        r.group("Hover")
        vh = math.sqrt(T / (2 * rho * A))
        Ph = T ** 1.5 / math.sqrt(2 * rho * A)
        r.out("Hover induced velocity", vh, "m/s", symbol="v_h")
        r.out("Ideal hover power", Ph / 1000, "kW")
        if inp["P_actual"] > 0:
            r.out("Figure of merit", Ph / (inp["P_actual"] * 1000), symbol="FM",
                  note="0.7 to 0.8 for a good helicopter rotor")
        r.out("Power loading", T / Ph, "N/W",
              note="lower disk loading always means less power to hover")
    elif inp["P_actual"] > 0:
        r.group("Real propeller")
        Pa = inp["P_actual"] * 1000
        r.out("Shaft power supplied", inp["P_actual"], "kW")
        r.out("Useful power TV", T * V / 1000, "kW")
        r.out("Actual propulsive efficiency", T * V / Pa * 100, "%", symbol="\u03b7_p")
        r.out("Fraction of ideal achieved", (T * V / Pa) / eta_ideal * 100, "%"
              if eta_ideal else float("nan"))

    if inp["blade"]:
        n = inp["rpm"] / 60
        J = V / (n * D) if n > 0 else 0.0
        CT = T / (rho * n ** 2 * D ** 4) if n > 0 else float("nan")
        r.group("Blade element parameters", f"{inp['rpm']:g} rpm")
        r.out("Rotational speed", n, "rev/s", symbol="n")
        r.out("Tip speed", math.pi * n * D, "m/s", symbol="V_tip")
        r.out("Advance ratio", J, symbol="J = V/(nD)")
        r.out("Thrust coefficient", CT, symbol="C_T")
        if inp["P_actual"] > 0 and n > 0:
            CP = inp["P_actual"] * 1000 / (rho * n ** 3 * D ** 5)
            r.out("Power coefficient", CP, symbol="C_P")
            r.out("Efficiency from coefficients", J * CT / CP if CP else float("nan"),
                  symbol="\u03b7 = J\u00b7C_T/C_P")
        a_local = 340.294
        Mtip = math.sqrt((math.pi * n * D) ** 2 + V ** 2) / a_local
        r.out("Helical tip Mach number", Mtip, symbol="M_tip",
              note="keep below about 0.85 or noise and compressibility losses bite")

    vs = linspace(0.1, max(120.0, V * 1.5), 300)
    r.plot(**P.chart(
        [{"x": vs, "y": [v / (v + (-v / 2 + math.sqrt((v / 2) ** 2 + T / (2 * rho * A)))) * 100
                         for v in vs], "label": "ideal (Froude) efficiency"}],
        xlabel="Flight speed  V  [m/s]", ylabel="Ideal efficiency  [%]",
        title="Froude efficiency against flight speed",
        points=[{"x": V, "y": eta_ideal * 100, "label": "your condition"}] if V > 0 else None,
        caption="High efficiency needs a small velocity increment over a large "
                "disk \u2014 the physical reason turbofans grew large fans."))

    dls = linspace(50, max(2000.0, DL * 1.5), 300)
    r.plot(**P.chart(
        [{"x": dls, "y": [math.sqrt(x / (2 * rho)) for x in dls],
          "label": "hover induced velocity", "color": P.SERIES[1]}],
        xlabel="Disk loading  T/A  [N/m\u00b2]", ylabel="Induced velocity  [m/s]",
        title="Hover induced velocity against disk loading",
        points=[{"x": DL, "y": math.sqrt(DL / (2 * rho)), "label": "your rotor"}],
        caption="Helicopters sit near 250\u2013500 N/m\u00b2; a lift fan or "
                "jet-lift aircraft is an order of magnitude higher, and pays for "
                "it in power."))
    return r


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CALCULATORS = [
    {
        "id": "turbofan-cycle",
        "name": "Turbojet and turbofan cycle",
        "category": CATEGORY,
        "summary": "On-design station analysis with real components, bypass and afterburner.",
        "description": "Full parametric cycle analysis: set the bypass ratio to zero for a "
                       "turbojet, or raise it for a turbofan with separate exhausts.",
        "tags": ["turbojet", "turbofan", "bypass", "TSFC", "specific thrust", "afterburner"],
        "inputs": [
            num("M0", "Flight Mach number", 0.85, minimum=0.0, maximum=4.0,
                section="Flight condition"),
            num("altitude", "Altitude", 11000.0, minimum=-1000, maximum=30000,
                section="Flight condition"),
            choice("alt_unit", "Altitude unit", [("m", "metres"), ("ft", "feet")], "m",
                   section="Flight condition"),
            num("bypass", "Bypass ratio \u03b1", 5.0, minimum=0.0, maximum=20.0,
                section="Cycle", help="Zero gives a pure turbojet."),
            num("pi_c", "Overall compressor pressure ratio", 30.0, minimum=1.0,
                maximum=80.0, section="Cycle"),
            num("pi_f", "Fan pressure ratio", 1.6, minimum=1.0, maximum=4.0,
                section="Cycle"),
            num("Tt4", "Turbine inlet total temperature T_t4", 1600.0, "K",
                minimum=300.0, maximum=2500.0, section="Cycle"),
            num("hPR", "Fuel heating value", 43.0, "MJ/kg", minimum=1.0, section="Cycle"),
            num("eta_c", "Compressor efficiency", 0.88, minimum=0.3, maximum=1.0,
                section="Component efficiencies"),
            num("eta_f", "Fan efficiency", 0.90, minimum=0.3, maximum=1.0,
                section="Component efficiencies"),
            num("eta_t", "Turbine efficiency", 0.90, minimum=0.3, maximum=1.0,
                section="Component efficiencies"),
            num("eta_b", "Burner efficiency", 0.99, minimum=0.3, maximum=1.0,
                section="Component efficiencies"),
            num("eta_m", "Mechanical efficiency", 0.99, minimum=0.3, maximum=1.0,
                section="Component efficiencies"),
            num("pi_d", "Inlet pressure ratio (subsonic)", 0.98, minimum=0.5, maximum=1.0,
                section="Pressure ratios"),
            num("pi_b", "Burner pressure ratio", 0.96, minimum=0.5, maximum=1.0,
                section="Pressure ratios"),
            num("pi_n", "Core nozzle pressure ratio", 0.99, minimum=0.5, maximum=1.0,
                section="Pressure ratios"),
            num("pi_fn", "Fan nozzle pressure ratio", 0.99, minimum=0.5, maximum=1.0,
                section="Pressure ratios"),
            toggle("afterburner", "Afterburner lit", False, section="Afterburner"),
            num("Tt7", "Afterburner exit temperature T_t7", 2000.0, "K", minimum=300.0,
                maximum=2600.0, section="Afterburner",
                show_if={"key": "afterburner", "in": [True]}),
            num("eta_ab", "Afterburner efficiency", 0.95, minimum=0.3, maximum=1.0,
                section="Afterburner", show_if={"key": "afterburner", "in": [True]}),
            num("pi_ab", "Afterburner pressure ratio", 0.94, minimum=0.5, maximum=1.0,
                section="Afterburner", show_if={"key": "afterburner", "in": [True]}),
            num("gamma_c", "\u03b3 cold section", 1.4, minimum=1.1, maximum=1.7,
                section="Gas properties"),
            num("cp_c", "c_p cold section", 1004.0, "J/(kg\u00b7K)", minimum=100.0,
                section="Gas properties"),
            num("gamma_t", "\u03b3 hot section", 1.33, minimum=1.1, maximum=1.7,
                section="Gas properties"),
            num("cp_t", "c_p hot section", 1156.0, "J/(kg\u00b7K)", minimum=100.0,
                section="Gas properties"),
            num("mdot", "Total inlet mass flow", 0.0, "kg/s", minimum=0.0,
                section="Engine size", help="Set to 0 for specific results only."),
        ],
        "compute": _turbofan,
    },
    {
        "id": "ramjet",
        "name": "Ramjet",
        "category": CATEGORY,
        "summary": "Specific thrust and fuel consumption with the ram-compression limit.",
        "tags": ["ramjet", "scramjet", "hypersonic", "specific thrust", "ram compression"],
        "inputs": [
            num("M0", "Flight Mach number", 3.0, minimum=0.1, maximum=8.0,
                section="Flight condition"),
            num("altitude", "Altitude", 20000.0, minimum=-1000, maximum=60000,
                section="Flight condition"),
            choice("alt_unit", "Altitude unit", [("m", "metres"), ("ft", "feet")], "m",
                   section="Flight condition"),
            num("Tt4", "Combustor exit total temperature", 2000.0, "K", minimum=300.0,
                maximum=3000.0, section="Cycle"),
            num("hPR", "Fuel heating value", 43.0, "MJ/kg", minimum=1.0, section="Cycle"),
            num("eta_b", "Burner efficiency", 0.95, minimum=0.3, maximum=1.0,
                section="Cycle"),
            num("pi_d", "Inlet pressure ratio", 0.95, minimum=0.2, maximum=1.0,
                section="Pressure ratios"),
            num("pi_b", "Burner pressure ratio", 0.94, minimum=0.5, maximum=1.0,
                section="Pressure ratios"),
            num("pi_n", "Nozzle pressure ratio", 0.98, minimum=0.5, maximum=1.0,
                section="Pressure ratios"),
            num("gamma", "Specific heat ratio \u03b3", 1.35, minimum=1.1, maximum=1.7,
                section="Gas properties"),
            num("cp", "Specific heat c_p", 1100.0, "J/(kg\u00b7K)", minimum=100.0,
                section="Gas properties"),
            num("mdot", "Inlet mass flow", 0.0, "kg/s", minimum=0.0, section="Engine size"),
        ],
        "compute": _ramjet,
    },
    {
        "id": "rocket-nozzle",
        "name": "Rocket nozzle performance",
        "category": CATEGORY,
        "summary": "Thrust coefficient, c*, specific impulse and optimum expansion.",
        "description": "Ideal rocket theory with the pressure-thrust term handled properly, "
                       "so sea-level and vacuum performance both come out right.",
        "tags": ["rocket", "Isp", "thrust coefficient", "c star", "area ratio", "nozzle"],
        "inputs": [
            num("pc", "Chamber pressure", 7000000.0, "Pa", minimum=1000.0,
                section="Chamber"),
            num("Tc", "Chamber temperature", 3500.0, "K", minimum=100.0, section="Chamber"),
            num("gamma", "Specific heat ratio \u03b3", 1.2, minimum=1.05, maximum=1.7,
                section="Chamber"),
            choice("gas_spec", "Gas constant from", [("molar", "Molar mass"),
                                                     ("R", "Specific gas constant")],
                   "molar", section="Chamber"),
            num("Mw", "Exhaust molar mass", 22.0, "g/mol", minimum=1.0, section="Chamber",
                show_if={"key": "gas_spec", "in": ["molar"]}),
            num("R", "Specific gas constant", 378.0, "J/(kg\u00b7K)", minimum=10.0,
                section="Chamber", show_if={"key": "gas_spec", "in": ["R"]}),
            choice("expansion", "Expansion specified by", [("area", "Area ratio"),
                                                           ("pressure", "Exit pressure")],
                   "area", section="Nozzle"),
            num("eps", "Area ratio A\u2091/A\u209c", 25.0, minimum=1.0, section="Nozzle",
                show_if={"key": "expansion", "in": ["area"]}),
            num("pe", "Exit pressure", 20000.0, "Pa", minimum=0.001, section="Nozzle",
                show_if={"key": "expansion", "in": ["pressure"]}),
            choice("size_by", "Size the engine by", [("throat", "Throat area"),
                                                     ("thrust", "Required thrust")],
                   "throat", section="Sizing"),
            num("At", "Throat area", 0.02, "m\u00b2", minimum=1e-9, section="Sizing",
                show_if={"key": "size_by", "in": ["throat"]}),
            num("F", "Required thrust", 500000.0, "N", minimum=1.0, section="Sizing",
                show_if={"key": "size_by", "in": ["thrust"]}),
            num("pa", "Ambient pressure", 0.0, "Pa", minimum=0.0, section="Environment",
                help="Use 0 for vacuum, 101325 for sea level."),
            toggle("real", "Apply efficiency factors", False, section="Losses"),
            num("eta_cstar", "c* efficiency", 0.96, minimum=0.5, maximum=1.0,
                section="Losses", show_if={"key": "real", "in": [True]}),
            num("eta_cf", "C_F efficiency", 0.98, minimum=0.5, maximum=1.0,
                section="Losses", show_if={"key": "real", "in": [True]}),
        ],
        "compute": _rocket_nozzle,
    },
    {
        "id": "propeller-momentum",
        "name": "Propeller and rotor momentum theory",
        "category": CATEGORY,
        "summary": "Induced velocity, ideal power, Froude efficiency and figure of merit.",
        "tags": ["propeller", "actuator disk", "rotor", "hover", "figure of merit",
                 "disk loading"],
        "inputs": [
            num("T", "Thrust", 5000.0, "N", minimum=1e-9, section="Operating point"),
            num("V", "Flight speed", 50.0, "m/s", minimum=0.0, section="Operating point",
                help="Set to 0 for hover."),
            num("D", "Disk diameter", 2.0, "m", minimum=1e-6, section="Geometry"),
            num("rho", "Air density", 1.225, "kg/m\u00b3", minimum=1e-9, section="Geometry"),
            num("P_actual", "Shaft power supplied", 0.0, "kW", minimum=0.0,
                section="Power", help="Set to 0 to skip the efficiency comparison."),
            toggle("blade", "Add rotational parameters", False, section="Rotation"),
            num("rpm", "Rotational speed", 2400.0, "rpm", minimum=1.0, section="Rotation",
                show_if={"key": "blade", "in": [True]}),
        ],
        "compute": _propeller,
    },
]
