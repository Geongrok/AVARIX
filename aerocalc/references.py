"""Where each calculator's method is standardly derived.

These are attribution pointers, not transcriptions: the implementations were
written from the standard theory rather than copied from a particular edition,
so no page or equation numbers are claimed. Each entry names the reference a
reader should open to check the method, and the chapter where that treatment
normally sits.

Primary documents (freely available, and the right thing to cite for the
tabulated values themselves):

  NACA Report 1135, "Equations, Tables, and Charts for Compressible Flow",
  Ames Research Staff, 1953.
  https://ntrs.nasa.gov/api/citations/19930091059/downloads/19930091059.pdf

  U.S. Standard Atmosphere, 1976, NOAA/NASA/USAF, NOAA-S/T 76-1562.
  https://ntrs.nasa.gov/api/citations/19770009539/downloads/19770009539.pdf

  Colebrook, C.F. (1939), "Turbulent Flow in Pipes, with Particular Reference
  to the Transition Region between the Smooth and Rough Pipe Laws",
  J. Inst. Civil Engineers 11(4), 133-156.  doi:10.1680/ijoti.1939.13150
"""

NACA_1135 = "NACA Report 1135, Equations, Tables and Charts for Compressible Flow (1953)"
USSA_76 = "U.S. Standard Atmosphere 1976 (NOAA-S/T 76-1562)"
ANDERSON_FOA = "Anderson, Fundamentals of Aerodynamics"
ANDERSON_MCF = "Anderson, Modern Compressible Flow: With Historical Perspective"
ANDERSON_APD = "Anderson, Aircraft Performance and Design"
WHITE_FM = "White, Fluid Mechanics"
CENGEL = "\u00c7engel & Boles, Thermodynamics: An Engineering Approach"
INCROPERA = "Incropera & DeWitt, Fundamentals of Heat and Mass Transfer"
MATTINGLY = "Mattingly, Elements of Propulsion: Gas Turbines and Rockets (AIAA)"
HILL_PETERSON = "Hill & Peterson, Mechanics and Thermodynamics of Propulsion"
SUTTON = "Sutton & Biblarz, Rocket Propulsion Elements"
CURTIS = "Curtis, Orbital Mechanics for Engineering Students"
VALLADO = "Vallado, Fundamentals of Astrodynamics and Applications"
SMAD = "Wertz & Larson, Space Mission Analysis and Design"
JONES = "Jones, Mechanics of Composite Materials"
DANIEL_ISHAI = "Daniel & Ishai, Engineering Mechanics of Composite Materials"
HIBBELER = "Hibbeler, Mechanics of Materials"
SHIGLEY = "Budynas & Nisbett, Shigley's Mechanical Engineering Design"
MEGSON = "Megson, Aircraft Structures for Engineering Students"
NELSON = "Nelson, Flight Stability and Automatic Control"
RAYMER = "Raymer, Aircraft Design: A Conceptual Approach (AIAA)"
SCHLICHTING = "Schlichting, Boundary-Layer Theory"
ABBOTT = "Abbott & von Doenhoff, Theory of Wing Sections"
SKOLNIK = "Skolnik, Introduction to Radar Systems"
BALANIS = "Balanis, Antenna Theory: Analysis and Design"
PRATT = "Pratt, Bostian & Allnutt, Satellite Communications"
OGATA = "Ogata, Modern Control Engineering"

REFERENCES: dict[str, list[str]] = {
    # -- Aerodynamics ------------------------------------------------------
    "standard-atmosphere": [USSA_76, f"{ANDERSON_FOA}, ch. 3 (standard atmosphere)"],
    "airspeed-conversion": [f"{ANDERSON_FOA}, ch. 3 and 8",
                            f"{NACA_1135} (Rayleigh pitot formula)"],
    "reynolds-similarity": [f"{ANDERSON_FOA}, ch. 1 (dimensional analysis)", WHITE_FM],
    "thin-airfoil": [f"{ANDERSON_FOA}, ch. 4 (thin airfoil theory)", ABBOTT],
    "lifting-line": [f"{ANDERSON_FOA}, ch. 5 (Prandtl lifting-line theory)"],
    "drag-polar": [f"{ANDERSON_APD}, ch. 2", f"{RAYMER}, ch. 12 (drag build-up)"],
    "boundary-layer": [f"{SCHLICHTING}, ch. 6-7 (Blasius solution)",
                       f"{ANDERSON_FOA}, ch. 18-19"],
    "compressibility-correction": [f"{ANDERSON_FOA}, ch. 11 "
                                   "(Prandtl-Glauert, K\u00e1rm\u00e1n-Tsien, Laitone)"],

    # -- Gas Dynamics ------------------------------------------------------
    "isentropic-flow": [NACA_1135, f"{ANDERSON_MCF}, ch. 3"],
    "normal-shock": [NACA_1135, f"{ANDERSON_MCF}, ch. 3 (Rankine-Hugoniot relations)"],
    "oblique-shock": [f"{NACA_1135} (\u03b8-\u03b2-M relation)",
                      f"{ANDERSON_MCF}, ch. 4"],
    "prandtl-meyer": [f"{NACA_1135} (Prandtl-Meyer function)",
                      f"{ANDERSON_MCF}, ch. 4"],
    "fanno-flow": [f"{ANDERSON_MCF}, ch. 3 (Fanno line)", NACA_1135],
    "rayleigh-flow": [f"{ANDERSON_MCF}, ch. 3 (Rayleigh line)", NACA_1135],
    "cd-nozzle": [f"{ANDERSON_MCF}, ch. 5 (quasi-one-dimensional flow)", SUTTON],
    "shock-tube": [f"{ANDERSON_MCF}, ch. 7 (unsteady wave motion)"],
    "gas-tables": [f"{NACA_1135} \u2014 tables I and II reproduce this calculator's "
                   "output for \u03b3 = 1.4", ANDERSON_MCF],

    # -- Fluid Dynamics ----------------------------------------------------
    "pipe-flow": ["Colebrook (1939), J. Inst. Civil Engineers 11, 133-156, "
                  "doi:10.1680/ijoti.1939.13150",
                  "Moody (1944), Trans. ASME 66, 671-684",
                  f"{WHITE_FM}, ch. 6"],
    "flow-meter": ["ISO 5167 (differential-pressure flow measurement)",
                   f"{WHITE_FM}, ch. 6"],
    "pitot-static": [f"{ANDERSON_FOA}, ch. 3 and 8", NACA_1135],
    "dimensionless-numbers": [f"{WHITE_FM}, ch. 5 (dimensional analysis, "
                              "Buckingham Pi)"],
    "couette-poiseuille": [f"{WHITE_FM}, ch. 4 (exact solutions of Navier-Stokes)"],

    # -- Thermodynamics ----------------------------------------------------
    "polytropic-process": [f"{CENGEL}, ch. 3-7"],
    "brayton-cycle": [f"{CENGEL}, ch. 9 (gas power cycles)", HILL_PETERSON],
    "piston-cycles": [f"{CENGEL}, ch. 9 (Otto, Diesel and Dual cycles)"],
    "heat-transfer": [f"{INCROPERA}, ch. 3 (conduction), ch. 12-13 (radiation)"],
    "heat-exchanger": [f"{INCROPERA}, ch. 11 (\u03b5-NTU and LMTD methods)"],

    # -- Propulsion --------------------------------------------------------
    "turbofan-cycle": [f"{MATTINGLY}, ch. 7 (parametric cycle analysis)",
                       "MIL-E-5008B (inlet total pressure recovery)",
                       HILL_PETERSON],
    "ramjet": [f"{MATTINGLY}, ch. 7", f"{HILL_PETERSON}, ch. 5"],
    "rocket-nozzle": [f"{SUTTON}, ch. 3 (nozzle theory and thermodynamic relations)",
                      "Summerfield criterion for nozzle flow separation"],
    "propeller-momentum": ["Glauert, The Elements of Aerofoil and Airscrew Theory",
                           "Leishman, Principles of Helicopter Aerodynamics, ch. 2"],

    # -- Flight Mechanics --------------------------------------------------
    "level-flight": [f"{ANDERSON_APD}, ch. 5 (airplane performance)"],
    "range-endurance": [f"{ANDERSON_APD}, ch. 5 (Breguet range and endurance)"],
    "climb-performance": [f"{ANDERSON_APD}, ch. 5 (rate of climb, ceilings)"],
    "turn-performance": [f"{ANDERSON_APD}, ch. 6 (manoeuvring flight)",
                         f"{RAYMER}, ch. 17 (V-n diagram)"],
    "takeoff-landing": [f"{ANDERSON_APD}, ch. 5", f"{RAYMER}, ch. 17"],
    "static-stability": [f"{NELSON}, ch. 2 (static longitudinal stability)",
                         "Etkin & Reid, Dynamics of Flight: Stability and Control"],

    # -- Structures & Composites ------------------------------------------
    "beam-bending": [f"{HIBBELER}, ch. 6 and 12", MEGSON],
    "column-buckling": [f"{SHIGLEY}, ch. 4 (Euler and Johnson columns)", HIBBELER],
    "pressure-vessel": [f"{HIBBELER}, ch. 8 (thin- and thick-walled vessels)"],
    "stress-transformation": [f"{HIBBELER}, ch. 9 (Mohr's circle)"],
    "torsion": [f"{HIBBELER}, ch. 5", f"{MEGSON}, (Bredt-Batho thin-walled torsion)"],
    "laminate-clt": [f"{JONES}, ch. 4 (classical lamination theory)",
                     f"{DANIEL_ISHAI}, ch. 5",
                     "Tsai & Wu (1971), J. Composite Materials 5, 58-80"],
    "micromechanics": [f"{JONES}, ch. 3 (rule of mixtures)",
                       "Halpin & Kardos (1976), Polymer Eng. & Science 16, 344-352"],
    "fatigue-fracture": [f"{SHIGLEY}, ch. 6 (fatigue), Goodman and Gerber criteria",
                         "Paris & Erdogan (1963), J. Basic Engineering 85, 528-533",
                         "Anderson, Fracture Mechanics: Fundamentals and Applications"],

    # -- Space & Satellites ------------------------------------------------
    "orbital-elements": [f"{CURTIS}, ch. 2-4", f"{VALLADO}, ch. 1-2"],
    "orbit-transfer": [f"{CURTIS}, ch. 6 (orbital manoeuvres)", f"{VALLADO}, ch. 6"],
    "kepler-propagation": [f"{CURTIS}, ch. 3 (Kepler's equation)",
                           "Bate, Mueller & White, Fundamentals of Astrodynamics"],
    "rocket-equation": [f"{CURTIS}, ch. 11 (rocket vehicle dynamics)",
                        f"{SUTTON}, ch. 4"],
    "groundtrack-coverage": [f"{VALLADO}, ch. 9 (J\u2082 perturbations, "
                             "sun-synchronous orbits)",
                             f"{SMAD}, ch. 5 (coverage and access geometry)"],
    "escape-hyperbolic": [f"{CURTIS}, ch. 8 (interplanetary trajectories)",
                          f"{VALLADO}, ch. 12 (patched conics, gravity assist)"],

    # -- Avionics & Electronics -------------------------------------------
    "link-budget": [f"{PRATT}, ch. 4 (satellite link design)",
                    f"{SMAD}, ch. 13 (communications architecture)"],
    "radar-range": [f"{SKOLNIK}, ch. 1-2 (the radar range equation)",
                    "Richards, Fundamentals of Radar Signal Processing"],
    "antenna": [f"{BALANIS}, ch. 2 (fundamental parameters) and ch. 15 (apertures)",
                "Ruze (1966), Proc. IEEE 54, 633-640 (surface tolerance theory)"],
    "noise-cascade": ["Friis (1944), Proc. IRE 32, 419-422 (noise figure of networks)",
                      "Kester (Analog Devices), Data Conversion Handbook"],
    "control-response": [f"{OGATA}, ch. 5 (transient response analysis)",
                         "Nise, Control Systems Engineering, ch. 4",
                         "MIL-F-8785C (flying qualities damping requirements)"],
    "filter-design": ["Zverev, Handbook of Filter Synthesis",
                      "Sedra & Smith, Microelectronic Circuits, ch. 17"],
}


def attach(spec: dict) -> dict:
    """Give a calculator its references, unless the module already set some."""
    if not spec.get("references"):
        refs = REFERENCES.get(spec["id"])
        if refs:
            spec["references"] = list(refs)
    return spec
