# References

## A note on how to read this list

These are the standard references where each method used in AeroCalc is
derived. They are **attribution pointers, not transcriptions** — the
implementations were written from the standard theory, so this list does not
claim "equation 4.12 on page 217". Anyone wanting to check a result should open
the reference named for that calculator and confirm the method, which is the
useful thing to verify anyway.

Every calculator also carries its own references in the application: they appear
at the bottom of the results panel after you press Calculate, and are returned
by the API under `calculator.references`.

---

## Primary documents

These are freely available, and are the correct things to cite for the
tabulated values themselves rather than for a textbook treatment of them.

| Document | Used for | Link |
|---|---|---|
| **NACA Report 1135** — *Equations, Tables, and Charts for Compressible Flow*, Ames Research Staff, 1953 | All compressible flow relations; tables I and II correspond to this app's gas tables at γ = 1.4 | [NTRS PDF](https://ntrs.nasa.gov/api/citations/19930091059/downloads/19930091059.pdf) · [NTRS record](https://ntrs.nasa.gov/citations/19930091059) |
| **U.S. Standard Atmosphere, 1976**, NOAA/NASA/USAF, NOAA-S/T 76-1562 | The atmosphere model, all seven layers to 84.852 km geopotential | [NTRS PDF](https://ntrs.nasa.gov/api/citations/19770009539/downloads/19770009539.pdf) · [NOAA copy](https://www.ngdc.noaa.gov/stp/space-weather/online-publications/miscellaneous/us-standard-atmosphere-1976/us-standard-atmosphere_st76-1562_noaa.pdf) |
| **Colebrook, C.F. (1939)** — *Turbulent Flow in Pipes, with Particular Reference to the Transition Region between the Smooth and Rough Pipe Laws*, J. Inst. Civil Engineers **11**(4), 133–156 | The friction factor, solved implicitly rather than approximated | [doi:10.1680/ijoti.1939.13150](https://doi.org/10.1680/ijoti.1939.13150) |
| **Moody, L.F. (1944)** — *Friction Factors for Pipe Flow*, Trans. ASME **66**, 671–684 | The Moody chart, regenerated from the Colebrook equation | — |
| **ISO 5167** — Measurement of fluid flow by differential pressure devices | Venturi, orifice and nozzle discharge coefficients | (paywalled standard) |
| **Tsai, S.W. & Wu, E.M. (1971)** — *A General Theory of Strength for Anisotropic Materials*, J. Composite Materials **5**, 58–80 | The Tsai–Wu failure index | — |
| **Paris, P. & Erdogan, F. (1963)** — *A Critical Analysis of Crack Propagation Laws*, J. Basic Engineering **85**, 528–533 | Fatigue crack growth | — |
| **Friis, H.T. (1944)** — *Noise Figures of Radio Receivers*, Proc. IRE **32**, 419–422 | The cascade noise figure formula | — |
| **Ruze, J. (1966)** — *Antenna Tolerance Theory — A Review*, Proc. IEEE **54**, 633–640 | Antenna surface-error gain loss | — |
| **MIL-E-5008B** | Supersonic inlet total pressure recovery | — |
| **MIL-F-8785C** | Flying-qualities damping ratio requirements | — |

---

## Textbooks by discipline

### Aerodynamics
- Anderson, *Fundamentals of Aerodynamics*, McGraw-Hill — ch. 3 (atmosphere, Bernoulli), ch. 4 (thin airfoil theory), ch. 5 (lifting line), ch. 11 (compressibility corrections), ch. 18–19 (boundary layers)
- Abbott & von Doenhoff, *Theory of Wing Sections*, Dover — NACA airfoil geometry
- Schlichting, *Boundary-Layer Theory* — the Blasius solution

### Gas Dynamics
- Anderson, *Modern Compressible Flow: With Historical Perspective*, McGraw-Hill — ch. 3 (isentropic, normal shock, Fanno, Rayleigh), ch. 4 (oblique shocks, Prandtl–Meyer), ch. 5 (quasi-1D nozzle flow), ch. 7 (shock tubes)

### Fluid Dynamics
- White, *Fluid Mechanics*, McGraw-Hill — ch. 4 (exact Navier–Stokes solutions), ch. 5 (dimensional analysis), ch. 6 (pipe flow, flow measurement)
- Munson, Young & Okiishi, *Fundamentals of Fluid Mechanics* — alternative treatment

### Thermodynamics
- Çengel & Boles, *Thermodynamics: An Engineering Approach*, McGraw-Hill — ch. 3–7 (processes), ch. 9 (Brayton, Otto, Diesel, Dual cycles)
- Incropera & DeWitt, *Fundamentals of Heat and Mass Transfer*, Wiley — ch. 3 (conduction, fins), ch. 11 (ε–NTU and LMTD), ch. 12–13 (radiation)

### Propulsion
- Mattingly, *Elements of Propulsion: Gas Turbines and Rockets*, AIAA Education Series — ch. 7 (parametric cycle analysis; the turbofan and ramjet calculators follow this formulation)
- Hill & Peterson, *Mechanics and Thermodynamics of Propulsion*, Addison-Wesley
- Sutton & Biblarz, *Rocket Propulsion Elements*, Wiley — ch. 3 (nozzle theory), ch. 4 (flight performance)
- Leishman, *Principles of Helicopter Aerodynamics* — ch. 2 (momentum theory, figure of merit)
- Glauert, *The Elements of Aerofoil and Airscrew Theory*

### Flight Mechanics
- Anderson, *Aircraft Performance and Design*, McGraw-Hill — ch. 5 (performance, Breguet range), ch. 6 (manoeuvring)
- Raymer, *Aircraft Design: A Conceptual Approach*, AIAA — ch. 12 (drag build-up), ch. 17 (V–n diagram, field length)
- Nelson, *Flight Stability and Automatic Control*, McGraw-Hill — ch. 2 (static longitudinal stability, neutral point)
- Etkin & Reid, *Dynamics of Flight: Stability and Control*, Wiley

### Structures & Composites
- Hibbeler, *Mechanics of Materials*, Pearson — ch. 5 (torsion), ch. 6 & 12 (bending, deflection), ch. 8 (pressure vessels), ch. 9 (Mohr's circle)
- Budynas & Nisbett, *Shigley's Mechanical Engineering Design*, McGraw-Hill — ch. 4 (Euler and Johnson columns), ch. 6 (fatigue, Goodman/Gerber/Soderberg)
- Megson, *Aircraft Structures for Engineering Students*, Elsevier — thin-walled sections, Bredt–Batho torsion
- Jones, *Mechanics of Composite Materials*, Taylor & Francis — ch. 3 (micromechanics), ch. 4 (classical lamination theory, ABD matrices)
- Daniel & Ishai, *Engineering Mechanics of Composite Materials*, OUP — ch. 5
- Halpin & Kardos (1976), *The Halpin–Tsai Equations: A Review*, Polymer Eng. & Science **16**, 344–352
- Anderson, T.L., *Fracture Mechanics: Fundamentals and Applications*, CRC Press

### Space & Satellites
- Curtis, *Orbital Mechanics for Engineering Students*, Elsevier — ch. 2–4 (two-body, Kepler's equation), ch. 6 (manoeuvres), ch. 8 (interplanetary), ch. 11 (rocket dynamics)
- Vallado, *Fundamentals of Astrodynamics and Applications*, Microcosm — ch. 9 (J₂ perturbations, sun-synchronous orbits), ch. 12 (patched conics)
- Bate, Mueller & White, *Fundamentals of Astrodynamics*, Dover
- Wertz & Larson, *Space Mission Analysis and Design* (SMAD), Microcosm — ch. 5 (coverage geometry), ch. 13 (communications)

### Avionics & Electronics
- Skolnik, *Introduction to Radar Systems*, McGraw-Hill — ch. 1–2 (radar range equation)
- Richards, *Fundamentals of Radar Signal Processing*, McGraw-Hill
- Balanis, *Antenna Theory: Analysis and Design*, Wiley — ch. 2 (gain, beamwidth, effective aperture), ch. 15 (aperture antennas)
- Pratt, Bostian & Allnutt, *Satellite Communications*, Wiley — ch. 4 (link budgets)
- Ogata, *Modern Control Engineering*, Pearson — ch. 5 (transient response)
- Nise, *Control Systems Engineering*, Wiley — ch. 4
- Zverev, *Handbook of Filter Synthesis*, Wiley
- Sedra & Smith, *Microelectronic Circuits*, OUP — ch. 17 (filters)

---

## Physical constants

- Gravitational parameters, planetary radii and J₂ values: JPL/NASA planetary
  fact sheets and the IAU working group values.
- Universal gas constant, Boltzmann constant, speed of light: CODATA 2018.
- Standard gravity g₀ = 9.80665 m/s², dry-air gas constant R = 287.05287
  J/(kg·K): U.S. Standard Atmosphere 1976.
- Material properties (aluminium, titanium, steel alloys, composite plies):
  representative handbook values, principally MIL-HDBK-5 / MMPDS for metals and
  MIL-HDBK-17 / CMH-17 for composites. These are typical design values for
  coursework, **not** certified allowables for a real design.
