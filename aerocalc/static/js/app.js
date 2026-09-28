/* AeroCalc front end.
 *
 * The form is built entirely from the schema the API returns, so adding a
 * calculator on the server needs no change here. Conditional fields, units,
 * help text and validation ranges all come from the same field descriptors
 * the Python code uses.
 */

(function () {
  "use strict";

  var state = { spec: null, busy: false };

  var els = {
    welcome: document.getElementById("welcome"),
    calculator: document.getElementById("calculator"),
    category: document.getElementById("calc-category"),
    name: document.getElementById("calc-name"),
    summary: document.getElementById("calc-summary"),
    description: document.getElementById("calc-description"),
    form: document.getElementById("calc-form"),
    fields: document.getElementById("form-fields"),
    submit: document.getElementById("calc-submit"),
    reset: document.getElementById("calc-reset"),
    results: document.getElementById("results"),
    search: document.getElementById("search"),
    searchCount: document.getElementById("search-count"),
    catList: document.getElementById("cat-list"),
    noResults: document.getElementById("no-results"),
    sidebar: document.getElementById("sidebar"),
    menuToggle: document.getElementById("menu-toggle")
  };

  /* ---------------------------------------------------------------- utils */

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function isMobile() { return window.matchMedia("(max-width: 820px)").matches; }

  function closeSidebar() {
    els.sidebar.classList.remove("open");
    els.menuToggle.setAttribute("aria-expanded", "false");
    var scrim = document.querySelector(".scrim");
    if (scrim) scrim.remove();
  }

  /* --------------------------------------------------------------- search */

  els.search.addEventListener("input", function () {
    var q = els.search.value.trim().toLowerCase();
    var terms = q ? q.split(/\s+/) : [];
    var shown = 0;

    Array.prototype.forEach.call(els.catList.querySelectorAll(".cat"), function (cat) {
      var visibleInCat = 0;
      Array.prototype.forEach.call(cat.querySelectorAll(".calc-link"), function (btn) {
        var hay = btn.dataset.search;
        var match = terms.every(function (t) { return hay.indexOf(t) !== -1; });
        btn.parentElement.hidden = !match;
        if (match) { visibleInCat++; shown++; }
      });
      cat.hidden = visibleInCat === 0;
    });

    els.noResults.hidden = shown !== 0;
    els.searchCount.textContent = q
      ? shown + (shown === 1 ? " match" : " matches")
      : shown + " calculators";
  });

  /* ------------------------------------------------------------ navigation */

  document.addEventListener("click", function (e) {
    var link = e.target.closest(".calc-link");
    if (link) { selectCalculator(link.dataset.id); return; }

    var card = e.target.closest(".discipline-card");
    if (card) { selectCalculator(card.dataset.first); return; }

    if (e.target.closest(".scrim")) closeSidebar();
  });

  els.menuToggle.addEventListener("click", function () {
    var open = els.sidebar.classList.toggle("open");
    els.menuToggle.setAttribute("aria-expanded", String(open));
    if (open) {
      var scrim = el("div", "scrim");
      document.body.appendChild(scrim);
    } else {
      closeSidebar();
    }
  });

  window.addEventListener("popstate", function () {
    var id = location.hash.replace(/^#\/?/, "");
    if (id) selectCalculator(id, true); else showWelcome();
  });

  function showWelcome() {
    els.welcome.hidden = false;
    els.calculator.hidden = true;
    markCurrent(null);
    document.title = "AeroCalc — aerospace engineering calculators";
  }

  function markCurrent(id) {
    Array.prototype.forEach.call(document.querySelectorAll(".calc-link"), function (b) {
      if (b.dataset.id === id) b.setAttribute("aria-current", "true");
      else b.removeAttribute("aria-current");
    });
  }

  function selectCalculator(id, fromHistory) {
    if (!id) return;
    fetch("/api/calculator/" + encodeURIComponent(id))
      .then(function (r) {
        if (!r.ok) throw new Error("That calculator could not be loaded.");
        return r.json();
      })
      .then(function (spec) {
        state.spec = spec;
        renderHeader(spec);
        buildForm(spec);
        els.welcome.hidden = true;
        els.calculator.hidden = false;
        els.results.innerHTML = "";
        els.results.appendChild(placeholder());
        markCurrent(id);
        if (!fromHistory) history.pushState({}, "", "#/" + id);
        document.title = spec.name + " — AeroCalc";
        if (isMobile()) closeSidebar();
        window.scrollTo({ top: 0, behavior: "auto" });
        var active = document.querySelector('.calc-link[aria-current="true"]');
        if (active && !isMobile()) {
          active.scrollIntoView({ block: "nearest" });
        }
        compute();
      })
      .catch(function (err) { showError(err.message); });
  }

  function placeholder() {
    var box = el("div", "results-placeholder");
    box.appendChild(el("div", "ph-mark", "Awaiting inputs"));
    box.appendChild(document.createTextNode(
      "Set the values you know and select Calculate."));
    return box;
  }

  function renderHeader(spec) {
    els.category.textContent = spec.category;
    els.name.textContent = spec.name;
    els.summary.textContent = spec.summary;
    els.description.textContent = spec.description || "";
    els.description.hidden = !spec.description;
  }

  /* ----------------------------------------------------------- form build */

  function buildForm(spec) {
    els.fields.innerHTML = "";
    var sections = [];
    var bySection = {};

    spec.inputs.forEach(function (f) {
      var key = f.section || "Inputs";
      if (!bySection[key]) { bySection[key] = []; sections.push(key); }
      bySection[key].push(f);
    });

    sections.forEach(function (title) {
      var wrap = el("div", "field-section");
      wrap.appendChild(el("div", "field-section-title", title));
      bySection[title].forEach(function (f) { wrap.appendChild(buildField(f)); });
      els.fields.appendChild(wrap);
    });

    applyConditionals();
    els.fields.addEventListener("change", applyConditionals);
    els.fields.addEventListener("input", applyConditionals);
  }

  function buildField(f) {
    var wrap = el("div", "field");
    wrap.dataset.key = f.key;
    if (f.show_if) wrap.dataset.showIf = JSON.stringify(f.show_if);

    var id = "f_" + f.key;

    if (f.type === "toggle") {
      wrap.classList.add("toggle-field");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = id;
      cb.name = f.key;
      cb.checked = !!f.default;
      var lab = el("label", null, f.label);
      lab.htmlFor = id;
      wrap.appendChild(cb);
      var col = el("div");
      col.appendChild(lab);
      if (f.help) col.appendChild(el("div", "help", f.help));
      wrap.appendChild(col);
      return wrap;
    }

    var label = el("label", null, f.label);
    label.htmlFor = id;
    wrap.appendChild(label);

    if (f.type === "choice") {
      var sel = document.createElement("select");
      sel.id = id;
      sel.name = f.key;
      f.options.forEach(function (o) {
        var opt = document.createElement("option");
        opt.value = o.value;
        opt.textContent = o.label;
        if (o.value === f.default) opt.selected = true;
        sel.appendChild(opt);
      });
      wrap.appendChild(sel);
    } else if (f.type === "text") {
      var ti = document.createElement("input");
      ti.type = "text";
      ti.id = id;
      ti.name = f.key;
      ti.value = f.default === null || f.default === undefined ? "" : f.default;
      if (f.placeholder) ti.placeholder = f.placeholder;
      wrap.appendChild(ti);
    } else {
      var row = el("div", "input-row");
      var inp = document.createElement("input");
      inp.type = "number";
      inp.id = id;
      inp.name = f.key;
      inp.value = f.default;
      inp.step = f.type === "integer" ? "1" : "any";
      if (f.min !== null && f.min !== undefined) inp.min = f.min;
      if (f.max !== null && f.max !== undefined) inp.max = f.max;
      row.appendChild(inp);
      if (f.unit) row.appendChild(el("div", "unit", f.unit));
      wrap.appendChild(row);
    }

    if (f.help) wrap.appendChild(el("div", "help", f.help));
    return wrap;
  }

  /* Conditional visibility — mirrors the show_if descriptors from Python. */
  function applyConditionals() {
    var values = collectRaw();
    Array.prototype.forEach.call(els.fields.querySelectorAll(".field"), function (w) {
      if (!w.dataset.showIf) return;
      var cond = JSON.parse(w.dataset.showIf);
      var v = values[cond.key];
      var allowed = cond["in"];
      var match;
      if (typeof v === "boolean") {
        match = allowed.some(function (a) { return Boolean(a) === v; });
      } else if (isFinite(parseFloat(v)) && allowed.every(function (a) {
        return typeof a === "number";
      })) {
        match = allowed.indexOf(parseFloat(v)) !== -1;
      } else {
        match = allowed.indexOf(v) !== -1;
      }
      w.classList.toggle("hidden", !match);
    });
  }

  function collectRaw() {
    var out = {};
    Array.prototype.forEach.call(
      els.fields.querySelectorAll("input, select"), function (n) {
        out[n.name] = n.type === "checkbox" ? n.checked : n.value;
      });
    return out;
  }

  function collectPayload() {
    var raw = collectRaw();
    var payload = {};
    state.spec.inputs.forEach(function (f) {
      var v = raw[f.key];
      if (f.type === "toggle") payload[f.key] = !!v;
      else if (f.type === "number" || f.type === "integer") {
        payload[f.key] = v === "" || v === undefined ? f.default : parseFloat(v);
      } else payload[f.key] = v === undefined ? f.default : v;
    });
    return payload;
  }

  /* ------------------------------------------------------------- compute */

  els.form.addEventListener("submit", function (e) {
    e.preventDefault();
    compute();
  });

  els.reset.addEventListener("click", function () {
    if (state.spec) buildForm(state.spec);
    els.results.innerHTML = "";
    els.results.appendChild(placeholder());
    if (state.spec) {
      buildForm(state.spec);
      compute();
    }
  });

  function compute() {
    if (!state.spec || state.busy) return;
    state.busy = true;
    els.submit.disabled = true;
    els.submit.textContent = "Calculating…";

    var busy = el("div", "spinner-row");
    busy.appendChild(el("div", "spinner"));
    busy.appendChild(document.createTextNode("Running the calculation…"));
    els.results.innerHTML = "";
    els.results.appendChild(busy);

    fetch("/api/compute/" + encodeURIComponent(state.spec.id), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectPayload())
    })
      .then(function (r) {
        return r.json().then(function (body) { return { ok: r.ok, body: body }; });
      })
      .then(function (res) {
        if (!res.ok) { showError(res.body.error || "The calculation failed."); return; }
        renderResults(res.body);
      })
      .catch(function () {
        showError("Could not reach the calculation server. Check that it is still running.");
      })
      .finally(function () {
        state.busy = false;
        els.submit.disabled = false;
        els.submit.textContent = "Calculate";
      });
  }

  function showError(message) {
    els.results.innerHTML = "";
    var box = el("div", "error-box");
    box.appendChild(el("strong", null, "That calculation could not be run"));
    box.appendChild(document.createTextNode(message));
    els.results.appendChild(box);
  }

  /* ------------------------------------------------------------- results */

  function renderResults(data) {
    var frag = document.createDocumentFragment();

    // Headline readouts, pulled out of their groups into an instrument strip.
    var headline = [];
    data.groups.forEach(function (g) {
      g.rows.forEach(function (r) { if (r.highlight) headline.push(r); });
    });
    if (headline.length) {
      var strip = el("div", "readouts");
      headline.slice(0, 6).forEach(function (r) {
        var card = el("div", "readout");
        card.appendChild(el("div", "readout-label", r.label));
        var val = el("div", "readout-value");
        val.appendChild(document.createTextNode(r.display));
        if (r.unit) {
          var u = el("span", "readout-unit", r.unit);
          val.appendChild(u);
        }
        card.appendChild(val);
        if (r.symbol) card.appendChild(el("div", "readout-symbol", r.symbol));
        if (r.note) card.appendChild(el("div", "readout-note", r.note));
        strip.appendChild(card);
      });
      frag.appendChild(strip);
    }

    data.groups.forEach(function (g) { frag.appendChild(renderGroup(g)); });

    (data.notes || []).forEach(function (n) {
      var box = el("div", "note-box");
      box.appendChild(el("span", "note-tag", "Note"));
      box.appendChild(document.createTextNode(n));
      frag.appendChild(box);
    });

    (data.tables || []).forEach(function (t, i) {
      frag.appendChild(renderTable(t, i));
    });

    (data.plots || []).forEach(function (p, i) {
      frag.appendChild(renderFigure(p, i + 1));
    });

    var steps = (data.steps && data.steps.length) ? data.steps : buildFallbackSteps(data);
    if (steps && steps.length) {
      frag.appendChild(renderSteps(steps));
    }

    var refs = (data.calculator && data.calculator.references) || [];
    if (refs.length) {
      var r = el("div", "references");
      r.appendChild(el("span", "ref-tag", "Reference"));
      r.appendChild(document.createTextNode(refs.join("; ")));
      frag.appendChild(r);
    }

    els.results.innerHTML = "";
    els.results.appendChild(frag);
    typesetMath(els.results);
  }

  function typesetMath(root) {
    if (!root) return;
    function doRender() {
      if (window.renderMathInElement) {
        try {
          window.renderMathInElement(root, {
            delimiters: [
              { left: "$$", right: "$$", display: true },
              { left: "\\[", right: "\\]", display: true },
              { left: "$", right: "$", display: false },
              { left: "\\(", right: "\\)", display: false }
            ],
            throwOnError: false
          });
        } catch (e) {
          console.warn("KaTeX error:", e);
        }
      }
    }
    if (window.renderMathInElement) {
      doRender();
    } else {
      setTimeout(doRender, 200);
      setTimeout(doRender, 800);
    }
  }

  function sanitizeTex(str) {
    if (!str) return "";
    var s = String(str);
    s = s.replace(/·/g, " \\cdot ");
    s = s.replace(/\\cdot([a-zA-Z])/g, "\\cdot $1");
    s = s.replace(/(^|[^\\])%/g, "$1\\%");
    s = s.replace(/([a-zA-Z\\]+)_([a-zA-Z0-9]{2,})(?![{a-zA-Z0-9])/g, function (m, p1, p2) {
      if (p1.indexOf("{") === -1) {
        return p1 + "_{\\text{" + p2 + "}}";
      }
      return m;
    });
    return s;
  }

  function renderSteps(steps) {
    var sec = el("section", "calc-steps-section");

    var head = el("div", "calc-steps-head");
    var left = el("div", "calc-steps-head-left");
    left.appendChild(el("div", "calc-steps-eyebrow", "Worked Engineering Solution"));
    left.appendChild(el("h2", null, "Step-by-Step Calculations & Governing Equations"));
    left.appendChild(el("p", "calc-steps-intro",
      "College-level worked derivation showing the underlying equations, unit-consistent numerical substitutions, and physical interpretations."));
    head.appendChild(left);

    var actions = el("div", "calc-steps-actions");

    var collapseAllBtn = el("button", "btn-steps-toggle", "Collapse All Steps");
    collapseAllBtn.type = "button";
    collapseAllBtn.title = "Collapse all individual steps";

    var toggleSecBtn = el("button", "btn-steps-toggle btn-steps-secondary", "Hide Section");
    toggleSecBtn.type = "button";
    toggleSecBtn.title = "Hide / Show the entire steps section";

    actions.appendChild(collapseAllBtn);
    actions.appendChild(toggleSecBtn);
    head.appendChild(actions);
    sec.appendChild(head);

    var list = el("div", "calc-steps-list");
    steps.forEach(function (st, idx) {
      var card = el("div", "calc-step-card");

      var cardTop = el("div", "calc-step-top");
      cardTop.style.cursor = "pointer";
      cardTop.title = "Click to collapse / expand this step";
      var numStr = (idx + 1 < 10 ? "0" : "") + (idx + 1);
      cardTop.appendChild(el("span", "calc-step-badge", "STEP " + numStr));

      var titleWrap = el("div", "calc-step-title-wrap");
      var titleEl = el("h3", "calc-step-title", st.title);
      titleWrap.appendChild(titleEl);

      // Symbol badge beside the title showing what this step calculates
      var stepSymbol = st.symbol || "";
      if (!stepSymbol && st.formula && st.formula.indexOf("=") > -1) {
        var candidate = st.formula.split("=")[0].trim();
        if (candidate.length < 35 && candidate.indexOf("\\text{Method") === -1) {
          stepSymbol = candidate;
        }
      }
      if (stepSymbol) {
        var cleanSym = sanitizeTex(stepSymbol);
        var symBadge = el("span", "calc-step-symbol-badge");
        symBadge.appendChild(document.createTextNode("\\([\\ " + cleanSym + "\\ ]\\)"));
        titleWrap.appendChild(symBadge);
      }
      cardTop.appendChild(titleWrap);

      var cardToggle = el("span", "calc-step-toggle-indicator", "−");
      cardTop.appendChild(cardToggle);
      card.appendChild(cardTop);

      var cardBody = el("div", "calc-step-body");

      if (st.formula) {
        var rowF = el("div", "calc-step-row");
        rowF.appendChild(el("div", "calc-step-label", "Governing Equation"));
        var boxF = el("div", "calc-step-box calc-step-formula");
        boxF.appendChild(document.createTextNode("\\[" + sanitizeTex(st.formula) + "\\]"));
        rowF.appendChild(boxF);
        cardBody.appendChild(rowF);
      }

      if (st.substitution) {
        var rowS = el("div", "calc-step-row");
        rowS.appendChild(el("div", "calc-step-label", "Substitution with Given Values"));
        var boxS = el("div", "calc-step-box calc-step-sub");
        boxS.appendChild(document.createTextNode("\\[" + sanitizeTex(st.substitution) + "\\]"));
        rowS.appendChild(boxS);
        cardBody.appendChild(rowS);
      }

      if (st.result) {
        var rowR = el("div", "calc-step-row");
        rowR.appendChild(el("div", "calc-step-label", "Evaluated Result"));
        var boxR = el("div", "calc-step-box calc-step-result");
        boxR.appendChild(document.createTextNode("\\[" + sanitizeTex(st.result) + "\\]"));
        rowR.appendChild(boxR);
        cardBody.appendChild(rowR);
      }

      if (st.explanation) {
        var exp = el("div", "calc-step-explanation");
        exp.appendChild(el("div", "calc-step-exp-tag", "Engineering Concept & Context"));
        var p = el("p", null, st.explanation);
        exp.appendChild(p);
        cardBody.appendChild(exp);
      }

      cardTop.addEventListener("click", function () {
        var isClosed = cardBody.classList.toggle("is-collapsed");
        cardBody.style.display = isClosed ? "none" : "flex";
        cardToggle.textContent = isClosed ? "+" : "−";
      });

      card.appendChild(cardBody);
      list.appendChild(card);
    });

    sec.appendChild(list);

    var allCollapsed = false;
    collapseAllBtn.addEventListener("click", function () {
      allCollapsed = !allCollapsed;
      collapseAllBtn.textContent = allCollapsed ? "Expand All Steps" : "Collapse All Steps";
      Array.prototype.forEach.call(list.querySelectorAll(".calc-step-card"), function (card) {
        var body = card.querySelector(".calc-step-body");
        var indicator = card.querySelector(".calc-step-toggle-indicator");
        if (body) {
          body.classList.toggle("is-collapsed", allCollapsed);
          body.style.display = allCollapsed ? "none" : "flex";
        }
        if (indicator) {
          indicator.textContent = allCollapsed ? "+" : "−";
        }
      });
    });

    toggleSecBtn.addEventListener("click", function () {
      var isSecCollapsed = sec.classList.toggle("collapsed");
      list.hidden = isSecCollapsed;
      list.style.display = isSecCollapsed ? "none" : "flex";
      toggleSecBtn.textContent = isSecCollapsed ? "Show Section" : "Hide Section";
    });

    return sec;
  }

  function buildFallbackSteps(data) {
    var steps = [];
    var calc = data.calculator || {};

    // Filter only necessary, order-wise primary calculated readouts (highlighted rows first)
    var selectedRows = [];
    (data.groups || []).forEach(function (g) {
      (g.rows || []).forEach(function (r) {
        if (r.highlight) {
          selectedRows.push({ group: g, row: r });
        }
      });
    });

    // If none highlighted, take at most 1 primary row per group up to 4
    if (!selectedRows.length) {
      (data.groups || []).forEach(function (g) {
        var rows = g.rows || [];
        if (rows.length && selectedRows.length < 4) {
          selectedRows.push({ group: g, row: rows[0] });
        }
      });
    }

    // Limit strictly to 4-5 essential calculation steps
    selectedRows.slice(0, 5).forEach(function (item) {
      var r = item.row;
      var sym = r.symbol || ("\\text{" + r.label + "}");
      var unitStr = r.unit ? ("\\text{ " + sanitizeTex(r.unit) + "}") : "";
      var dispStr = sanitizeTex(r.display);
      var sub = sym + " = " + dispStr + " " + unitStr;
      var exp = r.note || ("Computed value for " + r.label + " based on governing aerospace engineering formulations.");

      steps.push({
        title: r.label,
        symbol: r.symbol || sym,
        formula: sym,
        substitution: sub,
        result: sym + " = " + dispStr + " " + unitStr,
        explanation: exp
      });
    });

    return steps;
  }

  function renderGroup(g) {
    var sec = el("section", "group");
    var head = el("div", "group-head");
    head.appendChild(el("h2", null, g.title));
    if (g.subtitle) head.appendChild(el("div", "group-subtitle", g.subtitle));
    sec.appendChild(head);

    var table = el("table", "result-table");
    var tbody = document.createElement("tbody");

    g.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      if (row.highlight) tr.className = "is-highlight";
      tr.appendChild(el("td", "label", row.label));
      tr.appendChild(el("td", "symbol", row.symbol || ""));
      tr.appendChild(el("td", "result-value", row.display));
      tr.appendChild(el("td", "unit-cell", row.unit || ""));
      tbody.appendChild(tr);

      if (row.note) {
        var nr = document.createElement("tr");
        var td = el("td", "row-note", row.note);
        td.colSpan = 4;
        nr.appendChild(td);
        tbody.appendChild(nr);
      }
    });

    table.appendChild(tbody);
    sec.appendChild(table);
    return sec;
  }

  function renderFigure(p, n) {
    var fig = el("figure", "figure");
    var img = document.createElement("img");
    img.src = p.image;
    img.alt = p.title || "Chart";
    img.loading = "lazy";
    fig.appendChild(img);
    if (p.caption || p.title) {
      var cap = el("figcaption", "figure-caption");
      cap.appendChild(el("span", "figure-number", "Fig. " + n));
      cap.appendChild(document.createTextNode(p.caption || p.title));
      fig.appendChild(cap);
    }
    return fig;
  }

  function renderTable(t, index) {
    var block = el("div", "table-block");
    var head = el("div", "table-head");
    head.appendChild(el("h3", null, t.title));

    var btn = el("button", "btn-csv", "Download CSV");
    btn.type = "button";
    btn.addEventListener("click", function () { downloadCsv(index, btn); });
    head.appendChild(btn);
    block.appendChild(head);

    var scroll = el("div", "table-scroll");
    var table = el("table", "data-table");

    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    t.columns.forEach(function (c) { htr.appendChild(el("th", null, c)); });
    thead.appendChild(htr);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    t.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      row.forEach(function (c) { tr.appendChild(el("td", null, c)); });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scroll.appendChild(table);
    block.appendChild(scroll);

    if (t.caption) {
      var cap = el("div", "figure-caption", t.caption);
      cap.style.borderTop = "0";
      cap.style.paddingTop = "0";
      block.appendChild(cap);
    }
    return block;
  }

  function downloadCsv(index, btn) {
    var payload = collectPayload();
    payload.__table__ = index;
    var original = btn.textContent;
    btn.textContent = "Preparing…";
    btn.disabled = true;

    fetch("/api/export/" + encodeURIComponent(state.spec.id), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        if (!r.ok) throw new Error("export failed");
        return r.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = state.spec.id + "-table.csv";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      })
      .catch(function () { btn.textContent = "Export failed"; })
      .finally(function () {
        setTimeout(function () {
          btn.textContent = original;
          btn.disabled = false;
        }, 900);
      });
  }

  /* --------------------------------------------------------------- start */

  var initial = location.hash.replace(/^#\/?/, "");
  if (initial) selectCalculator(initial, true);
})();
