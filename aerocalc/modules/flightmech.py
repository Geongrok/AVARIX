"""Flight mechanics: performance, manoeuvring, stability and control."""

from __future__ import annotations

import math

from .. import plotting as P
from ..core import CalculationError, Result, choice, num, toggle
from ..numeric import linspace, solve
from ..physics import G0, atmosphere

CATEGORY = "Flight Mechanics"

FT = 0.3048
KT = 0.514444444


def _atmos(inp):
    z = inp["altitude"] * (FT if inp["alt_unit"] == "ft" else 1.0)
    return z, atmosphere(z, dT=inp.get("dT", 0.0))


def _alt_fields(default=0.0):
    return [
        num("altitude", "Altitude", default, minimum=-1000, maximum=30000,
            section="Flight condition"),
        choice("alt_unit", "Altitude unit", [("m", "metres"), ("ft", "feet")], "m",
               section="Flight condition"),
    ]


def _aircraft_fields():
    return [
        num("W", "Weight", 50000.0, "N", minimum=1.0, section="Aircraft"),
        num("S", "Wing area", 30.0, "m\u00b2", minimum=1e-6, section="Aircraft"),
        num("CD0", "Zero-lift drag coefficient", 0.022, minimum=1e-6, section="Aircraft"),
        num("AR", "Aspect ratio", 8.0, minimum=0.5, maximum=50, section="Aircraft"),
        num("e", "Oswald efficiency", 0.8, minimum=0.1, maximum=1.0, section="Aircraft"),
        num("CLmax", "Maximum lift coefficient", 1.6, minimum=0.1, maximum=5.0,
            section="Aircraft"),
    ]


# ---------------------------------------------------------------------------
# 1. Level flight performance
# ---------------------------------------------------------------------------


def _level_flight(inp):
    z, atm = _atmos(inp)
    rho = atm["rho"]
    W, S, CD0, AR, e = inp["W"], inp["S"], inp["CD0"], inp["AR"], inp["e"]
    k = 1 / (math.pi * AR * e)
    CLmax = inp["CLmax"]

    V_stall = math.sqrt(2 * W / (rho * S * CLmax))
    CL_md = math.sqrt(CD0 / k)
    LD_max = 1 / (2 * math.sqrt(CD0 * k))
    V_md = math.sqrt(2 * W / (rho * S * CL_md))
    V_mp = V_md / 3 ** 0.25
    D_min = W / LD_max

    def thrust_req(V):
        q = 0.5 * rho * V * V
        return q * S * CD0 + k * W * W / (q * S)

    def power_req(V):
        return thrust_req(V) * V

    jet = inp["engine"] == "jet"
    if jet:
        Ta = inp["T_sl"] * (atm["sigma"] ** inp["lapse"])
        avail_label = f"Thrust available {Ta / 1000:.4g} kN"
    else:
        Pa = inp["P_sl"] * 1000 * inp["eta_p"] * (atm["sigma"] ** inp["lapse"])
        avail_label = f"Power available {Pa / 1000:.4g} kW"

    r = Result()
    r.group("Reference speeds", f"{z:.0f} m, \u03c1 = {rho:.5g} kg/m\u00b3")
    r.headline("Stall speed", V_stall, "m/s", symbol="V_stall")
    r.out("Stall speed", V_stall / KT, "kt")
    r.headline("Minimum drag speed", V_md, "m/s", symbol="V_md",
               note="also the best glide and best jet endurance speed")
    r.out("Minimum drag speed", V_md / KT, "kt")
    r.out("Minimum power speed", V_mp, "m/s", symbol="V_mp",
          note="V_md/3^0.25 \u2014 best propeller endurance speed")
    r.out("Maximum lift-to-drag ratio", LD_max, symbol="(L/D)\u2098\u2090\u2093")
    r.out("Minimum drag", D_min, "N", symbol="D_min")
    r.out("Minimum power required", power_req(V_mp) / 1000, "kW")
    r.out("Wing loading", W / S, "N/m\u00b2", symbol="W/S")
    r.out("C_L at minimum drag", CL_md)

    r.group("Envelope", avail_label)
    vs = linspace(max(V_stall * 0.4, 5.0), max(V_md * 4, 200.0), 500)
    Tr = [thrust_req(v) for v in vs]
    Pr = [power_req(v) for v in vs]

    try:
        if jet:
            V_max = solve(lambda v: Ta - thrust_req(v), V_md, vs[-1] * 3,
                          what="maximum speed", expand=True)
        else:
            V_max = solve(lambda v: Pa - power_req(v), V_mp, vs[-1] * 3,
                          what="maximum speed", expand=True)
        r.headline("Maximum level speed", V_max, "m/s", symbol="V_max")
        r.out("Maximum level speed", V_max / KT, "kt")
        r.out("Mach number at V_max", V_max / atm["a"], symbol="M")
        r.out("C_L at V_max", 2 * W / (rho * V_max ** 2 * S))
    except CalculationError:
        V_max = None
        r.note("The engine cannot overcome the drag at any speed at this altitude — "
               "level flight is not possible here.")

    try:
        if jet:
            V_min = solve(lambda v: Ta - thrust_req(v), 1.0, V_md, what="minimum speed")
        else:
            V_min = solve(lambda v: Pa - power_req(v), 1.0, V_mp, what="minimum speed")
        limited = "stall" if V_stall > V_min else "thrust"
        r.out("Minimum thrust-limited speed", V_min, "m/s")
        r.out("Actual minimum speed", max(V_min, V_stall), "m/s",
              note=f"{limited}-limited at this altitude")
    except CalculationError:
        r.out("Actual minimum speed", V_stall, "m/s", note="stall-limited")

    if inp["V_op"] > 0:
        V = inp["V_op"]
        q = 0.5 * rho * V * V
        CL = W / (q * S)
        CD = CD0 + k * CL ** 2
        r.group("At your operating speed", f"V = {V:g} m/s")
        r.out("Lift coefficient required", CL, symbol="C_L")
        r.out("Drag coefficient", CD, symbol="C_D")
        r.out("Lift-to-drag ratio", CL / CD, symbol="L/D")
        r.out("Drag (= thrust required)", thrust_req(V), "N", symbol="D")
        r.out("Power required", power_req(V) / 1000, "kW")
        r.out("Angle of attack margin to stall", CLmax / CL, symbol="C_Lmax/C_L")
        r.out("Dynamic pressure", q, "Pa", symbol="q")
        if CL > CLmax:
            r.note("The lift coefficient needed exceeds C_Lmax — the aircraft "
                   "cannot sustain level flight this slowly.")

    series = [{"x": vs, "y": [t / 1000 for t in Tr], "label": "thrust required"}]
    if jet:
        series.append({"x": vs, "y": [Ta / 1000] * len(vs), "label": "thrust available",
                       "color": P.SERIES[1]})
    series.append({"x": vs, "y": [0.5 * rho * v * v * S * CD0 / 1000 for v in vs],
                   "label": "parasite drag", "style": ":", "color": P.MUTED, "width": 1.2})
    series.append({"x": vs, "y": [k * W * W / (0.5 * rho * v * v * S) / 1000 for v in vs],
                   "label": "induced drag", "style": "--", "color": P.MUTED, "width": 1.2})
    r.plot(**P.chart(
        series, xlabel="True airspeed  V  [m/s]", ylabel="Force  [kN]",
        title="Thrust required and available",
        ylim=(0, max(Tr) / 1000 * 0.5),
        vlines=[{"value": V_stall, "label": "stall", "color": "#B3242B"}],
        points=[{"x": V_md, "y": D_min / 1000, "label": "minimum drag"}],
        caption="Parasite and induced drag are equal at V_md, which is what makes "
                "it the minimum of the total curve."))

    pseries = [{"x": vs, "y": [p / 1000 for p in Pr], "label": "power required"}]
    if not jet:
        pseries.append({"x": vs, "y": [Pa / 1000] * len(vs), "label": "power available",
                        "color": P.SERIES[1]})
    else:
        pseries.append({"x": vs, "y": [Ta * v / 1000 for v in vs],
                        "label": "power available", "color": P.SERIES[1]})
    r.plot(**P.chart(
        pseries, xlabel="True airspeed  V  [m/s]", ylabel="Power  [kW]",
        title="Power required and available",
        ylim=(0, max(Pr) / 1000 * 0.4),
        points=[{"x": V_mp, "y": power_req(V_mp) / 1000, "label": "minimum power"}],
        caption="The gap between the curves is excess power, which is what "
                "produces rate of climb."))
    return r


# ---------------------------------------------------------------------------
# 2. Range and endurance
# ---------------------------------------------------------------------------


def _range_endurance(inp):
    z, atm = _atmos(inp)
    rho = atm["rho"]
    W0, Wf = inp["W0"], inp["W_fuel"]
    W1 = W0 - Wf
    if W1 <= 0:
        raise CalculationError("The fuel weight cannot exceed the take-off weight.")
    S, CD0, AR, e = inp["S"], inp["CD0"], inp["AR"], inp["e"]
    k = 1 / (math.pi * AR * e)
    LD_max = 1 / (2 * math.sqrt(CD0 * k))
    CL_md = math.sqrt(CD0 / k)

    r = Result()
    r.group("Weights")
    r.out("Take-off weight", W0, "N", symbol="W\u2080")
    r.out("Fuel weight", Wf, "N", symbol="W_f")
    r.out("End-of-cruise weight", W1, "N", symbol="W\u2081")
    r.out("Weight ratio", W0 / W1, symbol="W\u2080/W\u2081")
    r.out("Fuel fraction", Wf / W0 * 100, "%")

    if inp["engine"] == "jet":
        ct = inp["ct"]
        cl_cd_max_r = 0.5 * math.sqrt(1 / (k * CD0)) * math.sqrt(CD0 / (3 * k)) ** 0.5 \
            if False else (3 / 4) * (1 / (3 * k * CD0 ** 3)) ** 0.25
        # Constant-altitude, constant-CL cruise (Breguet for jets)
        R_alt = (2 / ct) * math.sqrt(2 / (rho * S)) * cl_cd_max_r * (
            math.sqrt(W0) - math.sqrt(W1))
        V_cruise = math.sqrt(2 * W0 / (rho * S * math.sqrt(CD0 / (3 * k))))
        R_cc = (V_cruise / ct) * LD_max * math.log(W0 / W1)
        E = (1 / ct) * LD_max * math.log(W0 / W1)

        r.group("Jet performance", f"c_t = {ct:g} 1/s, {z:.0f} m")
        r.headline("Maximum range (constant altitude)", R_alt / 1000, "km", symbol="R")
        r.out("Maximum range (cruise-climb)", R_cc / 1000, "km",
              note="flying at constant C_L and drifting up as fuel burns")
        r.headline("Maximum endurance", E / 3600, "h", symbol="E")
        r.out("Best range parameter \u221aC_L/C_D", cl_cd_max_r, symbol="(\u221aC_L/C_D)\u2098\u2090\u2093")
        r.out("C_L for best range", math.sqrt(CD0 / (3 * k)))
        r.out("Speed for best range at W\u2080", V_cruise, "m/s")
        r.out("Speed for best range at W\u2080", V_cruise / KT, "kt")
        r.out("C_L for best endurance", CL_md, note="best endurance is at maximum L/D")
        r.out("Speed for best endurance at W\u2080",
              math.sqrt(2 * W0 / (rho * S * CL_md)), "m/s")
        r.out("Maximum L/D", LD_max)
        r.out("Fuel flow at best endurance", ct * W0 / LD_max, "N/s")
    else:
        c = inp["c_p"]
        eta = inp["eta_p"]
        R = (eta / c) * LD_max * math.log(W0 / W1)
        cl15 = (3 * CD0 / k) ** 0.75 / (4 * CD0)
        E = (eta / c) * cl15 * math.sqrt(2 * rho * S) * (
            1 / math.sqrt(W1) - 1 / math.sqrt(W0))
        r.group("Propeller performance", f"c = {c:g} 1/m, \u03b7 = {eta:g}, {z:.0f} m")
        r.headline("Maximum range", R / 1000, "km", symbol="R")
        r.headline("Maximum endurance", E / 3600, "h", symbol="E")
        r.out("Maximum L/D", LD_max, note="best range is at maximum L/D for a propeller")
        r.out("C_L for best range", CL_md)
        r.out("Speed for best range at W\u2080",
              math.sqrt(2 * W0 / (rho * S * CL_md)), "m/s")
        r.out("Best endurance parameter C_L^1.5/C_D", cl15)
        r.out("C_L for best endurance", math.sqrt(3 * CD0 / k))
        r.out("Speed for best endurance at W\u2080",
              math.sqrt(2 * W0 / (rho * S * math.sqrt(3 * CD0 / k))), "m/s")
        R = R
    r.note("Breguet results assume steady cruise only. Real block range must also "
           "allow for climb, descent, diversion and reserves — typically 5 to 10 % "
           "of the fuel.")

    ratios = linspace(1.0, max(3.0, W0 / W1 * 1.3), 200)
    if inp["engine"] == "jet":
        rr = [(math.sqrt(2 * W0 / (rho * S * math.sqrt(CD0 / (3 * k)))) / inp["ct"])
              * LD_max * math.log(x) / 1000 for x in ratios]
    else:
        rr = [(inp["eta_p"] / inp["c_p"]) * LD_max * math.log(x) / 1000 for x in ratios]
    r.plot(**P.chart(
        [{"x": ratios, "y": rr, "label": "range"}],
        xlabel="Weight ratio  W\u2080/W\u2081", ylabel="Range  [km]",
        title="Range against weight ratio",
        points=[{"x": W0 / W1, "y": rr[min(range(len(ratios)),
                                           key=lambda i: abs(ratios[i] - W0 / W1))],
                 "label": "your aircraft"}],
        caption="Range grows only with the logarithm of the weight ratio, which is "
                "why carrying more fuel gives steadily diminishing returns."))

    alts = linspace(0, 15000, 200)
    if inp["engine"] == "jet":
        ys = [(math.sqrt(2 * W0 / (atmosphere(a)["rho"] * S * math.sqrt(CD0 / (3 * k))))
               / inp["ct"]) * LD_max * math.log(W0 / W1) / 1000 for a in alts]
        cap = ("Jet range improves with altitude because the true airspeed at the "
               "best-range lift coefficient rises as density falls.")
    else:
        ys = [(inp["eta_p"] / inp["c_p"]) * LD_max * math.log(W0 / W1) / 1000
              for _ in alts]
        cap = ("Propeller range is independent of altitude in this model — the "
               "real variation comes from engine and propeller efficiency.")
    r.plot(**P.chart(
        [{"x": [a / 1000 for a in alts], "y": ys, "label": "range", "color": P.SERIES[2]}],
        xlabel="Altitude  [km]", ylabel="Range  [km]",
        title="Range against cruise altitude",
        vlines=[{"value": z / 1000, "label": "your altitude"}],
        caption=cap))
    return r


# ---------------------------------------------------------------------------
# 3. Climb performance
# ---------------------------------------------------------------------------


def _climb(inp):
    z, atm = _atmos(inp)
    rho = atm["rho"]
    W, S, CD0, AR, e = inp["W"], inp["S"], inp["CD0"], inp["AR"], inp["e"]
    k = 1 / (math.pi * AR * e)
    CLmax = inp["CLmax"]
    jet = inp["engine"] == "jet"

    def excess_power(V, density):
        q = 0.5 * density * V * V
        D = q * S * CD0 + k * W * W / (q * S)
        sigma = density / 1.225
        if jet:
            T = inp["T_sl"] * sigma ** inp["lapse"]
            return (T - D) * V, T, D
        Pav = inp["P_sl"] * 1000 * inp["eta_p"] * sigma ** inp["lapse"]
        return Pav - D * V, Pav / V, D

    V_stall = math.sqrt(2 * W / (rho * S * CLmax))
    vs = linspace(max(V_stall, 5.0), 400.0, 600)
    rc = [excess_power(v, rho)[0] / W for v in vs]
    best_i = max(range(len(vs)), key=lambda i: rc[i])
    RC_max, V_y = rc[best_i], vs[best_i]

    gamma = [math.degrees(math.asin(min(1.0, max(-1.0, rc[i] / vs[i])))) for i in range(len(vs))]
    best_g = max(range(len(vs)), key=lambda i: gamma[i])

    r = Result()
    r.group("Climb", f"{z:.0f} m, \u03c1 = {rho:.5g} kg/m\u00b3")
    r.headline("Maximum rate of climb", RC_max, "m/s", symbol="RC_max")
    r.out("Maximum rate of climb", RC_max * 196.85, "ft/min")
    r.headline("Speed for best rate of climb", V_y, "m/s", symbol="V_y")
    r.out("Speed for best rate of climb", V_y / KT, "kt")
    r.out("Best climb angle", gamma[best_g], "\u00b0", symbol="\u03b3_max")
    r.out("Speed for best climb angle", vs[best_g], "m/s", symbol="V_x")
    r.out("Climb gradient at V_x", math.tan(math.radians(gamma[best_g])) * 100, "%")
    r.out("Excess power at V_y", RC_max * W / 1000, "kW")
    r.out("Specific excess power at V_y", RC_max, "m/s", symbol="P_s")
    r.out("Stall speed", V_stall, "m/s")

    # Ceilings
    def rc_at(alt):
        a = atmosphere(alt)
        v_stall = math.sqrt(2 * W / (a["rho"] * S * CLmax))
        best = -1e9
        for v in linspace(max(v_stall, 5.0), 400.0, 200):
            best = max(best, excess_power(v, a["rho"])[0] / W)
        return best

    r.group("Ceilings")
    try:
        abs_ceiling = solve(lambda a: rc_at(a), z, 25000.0, what="absolute ceiling")
        r.headline("Absolute ceiling", abs_ceiling, "m", symbol="h_abs")
        r.out("Absolute ceiling", abs_ceiling / FT, "ft")
    except CalculationError:
        abs_ceiling = None
        r.out("Absolute ceiling", "above 25 000 m — outside the model range")
    try:
        svc = solve(lambda a: rc_at(a) - 0.508, z, 25000.0, what="service ceiling")
        r.out("Service ceiling", svc, "m", note="where max RC falls to 100 ft/min")
        r.out("Service ceiling", svc / FT, "ft")
    except CalculationError:
        r.out("Service ceiling", "above 25 000 m")

    if inp["climb_to"] > 0:
        target = inp["climb_to"] * (FT if inp["alt_unit"] == "ft" else 1.0)
        if abs_ceiling and target >= abs_ceiling:
            r.note(f"The target altitude is at or above the absolute ceiling, so the "
                   "aircraft can never reach it in steady climb.")
        else:
            n = 60
            alts = linspace(z, target, n)
            t = 0.0
            for i in range(n - 1):
                rc_mid = rc_at((alts[i] + alts[i + 1]) / 2)
                if rc_mid <= 0:
                    t = float("inf")
                    break
                t += (alts[i + 1] - alts[i]) / rc_mid
            r.group("Time to climb")
            r.out("Target altitude", target, "m")
            r.out("Time to climb", t / 60, "min",
                  note="integrated numerically over 60 altitude steps")
            r.out("Average rate of climb", (target - z) / t if t else float("nan"), "m/s")

    r.plot(**P.chart(
        [{"x": vs, "y": rc, "label": "rate of climb"}],
        xlabel="True airspeed  V  [m/s]", ylabel="Rate of climb  [m/s]",
        title="Rate of climb against speed", ylim=(0, RC_max * 1.3),
        points=[{"x": V_y, "y": RC_max, "label": "V_y (best rate)"},
                {"x": vs[best_g], "y": rc[best_g], "label": "V_x (best angle)",
                 "color": "#0E7C6B"}],
        vlines=[{"value": V_stall, "label": "stall", "color": "#B3242B"}],
        caption="V_x is where the tangent from the origin touches the curve; V_y "
                "is the peak. V_x matters for obstacle clearance, V_y for time."))

    alts = linspace(z, 20000, 60)
    rcs = [rc_at(a) for a in alts]
    r.plot(**P.chart(
        [{"x": P.safe(rcs), "y": [a / 1000 for a in alts], "label": "maximum RC"}],
        xlabel="Maximum rate of climb  [m/s]", ylabel="Altitude  [km]",
        title="Climb performance with altitude",
        hlines=[{"value": abs_ceiling / 1000, "label": "absolute ceiling",
                 "color": "#B3242B"}] if abs_ceiling else None,
        caption="Rate of climb falls almost linearly with altitude, reaching zero "
                "at the absolute ceiling."))
    return r


# ---------------------------------------------------------------------------
# 4. Turning flight and the V-n diagram
# ---------------------------------------------------------------------------


def _turn(inp):
    z, atm = _atmos(inp)
    rho = atm["rho"]
    W, S, CLmax = inp["W"], inp["S"], inp["CLmax"]
    n_max, n_min = inp["n_max"], inp["n_min"]
    V = inp["V"]

    if inp["specify"] == "bank":
        phi = math.radians(inp["bank"])
        if abs(inp["bank"]) >= 90:
            raise CalculationError(
                "A bank angle of 90\u00b0 cannot sustain level flight — the lift "
                "vector is horizontal and nothing supports the weight.")
        n = 1 / math.cos(phi)
    else:
        n = inp["n"]
        if n < 1:
            raise CalculationError(
                "A level turn needs a load factor of at least 1.")
        phi = math.acos(1 / n)

    V_stall = math.sqrt(2 * W / (rho * S * CLmax))
    V_stall_n = V_stall * math.sqrt(n)
    if V < V_stall_n:
        raise CalculationError(
            f"At load factor {n:.3f} the accelerated stall speed is "
            f"{V_stall_n:.4g} m/s, above the speed you entered. The aircraft "
            "would stall in this turn.")

    R = V ** 2 / (G0 * math.sqrt(max(n * n - 1, 1e-12)))
    omega = G0 * math.sqrt(max(n * n - 1, 1e-12)) / V
    V_corner = V_stall * math.sqrt(n_max)
    CL = 2 * n * W / (rho * V * V * S)

    r = Result()
    r.group("Turn", f"{z:.0f} m, V = {V:g} m/s")
    r.headline("Load factor", n, "g", symbol="n")
    r.headline("Bank angle", math.degrees(phi), "\u00b0", symbol="\u03d5")
    r.headline("Turn radius", R, "m", symbol="R")
    r.out("Turn rate", math.degrees(omega), "\u00b0/s", symbol="\u03c9")
    r.out("Time for a 360\u00b0 turn", 2 * math.pi / omega, "s")
    r.out("Lift required", n * W / 1000, "kN", symbol="L = nW")
    r.out("Lift coefficient required", CL, symbol="C_L")
    r.out("Margin to C_Lmax", CLmax / CL, note="1.0 means at the stall boundary")
    r.out("Apparent weight increase", (n - 1) * 100, "%")

    r.group("Limits")
    r.out("1 g stall speed", V_stall, "m/s", symbol="V_s")
    r.out("Accelerated stall speed at this n", V_stall_n, "m/s")
    r.headline("Corner speed", V_corner, "m/s", symbol="V*",
               note="slowest speed at which the limit load factor can be reached")
    r.out("Corner speed", V_corner / KT, "kt")
    r.out("Turn radius at corner speed",
          V_corner ** 2 / (G0 * math.sqrt(n_max ** 2 - 1)), "m")
    r.out("Turn rate at corner speed",
          math.degrees(G0 * math.sqrt(n_max ** 2 - 1) / V_corner), "\u00b0/s",
          note="the tightest, fastest turn the airframe can make")
    r.out("Maximum load factor at this speed",
          min(n_max, 0.5 * rho * V * V * S * CLmax / W), "g",
          note="whichever of stall or structural limit binds first")

    if inp["thrust"] > 0:
        k = 1 / (math.pi * inp["AR"] * inp["e"])
        q = 0.5 * rho * V * V
        D = q * S * inp["CD0"] + k * (n * W) ** 2 / (q * S)
        n_sustained = math.sqrt(max(0.0,
                                    (inp["thrust"] / (q * S) - inp["CD0"])
                                    * q * S * q * S / (k * W * W)))
        r.group("Sustained turn", f"Thrust {inp['thrust'] / 1000:g} kN")
        r.out("Drag in this turn", D / 1000, "kN")
        r.out("Thrust margin", (inp["thrust"] - D) / 1000, "kN",
              note="negative means the turn bleeds speed")
        r.out("Maximum sustained load factor", n_sustained, "g")
        r.out("Sustained turn rate at this speed",
              math.degrees(G0 * math.sqrt(max(n_sustained ** 2 - 1, 0)) / V), "\u00b0/s")

    v_range = linspace(0.1, V_stall * math.sqrt(abs(n_max)) * 2.6, 400)
    pos_stall = [min(0.5 * rho * v * v * S * CLmax / W, n_max) for v in v_range]
    neg_stall = [max(-0.5 * rho * v * v * S * CLmax / W, n_min) for v in v_range]
    r.plot(**P.chart(
        [{"x": v_range, "y": pos_stall, "label": "positive limit"},
         {"x": v_range, "y": neg_stall, "label": "negative limit", "color": P.SERIES[1]}],
        xlabel="True airspeed  V  [m/s]", ylabel="Load factor  n  [g]",
        title="V\u2013n manoeuvre diagram",
        hlines=[{"value": 0.0}, {"value": 1.0, "label": "1 g level flight"}],
        vlines=[{"value": V_corner, "label": "corner speed", "color": "#0E7C6B"}],
        points=[{"x": V, "y": n, "label": "your turn"}],
        caption="The curved edges are the aerodynamic stall boundary; the flat tops "
                "are the structural limit. They meet at the corner speed."))

    vs2 = linspace(V_stall, V_stall * 4, 300)
    r.plot(**P.chart(
        [{"x": vs2, "y": [v ** 2 / (G0 * math.sqrt(max(min(n_max, 0.5 * rho * v * v * S * CLmax / W) ** 2 - 1, 1e-9)))
                          for v in vs2], "label": "minimum turn radius"}],
        xlabel="True airspeed  V  [m/s]", ylabel="Turn radius  [m]",
        title="Tightest turn against speed", ylog=True,
        ylim=(V_corner ** 2 / (G0 * math.sqrt(n_max ** 2 - 1)) * 0.6,
              V_corner ** 2 / (G0 * math.sqrt(n_max ** 2 - 1)) * 60),
        points=[{"x": V, "y": R, "label": "your turn"}],
        vlines=[{"value": V_corner, "label": "corner speed", "color": "#0E7C6B"}],
        caption="Radius is smallest at the corner speed: below it the aircraft "
                "stalls before reaching the limit load, above it the higher speed "
                "widens the turn."))
    return r


# ---------------------------------------------------------------------------
# 5. Take-off and landing
# ---------------------------------------------------------------------------


def _takeoff_landing(inp):
    z, atm = _atmos(inp)
    rho = atm["rho"]
    W, S, CLmax = inp["W"], inp["S"], inp["CLmax"]
    CD0, AR, e = inp["CD0"], inp["AR"], inp["e"]
    k = 1 / (math.pi * AR * e)
    mu = inp["mu"]
    m = W / G0

    V_stall = math.sqrt(2 * W / (rho * S * CLmax))
    V_lof = inp["k_lof"] * V_stall
    V_td = inp["k_td"] * V_stall
    V_app = 1.3 * V_stall

    # Ground effect reduces induced drag
    h_b = inp["h_over_b"]
    phi_ge = (16 * h_b) ** 2 / (1 + (16 * h_b) ** 2)
    k_ge = k * phi_ge

    T = inp["T_sl"] * (atm["sigma"] ** inp["lapse"])
    V07 = 0.707 * V_lof
    q07 = 0.5 * rho * V07 ** 2
    CL_roll = inp["CL_roll"]
    D07 = q07 * S * (CD0 + k_ge * CL_roll ** 2)
    L07 = q07 * S * CL_roll
    F_net = T - D07 - mu * (W - L07)
    if F_net <= 0:
        raise CalculationError(
            "The available thrust cannot overcome drag and rolling friction — "
            "the aircraft would never accelerate to lift-off speed.")
    S_ground = 1.44 * W ** 2 / (G0 * rho * S * CLmax * F_net)

    # Transition and climb to screen height
    R_trans = V_lof ** 2 / (G0 * (inp["n_trans"] - 1))
    gamma_climb = math.asin(min(1.0, max(0.0,
                                         (T - 0.5 * rho * V_lof ** 2 * S
                                          * (CD0 + k * (2 * W / (rho * V_lof ** 2 * S)) ** 2)) / W)))
    h_trans = R_trans * (1 - math.cos(gamma_climb))
    h_screen = inp["h_screen"]
    S_trans = R_trans * math.sin(gamma_climb)
    S_climb = (h_screen - h_trans) / math.tan(gamma_climb) if h_trans < h_screen and gamma_climb > 0 else 0.0
    S_takeoff = S_ground + S_trans + max(S_climb, 0.0)

    r = Result()
    r.group("Take-off", f"{z:.0f} m, \u03c1 = {rho:.5g} kg/m\u00b3, \u03bc = {mu:g}")
    r.headline("Ground roll", S_ground, "m", symbol="S_G")
    r.headline("Total distance to screen height", S_takeoff, "m")
    r.out("Total distance to screen height", S_takeoff / FT, "ft")
    r.out("Stall speed", V_stall, "m/s")
    r.out("Lift-off speed", V_lof, "m/s", symbol="V_LOF",
          note=f"{inp['k_lof']:g} \u00d7 V_stall")
    r.out("Lift-off speed", V_lof / KT, "kt")
    r.out("Net accelerating force at 0.707 V_LOF", F_net / 1000, "kN")
    r.out("Mean acceleration", F_net / m, "m/s\u00b2")
    r.out("Time on the ground roll", V_lof / (F_net / m), "s", note="approximate")
    r.out("Transition distance", S_trans, "m")
    r.out("Climb distance to screen", max(S_climb, 0.0), "m")
    r.out("Initial climb angle", math.degrees(gamma_climb), "\u00b0")
    r.out("Ground effect factor on induced drag", phi_ge, symbol="\u03d5",
          note=f"at h/b = {h_b:g}")

    # Landing
    T_rev = -inp["T_reverse"] * 1000
    mu_b = inp["mu_brake"]
    V07L = 0.707 * V_td
    q07L = 0.5 * rho * V07L ** 2
    D07L = q07L * S * (CD0 + k_ge * CL_roll ** 2)
    L07L = q07L * S * CL_roll
    F_dec = -T_rev + D07L + mu_b * (W - L07L)
    S_ground_land = 1.69 * W ** 2 / (G0 * rho * S * CLmax * F_dec)
    S_air = (inp["h_screen"] / math.tan(math.radians(inp["gamma_app"]))
             + (V_app ** 2 - V_td ** 2) / (2 * G0 * (inp["n_flare"] - 1)))

    r.group("Landing", f"braking \u03bc = {mu_b:g}")
    r.headline("Ground roll", S_ground_land, "m", symbol="S_L")
    r.headline("Total landing distance from screen height",
               S_ground_land + S_air, "m")
    r.out("Approach speed", V_app, "m/s", note="1.3 \u00d7 V_stall")
    r.out("Approach speed", V_app / KT, "kt")
    r.out("Touchdown speed", V_td, "m/s", symbol="V_TD")
    r.out("Air distance from screen height", S_air, "m")
    r.out("Mean deceleration", F_dec / m, "m/s\u00b2")
    r.out("Braking force at 0.707 V_TD", F_dec / 1000, "kN")
    r.out("Time on the landing roll", V_td / (F_dec / m), "s", note="approximate")

    r.group("Comparison")
    r.out("Take-off / landing ground roll ratio", S_ground / S_ground_land)
    r.out("Runway needed for both", max(S_takeoff, S_ground_land + S_air), "m")
    r.note("These are classical estimates that assume constant mean forces. "
           "Certified field lengths add engine-failure cases and regulatory "
           "factors (a 1.15 to 1.67 multiplier depending on the rule set).")

    alts = linspace(0, 4000, 200)
    ss = []
    for a in alts:
        at = atmosphere(a)
        Ta = inp["T_sl"] * at["sigma"] ** inp["lapse"]
        vlof = inp["k_lof"] * math.sqrt(2 * W / (at["rho"] * S * CLmax))
        q = 0.5 * at["rho"] * (0.707 * vlof) ** 2
        Fn = Ta - q * S * (CD0 + k_ge * CL_roll ** 2) - mu * (W - q * S * CL_roll)
        ss.append(1.44 * W ** 2 / (G0 * at["rho"] * S * CLmax * Fn) if Fn > 0 else float("nan"))
    r.plot(**P.chart(
        [{"x": [a for a in alts], "y": P.safe(ss), "label": "ground roll"}],
        xlabel="Airfield elevation  [m]", ylabel="Ground roll  [m]",
        title="Take-off roll against airfield elevation",
        points=[{"x": z, "y": S_ground, "label": "your airfield"}],
        caption="Density altitude hurts twice: it raises the lift-off speed and "
                "reduces the thrust available to reach it."))
    return r


# ---------------------------------------------------------------------------
# 6. Longitudinal static stability
# ---------------------------------------------------------------------------


def _static_stability(inp):
    Sw, cbar, bw = inp["Sw"], inp["cbar"], inp["bw"]
    St, lt = inp["St"], inp["lt"]
    aw, at = inp["aw"], inp["at"]
    eta_t = inp["eta_t"]
    x_ac = inp["x_ac"]
    x_cg = inp["x_cg"]
    ARw = bw ** 2 / Sw if Sw > 0 else 0.0

    VH = St * lt / (Sw * cbar)
    deda = inp["deda"] if inp["custom_deda"] else 2 * aw / (math.pi * ARw)

    x_np = x_ac + eta_t * VH * (at / aw) * (1 - deda)
    SM = x_np - x_cg
    CL_alpha = aw + eta_t * (St / Sw) * at * (1 - deda)
    Cm_alpha = -CL_alpha * SM
    Cm_alpha_simple = aw * (x_cg - x_ac) - eta_t * VH * at * (1 - deda)

    r = Result()
    r.group("Geometry")
    r.out("Wing aspect ratio", ARw, symbol="AR_w")
    r.headline("Tail volume coefficient", VH, symbol="V_H = S_t\u00b7l_t/(S_w\u00b7c\u0304)")
    r.out("Tail area ratio", St / Sw, symbol="S_t/S_w")
    r.out("Tail arm in chords", lt / cbar, symbol="l_t/c\u0304")
    r.out("Downwash derivative", deda, symbol="d\u03b5/d\u03b1",
          note="estimated as 2a_w/(\u03c0AR)" if not inp["custom_deda"] else "as entered")

    r.group("Stability")
    r.headline("Neutral point", x_np, "x/c\u0304", symbol="x_np")
    r.headline("Static margin", SM * 100, "% c\u0304", symbol="SM")
    r.out("Aircraft lift-curve slope", CL_alpha, "per rad", symbol="C_L\u03b1")
    r.out("Pitching moment derivative", Cm_alpha, "per rad", symbol="C_m\u03b1")
    r.out("Pitching moment derivative", Cm_alpha_simple, "per rad",
          note="computed the long way as a cross-check")
    r.out("Verdict", "statically stable" if SM > 0 else
          ("neutrally stable" if abs(SM) < 1e-6 else "statically unstable"),
          note="a positive static margin means the nose drops when the aircraft "
               "is disturbed nose-up")
    r.out("Tail contribution to C_m\u03b1", -eta_t * VH * at * (1 - deda), "per rad")
    r.out("Wing-body contribution to C_m\u03b1", aw * (x_cg - x_ac), "per rad")

    if SM < 0.05 and SM > 0:
        r.note("A static margin below about 5 % of the chord is very relaxed. "
               "Transport aircraft usually sit between 5 % and 25 %; fighters may "
               "go negative and rely on the flight control system.")

    r.group("Trim")
    Cm0 = inp["Cm0"]
    alpha_trim = -(Cm0 + inp["Cm_de"] * math.radians(inp["de"])) / Cm_alpha if Cm_alpha else float("nan")
    r.out("Zero-lift pitching moment", Cm0, symbol="C_m0")
    r.out("Elevator effectiveness", inp["Cm_de"], "per rad", symbol="C_m\u03b4e")
    r.out("Trim angle of attack at this elevator setting",
          math.degrees(alpha_trim), "\u00b0")
    r.out("Trim lift coefficient", CL_alpha * alpha_trim)
    r.out("Elevator angle per g",
          -inp["W"] / (inp["Sw"] * 0.5 * 1.225 * inp["V"] ** 2) * SM / inp["Cm_de"]
          if inp["Cm_de"] and inp["V"] > 0 else float("nan"), "rad/g",
          note="stick-fixed manoeuvre gradient, approximate")

    cgs = linspace(0.0, 1.0, 200)
    r.plot(**P.chart(
        [{"x": cgs, "y": [-(CL_alpha) * (x_np - c) for c in cgs], "label": "C_m\u03b1"}],
        xlabel="Centre of gravity position  x_cg/c\u0304",
        ylabel="C_m\u03b1  [per rad]",
        title="Stability against centre of gravity position",
        hlines=[{"value": 0.0, "label": "neutral point", "color": "#B3242B"}],
        vlines=[{"value": x_cg, "label": "your CG", "color": "#0E7C6B"}],
        bands=[{"x0": 0.0, "x1": x_np, "label": "stable", "color": "#0E7C6B"}],
        points=[{"x": x_cg, "y": Cm_alpha, "label": "your configuration"}],
        caption="Everything left of the neutral point is stable. Loading the "
                "aircraft aft moves the CG right and eats the margin."))

    alphas = linspace(-5, 15, 100)
    series = []
    for de in (-15, -5, 0, 5, 15):
        cms = [Cm0 + Cm_alpha * math.radians(a) + inp["Cm_de"] * math.radians(de)
               for a in alphas]
        series.append({"x": alphas, "y": cms, "label": f"\u03b4_e = {de}\u00b0",
                       "width": 2.2 if de == inp["de"] else 1.2})
    r.plot(**P.chart(
        series, xlabel="Angle of attack  \u03b1  [\u00b0]",
        ylabel="Pitching moment coefficient  C_m",
        title="Trim diagram",
        hlines=[{"value": 0.0, "color": "#B3242B"}],
        caption="Each elevator setting trims where its line crosses C_m = 0. "
                "A negative slope is what makes those trim points stable."))
    return r


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ENGINE_FIELDS = [
    choice("engine", "Powerplant", [("jet", "Jet (thrust-producing)"),
                                    ("prop", "Propeller (power-producing)")],
           "jet", section="Powerplant"),
    num("T_sl", "Sea-level thrust", 25000.0, "N", minimum=0.0, section="Powerplant",
        show_if={"key": "engine", "in": ["jet"]}),
    num("P_sl", "Sea-level shaft power", 300.0, "kW", minimum=0.0,
        section="Powerplant", show_if={"key": "engine", "in": ["prop"]}),
    num("eta_p", "Propeller efficiency", 0.8, minimum=0.1, maximum=1.0,
        section="Powerplant", show_if={"key": "engine", "in": ["prop"]}),
    num("lapse", "Altitude lapse exponent", 0.7, minimum=0.0, maximum=1.5,
        section="Powerplant",
        help="Available thrust or power scales as \u03c3 raised to this power."),
]

CALCULATORS = [
    {
        "id": "level-flight",
        "name": "Level flight performance",
        "category": CATEGORY,
        "summary": "Thrust and power required, stall speed, minimum drag speed and V_max.",
        "tags": ["thrust required", "power required", "V_max", "stall", "drag curve"],
        "inputs": _aircraft_fields() + _alt_fields() + _ENGINE_FIELDS + [
            num("V_op", "Operating speed to evaluate", 0.0, "m/s", minimum=0.0,
                section="Operating point", help="Set to 0 to skip."),
        ],
        "compute": _level_flight,
    },
    {
        "id": "range-endurance",
        "name": "Range and endurance",
        "category": CATEGORY,
        "summary": "Breguet range and endurance for jet and propeller aircraft.",
        "tags": ["Breguet", "range", "endurance", "SFC", "cruise", "fuel fraction"],
        "inputs": [
            num("W0", "Take-off weight", 60000.0, "N", minimum=1.0, section="Weights"),
            num("W_fuel", "Usable fuel weight", 15000.0, "N", minimum=0.0,
                section="Weights"),
            num("S", "Wing area", 30.0, "m\u00b2", minimum=1e-6, section="Aircraft"),
            num("CD0", "Zero-lift drag coefficient", 0.022, minimum=1e-6,
                section="Aircraft"),
            num("AR", "Aspect ratio", 9.0, minimum=0.5, maximum=50, section="Aircraft"),
            num("e", "Oswald efficiency", 0.8, minimum=0.1, maximum=1.0,
                section="Aircraft"),
            choice("engine", "Powerplant", [("jet", "Jet"), ("prop", "Propeller")],
                   "jet", section="Powerplant"),
            num("ct", "Thrust specific fuel consumption", 0.00002, "1/s",
                minimum=1e-9, section="Powerplant",
                show_if={"key": "engine", "in": ["jet"]},
                help="Weight of fuel per unit thrust per second."),
            num("c_p", "Power specific fuel consumption", 8e-7, "1/m", minimum=1e-12,
                section="Powerplant", show_if={"key": "engine", "in": ["prop"]}),
            num("eta_p", "Propeller efficiency", 0.85, minimum=0.1, maximum=1.0,
                section="Powerplant", show_if={"key": "engine", "in": ["prop"]}),
        ] + _alt_fields(10000.0),
        "compute": _range_endurance,
    },
    {
        "id": "climb-performance",
        "name": "Climb performance and ceilings",
        "category": CATEGORY,
        "summary": "Rate of climb, best climb speeds, service and absolute ceilings.",
        "tags": ["rate of climb", "Vx", "Vy", "ceiling", "excess power", "time to climb"],
        "inputs": _aircraft_fields() + _alt_fields() + _ENGINE_FIELDS + [
            num("climb_to", "Climb to altitude", 0.0, section="Time to climb",
                minimum=0.0, help="Set to 0 to skip. Uses the altitude unit above."),
        ],
        "compute": _climb,
    },
    {
        "id": "turn-performance",
        "name": "Turning flight and V–n diagram",
        "category": CATEGORY,
        "summary": "Load factor, turn radius and rate, corner speed and the flight envelope.",
        "tags": ["load factor", "turn radius", "corner speed", "V-n diagram", "bank angle"],
        "inputs": [
            num("W", "Weight", 50000.0, "N", minimum=1.0, section="Aircraft"),
            num("S", "Wing area", 30.0, "m\u00b2", minimum=1e-6, section="Aircraft"),
            num("CLmax", "Maximum lift coefficient", 1.6, minimum=0.1, maximum=5.0,
                section="Aircraft"),
            num("n_max", "Positive limit load factor", 6.0, "g", minimum=1.0,
                maximum=15.0, section="Aircraft"),
            num("n_min", "Negative limit load factor", -3.0, "g", minimum=-10.0,
                maximum=0.0, section="Aircraft"),
            num("V", "True airspeed", 150.0, "m/s", minimum=1.0, section="Turn"),
            choice("specify", "Specify turn by", [("bank", "Bank angle"),
                                                  ("n", "Load factor")], "bank",
                   section="Turn"),
            num("bank", "Bank angle", 60.0, "\u00b0", minimum=0.0, maximum=89.9,
                section="Turn", show_if={"key": "specify", "in": ["bank"]}),
            num("n", "Load factor", 2.0, "g", minimum=1.0, maximum=15.0, section="Turn",
                show_if={"key": "specify", "in": ["n"]}),
            num("thrust", "Thrust available", 0.0, "N", minimum=0.0,
                section="Sustained turn", help="Set to 0 to skip the sustained turn."),
            num("CD0", "Zero-lift drag coefficient", 0.022, minimum=1e-6,
                section="Sustained turn"),
            num("AR", "Aspect ratio", 4.0, minimum=0.5, maximum=50,
                section="Sustained turn"),
            num("e", "Oswald efficiency", 0.8, minimum=0.1, maximum=1.0,
                section="Sustained turn"),
        ] + _alt_fields(5000.0),
        "compute": _turn,
    },
    {
        "id": "takeoff-landing",
        "name": "Take-off and landing distances",
        "category": CATEGORY,
        "summary": "Ground roll, transition and air distance including ground effect.",
        "tags": ["ground roll", "V_LOF", "screen height", "braking", "field length"],
        "inputs": _aircraft_fields() + _alt_fields() + [
            num("T_sl", "Sea-level thrust", 25000.0, "N", minimum=0.0,
                section="Powerplant"),
            num("lapse", "Altitude lapse exponent", 0.7, minimum=0.0, maximum=1.5,
                section="Powerplant"),
            num("mu", "Rolling friction coefficient", 0.03, minimum=0.0, maximum=0.5,
                section="Take-off"),
            num("CL_roll", "Lift coefficient during the roll", 0.3, minimum=0.0,
                maximum=3.0, section="Take-off"),
            num("k_lof", "V_LOF / V_stall", 1.15, minimum=1.0, maximum=1.5,
                section="Take-off"),
            num("h_over_b", "Wing height above ground / span", 0.1, minimum=0.01,
                maximum=2.0, section="Take-off"),
            num("n_trans", "Load factor during transition", 1.2, minimum=1.01,
                maximum=2.0, section="Take-off"),
            num("h_screen", "Screen height", 10.7, "m", minimum=0.0, section="Take-off",
                help="10.7 m (35 ft) for transport aircraft, 15.2 m (50 ft) otherwise."),
            num("mu_brake", "Braking friction coefficient", 0.4, minimum=0.0,
                maximum=1.0, section="Landing"),
            num("k_td", "V_TD / V_stall", 1.15, minimum=1.0, maximum=1.5,
                section="Landing"),
            num("T_reverse", "Reverse thrust", 0.0, "kN", minimum=0.0, section="Landing"),
            num("gamma_app", "Approach angle", 3.0, "\u00b0", minimum=0.5, maximum=15.0,
                section="Landing"),
            num("n_flare", "Load factor during flare", 1.2, minimum=1.01, maximum=2.0,
                section="Landing"),
        ],
        "compute": _takeoff_landing,
    },
    {
        "id": "static-stability",
        "name": "Longitudinal static stability",
        "category": CATEGORY,
        "summary": "Neutral point, static margin, C_mα and the trim diagram.",
        "tags": ["neutral point", "static margin", "tail volume", "trim", "downwash"],
        "inputs": [
            num("Sw", "Wing area", 30.0, "m\u00b2", minimum=1e-6, section="Wing"),
            num("bw", "Wing span", 15.0, "m", minimum=1e-6, section="Wing"),
            num("cbar", "Mean aerodynamic chord", 2.0, "m", minimum=1e-6, section="Wing"),
            num("aw", "Wing lift-curve slope", 4.8, "per rad", minimum=0.5, maximum=8.0,
                section="Wing"),
            num("x_ac", "Wing-body aerodynamic centre", 0.25, "x/c\u0304", minimum=0.0,
                maximum=1.0, section="Wing"),
            num("St", "Horizontal tail area", 6.0, "m\u00b2", minimum=1e-9, section="Tail"),
            num("lt", "Tail arm", 7.0, "m", minimum=1e-9, section="Tail",
                help="Distance from the CG to the tail aerodynamic centre."),
            num("at", "Tail lift-curve slope", 4.0, "per rad", minimum=0.5, maximum=8.0,
                section="Tail"),
            num("eta_t", "Tail dynamic pressure ratio", 0.95, minimum=0.1, maximum=1.2,
                section="Tail"),
            toggle("custom_deda", "Enter the downwash derivative", False, section="Tail"),
            num("deda", "Downwash derivative d\u03b5/d\u03b1", 0.35, minimum=0.0,
                maximum=1.0, section="Tail",
                show_if={"key": "custom_deda", "in": [True]}),
            num("x_cg", "Centre of gravity", 0.30, "x/c\u0304", minimum=0.0, maximum=1.2,
                section="Loading"),
            num("Cm0", "Zero-lift pitching moment", -0.05, section="Trim"),
            num("Cm_de", "Elevator effectiveness C_m\u03b4e", -1.2, "per rad",
                maximum=0.0, section="Trim"),
            num("de", "Elevator deflection", 0.0, "\u00b0", minimum=-30.0, maximum=30.0,
                section="Trim"),
            num("W", "Weight", 50000.0, "N", minimum=1.0, section="Trim"),
            num("V", "True airspeed", 100.0, "m/s", minimum=0.0, section="Trim"),
        ],
        "compute": _static_stability,
    },
]
