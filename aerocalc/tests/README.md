# Validation suite

Run from the project root:

```bash
PYTHONPATH=. python tests/test_all_defaults.py        # all 57 run on defaults
PYTHONPATH=. python tests/test_all_branches.py 0 57   # every choice/toggle branch
PYTHONPATH=. python tests/test_reference_values.py    # space, avionics, structures
PYTHONPATH=. python tests/test_reference_values_2.py  # fluids, thermo, propulsion, flight
```

The two reference-value suites check 82 quantities against published tables
(NACA 1135, USSA-1976) or against an independent closed-form recomputation
written separately from the implementation — for example the Colebrook friction
factor is re-solved here by fixed-point iteration rather than by the Brent
solver the application uses, so agreement means two different methods concur.

`test_all_branches.py` takes a start and end calculator index so it can be run
in chunks; it exercises every combination of every dropdown and checkbox
(1,858 combinations in total) and treats a `CalculationError` as a pass, since
refusing a physically impossible input is correct behaviour.
