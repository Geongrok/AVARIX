"""Shared physical constants and models used across several modules.

The atmosphere is the full U.S. Standard Atmosphere 1976 geopotential model to
84.852 km' geopotential (86 km geometric), not the 11 km troposphere shortcut,
so the aerodynamics, performance and re-entry calculators all agree with each
other and with published tables.
"""

from __future__ import annotations

import math

from .core import CalculationError

# ---------------------------------------------------------------------------
# Constants (CODATA 2018 / U.S. Standard Atmosphere 1976 / IAU)
# ---------------------------------------------------------------------------

R_UNIVERSAL = 8.31446261815324      # J/(mol*K)
G0 = 9.80665                        # m/s^2, standard gravity
R_AIR = 287.05287                   # J/(kg*K), USSA-1976 dry air
GAMMA_AIR = 1.4
STEFAN_BOLTZMANN = 5.670374419e-8   # W/(m^2*K^4)
BOLTZMANN = 1.380649e-23            # J/K
C_LIGHT = 299792458.0               # m/s

# Sea-level standard
T0_SL = 288.15                      # K
P0_SL = 101325.0                    # Pa
RHO_SL = 1.2250                     # kg/m^3
A0_SL = 340.294                     # m/s
MU_SL = 1.7894e-5                   # Pa*s

# Sutherland's law for air
SUTH_MU0 = 1.716e-5
SUTH_T0 = 273.15
SUTH_S = 110.4

# Earth
R_EARTH = 6378.137e3                # m, WGS-84 equatorial radius
R_ATM = 6356766.0                   # m, effective Earth radius used by USSA-1976
MU_EARTH = 3.986004418e14           # m^3/s^2
J2_EARTH = 1.08262668e-3
OMEGA_EARTH = 7.2921150e-5          # rad/s
EARTH_SIDEREAL_DAY = 86164.0905     # s

BODIES = {
    "earth":   ("Earth",   3.986004418e14, 6378.137e3,   1.08262668e-3),
    "moon":    ("Moon",    4.9048695e12,   1737.4e3,     2.033e-4),
    "mars":    ("Mars",    4.282837e13,    3396.2e3,     1.96045e-3),
    "venus":   ("Venus",   3.24858592e14,  6051.8e3,     4.458e-6),
    "sun":     ("Sun",     1.32712440018e20, 695700e3,   0.0),
    "jupiter": ("Jupiter", 1.26686534e17,  71492e3,      1.4696e-2),
}

# ---------------------------------------------------------------------------
# U.S. Standard Atmosphere 1976
# ---------------------------------------------------------------------------

# (base geopotential altitude [m], lapse rate [K/m], base temperature [K])
_LAYERS = [
    (0.0,      -0.0065, 288.15),
    (11000.0,   0.0,    216.65),
    (20000.0,   0.0010, 216.65),
    (32000.0,   0.0028, 228.65),
    (47000.0,   0.0,    270.65),
    (51000.0,  -0.0028, 270.65),
    (71000.0,  -0.0020, 214.65),
    (84852.0,   0.0,    186.946),
]


def _base_pressures():
    """Pressure at the foot of each layer, integrated from sea level."""
    p = [P0_SL]
    for i in range(len(_LAYERS) - 1):
        h0, lam, t0 = _LAYERS[i]
        h1 = _LAYERS[i + 1][0]
        if lam == 0.0:
            p.append(p[i] * math.exp(-G0 * (h1 - h0) / (R_AIR * t0)))
        else:
            t1 = t0 + lam * (h1 - h0)
            p.append(p[i] * (t1 / t0) ** (-G0 / (R_AIR * lam)))
    return p


_PB = _base_pressures()


def geopotential(z: float) -> float:
    """Geometric altitude z [m] -> geopotential altitude H [m].

    Uses the USSA-1976 effective Earth radius, not the equatorial radius, so
    the layer boundaries fall exactly where the published tables put them.
    """
    return R_ATM * z / (R_ATM + z)


def geometric(h: float) -> float:
    """Geopotential altitude H [m] -> geometric altitude z [m]."""
    return R_ATM * h / (R_ATM - h)


def atmosphere(z: float, *, dT: float = 0.0) -> dict:
    """U.S. Standard Atmosphere 1976 properties at geometric altitude z [m].

    ``dT`` offsets the temperature (ISA+dT) while leaving the pressure profile
    at its standard value, which is the convention used for performance work.
    """
    if z < -5000 or z > 86000:
        raise CalculationError(
            "Altitude must be between -5000 m and 86 000 m for the "
            "U.S. Standard Atmosphere 1976 model.")

    h = geopotential(z)
    i = 0
    for k in range(len(_LAYERS)):
        if h >= _LAYERS[k][0]:
            i = k
        else:
            break
    h0, lam, t0 = _LAYERS[i]

    if lam == 0.0:
        t = t0
        p = _PB[i] * math.exp(-G0 * (h - h0) / (R_AIR * t0))
    else:
        t = t0 + lam * (h - h0)
        p = _PB[i] * (t / t0) ** (-G0 / (R_AIR * lam))

    t_std = t
    t = t + dT
    rho = p / (R_AIR * t)
    a = math.sqrt(GAMMA_AIR * R_AIR * t)
    mu = sutherland(t)
    return {
        "z": z, "h": h, "T": t, "T_std": t_std, "p": p, "rho": rho,
        "a": a, "mu": mu, "nu": mu / rho,
        "theta": t / T0_SL, "delta": p / P0_SL, "sigma": rho / RHO_SL,
        "g": G0 * (R_ATM / (R_ATM + z)) ** 2,
    }


def pressure_altitude(p: float) -> float:
    """Invert the standard atmosphere: pressure [Pa] -> geometric altitude [m]."""
    from .numeric import solve
    if p <= 0:
        raise CalculationError("Pressure must be positive.")
    p_top = atmosphere(86000.0)["p"]
    if p < p_top:
        raise CalculationError("Pressure is below the 86 km limit of the model.")
    return solve(lambda z: atmosphere(z)["p"] - p, -5000.0, 86000.0,
                 what="pressure altitude")


def sutherland(T: float) -> float:
    """Dynamic viscosity of air [Pa*s] from Sutherland's law."""
    return SUTH_MU0 * (T / SUTH_T0) ** 1.5 * (SUTH_T0 + SUTH_S) / (T + SUTH_S)


def air_conductivity(T: float) -> float:
    """Thermal conductivity of air [W/(m*K)], Sutherland-type fit."""
    return 2.646e-3 * T ** 1.5 / (T + 245.4 * 10 ** (-12.0 / T))


# ---------------------------------------------------------------------------
# Working-gas presets
# ---------------------------------------------------------------------------

GASES = {
    # key: (label, gamma, R [J/kg/K])
    "air":     ("Air", 1.4, 287.05287),
    "air_hot": ("Air, hot section (1000 K)", 1.33, 287.05287),
    "n2":      ("Nitrogen N2", 1.40, 296.80),
    "o2":      ("Oxygen O2", 1.395, 259.84),
    "co2":     ("Carbon dioxide CO2", 1.289, 188.92),
    "he":      ("Helium He", 1.667, 2077.1),
    "ar":      ("Argon Ar", 1.667, 208.13),
    "h2":      ("Hydrogen H2", 1.405, 4124.2),
    "ch4":     ("Methane CH4", 1.32, 518.28),
    "steam":   ("Steam H2O", 1.33, 461.52),
    "exhaust": ("Rocket exhaust (typical)", 1.20, 355.0),
}

GAS_OPTIONS = [(k, v[0]) for k, v in GASES.items()] + [("custom", "Custom \u03b3 and R")]


def gas_properties(inp: dict, prefix: str = "") -> tuple[float, float, str]:
    """Resolve a gas selector plus custom overrides into (gamma, R, label)."""
    key = inp.get(prefix + "gas", "air")
    if key == "custom":
        g = float(inp.get(prefix + "gamma", 1.4))
        r = float(inp.get(prefix + "R", 287.05287))
        if g <= 1.0:
            raise CalculationError("Specific heat ratio \u03b3 must be greater than 1.")
        if r <= 0:
            raise CalculationError("Gas constant R must be positive.")
        return g, r, "Custom gas"
    label, g, r = GASES[key]
    return g, r, label


def cp_from(gamma: float, R: float) -> float:
    return gamma * R / (gamma - 1.0)


def cv_from(gamma: float, R: float) -> float:
    return R / (gamma - 1.0)
