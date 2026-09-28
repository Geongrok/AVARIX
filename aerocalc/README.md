# AeroCalc

A multi-discipline aerospace engineering calculator: **57 calculators across
nine disciplines**, each one computed on a Python backend and returned to the
browser with the charts and tables that put the answer in context.


## Running it

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>.

To put it on a public URL for free, see **`DEPLOY.md`** — PythonAnywhere (no
cold start) or Render (Git-based). The project already contains `wsgi.py`,
`Procfile` and `render.yaml`, so neither route needs you to write anything.

On the first load the page pulls IBM Plex from Google Fonts. Without a network
connection it falls back to the system sans and mono faces and still looks
correct.


## What's included

| # | Discipline | Calculators |
|---|---|---|
| 01 | Aerodynamics | 8 |
| 02 | Fluid Dynamics | 5 |
| 03 | Gas Dynamics | 9 |
| 04 | Thermodynamics | 5 |
| 05 | Propulsion | 4 |
| 06 | Flight Mechanics | 6 |
| 07 | Structures & Composites | 8 |
| 08 | Space & Satellites | 6 |
| 09 | Avionics & Electronics | 6 |

A few worth pointing out:

- **Gas tables** — isentropic, normal shock, Fanno, Rayleigh and Prandtl-Meyer
  tables for any γ and any Mach range, with CSV export at 12 significant
  figures. This is the reference-table requirement, generated from the same
  equations the other calculators use rather than from a stored data file.
- **Classical lamination theory** — builds the transformed stiffness of every
  ply, assembles the full A, B and D matrices, reports effective laminate
  properties, and applies a load case to get ply-by-ply stresses in material
  axes with a Tsai-Wu first-ply-failure index.
- **θ–β–M oblique shocks** — solved exactly from the relation, including the
  strong branch and the detachment check, and drawn on the θ–β–M diagram with
  your solution marked.
- **Turbofan cycle analysis** — full on-design station analysis with real
  component efficiencies, bypass and afterburner.


## How it is built


app.py                    Flask: routing, JSON API, CSV export
aerocalc/
  core.py                 field descriptors, Result builder, registry, formatting
  numeric.py              Brent and Newton solvers used by every inverse problem
  physics.py              constants, U.S. Standard Atmosphere 1976, gas properties
  compressible.py         isentropic, shock, Fanno, Rayleigh, Prandtl-Meyer
  plotting.py             Matplotlib charts rendered server-side to base64 PNG
  modules/                the 57 calculators, grouped by discipline
templates/index.html      application shell
static/css/style.css      design tokens and layout
static/js/app.js          schema-driven form building and result rendering
```

**The frontend never knows what a calculator does.** Each one declares its
inputs in Python — type, unit, default, valid range, help text, and any
`show_if` condition — and the browser builds the form from that schema. Adding
a calculator means writing one function and one spec; no JavaScript changes.

The charts are drawn on the server with Matplotlib and sent as base64 PNGs.
The chart palette in `plotting.py` and the CSS custom properties in `style.css`
are the same hex values, so a figure reads as though it were printed on the
page rather than pasted onto it.

### The API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/catalog` | every calculator, grouped by discipline |
| `GET` | `/api/calculator/<id>` | the input schema for one calculator |
| `POST` | `/api/compute/<id>` | run it; returns groups, plots, tables, notes |
| `POST` | `/api/export/<id>` | the same run as CSV at full precision |

```bash
curl -s localhost:5000/api/compute/normal-shock \
     -H 'Content-Type: application/json' \
     -d '{"M1": 2.0, "gamma": 1.4, "known": "M1"}'
```

Inadmissible inputs return HTTP 400 with a message written for the reader —
"Periapsis is 9000 km below the surface of Earth", not a stack trace.


## Where the methods come from

`REFERENCES.md` lists the source for every method, and each calculator carries
its own citation — shown at the bottom of the results panel and returned by the
API under `calculator.references`. The primary documents (NACA Report 1135, the
U.S. Standard Atmosphere 1976, Colebrook 1939) are freely available and linked
there.

These are attribution pointers rather than transcriptions: the implementations
were written from the standard theory, so no page or equation numbers are
claimed.


## Accuracy

Values are computed in double precision. Inverse problems — Mach number from an
area ratio, the friction factor from Colebrook-White, Kepler's equation, the
θ–β–M relation, the shock-tube diaphragm ratio — are solved by bracketed
root-finding to a tolerance of about 1e-14, never by curve fits or lookup
interpolation.

Checked against published references:

- **Compressible flow** — at M = 2, γ = 1.4 the app returns p/p₀ = 0.127804525,
  ρ/ρ₀ = 0.230048146, A/A\* = 1.6875, M\* = 1.632993162, θ_max = 22.9735°.
  These were obtained by independent re-derivation from the closed-form
  relations, and are the values NACA Report 1135 tabulates for γ = 1.4. They
  have **not** been compared line-by-line against the printed report; anyone
  wanting that check can do it from the free PDF linked in `REFERENCES.md`.
- **U.S. Standard Atmosphere 1976** — 216.65 K, 22 632.06 Pa and
  0.3639176 kg/m³ at 11 km geopotential.
- **Laminate theory** — a [0/45/−45/90]s carbon/epoxy laminate returns
  Eₓ = E_y = 58.18 GPa with G = E/2(1+ν) satisfied to machine precision, which
  is the isotropy that quasi-isotropic stacking must produce, and matches the
  laminate-invariant result exactly.
- **Orbital mechanics** — a 400 km circular orbit gives a period of 92.56 min
  and 7.6686 km/s; the geostationary radius comes out at 42 164.17 km; a
  LEO-to-GEO Hohmann transfer needs 3.8926 km/s.
- **Everything else** — checked against an independent closed-form
  recomputation written separately from the implementation. The Colebrook
  friction factor, for instance, is re-solved in the tests by fixed-point
  iteration rather than by the Brent solver the application uses, so agreement
  means two different methods concur.

`tests/` holds the whole suite: 82 reference checks, a run of all 57
calculators on their defaults, and a sweep of all 1,858 combinations of every
dropdown and checkbox. See `tests/README.md` to run them.

Bugs found and fixed during validation, recorded because each produced a
plausible-looking wrong answer rather than an obvious failure:

1. The atmosphere used the WGS-84 equatorial radius instead of the effective
   radius the 1976 standard defines, shifting temperatures in the third decimal.
2. Column buckling used the strong-axis second moment of area. A column buckles
   about its **weak** axis, so a 50 × 100 mm section was reported four times
   stronger than it is. Every section now reports `I_min` and buckling uses it.
3. Channel-flow maximum velocity was read off a 200-point sample of the
   profile instead of from the parabola's vertex, costing about one part in
   10⁵. It is now solved in closed form.

Four chart defects were caught by rendering all 89 figures and reading them:
logarithmic axes were being labelled by `ScalarFormatter` on *both* axes, which
turned the Moody chart's six-decade Reynolds range into `0.00 … 1.00 ×1e8`; an
isentropic T–s diagram plotted 1e-13 of floating-point noise as a zigzag; the
pressure-vessel chart drew a sweep that excluded its own operating point; and
the V–n diagram labelled a true-airspeed abscissa as equivalent airspeed.

### A note on altitude

The atmosphere calculator distinguishes **geometric** from **geopotential**
altitude. Entering 11 000 m as a geometric altitude returns 216.77 K, not the
tabulated 216.65 K, because the standard's tables are indexed by geopotential
altitude. Both are shown. This is correct physics rather than a discrepancy.

## Adding a calculator

Write a function that takes a dict of validated inputs and returns a `Result`,
then describe its inputs:

```python
from ..core import Result, num, choice

def _my_calc(inp):
    r = Result()
    r.group("Results")
    r.headline("Answer", inp["x"] * 2, "m/s", symbol="v")
    r.out("Something else", inp["x"], note="context for the reader")
    return r

CALCULATORS = [{
    "id": "my-calc",
    "name": "My calculator",
    "category": "Aerodynamics",
    "summary": "One line describing what it does.",
    "tags": ["searchable", "keywords"],
    "inputs": [num("x", "Some input", 1.0, "m", minimum=0.0, section="Inputs")],
    "compute": _my_calc,
}]
```

Add the module to `aerocalc/modules/__init__.py`. The sidebar, search, form,
validation and result rendering all follow automatically.

Raise `CalculationError("...")` for physically impossible inputs; the message
goes straight to the user, so write it as advice about what to change.
