import traceback, json
from aerocalc.modules import load_all
from aerocalc import core
load_all()
fails = []
for spec in core.all_calculators():
    payload = {}
    for f in spec["inputs"]:
        payload[f["key"]] = f["default"]
    try:
        inp = core.coerce_inputs(spec, payload)
        res = spec["compute"](inp)
        d = res.to_dict()
        json.dumps(d)
        nplots = len(d.get("plots", []))
        nrows = sum(len(g.get("rows", [])) for g in d.get("groups", []))
        print(f"OK   {spec['id']:26s} rows={nrows:3d} plots={nplots}")
    except Exception as e:
        fails.append((spec["id"], traceback.format_exc()))
        print(f"FAIL {spec['id']:26s} {type(e).__name__}: {e}")
print("\n==== FAILURES:", len(fails))
for i,(k,tb) in enumerate(fails):
    print("="*70); print(k); print(tb[-1600:])
