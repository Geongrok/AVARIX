"""Avionics and electronics: communications, radar, noise, control and filters."""

from __future__ import annotations

import math

from .. import plotting as P
from ..core import CalculationError, Result, choice, integer, num, toggle
from ..numeric import linspace, logspace, solve
from ..physics import BOLTZMANN, C_LIGHT

CATEGORY = "Avionics & Electronics"

K_DB = 10 * math.log10(BOLTZMANN)      # -228.599 dBW/(K*Hz)


def _db(x):
    if x <= 0:
        raise CalculationError("Cannot take the logarithm of a non-positive quantity.")
    return 10 * math.log10(x)


# ---------------------------------------------------------------------------
# 1. Communications link budget
# ---------------------------------------------------------------------------


def _link_budget(inp):
    f = inp["freq"] * 1e9
    lam = C_LIGHT / f
    d = inp["range"] * 1000

    Pt_dbw = _db(inp["Pt"]) if inp["power_unit"] == "W" else inp["Pt"] - 30

    if inp["tx_spec"] == "gain":
        Gt = inp["Gt"]
        Dt = math.sqrt(10 ** (Gt / 10) / inp["eta_t"]) * lam / math.pi
    else:
        Dt = inp["Dt"]
        Gt = _db(inp["eta_t"] * (math.pi * Dt / lam) ** 2)

    if inp["rx_spec"] == "gain":
        Gr = inp["Gr"]
        Dr = math.sqrt(10 ** (Gr / 10) / inp["eta_r"]) * lam / math.pi
    else:
        Dr = inp["Dr"]
        Gr = _db(inp["eta_r"] * (math.pi * Dr / lam) ** 2)

    EIRP = Pt_dbw + Gt - inp["L_tx"]
    FSPL = 20 * math.log10(4 * math.pi * d / lam)
    L_other = inp["L_atm"] + inp["L_rain"] + inp["L_point"] + inp["L_pol"]

    Ts = inp["Ts"]
    G_T = Gr - _db(Ts)
    Pr = EIRP - FSPL - L_other + Gr - inp["L_rx"]
    N0 = K_DB + _db(Ts)
    C_N0 = Pr - N0
    Rb = inp["Rb"] * 1e6
    Eb_N0 = C_N0 - _db(Rb)
    B = inp["B"] * 1e6
    N = N0 + _db(B)
    SNR = Pr - N
    margin = Eb_N0 - inp["Eb_N0_req"] - inp["L_impl"]

    r = Result()
    r.group("Link", f"{inp['freq']:g} GHz, {inp['range']:g} km")
    r.out("Wavelength", lam * 100, "cm", symbol="\u03bb")
    r.out("Transmit power", Pt_dbw, "dBW", symbol="P_t")
    r.out("Transmit power", 10 ** (Pt_dbw / 10), "W")
    r.out("Transmit antenna gain", Gt, "dBi", symbol="G_t")
    r.out("Transmit antenna diameter", Dt, "m")
    r.headline("EIRP", EIRP, "dBW")
    r.out("Receive antenna gain", Gr, "dBi", symbol="G_r")
    r.out("Receive antenna diameter", Dr, "m")
    r.headline("Free space path loss", FSPL, "dB", symbol="L_fs")
    r.out("Other losses", L_other, "dB",
          note="atmosphere, rain, pointing and polarisation combined")

    r.group("Received signal")
    r.headline("Received power", Pr, "dBW", symbol="P_r")
    r.out("Received power", 10 ** (Pr / 10) * 1e12, "pW")
    r.out("System noise temperature", Ts, "K", symbol="T_s")
    r.headline("Figure of merit G/T", G_T, "dB/K")
    r.out("Noise power spectral density", N0, "dBW/Hz", symbol="N\u2080")
    r.out("Noise power in the bandwidth", N, "dBW")
    r.headline("Carrier to noise density", C_N0, "dB\u00b7Hz", symbol="C/N\u2080")
    r.out("Signal to noise ratio", SNR, "dB", symbol="SNR")
    r.out("Signal to noise ratio", 10 ** (SNR / 10), "\u00d7", note="linear")

    r.group("Data link", f"{inp['Rb']:g} Mbit/s in {inp['B']:g} MHz")
    r.headline("Energy per bit to noise density", Eb_N0, "dB", symbol="E_b/N\u2080")
    r.out("Required E_b/N\u2080", inp["Eb_N0_req"], "dB")
    r.out("Implementation loss", inp["L_impl"], "dB")
    r.headline("Link margin", margin, "dB")
    r.out("Verdict",
          "the link closes" if margin > 0 else "the link does not close",
          note="3 dB is a common minimum design margin")
    r.out("Spectral efficiency", Rb / B, "bit/s/Hz")
    shannon = B * math.log2(1 + 10 ** (SNR / 10))
    r.out("Shannon capacity", shannon / 1e6, "Mbit/s",
          note="the theoretical ceiling for this bandwidth and SNR")
    r.out("Fraction of the Shannon limit used", Rb / shannon * 100, "%")
    r.out("Maximum range at zero margin",
          d * 10 ** (margin / 20) / 1000, "km",
          note="path loss scales with the square of range")

    r.table("Link budget",
            ["Item", "Value [dB]"],
            [["Transmit power [dBW]", Pt_dbw],
             ["Transmit line loss", -inp["L_tx"]],
             ["Transmit antenna gain", Gt],
             ["EIRP [dBW]", EIRP],
             ["Free space path loss", -FSPL],
             ["Atmospheric loss", -inp["L_atm"]],
             ["Rain loss", -inp["L_rain"]],
             ["Pointing loss", -inp["L_point"]],
             ["Polarisation loss", -inp["L_pol"]],
             ["Receive antenna gain", Gr],
             ["Receive line loss", -inp["L_rx"]],
             ["Received power [dBW]", Pr],
             ["Noise density [dBW/Hz]", -N0],
             ["C/N\u2080 [dB\u00b7Hz]", C_N0],
             ["Data rate [dB\u00b7Hz]", -_db(Rb)],
             ["E_b/N\u2080 [dB]", Eb_N0],
             ["Required E_b/N\u2080", -inp["Eb_N0_req"]],
             ["Implementation loss", -inp["L_impl"]],
             ["Margin [dB]", margin]],
            sig=4,
            caption="Each row adds to the running total, which is why link budgets "
                    "are done in decibels.")

    ranges = logspace(max(d / 1000 / 100, 1), d / 1000 * 20, 300)
    r.plot(**P.chart(
        [{"x": ranges,
          "y": [EIRP - 20 * math.log10(4 * math.pi * x * 1000 / lam) - L_other
                + Gr - inp["L_rx"] - N0 - _db(Rb) - inp["Eb_N0_req"] - inp["L_impl"]
                for x in ranges], "label": "link margin"}],
        xlabel="Range  [km]", ylabel="Margin  [dB]", xlog=True,
        title="Link margin against range",
        hlines=[{"value": 0.0, "label": "link closes above this", "color": "#B3242B"},
                {"value": 3.0, "label": "3 dB design margin"}],
        points=[{"x": d / 1000, "y": margin, "label": "your link"}],
        caption="Margin falls 6 dB for every doubling of range \u2014 the inverse "
                "square law written in decibels."))

    freqs = linspace(0.5, 40, 300)
    r.plot(**P.chart(
        [{"x": freqs, "y": [20 * math.log10(4 * math.pi * d * x * 1e9 / C_LIGHT)
                            for x in freqs], "label": "path loss"},
         {"x": freqs, "y": [_db(inp["eta_t"] * (math.pi * Dt * x * 1e9 / C_LIGHT) ** 2)
                            + _db(inp["eta_r"] * (math.pi * Dr * x * 1e9 / C_LIGHT) ** 2)
                            for x in freqs], "label": "combined antenna gain",
          "color": P.SERIES[2]}],
        xlabel="Frequency  [GHz]", ylabel="Decibels",
        title="Why higher frequencies still win",
        vlines=[{"value": inp["freq"], "label": "your frequency"}],
        caption="Path loss rises with frequency, but fixed-diameter antenna gain "
                "rises faster \u2014 twice as fast, in fact, since two antennas both "
                "gain."))
    return r


# ---------------------------------------------------------------------------
# 2. Radar range equation
# ---------------------------------------------------------------------------


def _radar(inp):
    f = inp["freq"] * 1e9
    lam = C_LIGHT / f
    Pt = inp["Pt"] * 1000 if inp["peak_unit"] == "kW" else inp["Pt"]
    G = 10 ** (inp["G"] / 10)
    sigma = inp["sigma"]
    B = inp["B"] * 1e6
    Ts = inp["Ts"]
    L = 10 ** (inp["L"] / 10)
    F = 10 ** (inp["F"] / 10)
    snr_min = 10 ** (inp["snr_min"] / 10)

    n_pulses = inp["n_pulses"] if inp["integrate"] else 1
    gain_int = n_pulses if inp["coherent"] else math.sqrt(n_pulses)

    num = Pt * G ** 2 * lam ** 2 * sigma * gain_int
    den = (4 * math.pi) ** 3 * BOLTZMANN * Ts * B * F * L * snr_min
    R_max = (num / den) ** 0.25

    R = inp["R"] * 1000
    Pr = Pt * G ** 2 * lam ** 2 * sigma / ((4 * math.pi) ** 3 * R ** 4 * L)
    N = BOLTZMANN * Ts * B * F
    snr = Pr / N * gain_int

    PRF = inp["PRF"]
    R_unamb = C_LIGHT / (2 * PRF)
    tau = inp["tau"] * 1e-6
    dR = C_LIGHT * tau / 2 if not inp["compress"] else C_LIGHT / (2 * B)
    duty = tau * PRF
    P_avg = Pt * duty
    v = inp["v"]
    fd = 2 * v / lam
    v_unamb = lam * PRF / 4

    r = Result()
    r.group("Radar", f"{inp['freq']:g} GHz, {inp['G']:g} dBi antenna")
    r.out("Wavelength", lam * 100, "cm", symbol="\u03bb")
    r.out("Peak transmit power", Pt / 1000, "kW")
    r.out("Average transmit power", P_avg, "W")
    r.out("Duty cycle", duty * 100, "%")
    r.out("Target radar cross-section", sigma, "m\u00b2", symbol="\u03c3")
    r.out("Radar cross-section", _db(sigma), "dBsm")

    r.group("Detection")
    r.headline("Maximum detection range", R_max / 1000, "km", symbol="R_max")
    r.headline("SNR at the stated range", _db(snr), "dB",
               note=f"at {inp['R']:g} km")
    r.out("Received power at the stated range", _db(Pr), "dBW")
    r.out("Received power", Pr * 1e15, "fW")
    r.out("Noise power", _db(N), "dBW")
    r.out("Detection threshold", inp["snr_min"], "dB")
    r.out("Detectable?", "yes" if snr >= snr_min else "no")
    if inp["integrate"]:
        r.out("Integration gain", _db(gain_int), "dB",
              note=("coherent integration gains 10 log n"
                    if inp["coherent"] else "non-coherent integration gains 5 log n"))
        r.out("Range improvement from integration", gain_int ** 0.25,
              note="range only improves with the fourth root")
    r.out("Range for a 10 dB SNR",
          R * (snr / 10) ** 0.25 / 1000, "km")

    r.group("Resolution and ambiguity", f"PRF {PRF:g} Hz, pulse {inp['tau']:g} \u03bcs")
    r.headline("Range resolution", dR, "m", symbol="\u0394R",
               note="pulse compression assumed" if inp["compress"] else
                    "uncompressed pulse")
    r.out("Unambiguous range", R_unamb / 1000, "km", symbol="R_u")
    r.out("Pulse repetition interval", 1 / PRF * 1e6, "\u03bcs")
    r.out("Time-bandwidth product", tau * B,
          note="the compression ratio available")
    r.out("Doppler shift of the target", fd, "Hz", symbol="f_d")
    r.out("Doppler shift", fd / 1000, "kHz")
    r.out("Unambiguous velocity", v_unamb, "m/s", symbol="v_u")
    r.out("Velocity ambiguity?", "yes" if abs(v) > v_unamb else "no")
    r.out("Range ambiguity?", "yes" if R > R_unamb else "no")
    r.out("Product of unambiguous range and velocity",
          R_unamb * v_unamb / 1e6, "\u00d710\u2076 m\u00b2/s",
          note="c\u03bb/8 \u2014 a fixed limit, so range and velocity ambiguity "
               "trade directly against each other")

    if inp["beamwidth"] > 0:
        theta = math.radians(inp["beamwidth"])
        r.out("Cross-range resolution at the stated range", R * theta, "m")
        r.out("Time on target for a scanning radar",
              theta / math.radians(inp["scan_rate"]) if inp["scan_rate"] > 0
              else float("inf"), "s")
        r.out("Pulses on target",
              theta / math.radians(inp["scan_rate"]) * PRF if inp["scan_rate"] > 0
              else float("inf"))

    rs = linspace(max(R_max / 200, 100), R_max * 2.2, 400)
    r.plot(**P.chart(
        [{"x": [x / 1000 for x in rs],
          "y": [_db(Pt * G ** 2 * lam ** 2 * sigma * gain_int
                    / ((4 * math.pi) ** 3 * x ** 4 * L) / N) for x in rs],
          "label": "SNR"}],
        xlabel="Range  [km]", ylabel="Signal to noise ratio  [dB]",
        title="Radar SNR against range",
        hlines=[{"value": inp["snr_min"], "label": "detection threshold",
                 "color": "#B3242B"}],
        vlines=[{"value": R_max / 1000, "label": "maximum range"}],
        points=[{"x": R / 1000, "y": _db(snr), "label": "your target"}],
        caption="SNR falls as the fourth power of range, 12 dB per doubling. "
                "Doubling the detection range needs sixteen times the power."))

    sigmas = logspace(0.001, 1000, 300)
    r.plot(**P.chart(
        [{"x": sigmas, "y": [(Pt * G ** 2 * lam ** 2 * s * gain_int / den * snr_min
                              / snr_min) ** 0.25 / 1000 for s in sigmas],
          "label": "detection range"}],
        xlabel="Radar cross-section  \u03c3  [m\u00b2]",
        ylabel="Maximum detection range  [km]", xlog=True,
        title="Detection range against target size",
        points=[{"x": sigma, "y": R_max / 1000, "label": "your target"}],
        annotations=[{"x": 0.01, "y": R_max * 0.35 / 1000, "text": "stealth aircraft"},
                     {"x": 5, "y": R_max * 0.35 / 1000, "text": "fighter"},
                     {"x": 100, "y": R_max * 0.35 / 1000, "text": "airliner"}],
        caption="Range goes as the fourth root of cross-section, so a hundredfold "
                "reduction in RCS only cuts detection range by a factor of about "
                "three."))
    return r


# ---------------------------------------------------------------------------
# 3. Antenna fundamentals
# ---------------------------------------------------------------------------


def _antenna(inp):
    f = inp["freq"] * 1e9
    lam = C_LIGHT / f
    kind = inp["kind"]
    eta = inp["eta"]

    if kind == "dish":
        D = inp["D"]
        A_phys = math.pi * D ** 2 / 4
        G = eta * (math.pi * D / lam) ** 2
        hpbw = 70 * lam / D
        far_field = 2 * D ** 2 / lam
        size_label = f"\u00f8{D:g} m dish"
    elif kind == "aperture":
        a, b = inp["a"], inp["b"]
        A_phys = a * b
        G = eta * 4 * math.pi * A_phys / lam ** 2
        hpbw = 51 * lam / a
        far_field = 2 * max(a, b) ** 2 / lam
        D = math.sqrt(4 * A_phys / math.pi)
        size_label = f"{a:g}\u00d7{b:g} m aperture"
    else:  # array
        n_el = inp["n_el"]
        d_sp = inp["d_spacing"] * lam
        L_arr = n_el * d_sp
        A_phys = L_arr ** 2
        G = eta * 4 * math.pi * A_phys / lam ** 2
        hpbw = 51 * lam / L_arr
        far_field = 2 * L_arr ** 2 / lam
        D = L_arr
        size_label = f"{n_el:g}-element array, {L_arr:.3g} m aperture"

    G_db = _db(G)
    A_eff = G * lam ** 2 / (4 * math.pi)
    omega_beam = 4 * math.pi / G
    fnbw = 2.4 * hpbw

    r = Result()
    r.group("Antenna", f"{size_label} at {inp['freq']:g} GHz")
    r.out("Wavelength", lam * 100, "cm", symbol="\u03bb")
    r.out("Aperture in wavelengths", D / lam, symbol="D/\u03bb")
    r.headline("Gain", G_db, "dBi", symbol="G")
    r.out("Gain", G, "\u00d7", note="linear")
    r.headline("Half-power beamwidth", hpbw, "\u00b0", symbol="\u03b8_3dB")
    r.out("First-null beamwidth", fnbw, "\u00b0")
    r.out("Physical aperture area", A_phys, "m\u00b2", symbol="A")
    r.out("Effective aperture", A_eff, "m\u00b2", symbol="A_e")
    r.out("Aperture efficiency", eta * 100, "%", symbol="\u03b7")
    r.out("Beam solid angle", omega_beam, "sr", symbol="\u03a9_A")
    r.out("Far-field distance", far_field, "m", symbol="2D\u00b2/\u03bb",
          note="measurements closer than this are in the near field")
    r.out("Rayleigh distance in wavelengths", far_field / lam)

    r.group("Pointing and coverage")
    r.out("Pointing loss at 0.1\u00b0 error",
          12 * (0.1 / hpbw) ** 2, "dB",
          note="loss grows with the square of the pointing error")
    r.out("Pointing error for 1 dB loss", hpbw * math.sqrt(1 / 12), "\u00b0")
    r.out("Pointing error for 3 dB loss", hpbw / 2, "\u00b0")
    if inp["range"] > 0:
        d = inp["range"] * 1000
        r.out("Beam footprint diameter at range", 2 * d * math.tan(math.radians(hpbw / 2)) / 1000,
              "km")
        r.out("Footprint area", math.pi * (d * math.tan(math.radians(hpbw / 2))) ** 2 / 1e6,
              "km\u00b2")

    if inp["surface_rms"] > 0:
        eps_rms = inp["surface_rms"] / 1000
        ruze = math.exp(-(4 * math.pi * eps_rms / lam) ** 2)
        r.group("Surface accuracy", f"RMS error {inp['surface_rms']:g} mm")
        r.out("Ruze gain loss", -_db(ruze), "dB")
        r.out("Effective gain after surface losses", G_db + _db(ruze), "dBi")
        r.out("Surface error in wavelengths", eps_rms / lam)
        r.out("RMS error for 1 dB loss",
              lam / (4 * math.pi) * math.sqrt(math.log(10 ** 0.1)) * 1000, "mm",
              note="the practical limit on how high in frequency a dish can work")

    ths = linspace(-fnbw * 1.6, fnbw * 1.6, 601)
    pattern = []
    for th in ths:
        if abs(th) < 1e-9:
            pattern.append(0.0)
            continue
        u = math.pi * D / lam * math.sin(math.radians(th))
        val = (2 * _bessel_j1(u) / u) ** 2 if abs(u) > 1e-9 else 1.0
        pattern.append(max(_db(val) if val > 1e-9 else -90.0, -50.0))
    r.plot(**P.chart(
        [{"x": ths, "y": pattern, "label": "radiation pattern"}],
        xlabel="Angle from boresight  [\u00b0]", ylabel="Relative gain  [dB]",
        title="Antenna pattern (uniform circular aperture)",
        ylim=(-45, 3),
        hlines=[{"value": -3.0, "label": "half power"},
                {"value": -17.6, "label": "first sidelobe", "color": P.SERIES[1]}],
        caption="A uniformly illuminated aperture gives the highest gain but a "
                "first sidelobe only 17.6 dB down; tapering the illumination trades "
                "gain for lower sidelobes."))

    freqs = linspace(0.5, 40, 300)
    r.plot(**P.chart(
        [{"x": freqs, "y": [_db(eta * (math.pi * D * x * 1e9 / C_LIGHT) ** 2)
                            for x in freqs], "label": "gain"},
         {"x": freqs, "y": [70 * (C_LIGHT / (x * 1e9)) / D for x in freqs],
          "label": "beamwidth [\u00b0]", "color": P.SERIES[1]}],
        xlabel="Frequency  [GHz]", ylabel="dBi  /  degrees",
        title="Gain and beamwidth against frequency for a fixed aperture",
        vlines=[{"value": inp["freq"], "label": "your frequency"}],
        caption="Gain rises with the square of frequency while the beam narrows in "
                "proportion \u2014 more gain always means harder pointing."))
    return r


def _bessel_j1(x):
    """First-order Bessel function, ample precision for pattern plotting."""
    ax = abs(x)
    if ax < 8.0:
        y = x * x
        p1 = x * (72362614232.0 + y * (-7895059235.0 + y * (242396853.1
             + y * (-2972611.439 + y * (15704.48260 + y * (-30.16036606))))))
        p2 = (144725228442.0 + y * (2300535178.0 + y * (18583304.74
              + y * (99447.43394 + y * (376.9991397 + y)))))
        return p1 / p2
    z = 8.0 / ax
    y = z * z
    xx = ax - 2.356194491
    p1 = (1.0 + y * (0.183105e-2 + y * (-0.3516396496e-4
          + y * (0.2457520174e-5 + y * (-0.240337019e-6)))))
    p2 = (0.04687499995 + y * (-0.2002690873e-3 + y * (0.8449199096e-5
          + y * (-0.88228987e-6 + y * 0.105787412e-6))))
    ans = math.sqrt(0.636619772 / ax) * (math.cos(xx) * p1 - z * math.sin(xx) * p2)
    return ans if x >= 0 else -ans


# ---------------------------------------------------------------------------
# 4. Noise cascade and ADC
# ---------------------------------------------------------------------------


def _noise(inp):
    T0 = 290.0
    n = int(inp["n_stages"])
    stages = []
    for i in range(1, n + 1):
        stages.append((inp[f"g{i}"], inp[f"nf{i}"]))

    F_total = 0.0
    G_cum = 1.0
    rows = []
    for i, (g_db, nf_db) in enumerate(stages, start=1):
        g = 10 ** (g_db / 10)
        F = 10 ** (nf_db / 10)
        contrib = (F - 1) / G_cum if i > 1 else F
        F_total += contrib
        rows.append([f"{i}", g_db, nf_db, _db(G_cum), (F - 1) * T0,
                     contrib, _db(F_total)])
        G_cum *= g

    Te = (F_total - 1) * T0
    NF = _db(F_total)
    G_total = _db(G_cum)
    T_ant = inp["T_ant"]
    Ts = T_ant + Te

    r = Result()
    r.group("Cascade", f"{n} stage{'s' if n > 1 else ''}")
    r.headline("Total noise figure", NF, "dB", symbol="NF")
    r.headline("Equivalent noise temperature", Te, "K", symbol="T_e")
    r.out("Total gain", G_total, "dB")
    r.out("Noise factor", F_total, symbol="F", note="linear")
    r.out("Antenna noise temperature", T_ant, "K", symbol="T_a")
    r.headline("System noise temperature", Ts, "K", symbol="T_s = T_a + T_e")
    r.out("Noise power density", K_DB + _db(Ts), "dBW/Hz")
    r.out("First stage contribution to the total",
          (10 ** (stages[0][1] / 10)) / F_total * 100, "%",
          note="Friis: the first amplifier dominates, which is why low-noise "
               "amplifiers go first")

    r.table("Stage contributions",
            ["Stage", "Gain [dB]", "NF [dB]", "Preceding gain [dB]",
             "T_e [K]", "Contribution to F", "Cumulative NF [dB]"],
            rows, sig=5,
            caption="Each stage's noise is divided by all the gain ahead of it.")

    if inp["adc"]:
        bits = int(inp["bits"])
        fs = inp["fs"] * 1e6
        vref = inp["vref"]
        B_sig = inp["B_sig"] * 1e6
        snr_ideal = 6.02 * bits + 1.76
        lsb = vref / 2 ** bits
        q_noise = lsb / math.sqrt(12)
        enob = (inp["snr_actual"] - 1.76) / 6.02 if inp["snr_actual"] > 0 else bits
        proc_gain = _db(fs / (2 * B_sig)) if B_sig > 0 else 0.0
        r.group("Analogue to digital conversion", f"{bits}-bit at {inp['fs']:g} MSPS")
        r.headline("Ideal SNR", snr_ideal, "dB", symbol="SNR")
        r.out("LSB size", lsb * 1e6, "\u03bcV")
        r.out("RMS quantisation noise", q_noise * 1e6, "\u03bcV")
        r.out("Dynamic range", _db(2 ** (2 * bits)), "dB")
        r.out("Nyquist frequency", fs / 2e6, "MHz")
        r.out("Processing gain from oversampling", proc_gain, "dB",
              note="halving the signal bandwidth buys 3 dB")
        r.out("Effective SNR in the signal band", snr_ideal + proc_gain, "dB")
        if inp["snr_actual"] > 0:
            r.out("Effective number of bits", enob, "bits",
                  note="from the measured SNR")
            r.out("Bits lost to real-world effects", bits - enob)
        r.out("Aperture jitter for a full-scale sine at Nyquist",
              1 / (2 * math.pi * fs / 2 * 10 ** (snr_ideal / 20)) * 1e12, "ps",
              note="the clock purity needed to not degrade the converter")

        bs = list(range(6, 25))
        r.plot(**P.chart(
            [{"x": bs, "y": [6.02 * b + 1.76 for b in bs], "label": "ideal SNR"}],
            xlabel="Resolution  [bits]", ylabel="SNR  [dB]",
            title="Converter SNR against resolution",
            points=[{"x": bits, "y": snr_ideal, "label": "your converter"}],
            caption="Every extra bit is worth 6.02 dB \u2014 the origin of the "
                    "rule of thumb that one bit equals one factor of two in "
                    "amplitude resolution."))

    nfs = linspace(0.2, 10, 300)
    g1 = 10 ** (stages[0][0] / 10)
    rest = F_total - 10 ** (stages[0][1] / 10)
    r.plot(**P.chart(
        [{"x": nfs, "y": [_db(10 ** (x / 10) + rest) for x in nfs],
          "label": f"{stages[0][0]:g} dB first-stage gain"},
         {"x": nfs, "y": [_db(10 ** (x / 10) + rest * g1 / 10 ** 2) for x in nfs],
          "label": "with 20 dB first-stage gain", "color": P.SERIES[1]}],
        xlabel="First stage noise figure  [dB]", ylabel="System noise figure  [dB]",
        title="Sensitivity to the first amplifier",
        points=[{"x": stages[0][1], "y": NF, "label": "your cascade"}],
        caption="The system noise figure tracks the first stage almost exactly "
                "once there is enough gain ahead of everything else."))
    return r


# ---------------------------------------------------------------------------
# 5. Second-order control response
# ---------------------------------------------------------------------------


def _control(inp):
    if inp["spec"] == "params":
        wn = inp["wn"]
        zeta = inp["zeta"]
    else:
        Mp = inp["Mp"] / 100
        ts = inp["ts"]
        if not 0 < Mp < 1:
            raise CalculationError("Overshoot must be between 0 and 100 %.")
        lnMp = math.log(Mp)
        zeta = -lnMp / math.sqrt(math.pi ** 2 + lnMp ** 2)
        wn = 4 / (zeta * ts)

    if wn <= 0:
        raise CalculationError("The natural frequency must be positive.")
    if zeta < 0:
        raise CalculationError(
            "A negative damping ratio describes an unstable system, whose step "
            "response grows without bound.")

    r = Result()
    r.group("System", "G(s) = \u03c9\u2099\u00b2 / (s\u00b2 + 2\u03b6\u03c9\u2099s + \u03c9\u2099\u00b2)")
    r.headline("Natural frequency", wn, "rad/s", symbol="\u03c9\u2099")
    r.out("Natural frequency", wn / (2 * math.pi), "Hz")
    r.headline("Damping ratio", zeta, symbol="\u03b6")
    r.out("Damping classification",
          "undamped" if zeta == 0 else
          ("underdamped" if zeta < 1 else
           ("critically damped" if abs(zeta - 1) < 1e-9 else "overdamped")))

    if zeta < 1:
        wd = wn * math.sqrt(1 - zeta ** 2)
        Mp = math.exp(-math.pi * zeta / math.sqrt(1 - zeta ** 2))
        tp = math.pi / wd
        tr = (math.pi - math.acos(zeta)) / wd
        r.out("Damped natural frequency", wd, "rad/s", symbol="\u03c9_d")
        r.headline("Overshoot", Mp * 100, "%", symbol="M_p")
        r.out("Time to peak", tp, "s", symbol="t_p")
        r.out("Rise time (0 to 100 %)", tr, "s", symbol="t_r")
        r.out("Number of oscillations before settling",
              wd / (2 * math.pi) * (4 / (zeta * wn)))
        r.out("Poles", f"\u2212{zeta * wn:.5g} \u00b1 {wd:.5g}j")
        r.out("Logarithmic decrement",
              2 * math.pi * zeta / math.sqrt(1 - zeta ** 2))
    else:
        r.out("Overshoot", 0.0, "%", note="no overshoot at or above critical damping")
        s1 = -zeta * wn + wn * math.sqrt(zeta ** 2 - 1)
        s2 = -zeta * wn - wn * math.sqrt(zeta ** 2 - 1)
        r.out("Poles", f"{s1:.5g}, {s2:.5g}")
        r.out("Dominant time constant", -1 / s1 if s1 else float("inf"), "s")

    ts2 = 4 / (zeta * wn) if zeta > 0 else float("inf")
    r.headline("Settling time (2 %)", ts2, "s", symbol="t_s")
    r.out("Settling time (5 %)", 3 / (zeta * wn) if zeta > 0 else float("inf"), "s")
    r.out("Approximate rise time (10 to 90 %)", 1.8 / wn, "s")
    r.out("Bandwidth",
          wn * math.sqrt(1 - 2 * zeta ** 2
                         + math.sqrt(4 * zeta ** 4 - 4 * zeta ** 2 + 2)), "rad/s",
          symbol="\u03c9_B")
    r.out("Resonant peak",
          1 / (2 * zeta * math.sqrt(1 - zeta ** 2)) if zeta < 0.707 else 1.0,
          symbol="M_r", note="no resonant peak above \u03b6 = 0.707")
    r.out("Phase margin estimate", 100 * zeta, "\u00b0",
          note="the rule of thumb \u03d5_m \u2248 100\u03b6, good to \u03b6 \u2248 0.6")

    if inp["damping_advice"]:
        r.group("Design guidance")
        r.out("\u03b6 = 0.707 gives", "4.3 % overshoot, the fastest response with "
              "little ringing")
        r.out("Aircraft short period target", "\u03b6 between 0.35 and 1.30 "
              "(MIL-F-8785C level 1)")
        r.out("Dutch roll minimum", "\u03b6 \u2265 0.08 for level 1 handling")
        r.out("Your \u03b6 against 0.707", f"{zeta / 0.707:.3g}\u00d7")

    t_end = max(ts2 * 1.6 if ts2 != float("inf") else 20 / wn, 6 / wn)
    ts_arr = linspace(0, t_end, 600)
    ys = [_step_response(t, zeta, wn) for t in ts_arr]
    pts = []
    if zeta < 1:
        pts.append({"x": math.pi / (wn * math.sqrt(1 - zeta ** 2)),
                    "y": 1 + math.exp(-math.pi * zeta / math.sqrt(1 - zeta ** 2)),
                    "label": "peak"})
    r.plot(**P.chart(
        [{"x": ts_arr, "y": ys, "label": "step response"}],
        xlabel="Time  [s]", ylabel="Output",
        title="Unit step response",
        hlines=[{"value": 1.0, "label": "final value"},
                {"value": 1.02, "color": P.RULE, "style": ":"},
                {"value": 0.98, "color": P.RULE, "style": ":"}],
        vlines=[{"value": ts2, "label": "2 % settling", "color": "#0E7C6B"}]
        if ts2 != float("inf") else None,
        points=pts,
        caption="The dotted band is the 2 % envelope used to define settling time."))

    comp = []
    for z in (0.1, 0.3, 0.707, 1.0, 2.0):
        comp.append({"x": ts_arr, "y": [_step_response(t, z, wn) for t in ts_arr],
                     "label": f"\u03b6 = {z:g}",
                     "width": 2.4 if abs(z - zeta) < 1e-6 else 1.3})
    r.plot(**P.chart(
        comp, xlabel="Time  [s]", ylabel="Output",
        title="Effect of the damping ratio",
        hlines=[{"value": 1.0}],
        caption="Low damping is fast but rings; high damping is smooth but slow. "
                "The useful compromise sits near \u03b6 = 0.7."))

    ws = logspace(wn / 100, wn * 100, 400)
    mag = [_db(1 / math.sqrt((1 - (w / wn) ** 2) ** 2 + (2 * zeta * w / wn) ** 2))
           for w in ws]
    phase = [math.degrees(-math.atan2(2 * zeta * w / wn, 1 - (w / wn) ** 2))
             for w in ws]
    r.plot(**P.stack([
        {"series": [{"x": ws, "y": mag}], "xlabel": "Frequency  [rad/s]",
         "ylabel": "Magnitude  [dB]", "title": "Magnitude", "xlog": True},
        {"series": [{"x": ws, "y": phase, "color": P.SERIES[1]}],
         "xlabel": "Frequency  [rad/s]", "ylabel": "Phase  [\u00b0]",
         "title": "Phase", "xlog": True},
    ], title="Bode plot",
        caption="The magnitude peak near \u03c9\u2099 is the resonance; it "
                "disappears once \u03b6 exceeds 0.707."))
    return r


def _step_response(t, zeta, wn):
    if t <= 0:
        return 0.0
    if zeta < 1:
        wd = wn * math.sqrt(1 - zeta ** 2)
        phi = math.acos(zeta)
        return 1 - math.exp(-zeta * wn * t) / math.sqrt(1 - zeta ** 2) * \
            math.sin(wd * t + phi)
    if abs(zeta - 1) < 1e-9:
        return 1 - math.exp(-wn * t) * (1 + wn * t)
    s = math.sqrt(zeta ** 2 - 1)
    r1 = -zeta * wn + wn * s
    r2 = -zeta * wn - wn * s
    return 1 - (r2 * math.exp(r1 * t) - r1 * math.exp(r2 * t)) / (r2 - r1)


# ---------------------------------------------------------------------------
# 6. Filter design
# ---------------------------------------------------------------------------


def _filter(inp):
    fc = inp["fc"]
    order = int(inp["order"])
    kind = inp["kind"]
    ripple = inp["ripple"]

    fs_stop = inp["fs_stop"]
    A_stop = inp["A_stop"]

    def mag_db(f):
        w = f / fc
        if kind == "butter":
            return -10 * math.log10(1 + w ** (2 * order))
        eps2 = 10 ** (ripple / 10) - 1
        if w <= 1:
            cn = math.cos(order * math.acos(min(1.0, w)))
        else:
            cn = math.cosh(order * math.acosh(w))
        return -10 * math.log10(1 + eps2 * cn ** 2)

    att_at_stop = -mag_db(fs_stop)

    # Required order
    if fs_stop > fc:
        if kind == "butter":
            n_req = math.log10((10 ** (A_stop / 10) - 1)) / (2 * math.log10(fs_stop / fc))
        else:
            eps2 = 10 ** (ripple / 10) - 1
            n_req = math.acosh(math.sqrt((10 ** (A_stop / 10) - 1) / eps2)) / \
                math.acosh(fs_stop / fc)
    else:
        n_req = float("nan")

    r = Result()
    label = ("Butterworth" if kind == "butter" else
             f"Chebyshev type I, {ripple:g} dB ripple")
    r.group("Filter", f"{label}, order {order}, cutoff {fc:g} Hz")
    r.headline("Attenuation at the stopband edge", att_at_stop, "dB",
               note=f"at {fs_stop:g} Hz")
    r.headline("Minimum order for the requirement",
               math.ceil(n_req) if n_req == n_req else float("nan"),
               note=f"to reach {A_stop:g} dB at {fs_stop:g} Hz")
    r.out("Exact order required", n_req)
    r.out("Meets the specification?",
          "yes" if att_at_stop >= A_stop else "no")
    r.out("Ultimate roll-off rate", 20 * order, "dB/decade")
    r.out("Roll-off per octave", 6.02 * order, "dB/octave")
    r.out("Attenuation at the cutoff",
          -mag_db(fc), "dB",
          note="3.01 dB by definition for Butterworth; equals the ripple for "
               "Chebyshev of odd order")
    r.out("Attenuation one decade above cutoff", -mag_db(fc * 10), "dB")
    r.out("Number of poles", order)
    r.out("Number of second-order sections", math.ceil(order / 2))

    if kind == "cheby":
        eps = math.sqrt(10 ** (ripple / 10) - 1)
        r.out("Ripple factor \u03b5", eps)
        r.out("Passband ripple", ripple, "dB")
        r.out("Minimum passband gain", -ripple, "dB")

    poles = []
    for k in range(1, order + 1):
        theta = math.pi * (2 * k - 1) / (2 * order)
        if kind == "butter":
            re = -math.sin(theta)
            im = math.cos(theta)
        else:
            eps = math.sqrt(10 ** (ripple / 10) - 1)
            v0 = math.asinh(1 / eps) / order
            re = -math.sinh(v0) * math.sin(theta)
            im = math.cosh(v0) * math.cos(theta)
        if im >= 0:
            poles.append([f"{k}", re * fc, im * fc,
                          math.hypot(re, im) * fc, -re / math.hypot(re, im)])
    r.table("Pole locations (normalised to the cutoff frequency)",
            ["Pole", "Real [Hz]", "Imag [Hz]", "\u03c9\u2099 [Hz]", "\u03b6"],
            poles, sig=5,
            caption="Conjugate pairs are listed once. Each pair is one "
                    "second-order section in an implementation.")

    fs_arr = logspace(fc / 100, fc * 100, 600)
    series = [{"x": fs_arr, "y": [mag_db(f) for f in fs_arr],
               "label": f"order {order}", "width": 2.4}]
    for o in (2, 4, 8):
        if o == order:
            continue
        series.append({"x": fs_arr,
                       "y": [-10 * math.log10(1 + (f / fc) ** (2 * o))
                             if kind == "butter" else
                             _cheby_db(f / fc, o, ripple) for f in fs_arr],
                       "label": f"order {o}", "width": 1.1})
    r.plot(**P.chart(
        series, xlabel="Frequency  [Hz]", ylabel="Magnitude  [dB]", xlog=True,
        title="Magnitude response", ylim=(-90, 5),
        hlines=[{"value": -3.0, "label": "\u22123 dB"},
                {"value": -A_stop, "label": "stopband requirement",
                 "color": "#B3242B"}],
        vlines=[{"value": fc, "label": "cutoff"},
                {"value": fs_stop, "label": "stopband edge", "color": "#0E7C6B"}],
        caption="Each additional order adds 20 dB per decade of roll-off but also "
                "adds phase lag, which costs stability margin in a control loop."))

    fig, ax = P.new_axes(figsize=(5.8, 5.2))
    for k in range(1, order + 1):
        theta = math.pi * (2 * k - 1) / (2 * order)
        if kind == "butter":
            re, im = -math.sin(theta), math.cos(theta)
        else:
            eps = math.sqrt(10 ** (ripple / 10) - 1)
            v0 = math.asinh(1 / eps) / order
            re, im = -math.sinh(v0) * math.sin(theta), math.cosh(v0) * math.cos(theta)
        ax.plot([re], [im], marker="x", ms=9, mew=2.0, color=P.SERIES[0])
    cx, cy = plt_unit_circle()
    ax.plot(cx, cy, color=P.MUTED, lw=1.0, ls="--")
    ax.axhline(0, color=P.RULE, lw=0.9)
    ax.axvline(0, color=P.RULE, lw=0.9)
    ax.set_aspect("equal", adjustable="datalim")
    P.style_axes(ax, xlabel="Real  [\u03c3/\u03c9_c]", ylabel="Imaginary  [j\u03c9/\u03c9_c]",
                 title="Pole positions in the s-plane")
    r.plot(P.render(fig), "Pole positions",
           "Butterworth poles sit on a circle; Chebyshev poles sit on an ellipse, "
           "pushed closer to the imaginary axis, which is what produces both the "
           "sharper cutoff and the passband ripple.")
    return r


def _cheby_db(w, order, ripple):
    eps2 = 10 ** (ripple / 10) - 1
    if w <= 1:
        cn = math.cos(order * math.acos(min(1.0, w)))
    else:
        cn = math.cosh(order * math.acosh(w))
    return -10 * math.log10(1 + eps2 * cn ** 2)


def plt_unit_circle(n=200):
    th = linspace(0, 2 * math.pi, n)
    return [math.cos(t) for t in th], [math.sin(t) for t in th]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CALCULATORS = [
    {
        "id": "link-budget",
        "name": "Communications link budget",
        "category": CATEGORY,
        "summary": "EIRP, path loss, G/T, C/N₀, Eb/N₀ and margin as a full itemised budget.",
        "tags": ["link budget", "EIRP", "path loss", "Eb/N0", "G/T", "satcom"],
        "inputs": [
            num("freq", "Frequency", 12.0, "GHz", minimum=1e-6, section="Link"),
            num("range", "Range", 36000.0, "km", minimum=1e-6, section="Link"),
            num("Pt", "Transmit power", 20.0, section="Transmitter"),
            choice("power_unit", "Power unit", [("W", "watts"), ("dBm", "dBm")], "W",
                   section="Transmitter"),
            choice("tx_spec", "Transmit antenna given as",
                   [("gain", "Gain"), ("dia", "Diameter")], "gain",
                   section="Transmitter"),
            num("Gt", "Transmit antenna gain", 40.0, "dBi", section="Transmitter",
                show_if={"key": "tx_spec", "in": ["gain"]}),
            num("Dt", "Transmit antenna diameter", 1.0, "m", minimum=1e-6,
                section="Transmitter", show_if={"key": "tx_spec", "in": ["dia"]}),
            num("eta_t", "Transmit aperture efficiency", 0.6, minimum=0.05,
                maximum=1.0, section="Transmitter"),
            num("L_tx", "Transmit line loss", 1.0, "dB", minimum=0.0,
                section="Transmitter"),
            choice("rx_spec", "Receive antenna given as",
                   [("gain", "Gain"), ("dia", "Diameter")], "dia", section="Receiver"),
            num("Gr", "Receive antenna gain", 50.0, "dBi", section="Receiver",
                show_if={"key": "rx_spec", "in": ["gain"]}),
            num("Dr", "Receive antenna diameter", 2.4, "m", minimum=1e-6,
                section="Receiver", show_if={"key": "rx_spec", "in": ["dia"]}),
            num("eta_r", "Receive aperture efficiency", 0.65, minimum=0.05,
                maximum=1.0, section="Receiver"),
            num("L_rx", "Receive line loss", 0.5, "dB", minimum=0.0, section="Receiver"),
            num("Ts", "System noise temperature", 150.0, "K", minimum=1.0,
                section="Receiver"),
            num("L_atm", "Atmospheric loss", 0.5, "dB", minimum=0.0, section="Losses"),
            num("L_rain", "Rain loss", 3.0, "dB", minimum=0.0, section="Losses"),
            num("L_point", "Pointing loss", 0.5, "dB", minimum=0.0, section="Losses"),
            num("L_pol", "Polarisation loss", 0.2, "dB", minimum=0.0, section="Losses"),
            num("Rb", "Data rate", 10.0, "Mbit/s", minimum=1e-9, section="Data"),
            num("B", "Bandwidth", 12.0, "MHz", minimum=1e-9, section="Data"),
            num("Eb_N0_req", "Required E_b/N\u2080", 9.6, "dB", section="Data",
                help="9.6 dB is uncoded BPSK at a bit error rate of 10\u207b\u2075."),
            num("L_impl", "Implementation loss", 1.5, "dB", minimum=0.0,
                section="Data"),
        ],
        "compute": _link_budget,
    },
    {
        "id": "radar-range",
        "name": "Radar range equation",
        "category": CATEGORY,
        "summary": "Detection range, SNR, resolution and the range–Doppler ambiguity trade.",
        "tags": ["radar", "range equation", "SNR", "PRF", "Doppler", "RCS"],
        "inputs": [
            num("freq", "Frequency", 10.0, "GHz", minimum=1e-6, section="Radar"),
            num("Pt", "Peak transmit power", 100.0, section="Radar"),
            choice("peak_unit", "Power unit", [("kW", "kilowatts"), ("W", "watts")],
                   "kW", section="Radar"),
            num("G", "Antenna gain", 35.0, "dBi", section="Radar"),
            num("B", "Receiver bandwidth", 1.0, "MHz", minimum=1e-9, section="Radar"),
            num("Ts", "System noise temperature", 290.0, "K", minimum=1.0,
                section="Radar"),
            num("F", "Noise figure", 3.0, "dB", minimum=0.0, section="Radar"),
            num("L", "System losses", 4.0, "dB", minimum=0.0, section="Radar"),
            num("sigma", "Target radar cross-section", 5.0, "m\u00b2", minimum=1e-12,
                section="Target"),
            num("R", "Range to the target", 50.0, "km", minimum=1e-6, section="Target"),
            num("v", "Target radial velocity", 250.0, "m/s", section="Target"),
            num("snr_min", "Detection threshold SNR", 13.0, "dB", section="Detection"),
            toggle("integrate", "Integrate multiple pulses", False,
                   section="Detection"),
            integer("n_pulses", "Number of pulses integrated", 20, minimum=1,
                    maximum=100000, section="Detection",
                    show_if={"key": "integrate", "in": [True]}),
            toggle("coherent", "Coherent integration", True, section="Detection",
                   show_if={"key": "integrate", "in": [True]}),
            num("PRF", "Pulse repetition frequency", 1000.0, "Hz", minimum=1e-6,
                section="Waveform"),
            num("tau", "Pulse width", 1.0, "\u03bcs", minimum=1e-9, section="Waveform"),
            toggle("compress", "Pulse compression used", False, section="Waveform"),
            num("beamwidth", "Antenna beamwidth", 0.0, "\u00b0", minimum=0.0,
                section="Scanning", help="Set to 0 to skip the scanning results."),
            num("scan_rate", "Scan rate", 36.0, "\u00b0/s", minimum=0.0,
                section="Scanning"),
        ],
        "compute": _radar,
    },
    {
        "id": "antenna",
        "name": "Antenna gain, beamwidth and pattern",
        "category": CATEGORY,
        "summary": "Gain, beamwidth, effective aperture, far field, Ruze loss and pattern.",
        "tags": ["antenna", "gain", "beamwidth", "aperture", "Ruze", "sidelobe"],
        "inputs": [
            num("freq", "Frequency", 12.0, "GHz", minimum=1e-6, section="Antenna"),
            choice("kind", "Antenna type", [("dish", "Parabolic dish"),
                                            ("aperture", "Rectangular aperture"),
                                            ("array", "Planar array")], "dish",
                   section="Antenna"),
            num("D", "Dish diameter", 2.4, "m", minimum=1e-6, section="Antenna",
                show_if={"key": "kind", "in": ["dish"]}),
            num("a", "Aperture width", 1.0, "m", minimum=1e-6, section="Antenna",
                show_if={"key": "kind", "in": ["aperture"]}),
            num("b", "Aperture height", 0.5, "m", minimum=1e-6, section="Antenna",
                show_if={"key": "kind", "in": ["aperture"]}),
            integer("n_el", "Elements per side", 32, minimum=2, maximum=10000,
                    section="Antenna", show_if={"key": "kind", "in": ["array"]}),
            num("d_spacing", "Element spacing", 0.5, "\u03bb", minimum=0.1,
                maximum=2.0, section="Antenna",
                show_if={"key": "kind", "in": ["array"]}),
            num("eta", "Aperture efficiency", 0.6, minimum=0.05, maximum=1.0,
                section="Antenna"),
            num("range", "Range to the target", 0.0, "km", minimum=0.0,
                section="Application", help="Set to 0 to skip the footprint."),
            num("surface_rms", "Surface RMS error", 0.0, "mm", minimum=0.0,
                section="Application", help="Set to 0 to skip the Ruze loss."),
        ],
        "compute": _antenna,
    },
    {
        "id": "noise-cascade",
        "name": "Noise figure cascade and ADC",
        "category": CATEGORY,
        "summary": "Friis cascade noise figure, system temperature and converter SNR.",
        "tags": ["noise figure", "Friis", "noise temperature", "ADC", "ENOB", "SNR"],
        "inputs": [
            integer("n_stages", "Number of stages", 3, minimum=1, maximum=5,
                    section="Cascade"),
            num("T_ant", "Antenna noise temperature", 50.0, "K", minimum=0.0,
                section="Cascade"),
            num("g1", "Stage 1 gain", 20.0, "dB", section="Stage 1"),
            num("nf1", "Stage 1 noise figure", 1.0, "dB", minimum=0.0, section="Stage 1"),
            num("g2", "Stage 2 gain", -2.0, "dB", section="Stage 2",
                show_if={"key": "n_stages", "in": [2, 3, 4, 5]}),
            num("nf2", "Stage 2 noise figure", 2.0, "dB", minimum=0.0, section="Stage 2",
                show_if={"key": "n_stages", "in": [2, 3, 4, 5]}),
            num("g3", "Stage 3 gain", 30.0, "dB", section="Stage 3",
                show_if={"key": "n_stages", "in": [3, 4, 5]}),
            num("nf3", "Stage 3 noise figure", 6.0, "dB", minimum=0.0, section="Stage 3",
                show_if={"key": "n_stages", "in": [3, 4, 5]}),
            num("g4", "Stage 4 gain", 20.0, "dB", section="Stage 4",
                show_if={"key": "n_stages", "in": [4, 5]}),
            num("nf4", "Stage 4 noise figure", 8.0, "dB", minimum=0.0, section="Stage 4",
                show_if={"key": "n_stages", "in": [4, 5]}),
            num("g5", "Stage 5 gain", 10.0, "dB", section="Stage 5",
                show_if={"key": "n_stages", "in": [5]}),
            num("nf5", "Stage 5 noise figure", 10.0, "dB", minimum=0.0,
                section="Stage 5", show_if={"key": "n_stages", "in": [5]}),
            toggle("adc", "Include an analogue to digital converter", False,
                   section="Converter"),
            integer("bits", "Resolution", 12, minimum=4, maximum=32,
                    section="Converter", show_if={"key": "adc", "in": [True]}),
            num("fs", "Sampling rate", 100.0, "MSPS", minimum=1e-6,
                section="Converter", show_if={"key": "adc", "in": [True]}),
            num("vref", "Full-scale voltage", 2.0, "V", minimum=1e-9,
                section="Converter", show_if={"key": "adc", "in": [True]}),
            num("B_sig", "Signal bandwidth", 10.0, "MHz", minimum=1e-9,
                section="Converter", show_if={"key": "adc", "in": [True]}),
            num("snr_actual", "Measured SNR", 0.0, "dB", minimum=0.0,
                section="Converter", show_if={"key": "adc", "in": [True]},
                help="Set to 0 to skip the effective number of bits."),
        ],
        "compute": _noise,
    },
    {
        "id": "control-response",
        "name": "Second-order control response",
        "category": CATEGORY,
        "summary": "Damping, overshoot, settling time, step response and Bode plot.",
        "tags": ["control", "damping ratio", "overshoot", "settling time", "Bode",
                 "second order"],
        "inputs": [
            choice("spec", "Specify the system by",
                   [("params", "Natural frequency and damping"),
                    ("perf", "Overshoot and settling time")], "params",
                   section="System"),
            num("wn", "Natural frequency", 10.0, "rad/s", minimum=1e-9,
                section="System", show_if={"key": "spec", "in": ["params"]}),
            num("zeta", "Damping ratio", 0.7, minimum=0.0, maximum=5.0,
                section="System", show_if={"key": "spec", "in": ["params"]}),
            num("Mp", "Desired overshoot", 5.0, "%", minimum=0.01, maximum=99.0,
                section="System", show_if={"key": "spec", "in": ["perf"]}),
            num("ts", "Desired 2 % settling time", 2.0, "s", minimum=1e-6,
                section="System", show_if={"key": "spec", "in": ["perf"]}),
            toggle("damping_advice", "Show handling-qualities guidance", False,
                   section="Guidance"),
        ],
        "compute": _control,
    },
    {
        "id": "filter-design",
        "name": "Analogue filter design",
        "category": CATEGORY,
        "summary": "Butterworth and Chebyshev order selection, response and pole positions.",
        "tags": ["filter", "Butterworth", "Chebyshev", "roll-off", "poles", "anti-alias"],
        "inputs": [
            choice("kind", "Filter family", [("butter", "Butterworth"),
                                             ("cheby", "Chebyshev type I")],
                   "butter", section="Filter"),
            integer("order", "Order", 4, minimum=1, maximum=16, section="Filter"),
            num("fc", "Cutoff frequency", 1000.0, "Hz", minimum=1e-9, section="Filter"),
            num("ripple", "Passband ripple", 0.5, "dB", minimum=0.001, maximum=6.0,
                section="Filter", show_if={"key": "kind", "in": ["cheby"]}),
            num("fs_stop", "Stopband edge", 3000.0, "Hz", minimum=1e-9,
                section="Requirement"),
            num("A_stop", "Required stopband attenuation", 40.0, "dB", minimum=0.0,
                section="Requirement"),
        ],
        "compute": _filter,
    },
]
