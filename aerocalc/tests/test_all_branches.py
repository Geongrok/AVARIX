import itertools, sys, traceback  # noqa: E401
import matplotlib; matplotlib.use("Agg")
from aerocalc import plotting as P
P.render = lambda fig, **k: (__import__("matplotlib.pyplot", fromlist=["x"]).close(fig), "")[1]
from aerocalc.modules import load_all
from aerocalc import core
load_all()
lo, hi = int(sys.argv[1]), int(sys.argv[2])
fails=[]; total=0
for spec in core.all_calculators()[lo:hi]:
    fields = spec["inputs"]
    base = {f["key"]: f["default"] for f in fields}
    variants = []
    for f in fields:
        if f["type"] == "choice":
            variants.append([(f["key"], o["value"]) for o in f["options"]])
        elif f["type"] == "toggle":
            variants.append([(f["key"], True), (f["key"], False)])
    combos = list(itertools.product(*variants)) if variants else [()]
    if len(combos) > 96:
        combos = combos[::max(1, len(combos)//96)]
    for combo in combos:
        payload = dict(base); payload.update(dict(combo)); total += 1
        try:
            inp = core.coerce_inputs(spec, payload)
            spec["compute"](inp).to_dict()
        except core.CalculationError:
            pass
        except Exception:
            fails.append((spec["id"], dict(combo), traceback.format_exc()))
print(f"[{lo}:{hi}] ran {total} combos, {len(fails)} unexpected failures")
seen=set()
for cid, combo, tb in fails:
    last = tb.strip().split("\n")[-1][:150]
    if (cid,last) in seen: continue
    seen.add((cid,last))
    fl = [l for l in tb.strip().split("\n") if l.strip().startswith("File")][-1].strip()
    print("-"*70); print(cid, combo); print(" ", fl); print(" ", last)
