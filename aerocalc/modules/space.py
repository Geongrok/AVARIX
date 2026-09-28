"""Space and satellite mechanics: orbits, transfers, propagation and launch."""

from __future__ import annotations

import math

from .. import plotting as P
from ..core import CalculationError, Result, choice, integer, num, toggle
from ..numeric import linspace, newton, solve
from ..physics import BODIES, G0, OMEGA_EARTH, R_EARTH

CATEGORY = "Space & Satellites"

BODY_OPTIONS = [(k, v[0]) for k, v in BODIES.items()] + [("custom", "Custom body")]

# Mean motion of the Earth about the Sun, used for sun-synchronous orbits
N_SUN = 2 * math.pi / 365.2421897 / 86400.0     # rad/s


def _body(inp, prefix=""):
    key = inp.get(prefix + "body", "earth")
    if key == "custom":
        mu = inp[prefix + "mu"] * 1e9          # km^3/s^2 entered
        R = inp[prefix + "R_body"] * 1000.0
        return "Custom body", mu, R, inp.get(prefix + "J2", 0.0)
    name, mu, R, J2 = BODIES[key]
    return name, mu, R, J2


def _body_fields(section="Central body", default="earth"):
    return [
        choice("body", "Central body", BODY_OPTIONS, default, section=section),
        num("mu", "Gravitational parameter", 398600.4418, "km\u00b3/s\u00b2",
            minimum=1e-9, section=section, show_if={"key": "body", "in": ["custom"]}),
        num("R_body", "Body radius", 6378.137, "km", minimum=1e-9, section=section,
            show_if={"key": "body", "in": ["custom"]}),
        num("J2", "J\u2082", 0.00108263, minimum=0.0, section=section,
            show_if={"key": "body", "in": ["custom"]}),
    ]


def _draw_orbit(a, e, R_body, name, *, mark_nu=None, title="Orbit geometry",
                caption=""):
    """Ellipse with the central body drawn to scale at the occupied focus."""
    fig, ax = P.polar_orbit_figure()
    nus = linspace(0, 2 * math.pi, 720)
    p = a * (1 - e ** 2)
    xs = [p / (1 + e * math.cos(n)) * math.cos(n) / 1000 for n in nus]
    ys = [p / (1 + e * math.cos(n)) * math.sin(n) / 1000 for n in nus]
    ax.plot(xs, ys, color=P.SERIES[0], lw=2.0, zorder=4, label="orbit")

    body = plt_circle(R_body / 1000)
    ax.fill(body[0], body[1], color="#C7D4E2", zorder=2, lw=0)
    ax.plot(body[0], body[1], color=P.SERIES[0], lw=1.0, zorder=3)
    ax.annotate(name, (0, 0), ha="center", va="center", fontsize=8.5,
                color="#26425F", zorder=5)

    rp, ra = a * (1 - e), a * (1 + e)
    ax.plot([rp / 1000], [0], "o", ms=6, color="#B3242B",
            markeredgecolor="white", markeredgewidth=1.2, zorder=6)
    ax.annotate("periapsis", (rp / 1000, 0), xytext=(6, -12),
                textcoords="offset points", fontsize=8.5, color=P.MUTED)
    if e > 1e-9:
        ax.plot([-ra / 1000], [0], "o", ms=6, color="#B26B00",
                markeredgecolor="white", markeredgewidth=1.2, zorder=6)
        ax.annotate("apoapsis", (-ra / 1000, 0), xytext=(-8, -14),
                    textcoords="offset points", fontsize=8.5, color=P.MUTED,
                    ha="right")
    if mark_nu is not None:
        r_ = p / (1 + e * math.cos(mark_nu))
        ax.plot([r_ / 1000 * math.cos(mark_nu)], [r_ / 1000 * math.sin(mark_nu)],
                "o", ms=8, color="#0E7C6B", markeredgecolor="white",
                markeredgewidth=1.4, zorder=7)
        ax.plot([0, r_ / 1000 * math.cos(mark_nu)], [0, r_ / 1000 * math.sin(mark_nu)],
                color=P.MUTED, lw=0.9, ls=":", zorder=3)
    ax.set_xlabel("x  [km]")
    ax.set_ylabel("y  [km]")
    ax.set_title(title, loc="left", pad=9)
    return {"image": P.render(fig), "title": title, "caption": caption}


def plt_circle(r, n=200):
    th = linspace(0, 2 * math.pi, n)
    return [r * math.cos(t) for t in th], [r * math.sin(t) for t in th]


# ---------------------------------------------------------------------------
# 1. Orbital elements and properties
# ---------------------------------------------------------------------------


def _orbit(inp):
    name, mu, R_body, J2 = _body(inp)

    spec = inp["spec"]
    if spec == "alt":
        rp = R_body + inp["hp"] * 1000
        ra = R_body + inp["ha"] * 1000
        if ra < rp:
            rp, ra = ra, rp
        a = (rp + ra) / 2
        e = (ra - rp) / (ra + rp)
    elif spec == "radii":
        rp, ra = inp["rp"] * 1000, inp["ra"] * 1000
        if ra < rp:
            rp, ra = ra, rp
        a = (rp + ra) / 2
        e = (ra - rp) / (ra + rp)
    elif spec == "ae":
        a, e = inp["a"] * 1000, inp["e"]
        if e >= 1:
            raise CalculationError(
                "This calculator handles closed orbits only. For e \u2265 1 use the "
                "escape and hyperbolic calculator.")
        rp, ra = a * (1 - e), a * (1 + e)
    else:  # period
        T = inp["period"] * 60
        a = (mu * (T / (2 * math.pi)) ** 2) ** (1 / 3)
        e = inp["e"]
        rp, ra = a * (1 - e), a * (1 + e)

    if rp <= R_body:
        raise CalculationError(
            f"Periapsis is {(R_body - rp) / 1000:.1f} km below the surface of "
            f"{name} — this orbit intersects the body.")

    T = 2 * math.pi * math.sqrt(a ** 3 / mu)
    n = 2 * math.pi / T
    v_p = math.sqrt(mu * (2 / rp - 1 / a))
    v_a = math.sqrt(mu * (2 / ra - 1 / a))
    energy = -mu / (2 * a)
    h = math.sqrt(mu * a * (1 - e ** 2))
    p = a * (1 - e ** 2)

    r = Result()
    r.group("Orbit", f"about {name}")
    r.headline("Semi-major axis", a / 1000, "km", symbol="a")
    r.headline("Eccentricity", e, symbol="e")
    r.out("Semi-latus rectum", p / 1000, "km", symbol="p")
    r.out("Semi-minor axis", a * math.sqrt(1 - e ** 2) / 1000, "km", symbol="b")
    r.out("Periapsis radius", rp / 1000, "km", symbol="r_p")
    r.out("Apoapsis radius", ra / 1000, "km", symbol="r_a")
    r.out("Periapsis altitude", (rp - R_body) / 1000, "km", symbol="h_p")
    r.out("Apoapsis altitude", (ra - R_body) / 1000, "km", symbol="h_a")
    r.out("Orbit type",
          "circular" if e < 1e-4 else ("near-circular" if e < 0.01 else "elliptical"))

    r.group("Motion")
    r.headline("Orbital period", T / 60, "min", symbol="T")
    r.out("Orbital period", T / 3600, "h")
    r.out("Mean motion", n * 86400 / (2 * math.pi), "rev/day", symbol="n")
    r.out("Mean motion", n, "rad/s")
    r.headline("Velocity at periapsis", v_p / 1000, "km/s", symbol="v_p")
    r.out("Velocity at apoapsis", v_a / 1000, "km/s", symbol="v_a")
    r.out("Mean orbital velocity", 2 * math.pi * a / T / 1000, "km/s",
          note="exact only for a circular orbit")
    r.out("Specific angular momentum", h / 1e6, "km\u00b2/s", symbol="h")
    r.out("Specific orbital energy", energy / 1e6, "km\u00b2/s\u00b2",
          symbol="\u03b5 = \u2212\u03bc/2a")
    r.out("Escape velocity at periapsis", math.sqrt(2 * mu / rp) / 1000, "km/s")
    r.out("Extra \u0394v to escape from periapsis",
          (math.sqrt(2 * mu / rp) - v_p) / 1000, "km/s")

    r.group("Reference orbits", f"for {name}")
    v_circ_surface = math.sqrt(mu / R_body)
    r.out("Circular velocity at the surface", v_circ_surface / 1000, "km/s")
    r.out("Surface gravity", mu / R_body ** 2, "m/s\u00b2", symbol="g\u2080")
    if inp["body"] == "earth":
        r_geo = (mu * (86164.0905 / (2 * math.pi)) ** 2) ** (1 / 3)
        r.out("Geostationary radius", r_geo / 1000, "km")
        r.out("Geostationary altitude", (r_geo - R_body) / 1000, "km")

    if inp["j2_rates"] and J2 > 0:
        i = math.radians(inp["i"])
        factor = -1.5 * n * J2 * (R_body / p) ** 2
        raan_dot = factor * math.cos(i)
        argp_dot = -0.5 * factor * (5 * math.cos(i) ** 2 - 1)
        r.group("J\u2082 perturbations", f"inclination {inp['i']:g}\u00b0")
        r.headline("Nodal regression rate", math.degrees(raan_dot) * 86400,
                   "\u00b0/day", symbol="\u03a9\u0307")
        r.out("Argument of periapsis drift", math.degrees(argp_dot) * 86400,
              "\u00b0/day", symbol="\u03c9\u0307")
        r.out("Critical inclination", 63.4349, "\u00b0",
              note="where the argument of periapsis stops drifting")
        i_ss = _sun_sync_inclination(a, e, mu, R_body, J2)
        if i_ss:
            r.out("Sun-synchronous inclination for this orbit", math.degrees(i_ss),
                  "\u00b0", note="the node would then track the Sun at 0.9856\u00b0/day")
        r.out("Nodal period", 2 * math.pi / (n + argp_dot) / 60 if n + argp_dot else float("nan"),
              "min", note="the period between successive equator crossings")

    r.plot(**_draw_orbit(a, e, R_body, name,
                         caption="Drawn to scale with the central body at the "
                                 "occupied focus."))

    nus = linspace(0, 360, 361)
    rr = [p / (1 + e * math.cos(math.radians(x))) / 1000 for x in nus]
    vv = [math.sqrt(mu * (2 / (p / (1 + e * math.cos(math.radians(x)))) - 1 / a)) / 1000
          for x in nus]
    r.plot(**P.stack([
        {"series": [{"x": nus, "y": rr}], "xlabel": "True anomaly  \u03bd  [\u00b0]",
         "ylabel": "Radius  [km]", "title": "Radius"},
        {"series": [{"x": nus, "y": vv, "color": P.SERIES[1]}],
         "xlabel": "True anomaly  \u03bd  [\u00b0]", "ylabel": "Speed  [km/s]",
         "title": "Speed"},
    ], title="Radius and speed around the orbit",
        caption="Speed peaks at periapsis and bottoms out at apoapsis — the "
                "geometric statement of conservation of angular momentum."))
    return r


def _sun_sync_inclination(a, e, mu, R_body, J2):
    p = a * (1 - e ** 2)
    n = math.sqrt(mu / a ** 3)
    cos_i = N_SUN / (-1.5 * n * J2 * (R_body / p) ** 2)
    if abs(cos_i) > 1:
        return None
    return math.acos(cos_i)


# ---------------------------------------------------------------------------
# 2. Orbit transfers
# ---------------------------------------------------------------------------


def _transfer(inp):
    name, mu, R_body, J2 = _body(inp)
    if inp["spec"] == "alt":
        r1 = R_body + inp["h1"] * 1000
        r2 = R_body + inp["h2"] * 1000
    else:
        r1 = inp["r1"] * 1000
        r2 = inp["r2"] * 1000
    if r1 <= 0 or r2 <= 0:
        raise CalculationError("Both radii must be positive.")
    if abs(r2 - r1) / r1 < 1e-9:
        raise CalculationError("The two orbits are the same — there is nothing to transfer.")

    v1 = math.sqrt(mu / r1)
    v2 = math.sqrt(mu / r2)
    a_t = (r1 + r2) / 2
    v_p = math.sqrt(mu * (2 / r1 - 1 / a_t))
    v_a = math.sqrt(mu * (2 / r2 - 1 / a_t))
    dv1 = abs(v_p - v1)
    dv2 = abs(v2 - v_a)
    dv_hohmann = dv1 + dv2
    t_hohmann = math.pi * math.sqrt(a_t ** 3 / mu)

    r = Result()
    r.group("Initial and final orbits", f"about {name}")
    r.out("Initial radius", r1 / 1000, "km", symbol="r\u2081")
    r.out("Final radius", r2 / 1000, "km", symbol="r\u2082")
    r.out("Radius ratio", r2 / r1, symbol="r\u2082/r\u2081")
    r.out("Initial circular velocity", v1 / 1000, "km/s")
    r.out("Final circular velocity", v2 / 1000, "km/s")
    r.out("Initial period", 2 * math.pi * math.sqrt(r1 ** 3 / mu) / 60, "min")
    r.out("Final period", 2 * math.pi * math.sqrt(r2 ** 3 / mu) / 60, "min")

    r.group("Hohmann transfer")
    r.headline("Total \u0394v", dv_hohmann / 1000, "km/s", symbol="\u0394v")
    r.out("First burn", dv1 / 1000, "km/s", symbol="\u0394v\u2081")
    r.out("Second burn", dv2 / 1000, "km/s", symbol="\u0394v\u2082")
    r.headline("Transfer time", t_hohmann / 3600, "h", symbol="t")
    r.out("Transfer time", t_hohmann / 86400, "days")
    r.out("Transfer semi-major axis", a_t / 1000, "km")
    r.out("Transfer eccentricity", abs(r2 - r1) / (r1 + r2))
    r.out("Velocity at transfer periapsis", v_p / 1000, "km/s")
    r.out("Velocity at transfer apoapsis", v_a / 1000, "km/s")
    r.out("Phase angle required at departure",
          math.degrees(math.pi - 2 * math.pi * t_hohmann
                       / (2 * math.pi * math.sqrt(r2 ** 3 / mu))) % 360, "\u00b0",
          note="how far ahead the target must be when the first burn is made")

    # Bi-elliptic
    if inp["bielliptic"]:
        rb = inp["rb"] * 1000
        if rb <= max(r1, r2):
            raise CalculationError(
                "The bi-elliptic intermediate radius must be larger than both the "
                "initial and final radii.")
        a1 = (r1 + rb) / 2
        a2 = (rb + r2) / 2
        dvb1 = abs(math.sqrt(mu * (2 / r1 - 1 / a1)) - v1)
        dvb2 = abs(math.sqrt(mu * (2 / rb - 1 / a2)) - math.sqrt(mu * (2 / rb - 1 / a1)))
        dvb3 = abs(math.sqrt(mu * (2 / r2 - 1 / a2)) - v2)
        dv_bi = dvb1 + dvb2 + dvb3
        t_bi = math.pi * (math.sqrt(a1 ** 3 / mu) + math.sqrt(a2 ** 3 / mu))
        r.group("Bi-elliptic transfer", f"via {rb / 1000:g} km")
        r.headline("Total \u0394v", dv_bi / 1000, "km/s")
        r.out("First burn", dvb1 / 1000, "km/s")
        r.out("Second burn at the intermediate apoapsis", dvb2 / 1000, "km/s")
        r.out("Third burn", dvb3 / 1000, "km/s")
        r.out("Transfer time", t_bi / 86400, "days")
        r.out("Saving over Hohmann", (dv_hohmann - dv_bi) / 1000, "km/s",
              note="positive means bi-elliptic wins")
        r.out("Time penalty", (t_bi - t_hohmann) / 86400, "days")
        r.out("Verdict",
              "bi-elliptic is cheaper" if dv_bi < dv_hohmann else
              "Hohmann is cheaper")
        r.note("Bi-elliptic transfers only beat Hohmann above a radius ratio of "
               "about 11.94, and even then only if the intermediate radius is very "
               "large. The reward is a small \u0394v saving for a large time penalty.")

    if inp["plane_change"] != 0:
        di = math.radians(inp["plane_change"])
        dv_pure = 2 * v2 * math.sin(di / 2)
        # Combined with the second burn
        dv2_comb = math.sqrt(v_a ** 2 + v2 ** 2 - 2 * v_a * v2 * math.cos(di))
        r.group("Plane change", f"{inp['plane_change']:g}\u00b0")
        r.out("Separate plane change at the final orbit", dv_pure / 1000, "km/s")
        r.headline("Combined with the circularisation burn", dv2_comb / 1000, "km/s")
        r.out("Total \u0394v, separate manoeuvres",
              (dv_hohmann + dv_pure) / 1000, "km/s")
        r.headline("Total \u0394v, combined", (dv1 + dv2_comb) / 1000, "km/s")
        r.out("Saving from combining", (dv_hohmann + dv_pure - dv1 - dv2_comb) / 1000,
              "km/s", note="vector addition always beats two separate burns")
        r.out("Plane change at the initial orbit instead",
              2 * v1 * math.sin(di / 2) / 1000, "km/s",
              note="more expensive, because the vehicle is moving faster there")

    ratios = linspace(1.05, 60, 400)
    hoh = []
    bi15, bi50 = [], []
    for x in ratios:
        rr1, rr2 = 1.0, x
        at = (rr1 + rr2) / 2
        d = abs(math.sqrt(2 / rr1 - 1 / at) - math.sqrt(1 / rr1)) + \
            abs(math.sqrt(1 / rr2) - math.sqrt(2 / rr2 - 1 / at))
        hoh.append(d)
        for store, rbn in ((bi15, 15.0), (bi50, 50.0)):
            if rbn <= max(rr1, rr2):
                store.append(float("nan"))
                continue
            aa1, aa2 = (rr1 + rbn) / 2, (rbn + rr2) / 2
            store.append(abs(math.sqrt(2 / rr1 - 1 / aa1) - math.sqrt(1 / rr1))
                         + abs(math.sqrt(2 / rbn - 1 / aa2) - math.sqrt(2 / rbn - 1 / aa1))
                         + abs(math.sqrt(1 / rr2) - math.sqrt(2 / rr2 - 1 / aa2)))
    r.plot(**P.chart(
        [{"x": ratios, "y": hoh, "label": "Hohmann"},
         {"x": ratios, "y": P.safe(bi15), "label": "bi-elliptic via 15 r\u2081",
          "color": P.SERIES[1]},
         {"x": ratios, "y": P.safe(bi50), "label": "bi-elliptic via 50 r\u2081",
          "color": P.SERIES[2]}],
        xlabel="Radius ratio  r\u2082/r\u2081",
        ylabel="\u0394v  [units of \u221a(\u03bc/r\u2081)]",
        title="Transfer cost against radius ratio",
        vlines=[{"value": 11.94, "label": "11.94 crossover", "color": "#B3242B"}],
        points=[{"x": r2 / r1, "y": dv_hohmann / math.sqrt(mu / r1),
                 "label": "your transfer"}],
        caption="Hohmann \u0394v peaks near a ratio of 15.58 and then falls, which "
                "is what lets bi-elliptic transfers win at extreme ratios."))

    fig, ax = P.polar_orbit_figure()
    for rad, col, lab in ((r1, P.SERIES[0], "initial"), (r2, P.SERIES[2], "final")):
        cx, cy = plt_circle(rad / 1000)
        ax.plot(cx, cy, color=col, lw=1.8, label=lab)
    nus = linspace(0, math.pi, 300)
    e_t = abs(r2 - r1) / (r1 + r2)
    p_t = a_t * (1 - e_t ** 2)
    sign = 1 if r2 > r1 else -1
    ax.plot([p_t / (1 + e_t * math.cos(n)) * math.cos(n) * sign / 1000 for n in nus],
            [p_t / (1 + e_t * math.cos(n)) * math.sin(n) / 1000 for n in nus],
            color=P.SERIES[1], lw=2.2, label="transfer ellipse")
    bx, by = plt_circle(R_body / 1000)
    ax.fill(bx, by, color="#C7D4E2", lw=0, zorder=2)
    ax.legend(loc="upper right")
    ax.set_xlabel("x  [km]")
    ax.set_ylabel("y  [km]")
    ax.set_title("Transfer geometry", loc="left", pad=9)
    r.plot(P.render(fig), "Transfer geometry",
           "The transfer ellipse is tangent to both circular orbits, which is what "
           "makes it the cheapest two-burn route between them.")
    return r


# ---------------------------------------------------------------------------
# 3. Kepler propagation
# ---------------------------------------------------------------------------


def _kepler(inp):
    name, mu, R_body, J2 = _body(inp)
    a = inp["a"] * 1000
    e = inp["e"]
    if e < 0:
        raise CalculationError("Eccentricity cannot be negative.")
    if abs(e - 1) < 1e-9:
        raise CalculationError(
            "Parabolic orbits (e = 1 exactly) need Barker's equation, which this "
            "calculator does not cover. Try e = 0.9999 or 1.0001.")

    known = inp["known"]
    if e < 1:
        n = math.sqrt(mu / a ** 3)
        T = 2 * math.pi / n
        if known == "time":
            t = inp["t"] * 60
            M = n * t
            M = math.atan2(math.sin(M), math.cos(M))
            E = _solve_kepler(M, e)
            nu = 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2),
                                math.sqrt(1 - e) * math.cos(E / 2))
        else:
            nu = math.radians(inp["nu"])
            E = 2 * math.atan2(math.sqrt(1 - e) * math.sin(nu / 2),
                               math.sqrt(1 + e) * math.cos(nu / 2))
            M = E - e * math.sin(E)
            t = M / n
        r_ = a * (1 - e * math.cos(E))
    else:
        if a > 0:
            a = -a
        n = math.sqrt(mu / (-a) ** 3)
        T = float("inf")
        if known == "time":
            t = inp["t"] * 60
            M = n * t
            H = _solve_kepler_hyp(M, e)
            nu = 2 * math.atan2(math.sqrt(e + 1) * math.tanh(H / 2), math.sqrt(e - 1))
            E = H
        else:
            nu = math.radians(inp["nu"])
            nu_inf = math.acos(-1 / e)
            if abs(nu) >= nu_inf:
                raise CalculationError(
                    f"True anomaly must be below the asymptote at "
                    f"{math.degrees(nu_inf):.3f}\u00b0 for this hyperbola.")
            H = 2 * math.atanh(math.sqrt((e - 1) / (e + 1)) * math.tan(nu / 2))
            M = e * math.sinh(H) - H
            t = M / n
            E = H
        r_ = a * (1 - e * math.cosh(E))

    p = a * (1 - e ** 2)
    v = math.sqrt(mu * (2 / r_ - 1 / a))
    h = math.sqrt(mu * abs(p))
    gamma = math.atan2(e * math.sin(nu), 1 + e * math.cos(nu))

    r = Result()
    r.group("Orbit", f"about {name}, e = {e:g}")
    r.out("Semi-major axis", a / 1000, "km", symbol="a")
    r.out("Orbit type", "elliptical" if e < 1 else "hyperbolic")
    if e < 1:
        r.out("Period", T / 60, "min", symbol="T")
        r.out("Mean motion", math.degrees(n), "\u00b0/s")
    r.out("Periapsis radius", a * (1 - e) / 1000, "km")

    r.group("State at this point")
    r.headline("True anomaly", math.degrees(nu), "\u00b0", symbol="\u03bd")
    r.headline("Radius", r_ / 1000, "km", symbol="r")
    r.out("Altitude", (r_ - R_body) / 1000, "km")
    r.headline("Speed", v / 1000, "km/s", symbol="v")
    r.out("Radial velocity component", mu / h * e * math.sin(nu) / 1000, "km/s",
          symbol="v_r")
    r.out("Transverse velocity component", h / r_ / 1000, "km/s", symbol="v_\u03b8")
    r.out("Flight path angle", math.degrees(gamma), "\u00b0", symbol="\u03b3",
          note="zero at periapsis and apoapsis")
    r.out("Eccentric anomaly" if e < 1 else "Hyperbolic anomaly",
          math.degrees(E) if e < 1 else E, "\u00b0" if e < 1 else "", symbol="E")
    r.out("Mean anomaly", math.degrees(M) if e < 1 else M,
          "\u00b0" if e < 1 else "", symbol="M")
    r.headline("Time from periapsis", t / 60, "min", symbol="t")
    r.out("Time from periapsis", t / 3600, "h")

    if e < 1:
        ts = linspace(0, T, 400)
        Es, nus_, rs = [], [], []
        for tt in ts:
            Mm = n * tt
            Ee = _solve_kepler(math.atan2(math.sin(Mm), math.cos(Mm)), e)
            nn = 2 * math.atan2(math.sqrt(1 + e) * math.sin(Ee / 2),
                                math.sqrt(1 - e) * math.cos(Ee / 2))
            Es.append(math.degrees(Ee) % 360)
            nus_.append(math.degrees(nn) % 360)
            rs.append(a * (1 - e * math.cos(Ee)) / 1000)
        r.plot(**P.chart(
            [{"x": [x / 60 for x in ts], "y": [math.degrees(n * x) % 360 for x in ts],
              "label": "mean anomaly M"},
             {"x": [x / 60 for x in ts], "y": Es, "label": "eccentric anomaly E",
              "color": P.SERIES[1]},
             {"x": [x / 60 for x in ts], "y": nus_, "label": "true anomaly \u03bd",
              "color": P.SERIES[2]}],
            xlabel="Time from periapsis  [min]", ylabel="Angle  [\u00b0]",
            title="The three anomalies over one orbit",
            points=[{"x": t / 60 % (T / 60), "y": math.degrees(nu) % 360,
                     "label": "your point"}],
            caption="Mean anomaly advances uniformly with time; true anomaly races "
                    "ahead near periapsis. Kepler's equation is the bridge between "
                    "them, and it has no closed-form inverse."))
        r.plot(**_draw_orbit(a, e, R_body, name, mark_nu=nu,
                             title="Position on the orbit",
                             caption="The marker shows the spacecraft at the "
                                     "computed true anomaly."))
    return r


def _solve_kepler(M, e):
    """Kepler's equation M = E - e sin E, solved to machine precision."""
    E = M + e * math.sin(M) if e < 0.8 else math.pi
    return newton(lambda x: x - e * math.sin(x) - M,
                  lambda x: 1 - e * math.cos(x), E, what="the eccentric anomaly")


def _solve_kepler_hyp(M, e):
    H0 = math.asinh(M / e) if abs(M) > 1 else M / (e - 1)
    return newton(lambda x: e * math.sinh(x) - x - M,
                  lambda x: e * math.cosh(x) - 1, H0,
                  what="the hyperbolic anomaly")


# ---------------------------------------------------------------------------
# 4. Rocket equation and staging
# ---------------------------------------------------------------------------


def _rocket_equation(inp):
    r = Result()
    n_stages = int(inp["stages"])
    payload = inp["payload"]

    stage_data = []
    for i in range(1, n_stages + 1):
        isp = inp[f"isp{i}"]
        m_prop = inp[f"mp{i}"]
        m_struct = inp[f"ms{i}"]
        if m_prop <= 0 or m_struct <= 0:
            raise CalculationError(
                f"Stage {i} needs positive propellant and structural masses.")
        stage_data.append((isp, m_prop, m_struct))

    total_dv = 0.0
    m_above = payload
    rows = []
    for i in range(n_stages, 0, -1):
        isp, m_prop, m_struct = stage_data[i - 1]
        m0 = m_above + m_prop + m_struct
        mf = m_above + m_struct
        dv = isp * G0 * math.log(m0 / mf)
        total_dv += dv
        sigma = m_struct / (m_struct + m_prop)
        rows.insert(0, [f"{i}", isp, m_prop, m_struct, m0, mf, m0 / mf,
                        dv / 1000, sigma])
        m_above = m0

    m_total = m_above

    r.group("Vehicle", f"{n_stages} stage{'s' if n_stages > 1 else ''}")
    r.headline("Total \u0394v", total_dv / 1000, "km/s", symbol="\u0394v")
    r.headline("Gross lift-off mass", m_total, "kg", symbol="m\u2080")
    r.out("Payload mass", payload, "kg")
    r.headline("Payload fraction", payload / m_total * 100, "%", symbol="\u03bb")
    r.out("Overall mass ratio", m_total / (payload + sum(s[2] for s in stage_data)),
          symbol="m\u2080/m_f")
    r.out("Total propellant", sum(s[1] for s in stage_data), "kg")
    r.out("Total structure", sum(s[2] for s in stage_data), "kg")
    r.out("Propellant mass fraction",
          sum(s[1] for s in stage_data) / m_total * 100, "%")

    r.table("Stage breakdown",
            ["Stage", "I_sp [s]", "Propellant [kg]", "Structure [kg]",
             "m\u2080 [kg]", "m_f [kg]", "Mass ratio", "\u0394v [km/s]",
             "Structural coefficient"],
            rows, sig=5,
            caption="Stage 1 burns first; each stage carries everything above it.")

    if inp["target_dv"] > 0:
        target = inp["target_dv"] * 1000
        r.group("Against the mission requirement",
                f"target {inp['target_dv']:g} km/s")
        r.out("\u0394v margin", (total_dv - target) / 1000, "km/s")
        r.out("Margin as a fraction of the requirement",
              (total_dv - target) / target * 100, "%")
        r.out("Verdict", "sufficient" if total_dv >= target else "short of the target")
        if total_dv < target:
            isp_eff = total_dv / (G0 * math.log(m_total / (payload + sum(s[2] for s in stage_data))))
            extra = payload * (math.exp(target / (isp_eff * G0))
                               / math.exp(total_dv / (isp_eff * G0)) - 1)
            r.out("Approximate extra lift-off mass needed", extra, "kg",
                  note="holding the payload and stage efficiencies fixed")

    r.group("Reference \u0394v budgets", "Earth departure, approximate")
    for label, val in (("Low Earth orbit from the surface", 9.4),
                       ("LEO to geostationary transfer", 2.44),
                       ("GTO to geostationary", 1.47),
                       ("LEO to Earth escape", 3.22),
                       ("LEO to Mars transfer", 3.6),
                       ("Lunar surface from LEO", 6.0)):
        r.out(label, val, "km/s")

    isps = linspace(200, 480, 200)
    mr = m_total / (payload + sum(s[2] for s in stage_data))
    r.plot(**P.chart(
        [{"x": isps, "y": [x * G0 * math.log(mr) / 1000 for x in isps],
          "label": f"mass ratio {mr:.3g}"},
         {"x": isps, "y": [x * G0 * math.log(mr * 1.5) / 1000 for x in isps],
          "label": f"mass ratio {mr * 1.5:.3g}", "color": P.SERIES[1]},
         {"x": isps, "y": [x * G0 * math.log(mr * 0.7) / 1000 for x in isps],
          "label": f"mass ratio {mr * 0.7:.3g}", "color": P.SERIES[2]}],
        xlabel="Specific impulse  I_sp  [s]", ylabel="\u0394v  [km/s]",
        title="Ideal velocity against specific impulse",
        caption="\u0394v is linear in specific impulse but only logarithmic in mass "
                "ratio, which is why a better engine beats a bigger tank."))

    ratios = linspace(1.05, 20, 300)
    r.plot(**P.chart(
        [{"x": ratios, "y": [300 * G0 * math.log(x) / 1000 for x in ratios],
          "label": "I_sp = 300 s"},
         {"x": ratios, "y": [450 * G0 * math.log(x) / 1000 for x in ratios],
          "label": "I_sp = 450 s", "color": P.SERIES[1]}],
        xlabel="Mass ratio  m\u2080/m_f", ylabel="\u0394v  [km/s]",
        title="The tyranny of the rocket equation",
        points=[{"x": mr, "y": total_dv / 1000, "label": "your vehicle"}],
        hlines=[{"value": 9.4, "label": "LEO requirement", "color": "#B3242B"}],
        caption="Reaching orbit on one stage needs a mass ratio near 20, which "
                "leaves almost nothing for structure — the argument for staging."))
    return r


# ---------------------------------------------------------------------------
# 5. Ground track, coverage and J2
# ---------------------------------------------------------------------------


def _groundtrack(inp):
    name, mu, R_body, J2 = _body(inp)
    h = inp["h"] * 1000
    a = R_body + h
    e = inp["e"]
    i = math.radians(inp["i"])
    if a * (1 - e) <= R_body:
        raise CalculationError("The periapsis of this orbit is below the surface.")

    T = 2 * math.pi * math.sqrt(a ** 3 / mu)
    n = 2 * math.pi / T
    v = math.sqrt(mu / a)
    p = a * (1 - e ** 2)

    omega_body = OMEGA_EARTH if inp["body"] == "earth" else inp["omega_body"] * 2 * math.pi / 86400
    raan_dot = -1.5 * n * J2 * (R_body / p) ** 2 * math.cos(i) if J2 else 0.0
    argp_dot = 0.75 * n * J2 * (R_body / p) ** 2 * (5 * math.cos(i) ** 2 - 1) if J2 else 0.0

    dlon = -(omega_body - raan_dot) * T
    revs_per_day = 86400 / T

    r = Result()
    r.group("Orbit", f"{inp['h']:g} km altitude, {inp['i']:g}\u00b0 inclination")
    r.headline("Orbital period", T / 60, "min", symbol="T")
    r.out("Revolutions per day", revs_per_day)
    r.out("Orbital velocity", v / 1000, "km/s")
    r.out("Ground speed of the sub-satellite point",
          v * R_body / a / 1000, "km/s")
    r.headline("Ground track shift per revolution", math.degrees(dlon), "\u00b0",
               symbol="\u0394\u03bb",
               note="negative means the track moves west")
    r.out("Ground track shift", math.degrees(dlon) * math.pi / 180 * R_body / 1000, "km",
          note="measured at the equator")
    r.out("Maximum latitude reached", min(abs(inp["i"]), 180 - abs(inp["i"])), "\u00b0",
          note="the ground track is bounded by the inclination")

    if J2:
        r.group("J\u2082 precession")
        r.headline("Nodal regression", math.degrees(raan_dot) * 86400, "\u00b0/day",
                   symbol="\u03a9\u0307")
        r.out("Argument of periapsis drift", math.degrees(argp_dot) * 86400,
              "\u00b0/day", symbol="\u03c9\u0307")
        i_ss = _sun_sync_inclination(a, e, mu, R_body, J2)
        if i_ss:
            r.out("Sun-synchronous inclination at this altitude",
                  math.degrees(i_ss), "\u00b0",
                  note="gives a node rate of 0.9856\u00b0/day, matching the Sun")
            r.out("Is this orbit sun-synchronous?",
                  "yes" if abs(math.degrees(raan_dot) * 86400 - 0.9856) < 0.02 else "no")
        r.out("Nodal period", 2 * math.pi / (n + argp_dot) / 60, "min")

    eps = math.radians(inp["eps_min"])
    ratio = R_body / a
    if ratio * math.cos(eps) > 1:
        raise CalculationError("The geometry is impossible — check the altitude.")
    lam_max = math.acos(ratio * math.cos(eps)) - eps
    slant = R_body * (math.sin(lam_max) / math.sin(eps + math.pi / 2 - lam_max - eps)) \
        if eps > 0 else math.sqrt(a ** 2 - R_body ** 2)
    slant = math.sqrt(R_body ** 2 + a ** 2 - 2 * R_body * a * math.cos(lam_max))
    swath = 2 * lam_max * R_body
    area = 2 * math.pi * R_body ** 2 * (1 - math.cos(lam_max))
    t_access = 2 * lam_max / (n - omega_body * math.cos(i)) if n > omega_body else float("nan")

    r.group("Coverage", f"minimum elevation {inp['eps_min']:g}\u00b0")
    r.headline("Earth central angle", math.degrees(lam_max), "\u00b0", symbol="\u03bb")
    r.headline("Swath width", swath / 1000, "km")
    r.out("Maximum slant range", slant / 1000, "km")
    r.out("Nadir slant range", h / 1000, "km")
    r.out("Instantaneous coverage area", area / 1e6, "km\u00b2")
    r.out("Fraction of the surface in view", (1 - math.cos(lam_max)) / 2 * 100, "%")
    r.out("Maximum pass duration", t_access / 60 if t_access == t_access else float("nan"),
          "min", note="for a target passing directly overhead")
    r.out("Half-angle from nadir",
          math.degrees(math.asin(min(1.0, R_body / a * math.cos(eps)))), "\u00b0",
          note="the sensor cone half-angle needed to see the whole footprint")

    if inp["repeat"]:
        k = revs_per_day
        r.group("Repeat ground track")
        best = None
        for days in range(1, 31):
            revs = k * days
            nearest = round(revs)
            err = abs(revs - nearest)
            if nearest > 0 and (best is None or err / days < best[2] / best[0]):
                best = (days, nearest, err)
        if best:
            r.out("Closest repeat cycle",
                  f"{best[1]} revolutions in {best[0]} day"
                  f"{'s' if best[0] > 1 else ''}")
            r.out("Drift per cycle", best[2] * abs(math.degrees(dlon)), "\u00b0",
                  note="zero would be an exact repeat")
            a_exact = (mu * ((86400 * best[0] / best[1]) / (2 * math.pi)) ** 2) ** (1 / 3)
            r.out("Altitude for an exact repeat", (a_exact - R_body) / 1000, "km")
            r.out("Altitude change needed", (a_exact - a) / 1000, "km")

    # Ground track plot
    n_rev = 3
    lons, lats = [], []
    steps = 400 * n_rev
    for s in range(steps + 1):
        t = s * n_rev * T / steps
        u = n * t
        lat = math.asin(math.sin(i) * math.sin(u))
        dl = math.atan2(math.cos(i) * math.sin(u), math.cos(u))
        lon = dl - (omega_body - raan_dot) * t
        lon = (math.degrees(lon) + 180) % 360 - 180
        lons.append(lon)
        lats.append(math.degrees(lat))

    segs, cur_x, cur_y = [], [lons[0]], [lats[0]]
    for j in range(1, len(lons)):
        if abs(lons[j] - lons[j - 1]) > 180:
            segs.append((cur_x, cur_y))
            cur_x, cur_y = [], []
        cur_x.append(lons[j])
        cur_y.append(lats[j])
    segs.append((cur_x, cur_y))
    series = [{"x": sx, "y": sy, "color": P.SERIES[0],
               "label": "ground track" if idx == 0 else None}
              for idx, (sx, sy) in enumerate(segs) if sx]
    r.plot(**P.chart(
        series, xlabel="Longitude  [\u00b0]", ylabel="Latitude  [\u00b0]",
        title=f"Ground track over {n_rev} revolutions",
        xlim=(-180, 180), ylim=(-90, 90),
        hlines=[{"value": 0.0}],
        caption="Each pass lands west of the last because the body rotates "
                "underneath the orbit plane."))

    alts = linspace(200, 2000, 300)
    r.plot(**P.chart(
        [{"x": alts, "y": [math.degrees(math.acos(R_body / (R_body + x * 1000)
                                                  * math.cos(eps)) - eps) * 2
                           * R_body / 1000 * math.pi / 180 for x in alts],
          "label": "swath width"}],
        xlabel="Altitude  [km]", ylabel="Swath width  [km]",
        title="Coverage against altitude",
        points=[{"x": h / 1000, "y": swath / 1000, "label": "your orbit"}],
        caption="Higher orbits see more of the surface at once but resolve less "
                "detail and take longer to revisit any given point."))
    return r


# ---------------------------------------------------------------------------
# 6. Escape, hyperbolic orbits and gravity assist
# ---------------------------------------------------------------------------


def _escape(inp):
    name, mu, R_body, J2 = _body(inp)
    r_park = R_body + inp["h_park"] * 1000
    v_circ = math.sqrt(mu / r_park)
    v_esc = math.sqrt(2 * mu / r_park)

    mode = inp["mode"]
    if mode == "c3":
        C3 = inp["C3"] * 1e6
        v_inf = math.sqrt(C3) if C3 >= 0 else 0.0
    else:
        v_inf = inp["v_inf"] * 1000
        C3 = v_inf ** 2

    v_p = math.sqrt(v_inf ** 2 + 2 * mu / r_park)
    dv = v_p - v_circ
    a_hyp = -mu / C3 if C3 > 0 else float("-inf")
    e_hyp = 1 + r_park * C3 / mu if C3 > 0 else 1.0
    turn = 2 * math.asin(1 / e_hyp) if e_hyp > 1 else math.pi
    nu_inf = math.acos(-1 / e_hyp) if e_hyp > 1 else math.pi

    r = Result()
    r.group("Departure", f"from a {inp['h_park']:g} km parking orbit at {name}")
    r.out("Parking orbit radius", r_park / 1000, "km")
    r.out("Circular velocity", v_circ / 1000, "km/s", symbol="v_c")
    r.headline("Escape velocity", v_esc / 1000, "km/s", symbol="v_esc")
    r.out("\u0394v for simple escape", (v_esc - v_circ) / 1000, "km/s",
          note="the classic factor of \u221a2 \u2212 1 above circular velocity")

    r.group("Hyperbolic departure")
    r.headline("Hyperbolic excess velocity", v_inf / 1000, "km/s",
               symbol="v_\u221e")
    r.headline("Characteristic energy", C3 / 1e6, "km\u00b2/s\u00b2", symbol="C\u2083")
    r.headline("\u0394v required", dv / 1000, "km/s", symbol="\u0394v")
    r.out("Velocity at periapsis of the hyperbola", v_p / 1000, "km/s")
    r.out("Hyperbola eccentricity", e_hyp, symbol="e")
    r.out("Hyperbola semi-major axis", a_hyp / 1000 if C3 > 0 else float("-inf"),
          "km", note="negative for a hyperbola")
    r.out("True anomaly of the asymptote", math.degrees(nu_inf), "\u00b0",
          symbol="\u03bd_\u221e")
    r.out("Turn angle", math.degrees(turn), "\u00b0", symbol="\u03b4")
    r.out("Extra \u0394v over simple escape", (dv - (v_esc - v_circ)) / 1000, "km/s",
          note="the Oberth effect makes this far less than v_\u221e itself")
    r.out("Naive \u0394v if the burn were done far from the body",
          (v_esc - v_circ + v_inf) / 1000, "km/s",
          note="what it would cost without the Oberth benefit")

    if inp["body"] == "earth":
        r.group("Sphere of influence")
        a_earth = 1.495978707e11
        mu_sun = BODIES["sun"][1]
        soi = a_earth * (mu / mu_sun) ** 0.4
        r.out("Earth's sphere of influence", soi / 1000, "km")
        r.out("Sphere of influence in Earth radii", soi / R_body)
        r.out("Time to reach the sphere of influence",
              soi / v_inf / 86400 if v_inf > 0 else float("inf"), "days",
              note="rough, using the excess velocity alone")

    if inp["assist"]:
        v_body = inp["v_body"] * 1000
        r_peri = inp["r_flyby"] * 1000
        if r_peri <= R_body:
            raise CalculationError(
                "The flyby periapsis is inside the body. Raise the flyby radius.")
        e_fb = 1 + r_peri * v_inf ** 2 / mu
        delta = 2 * math.asin(1 / e_fb)
        dv_assist = 2 * v_inf * math.sin(delta / 2)
        v_out_max = math.sqrt(v_body ** 2 + v_inf ** 2 + 2 * v_body * v_inf)
        r.group("Gravity assist", f"flyby at {inp['r_flyby']:g} km radius")
        r.headline("Turn angle", math.degrees(delta), "\u00b0", symbol="\u03b4")
        r.headline("Velocity change in the heliocentric frame",
                   dv_assist / 1000, "km/s", symbol="\u0394v")
        r.out("Flyby eccentricity", e_fb)
        r.out("Flyby periapsis velocity",
              math.sqrt(v_inf ** 2 + 2 * mu / r_peri) / 1000, "km/s")
        r.out("Maximum possible outbound heliocentric speed",
              v_out_max / 1000, "km/s",
              note="the theoretical limit if the turn were a full reversal")
        r.out("Free \u0394v as a fraction of v_\u221e", dv_assist / v_inf)
        r.note("A gravity assist changes the spacecraft's velocity in the Sun's "
               "frame without using propellant. The speed relative to the planet is "
               "unchanged — only the direction turns, and the planet loses a "
               "vanishingly small amount of orbital energy in exchange.")

        radii = linspace(r_peri * 0.5 if r_peri > R_body * 1.2 else R_body,
                         r_peri * 8, 300)
        r.plot(**P.chart(
            [{"x": [x / 1000 for x in radii],
              "y": [math.degrees(2 * math.asin(1 / (1 + x * v_inf ** 2 / mu)))
                    for x in radii], "label": "turn angle"}],
            xlabel="Flyby periapsis radius  [km]", ylabel="Turn angle  \u03b4  [\u00b0]",
            title="Gravity assist turning against flyby distance",
            points=[{"x": r_peri / 1000, "y": math.degrees(delta),
                     "label": "your flyby"}],
            vlines=[{"value": R_body / 1000, "label": "surface", "color": "#B3242B"}],
            caption="Closer flybys turn the trajectory more, so mission designers "
                    "skim as low as the atmosphere and navigation errors allow."))

    c3s = linspace(0, max(60.0, C3 / 1e6 * 1.4), 300)
    r.plot(**P.chart(
        [{"x": c3s, "y": [(math.sqrt(x * 1e6 + 2 * mu / r_park) - v_circ) / 1000
                          for x in c3s], "label": "from the parking orbit"},
         {"x": c3s, "y": [(v_esc - v_circ + math.sqrt(x * 1e6)) / 1000 for x in c3s],
          "label": "without the Oberth effect", "style": "--", "color": P.MUTED}],
        xlabel="Characteristic energy  C\u2083  [km\u00b2/s\u00b2]",
        ylabel="\u0394v required  [km/s]",
        title="Departure cost against mission energy",
        points=[{"x": C3 / 1e6, "y": dv / 1000, "label": "your mission"}],
        caption="Burning deep in the gravity well converts propellant into far "
                "more energy than the same burn made at rest — the Oberth effect, "
                "and the gap between these two curves."))
    return r


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CALCULATORS = [
    {
        "id": "orbital-elements",
        "name": "Orbit geometry and properties",
        "category": CATEGORY,
        "summary": "Period, velocities, energy and J₂ precession from any orbit specification.",
        "tags": ["orbit", "vis-viva", "period", "apogee", "perigee", "geostationary"],
        "inputs": _body_fields() + [
            choice("spec", "Specify the orbit by",
                   [("alt", "Periapsis and apoapsis altitude"),
                    ("radii", "Periapsis and apoapsis radius"),
                    ("ae", "Semi-major axis and eccentricity"),
                    ("period", "Period and eccentricity")], "alt",
                   section="Orbit"),
            num("hp", "Periapsis altitude", 400.0, "km", section="Orbit",
                show_if={"key": "spec", "in": ["alt"]}),
            num("ha", "Apoapsis altitude", 400.0, "km", section="Orbit",
                show_if={"key": "spec", "in": ["alt"]}),
            num("rp", "Periapsis radius", 6778.0, "km", minimum=1e-6, section="Orbit",
                show_if={"key": "spec", "in": ["radii"]}),
            num("ra", "Apoapsis radius", 42164.0, "km", minimum=1e-6, section="Orbit",
                show_if={"key": "spec", "in": ["radii"]}),
            num("a", "Semi-major axis", 7000.0, "km", minimum=1e-6, section="Orbit",
                show_if={"key": "spec", "in": ["ae"]}),
            num("period", "Orbital period", 100.0, "min", minimum=1e-6,
                section="Orbit", show_if={"key": "spec", "in": ["period"]}),
            num("e", "Eccentricity", 0.0, minimum=0.0, maximum=0.999, section="Orbit",
                show_if={"key": "spec", "in": ["ae", "period"]}),
            toggle("j2_rates", "Include J\u2082 precession rates", True,
                   section="Orientation"),
            num("i", "Inclination", 51.6, "\u00b0", minimum=0.0, maximum=180.0,
                section="Orientation", show_if={"key": "j2_rates", "in": [True]}),
        ],
        "compute": _orbit,
    },
    {
        "id": "orbit-transfer",
        "name": "Orbit transfers",
        "category": CATEGORY,
        "summary": "Hohmann and bi-elliptic Δv, transfer time and combined plane changes.",
        "tags": ["Hohmann", "bi-elliptic", "delta-v", "plane change", "GTO"],
        "inputs": _body_fields() + [
            choice("spec", "Specify orbits by", [("alt", "Altitude"), ("r", "Radius")],
                   "alt", section="Orbits"),
            num("h1", "Initial altitude", 400.0, "km", section="Orbits",
                show_if={"key": "spec", "in": ["alt"]}),
            num("h2", "Final altitude", 35786.0, "km", section="Orbits",
                show_if={"key": "spec", "in": ["alt"]}),
            num("r1", "Initial radius", 6778.0, "km", minimum=1e-6, section="Orbits",
                show_if={"key": "spec", "in": ["r"]}),
            num("r2", "Final radius", 42164.0, "km", minimum=1e-6, section="Orbits",
                show_if={"key": "spec", "in": ["r"]}),
            num("plane_change", "Plane change at arrival", 0.0, "\u00b0",
                minimum=0.0, maximum=180.0, section="Plane change",
                help="Set to 0 for a coplanar transfer."),
            toggle("bielliptic", "Compare a bi-elliptic transfer", False,
                   section="Bi-elliptic"),
            num("rb", "Intermediate apoapsis radius", 400000.0, "km", minimum=1e-6,
                section="Bi-elliptic", show_if={"key": "bielliptic", "in": [True]}),
        ],
        "compute": _transfer,
    },
    {
        "id": "kepler-propagation",
        "name": "Kepler propagation",
        "category": CATEGORY,
        "summary": "Solve Kepler's equation for position and speed at any time or anomaly.",
        "tags": ["Kepler equation", "true anomaly", "eccentric anomaly", "time of flight"],
        "inputs": _body_fields() + [
            num("a", "Semi-major axis", 26600.0, "km", minimum=1e-6, section="Orbit",
                help="Enter a positive value; hyperbolic orbits are handled "
                     "automatically when e > 1."),
            num("e", "Eccentricity", 0.74, minimum=0.0, maximum=5.0, section="Orbit"),
            choice("known", "Solve from", [("time", "Time since periapsis"),
                                           ("nu", "True anomaly")], "time",
                   section="Point"),
            num("t", "Time since periapsis", 60.0, "min", section="Point",
                show_if={"key": "known", "in": ["time"]}),
            num("nu", "True anomaly", 120.0, "\u00b0", section="Point",
                show_if={"key": "known", "in": ["nu"]}),
        ],
        "compute": _kepler,
    },
    {
        "id": "rocket-equation",
        "name": "Rocket equation and staging",
        "category": CATEGORY,
        "summary": "Tsiolkovsky Δv for up to four stages with payload and mass fractions.",
        "tags": ["Tsiolkovsky", "delta-v", "staging", "mass ratio", "payload fraction"],
        "inputs": [
            integer("stages", "Number of stages", 2, minimum=1, maximum=4,
                    section="Vehicle"),
            num("payload", "Payload mass", 1000.0, "kg", minimum=0.0, section="Vehicle"),
            num("target_dv", "Mission \u0394v requirement", 9.4, "km/s", minimum=0.0,
                section="Vehicle", help="Set to 0 to skip the comparison."),
            num("isp1", "Stage 1 specific impulse", 300.0, "s", minimum=1.0,
                section="Stage 1"),
            num("mp1", "Stage 1 propellant mass", 40000.0, "kg", minimum=0.0,
                section="Stage 1"),
            num("ms1", "Stage 1 structural mass", 4000.0, "kg", minimum=0.0,
                section="Stage 1"),
            num("isp2", "Stage 2 specific impulse", 450.0, "s", minimum=1.0,
                section="Stage 2", show_if={"key": "stages", "in": [2, 3, 4]}),
            num("mp2", "Stage 2 propellant mass", 8000.0, "kg", minimum=0.0,
                section="Stage 2", show_if={"key": "stages", "in": [2, 3, 4]}),
            num("ms2", "Stage 2 structural mass", 1000.0, "kg", minimum=0.0,
                section="Stage 2", show_if={"key": "stages", "in": [2, 3, 4]}),
            num("isp3", "Stage 3 specific impulse", 450.0, "s", minimum=1.0,
                section="Stage 3", show_if={"key": "stages", "in": [3, 4]}),
            num("mp3", "Stage 3 propellant mass", 2000.0, "kg", minimum=0.0,
                section="Stage 3", show_if={"key": "stages", "in": [3, 4]}),
            num("ms3", "Stage 3 structural mass", 300.0, "kg", minimum=0.0,
                section="Stage 3", show_if={"key": "stages", "in": [3, 4]}),
            num("isp4", "Stage 4 specific impulse", 320.0, "s", minimum=1.0,
                section="Stage 4", show_if={"key": "stages", "in": [4]}),
            num("mp4", "Stage 4 propellant mass", 500.0, "kg", minimum=0.0,
                section="Stage 4", show_if={"key": "stages", "in": [4]}),
            num("ms4", "Stage 4 structural mass", 100.0, "kg", minimum=0.0,
                section="Stage 4", show_if={"key": "stages", "in": [4]}),
        ],
        "compute": _rocket_equation,
    },
    {
        "id": "groundtrack-coverage",
        "name": "Ground track, coverage and J₂",
        "category": CATEGORY,
        "summary": "Track drift, swath, access time, nodal regression and sun-synchronous orbits.",
        "tags": ["ground track", "sun-synchronous", "swath", "coverage", "revisit",
                 "nodal regression"],
        "inputs": _body_fields() + [
            num("h", "Altitude", 700.0, "km", minimum=1.0, section="Orbit"),
            num("e", "Eccentricity", 0.0, minimum=0.0, maximum=0.9, section="Orbit"),
            num("i", "Inclination", 98.2, "\u00b0", minimum=0.0, maximum=180.0,
                section="Orbit"),
            num("omega_body", "Body rotation rate", 1.0, "rev/day", minimum=0.0,
                section="Orbit", show_if={"key": "body", "in": ["custom", "moon",
                                                               "mars", "venus",
                                                               "jupiter", "sun"]}),
            num("eps_min", "Minimum elevation angle", 5.0, "\u00b0", minimum=0.0,
                maximum=89.0, section="Coverage"),
            toggle("repeat", "Look for a repeat ground track", True,
                   section="Coverage"),
        ],
        "compute": _groundtrack,
    },
    {
        "id": "escape-hyperbolic",
        "name": "Escape, C₃ and gravity assist",
        "category": CATEGORY,
        "summary": "Departure Δv from a parking orbit, hyperbolic geometry and flyby turning.",
        "tags": ["escape velocity", "C3", "hyperbolic excess", "Oberth", "gravity assist"],
        "inputs": _body_fields() + [
            num("h_park", "Parking orbit altitude", 200.0, "km", minimum=0.0,
                section="Departure"),
            choice("mode", "Specify the mission energy by",
                   [("c3", "Characteristic energy C\u2083"),
                    ("vinf", "Hyperbolic excess velocity")], "c3",
                   section="Departure"),
            num("C3", "Characteristic energy C\u2083", 12.0, "km\u00b2/s\u00b2",
                section="Departure", show_if={"key": "mode", "in": ["c3"]}),
            num("v_inf", "Hyperbolic excess velocity", 3.5, "km/s", minimum=0.0,
                section="Departure", show_if={"key": "mode", "in": ["vinf"]}),
            toggle("assist", "Analyse a gravity assist", False, section="Gravity assist"),
            num("r_flyby", "Flyby periapsis radius", 10000.0, "km", minimum=1.0,
                section="Gravity assist", show_if={"key": "assist", "in": [True]}),
            num("v_body", "Body's heliocentric velocity", 29.78, "km/s", minimum=0.0,
                section="Gravity assist", show_if={"key": "assist", "in": [True]}),
        ],
        "compute": _escape,
    },
]
