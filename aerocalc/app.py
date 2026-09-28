"""AeroCalc — a multi-discipline aerospace engineering calculator.

The Flask layer is deliberately thin: it exposes the calculator registry as
JSON, runs one calculation per request and serialises the result.  Every
formula, every root-find and every chart lives in the ``aerocalc`` package, so
the API contract is the same whether the caller is the bundled web front end,
a script, or a future mobile client.

Run with::

    python app.py

then open http://127.0.0.1:5000
"""

from __future__ import annotations

import csv
import io
import os
import threading
import traceback

from flask import Flask, jsonify, render_template, request, Response

from aerocalc import core
from aerocalc.modules import load_all

load_all()

app = Flask(__name__)
app.json.sort_keys = False

# Matplotlib is not thread-safe: it keeps shared state in the font cache and,
# critically, in the mathtext parser used for logarithmic axis labels. Two
# threads rendering at once corrupt each other and raise a parse error part way
# through a chart. Since every chart is produced inside a compute call, one
# lock around compute is enough, and it is the only place this has to be got
# right. Catalog and schema requests stay fully concurrent.
_RENDER_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    return render_template("index.html",
                           catalog=core.catalog(),
                           total=len(core.all_calculators()))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@app.get("/api/catalog")
def api_catalog():
    """Every calculator, grouped by discipline, for the sidebar and search."""
    return jsonify({
        "categories": core.catalog(),
        "total": len(core.all_calculators()),
    })


@app.get("/api/calculator/<calc_id>")
def api_calculator(calc_id: str):
    """The input schema for one calculator; the front end builds its form from this."""
    spec = core.get(calc_id)
    if spec is None:
        return jsonify({"error": f"No calculator with id {calc_id!r}."}), 404
    return jsonify(core.public_spec(spec))


@app.post("/api/compute/<calc_id>")
def api_compute(calc_id: str):
    """Run one calculation and return grouped results, plots and tables."""
    spec = core.get(calc_id)
    if spec is None:
        return jsonify({"error": f"No calculator with id {calc_id!r}."}), 404

    payload = request.get_json(silent=True) or {}
    try:
        inputs = core.coerce_inputs(spec, payload)
        with _RENDER_LOCK:
            result = spec["compute"](inputs).to_dict()
            res_obj = spec["compute"](inputs)
            core.ensure_steps(spec, inputs, res_obj)
            result = res_obj.to_dict()
    except core.CalculationError as exc:
        # A physically inadmissible input is a normal outcome, not a crash:
        # the message is written for the user and is safe to show verbatim.
        return jsonify({"error": str(exc)}), 400
    except Exception:                                   # pragma: no cover
        app.logger.error("calculator %s failed\n%s", calc_id, traceback.format_exc())
        return jsonify({
            "error": "The calculation failed unexpectedly. Please check the "
                     "inputs, or report this combination so it can be fixed."
        }), 500

    result["calculator"] = {
        "id": spec["id"],
        "name": spec["name"],
        "category": spec["category"],
        "summary": spec["summary"],
        "description": spec.get("description", ""),
        "references": spec.get("references", []),
    }
    result["inputs"] = inputs
    return jsonify(result)


@app.post("/api/scientific/eval")
def api_scientific_eval():
    """Evaluate a scientific calculator expression or operation directly."""
    payload = request.get_json(silent=True) or {}
    spec = core.get("scientific-calculator")
    if spec is None:
        return jsonify({"error": "Scientific calculator not available."}), 500
    try:
        inputs = core.coerce_inputs(spec, payload)
        with _RENDER_LOCK:
            res_obj = spec["compute"](inputs)
            core.ensure_steps(spec, inputs, res_obj)
            result = res_obj.to_dict()
        return jsonify(result)
    except core.CalculationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Evaluation error: {exc}"}), 500


@app.post("/api/export/<calc_id>")
def api_export(calc_id: str):
    """Download a result table as CSV at full working precision.

    The on-screen tables are rounded for readability; this endpoint re-runs the
    calculation and writes the unrounded values, which is what makes the gas
    tables usable as a reference rather than just a display.
    """
    spec = core.get(calc_id)
    if spec is None:
        return jsonify({"error": f"No calculator with id {calc_id!r}."}), 404

    payload = request.get_json(silent=True) or {}
    index = int(payload.pop("__table__", 0) or 0)
    try:
        inputs = core.coerce_inputs(spec, payload)
        with _RENDER_LOCK:
            result = spec["compute"](inputs).to_dict()
    except core.CalculationError as exc:
        return jsonify({"error": str(exc)}), 400

    tables = result.get("tables", [])
    if not tables:
        return jsonify({"error": "This calculator produced no table to export."}), 400
    table = tables[min(index, len(tables) - 1)]

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([f"# {spec['name']} — {table['title']}"])
    writer.writerow([f"# generated by AeroCalc; values at 12 significant figures"])
    for key, value in inputs.items():
        writer.writerow([f"# input: {key} = {value}"])
    writer.writerow([])
    writer.writerow(table["columns"])
    for row in table["raw"]:
        writer.writerow([f"{c:.12g}" if isinstance(c, (int, float)) and not isinstance(c, bool)
                         else ("" if c is None else c) for c in row])

    # Content-Disposition must be plain ASCII, and table titles carry Greek
    # letters and em dashes, so reduce the slug to safe characters.
    slug = "".join(c if (c.isalnum() and c.isascii()) else "-"
                   for c in table["title"].lower())
    slug = "-".join(p for p in slug.split("-") if p)[:40].strip("-")
    name = f"{spec['id']}-{slug or 'table'}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found."}), 404
    return render_template("index.html", catalog=core.catalog(),
                           total=len(core.all_calculators())), 404


if __name__ == "__main__":
    # Hosting platforms supply the port in $PORT and require 0.0.0.0. Running
    # locally, neither is set, so it stays on 127.0.0.1:5000 as before.
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"AeroCalc — {len(core.all_calculators())} calculators across "
          f"{len(core.catalog())} disciplines")
    print(f" * Local access:   http://127.0.0.1:{port}")
    print(f" * Network access: http://192.168.1.11:{port} (for devices on the same Wi-Fi)")
    app.run(debug=False, host=host, port=port)
