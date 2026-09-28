/**
 * AeroCalc - Physical Scientific Calculator Component
 * Emulates the Casio ClassWiz fx-991EX / TI-36X Pro physical calculator
 * Modes: COMP, MATRIX, EQN, SETS, TABLE & CALCULUS, BASE-N
 */

(function () {
  "use strict";

  var currentMode = "comp"; // comp | matrix | eqn | sets | table | base_n
  var angleMode = "deg";    // deg | rad | grad
  var isShift = false;
  var isAlpha = false;
  var expression = "";
  var lastAnswer = "0";
  var exactResult = "";
  var decimalResult = "0";
  var isShowingExact = false;
  var history = [];
  var historyIndex = -1;

  function init() {
    createHeaderButton();
    createCalculatorModal();
    setupKeyboardListeners();
  }

  function createHeaderButton() {
    var masthead = document.querySelector(".masthead-inner");
    if (!masthead) return;

    var btn = document.createElement("button");
    btn.className = "btn-scientific-modal-toggle";
    btn.innerHTML = '<span class="calc-icon">🖩</span> <span class="calc-text">Scientific Calculator</span>';
    btn.title = "Open Physical Scientific Calculator (Matrices, Equations, Sets, Calculus)";
    btn.addEventListener("click", toggleModal);

    // Insert before masthead-rule or meta
    var rule = masthead.querySelector(".masthead-rule");
    if (rule) {
      masthead.insertBefore(btn, rule);
    } else {
      masthead.appendChild(btn);
    }
  }

  function toggleModal() {
    var modal = document.getElementById("phys-calc-modal");
    if (!modal) return;
    var isOpen = modal.classList.toggle("is-open");
    if (isOpen) {
      modal.setAttribute("aria-hidden", "false");
      var input = document.getElementById("phys-calc-expr-input");
      if (input) input.focus();
      typesetScreen();
    } else {
      modal.setAttribute("aria-hidden", "true");
    }
  }

  function createCalculatorModal() {
    var overlay = document.createElement("div");
    overlay.id = "phys-calc-modal";
    overlay.className = "phys-calc-modal";
    overlay.setAttribute("aria-hidden", "true");

    var backdrop = document.createElement("div");
    backdrop.className = "phys-calc-backdrop";
    backdrop.addEventListener("click", toggleModal);
    overlay.appendChild(backdrop);

    var container = document.createElement("div");
    container.className = "phys-calc-container";

    // Header bar of the modal
    var modalHead = document.createElement("div");
    modalHead.className = "phys-calc-modal-head";
    modalHead.innerHTML = `
      <div class="phys-calc-brand">
        <span class="brand-logo">AeroCalc</span>
        <span class="brand-model">fx-991EX CLASSWIZ <em>College Edition</em></span>
      </div>
      <div class="phys-calc-solar-cell" title="High-efficiency dual solar cell emulation"></div>
      <button type="button" class="phys-calc-close-btn" title="Close Calculator (Esc)">✕</button>
    `;
    modalHead.querySelector(".phys-calc-close-btn").addEventListener("click", toggleModal);
    container.appendChild(modalHead);

    // Natural Textbook LCD Screen
    var screen = document.createElement("div");
    screen.className = "phys-calc-screen";
    screen.innerHTML = `
      <div class="screen-status-bar">
        <span class="st-indicator st-deg active" id="st-deg">DEG</span>
        <span class="st-indicator st-rad" id="st-rad">RAD</span>
        <span class="st-indicator st-shift" id="st-shift">SHIFT</span>
        <span class="st-indicator st-alpha" id="st-alpha">ALPHA</span>
        <span class="st-indicator st-math active">MATH</span>
        <span class="st-indicator st-mode" id="st-mode-label">COMP</span>
      </div>
      <div class="screen-expr-line" id="screen-expr-line">
        <input type="text" id="phys-calc-expr-input" class="screen-expr-input"
               placeholder="0" autocomplete="off" spellcheck="false" />
      </div>
      <div class="screen-render-line" id="screen-render-line"></div>
      <div class="screen-result-line" id="screen-result-line">
        <span class="result-sd-badge" id="btn-sd-toggle" title="Toggle Standard/Exact Fraction & Decimal (S<=>D)">S<=>D</span>
        <div class="result-value" id="screen-result-value">0</div>
      </div>
    `;
    container.appendChild(screen);

    // Mode Selector Pills
    var modeBar = document.createElement("div");
    modeBar.className = "phys-calc-mode-bar";
    modeBar.innerHTML = `
      <button type="button" class="btn-mode active" data-mode="comp">1: COMP</button>
      <button type="button" class="btn-mode" data-mode="matrix">2: MATRIX</button>
      <button type="button" class="btn-mode" data-mode="eqn">3: EQN</button>
      <button type="button" class="btn-mode" data-mode="sets">4: SETS</button>
      <button type="button" class="btn-mode" data-mode="table">5: TABLE & CALC</button>
      <button type="button" class="btn-mode" data-mode="base_n">6: BASE-N</button>
    `;
    modeBar.querySelectorAll(".btn-mode").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setMode(this.getAttribute("data-mode"));
      });
    });
    container.appendChild(modeBar);

    // Specialized Mode Panels (Matrix, Eqn, Sets, Table, Base-N)
    var modePanels = document.createElement("div");
    modePanels.className = "phys-calc-special-panels";
    modePanels.innerHTML = buildSpecialPanelsHTML();
    container.appendChild(modePanels);

    // Physical Hardware Keypad
    var keypad = document.createElement("div");
    keypad.className = "phys-calc-keypad";
    keypad.innerHTML = buildKeypadHTML();
    container.appendChild(keypad);

    // Step-by-Step Mini-Tray for the modal
    var stepTray = document.createElement("div");
    stepTray.className = "phys-calc-step-tray";
    stepTray.id = "phys-calc-step-tray";
    stepTray.innerHTML = `
      <div class="tray-head">
        <span class="tray-title">Step-by-Step Derivation</span>
        <button type="button" class="tray-toggle-btn" id="tray-toggle-btn">Show Steps</button>
      </div>
      <div class="tray-body" id="tray-body" style="display:none;">
        <p class="tray-placeholder">Execute a calculation to see its step-by-step mathematical proof.</p>
      </div>
    `;
    container.appendChild(stepTray);

    overlay.appendChild(container);
    document.body.appendChild(overlay);

    setupKeypadEvents(container);
    setupSpecialPanelEvents(container);
  }

  function buildSpecialPanelsHTML() {
    return `
      <!-- MATRIX PANEL -->
      <div class="special-panel" id="panel-matrix" style="display:none;">
        <div class="panel-section-title">Matrix Operations [A] & [B]</div>
        <div class="matrix-grid-controls">
          <label>Dims:
            <select id="matrix-a-dim">
              <option value="2x2">2 × 2</option>
              <option value="3x3" selected>3 × 3</option>
              <option value="4x4">4 × 4</option>
            </select>
          </label>
          <div class="matrix-op-buttons">
            <button type="button" class="btn-op-action" data-mat-op="det_a">det(A)</button>
            <button type="button" class="btn-op-action" data-mat-op="inv_a">A⁻¹</button>
            <button type="button" class="btn-op-action" data-mat-op="mult">A × B</button>
            <button type="button" class="btn-op-action" data-mat-op="add">A + B</button>
            <button type="button" class="btn-op-action" data-mat-op="eigen">Eigenvalues</button>
          </div>
        </div>
        <div class="matrix-inputs-row">
          <div class="matrix-input-box">
            <span class="box-label">Matrix A</span>
            <textarea id="mat-a-text" rows="3" placeholder="1, 2, 3&#10;0, 1, 4&#10;5, 6, 0">1, 2, 3&#10;0, 1, 4&#10;5, 6, 0</textarea>
          </div>
          <div class="matrix-input-box">
            <span class="box-label">Matrix B</span>
            <textarea id="mat-b-text" rows="3" placeholder="2, 0, -1&#10;1, 3, 2&#10;0, -2, 1">2, 0, -1&#10;1, 3, 2&#10;0, -2, 1</textarea>
          </div>
        </div>
      </div>

      <!-- EQN PANEL -->
      <div class="special-panel" id="panel-eqn" style="display:none;">
        <div class="panel-section-title">Simultaneous Linear Systems & Polynomial Roots</div>
        <div class="eqn-type-selector">
          <button type="button" class="btn-eqn-type active" data-eqn="poly_quad">Quadratic (ax²+bx+c=0)</button>
          <button type="button" class="btn-eqn-type" data-eqn="poly_cubic">Cubic (ax³+bx²+cx+d=0)</button>
          <button type="button" class="btn-eqn-type" data-eqn="linear_2x2">2×2 Linear System</button>
          <button type="button" class="btn-eqn-type" data-eqn="linear_3x3">3×3 Linear System</button>
        </div>
        <div class="eqn-inputs-grid" id="eqn-inputs-grid">
          <!-- Dynamically populated -->
        </div>
      </div>

      <!-- SETS PANEL -->
      <div class="special-panel" id="panel-sets" style="display:none;">
        <div class="panel-section-title">Set Theory & Discrete Relations</div>
        <div class="sets-inputs-row">
          <div class="set-input-group">
            <label>Set A = {</label>
            <input type="text" id="set-a-input" value="1, 2, 3, 4, 5" placeholder="comma separated" />
            <span>}</span>
          </div>
          <div class="set-input-group">
            <label>Set B = {</label>
            <input type="text" id="set-b-input" value="3, 4, 5, 6, 7" placeholder="comma separated" />
            <span>}</span>
          </div>
        </div>
        <div class="sets-buttons-grid">
          <button type="button" class="btn-set-action" data-set-op="union">Union (A ∪ B)</button>
          <button type="button" class="btn-set-action" data-set-op="inter">Intersection (A ∩ B)</button>
          <button type="button" class="btn-set-action" data-set-op="diff_ab">Difference (A \\ B)</button>
          <button type="button" class="btn-set-action" data-set-op="diff_ba">Difference (B \\ A)</button>
          <button type="button" class="btn-set-action" data-set-op="sym">Symmetric Diff (A Δ B)</button>
          <button type="button" class="btn-set-action" data-set-op="power">Power Set P(A)</button>
        </div>
      </div>

      <!-- TABLE & CALCULUS PANEL -->
      <div class="special-panel" id="panel-table" style="display:none;">
        <div class="panel-section-title">Function Table, Differentiation & Integration</div>
        <div class="table-calc-subtypes">
          <button type="button" class="btn-calc-sub active" data-sub="table">Table (x, f(x))</button>
          <button type="button" class="btn-calc-sub" data-sub="deriv">Derivative d/dx</button>
          <button type="button" class="btn-calc-sub" data-sub="integral">Definite Integral ∫</button>
        </div>
        <div class="table-calc-inputs">
          <div class="calc-input-row">
            <label>f(x) = </label>
            <input type="text" id="calc-fx-input" value="x**2 - 4*cos(x)" placeholder="e.g. x^2 - 4*cos(x)" />
          </div>
          <div class="calc-range-row" id="calc-range-row">
            <label>Start: <input type="number" id="calc-xstart" value="-3" step="0.5" /></label>
            <label>End: <input type="number" id="calc-xend" value="3" step="0.5" /></label>
            <label>Step Δx: <input type="number" id="calc-xstep" value="0.5" step="0.1" /></label>
          </div>
          <div class="calc-eval-row" id="calc-eval-row" style="display:none;">
            <label>Point a: <input type="number" id="calc-xpoint" value="1.0" step="0.1" /></label>
          </div>
          <div class="calc-int-row" id="calc-int-row" style="display:none;">
            <label>Lower a: <input type="number" id="calc-int-a" value="0" step="0.1" /></label>
            <label>Upper b: <input type="number" id="calc-int-b" value="2" step="0.1" /></label>
          </div>
        </div>
      </div>

      <!-- BASE-N PANEL -->
      <div class="special-panel" id="panel-base_n" style="display:none;">
        <div class="panel-section-title">Radix Bases, Bitwise Logic & Number Theory</div>
        <div class="base-inputs-row">
          <label>Number A: <input type="number" id="base-a-input" value="255" /></label>
          <label>Number B: <input type="number" id="base-b-input" value="15" /></label>
        </div>
        <div class="base-readouts-grid">
          <div class="base-badge">DEC: <strong id="base-dec">255</strong></div>
          <div class="base-badge">HEX: <strong id="base-hex">0xFF</strong></div>
          <div class="base-badge">BIN: <strong id="base-bin">0b11111111</strong></div>
          <div class="base-badge">OCT: <strong id="base-oct">0o377</strong></div>
        </div>
      </div>
    `;
  }

  function buildKeypadHTML() {
    return `
      <!-- Row 1: Function Control -->
      <div class="keypad-row control-row">
        <button type="button" class="calc-key key-shift" data-action="shift">SHIFT</button>
        <button type="button" class="calc-key key-alpha" data-action="alpha">ALPHA</button>
        <div class="dpad-cluster">
          <button type="button" class="dpad-btn dpad-up" data-action="arrow-up">▲</button>
          <button type="button" class="dpad-btn dpad-left" data-action="arrow-left">◀</button>
          <button type="button" class="dpad-btn dpad-right" data-action="arrow-right">▶</button>
          <button type="button" class="dpad-btn dpad-down" data-action="arrow-down">▼</button>
        </div>
        <button type="button" class="calc-key key-menu" data-action="angle-toggle" id="btn-angle-toggle">DEG</button>
        <button type="button" class="calc-key key-on" data-action="clear-all">ON/AC</button>
      </div>

      <!-- Row 2: Scientific Functions 1 -->
      <div class="keypad-row">
        <button type="button" class="calc-key key-fn" data-insert="**(-1)" data-shift="factorial" title="x⁻¹ / x!">x⁻¹</button>
        <button type="button" class="calc-key key-fn" data-insert="sqrt(" data-shift="cbrt(" title="√ / ∛">√</button>
        <button type="button" class="calc-key key-fn" data-insert="**2" data-shift="**3" title="x² / x³">x²</button>
        <button type="button" class="calc-key key-fn" data-insert="^" data-shift="sqrt(" title="xʸ / ʸ√x">xʸ</button>
        <button type="button" class="calc-key key-fn" data-insert="log(" data-shift="10**" title="log₁₀ / 10ˣ">log</button>
        <button type="button" class="calc-key key-fn" data-insert="ln(" data-shift="exp(" title="ln / eˣ">ln</button>
      </div>

      <!-- Row 3: Scientific Functions 2 -->
      <div class="keypad-row">
        <button type="button" class="calc-key key-fn" data-insert="-" title="Negative">(-)</button>
        <button type="button" class="calc-key key-fn" data-insert="°" data-shift="atan2(" title="DMS / Polar">° ' "</button>
        <button type="button" class="calc-key key-fn" data-insert="sin(" data-shift="asin(" title="sin / sin⁻¹">sin</button>
        <button type="button" class="calc-key key-fn" data-insert="cos(" data-shift="acos(" title="cos / cos⁻¹">cos</button>
        <button type="button" class="calc-key key-fn" data-insert="tan(" data-shift="atan(" title="tan / tan⁻¹">tan</button>
        <button type="button" class="calc-key key-fn" data-insert="pi" data-shift="e" title="π / e">π</button>
      </div>

      <!-- Row 4: Memory & Parens -->
      <div class="keypad-row">
        <button type="button" class="calc-key key-fn" data-insert="/" title="Fraction a/b">a/b</button>
        <button type="button" class="calc-key key-fn" data-action="toggle-sd" title="S<=>D Fraction/Decimal">S<=>D</button>
        <button type="button" class="calc-key key-fn" data-insert="(">(</button>
        <button type="button" class="calc-key key-fn" data-insert=")">)</button>
        <button type="button" class="calc-key key-fn" data-insert="nCr(" data-shift="nPr(" title="nCr / nPr">nCr</button>
        <button type="button" class="calc-key key-fn" data-action="ans-recall" title="Ans">Ans</button>
      </div>

      <!-- Numeric Keypad Rows -->
      <div class="keypad-row">
        <button type="button" class="calc-key key-num" data-insert="7">7</button>
        <button type="button" class="calc-key key-num" data-insert="8">8</button>
        <button type="button" class="calc-key key-num" data-insert="9">9</button>
        <button type="button" class="calc-key key-del" data-action="backspace">DEL</button>
        <button type="button" class="calc-key key-ac" data-action="clear-all">AC</button>
      </div>
      <div class="keypad-row">
        <button type="button" class="calc-key key-num" data-insert="4">4</button>
        <button type="button" class="calc-key key-num" data-insert="5">5</button>
        <button type="button" class="calc-key key-num" data-insert="6">6</button>
        <button type="button" class="calc-key key-op" data-insert=" * ">×</button>
        <button type="button" class="calc-key key-op" data-insert=" / ">÷</button>
      </div>
      <div class="keypad-row">
        <button type="button" class="calc-key key-num" data-insert="1">1</button>
        <button type="button" class="calc-key key-num" data-insert="2">2</button>
        <button type="button" class="calc-key key-num" data-insert="3">3</button>
        <button type="button" class="calc-key key-op" data-insert=" + ">+</button>
        <button type="button" class="calc-key key-op" data-insert=" - ">−</button>
      </div>
      <div class="keypad-row">
        <button type="button" class="calc-key key-num" data-insert="0">0</button>
        <button type="button" class="calc-key key-num" data-insert=".">.</button>
        <button type="button" class="calc-key key-fn" data-insert=" * 10^">×10ˣ</button>
        <button type="button" class="calc-key key-fn" data-action="ans-recall">Ans</button>
        <button type="button" class="calc-key key-exe" data-action="execute">=</button>
      </div>
    `;
  }

  function setupKeypadEvents(root) {
    root.querySelectorAll(".calc-key, .dpad-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        handleButtonPress(this);
      });
    });

    var exprInput = root.querySelector("#phys-calc-expr-input");
    if (exprInput) {
      exprInput.addEventListener("input", function () {
        expression = this.value;
        typesetScreen();
      });
      exprInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          executeCalculation();
        } else if (e.key === "Escape") {
          e.preventDefault();
          clearAll();
        }
      });
    }

    var sdBtn = root.querySelector("#btn-sd-toggle");
    if (sdBtn) {
      sdBtn.addEventListener("click", toggleSD);
    }

    var trayToggle = root.querySelector("#tray-toggle-btn");
    var trayBody = root.querySelector("#tray-body");
    if (trayToggle && trayBody) {
      trayToggle.addEventListener("click", function () {
        var isHidden = trayBody.style.display === "none";
        trayBody.style.display = isHidden ? "block" : "none";
        this.textContent = isHidden ? "Hide Steps" : "Show Steps";
      });
    }
  }

  function handleButtonPress(btn) {
    var action = btn.getAttribute("data-action");
    var insert = btn.getAttribute("data-insert");
    var shiftInsert = btn.getAttribute("data-shift");

    if (action === "shift") {
      isShift = !isShift;
      updateShiftAlphaIndicators();
      return;
    }
    if (action === "alpha") {
      isAlpha = !isAlpha;
      updateShiftAlphaIndicators();
      return;
    }
    if (action === "angle-toggle") {
      cycleAngleMode();
      return;
    }
    if (action === "clear-all") {
      clearAll();
      return;
    }
    if (action === "backspace") {
      backspace();
      return;
    }
    if (action === "execute") {
      executeCalculation();
      return;
    }
    if (action === "toggle-sd") {
      toggleSD();
      return;
    }
    if (action === "ans-recall") {
      insertText(lastAnswer);
      return;
    }

    // Insert text
    var textToInsert = insert || "";
    if (isShift && shiftInsert) {
      textToInsert = shiftInsert;
      isShift = false;
      updateShiftAlphaIndicators();
    }
    if (textToInsert) {
      insertText(textToInsert);
    }
  }

  function insertText(txt) {
    var input = document.getElementById("phys-calc-expr-input");
    if (!input) return;
    var start = input.selectionStart || input.value.length;
    var end = input.selectionEnd || input.value.length;
    var before = input.value.substring(0, start);
    var after = input.value.substring(end);
    input.value = before + txt + after;
    input.selectionStart = input.selectionEnd = start + txt.length;
    expression = input.value;
    input.focus();
    typesetScreen();
  }

  function backspace() {
    var input = document.getElementById("phys-calc-expr-input");
    if (!input) return;
    var start = input.selectionStart;
    var end = input.selectionEnd;
    if (start === end && start > 0) {
      input.value = input.value.substring(0, start - 1) + input.value.substring(end);
      input.selectionStart = input.selectionEnd = start - 1;
    } else if (start !== end) {
      input.value = input.value.substring(0, start) + input.value.substring(end);
      input.selectionStart = input.selectionEnd = start;
    }
    expression = input.value;
    input.focus();
    typesetScreen();
  }

  function clearAll() {
    var input = document.getElementById("phys-calc-expr-input");
    if (input) {
      input.value = "";
      expression = "";
      input.focus();
    }
    var resEl = document.getElementById("screen-result-value");
    if (resEl) resEl.textContent = "0";
    var renderEl = document.getElementById("screen-render-line");
    if (renderEl) renderEl.innerHTML = "";
    decimalResult = "0";
    exactResult = "";
    isShowingExact = false;
  }

  function toggleSD() {
    if (!exactResult) return;
    isShowingExact = !isShowingExact;
    var resEl = document.getElementById("screen-result-value");
    if (!resEl) return;
    resEl.innerHTML = isShowingExact ? ("\\(" + exactResult + "\\)") : ("\\(" + decimalResult + "\\)");
    if (window.renderMathInElement) {
      window.renderMathInElement(resEl, { throwOnError: false });
    }
  }

  function cycleAngleMode() {
    if (angleMode === "deg") angleMode = "rad";
    else if (angleMode === "rad") angleMode = "grad";
    else angleMode = "deg";

    var stDeg = document.getElementById("st-deg");
    var stRad = document.getElementById("st-rad");
    var btn = document.getElementById("btn-angle-toggle");

    if (stDeg) stDeg.classList.toggle("active", angleMode === "deg");
    if (stRad) stRad.classList.toggle("active", angleMode === "rad");
    if (btn) btn.textContent = angleMode.toUpperCase();

    // Re-evaluate if there is an expression
    if (expression) executeCalculation();
  }

  function updateShiftAlphaIndicators() {
    var stShift = document.getElementById("st-shift");
    var stAlpha = document.getElementById("st-alpha");
    if (stShift) stShift.classList.toggle("active", isShift);
    if (stAlpha) stAlpha.classList.toggle("active", isAlpha);
  }

  function typesetScreen() {
    var renderEl = document.getElementById("screen-render-line");
    if (!renderEl) return;
    if (!expression.trim()) {
      renderEl.innerHTML = "";
      return;
    }
    // Clean expression to display nicely in LaTeX
    var tex = expression
      .replace(/\*/g, " \\times ")
      .replace(/\//g, " \\div ")
      .replace(/sqrt\(/g, "\\sqrt{")
      .replace(/pi/g, "\\pi ")
      .replace(/\^/g, "^");

    renderEl.innerHTML = "\\(" + tex + "\\)";
    if (window.renderMathInElement) {
      window.renderMathInElement(renderEl, { throwOnError: false });
    }
  }

  function executeCalculation() {
    if (currentMode !== "comp") {
      executeSpecialMode();
      return;
    }

    if (!expression.trim()) return;

    var payload = {
      calc_mode: "comp",
      comp_expr: expression,
      angle_mode: angleMode
    };

    fetch("/api/scientific/eval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          showScreenError(data.error);
          return;
        }
        var headVal = "0";
        var exactVal = "";
        (data.groups || []).forEach(function (g) {
          (g.rows || []).forEach(function (r) {
            if (r.symbol === "Ans") headVal = r.display;
            if (r.symbol === "S\\Leftrightarrow D") exactVal = r.display;
          });
        });

        decimalResult = headVal;
        lastAnswer = headVal;
        exactResult = exactVal;
        isShowingExact = false;

        var resEl = document.getElementById("screen-result-value");
        if (resEl) {
          resEl.innerHTML = "\\(" + decimalResult + "\\)";
          if (window.renderMathInElement) {
            window.renderMathInElement(resEl, { throwOnError: false });
          }
        }

        renderStepTray(data.steps || []);
      })
      .catch(function (err) {
        showScreenError("Network error: " + err);
      });
  }

  function showScreenError(msg) {
    var resEl = document.getElementById("screen-result-value");
    if (resEl) {
      resEl.textContent = "Math ERROR";
    }
    var trayBody = document.getElementById("tray-body");
    if (trayBody) {
      trayBody.innerHTML = '<p class="tray-error">' + msg + '</p>';
    }
  }

  function renderStepTray(steps) {
    var trayBody = document.getElementById("tray-body");
    if (!trayBody) return;
    if (!steps || !steps.length) {
      trayBody.innerHTML = '<p class="tray-placeholder">No intermediate steps required for this standard calculation.</p>';
      return;
    }
    var html = '<div class="tray-steps-list">';
    steps.forEach(function (st, idx) {
      html += `
        <div class="tray-step-card">
          <div class="tray-step-title">STEP 0${idx + 1}: ${st.title} ${st.symbol ? `\\([\\ ${st.symbol}\\ ]\\)` : ''}</div>
          ${st.formula ? `<div class="tray-step-math">\\[ ${st.formula} \\]</div>` : ''}
          ${st.substitution ? `<div class="tray-step-sub">Substitution: \\[ ${st.substitution} \\]</div>` : ''}
          ${st.result ? `<div class="tray-step-res">Result: \\[ ${st.result} \\]</div>` : ''}
          ${st.explanation ? `<div class="tray-step-exp">${st.explanation}</div>` : ''}
        </div>
      `;
    });
    html += '</div>';
    trayBody.innerHTML = html;
    if (window.renderMathInElement) {
      window.renderMathInElement(trayBody, { throwOnError: false });
    }
  }

  function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll(".phys-calc-mode-bar .btn-mode").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });

    var stLabel = document.getElementById("st-mode-label");
    if (stLabel) stLabel.textContent = mode.toUpperCase();

    // Toggle special panels
    document.querySelectorAll(".special-panel").forEach(function (p) {
      p.style.display = "none";
    });
    var activePanel = document.getElementById("panel-" + mode);
    if (activePanel) {
      activePanel.style.display = "block";
    }

    if (mode === "eqn") {
      updateEqnInputsGrid();
    }
  }

  function setupSpecialPanelEvents(root) {
    // Matrix Actions
    root.querySelectorAll(".btn-op-action").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var op = this.getAttribute("data-mat-op");
        executeMatrixOp(op);
      });
    });

    // Eqn Type Selection
    root.querySelectorAll(".btn-eqn-type").forEach(function (btn) {
      btn.addEventListener("click", function () {
        root.querySelectorAll(".btn-eqn-type").forEach(function (b) { b.classList.remove("active"); });
        this.classList.add("active");
        updateEqnInputsGrid();
      });
    });

    // Sets Actions
    root.querySelectorAll(".btn-set-action").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var op = this.getAttribute("data-set-op");
        executeSetsOp(op);
      });
    });

    // Calculus Subtype Selection
    root.querySelectorAll(".btn-calc-sub").forEach(function (btn) {
      btn.addEventListener("click", function () {
        root.querySelectorAll(".btn-calc-sub").forEach(function (b) { b.classList.remove("active"); });
        this.classList.add("active");
        var sub = this.getAttribute("data-sub");
        var rangeRow = root.querySelector("#calc-range-row");
        var evalRow = root.querySelector("#calc-eval-row");
        var intRow = root.querySelector("#calc-int-row");
        if (rangeRow) rangeRow.style.display = sub === "table" ? "flex" : "none";
        if (evalRow) evalRow.style.display = sub === "deriv" ? "flex" : "none";
        if (intRow) intRow.style.display = sub === "integral" ? "flex" : "none";
      });
    });

    // Base-N Inputs
    var baseA = root.querySelector("#base-a-input");
    var baseB = root.querySelector("#base-b-input");
    if (baseA) baseA.addEventListener("input", updateBaseNReadouts);
    if (baseB) baseB.addEventListener("input", updateBaseNReadouts);
  }

  function updateEqnInputsGrid() {
    var container = document.getElementById("eqn-inputs-grid");
    if (!container) return;
    var activeBtn = document.querySelector(".btn-eqn-type.active");
    var eqnType = activeBtn ? activeBtn.getAttribute("data-eqn") : "poly_quad";

    var html = "";
    if (eqnType === "poly_quad") {
      html = `
        <div class="eqn-poly-row">
          <label>a: <input type="number" id="poly-a" value="1" step="any" /></label>
          <label>b: <input type="number" id="poly-b" value="-5" step="any" /></label>
          <label>c: <input type="number" id="poly-c" value="6" step="any" /></label>
          <button type="button" class="btn-execute-special" id="btn-solve-eqn">Solve Roots</button>
        </div>
      `;
    } else if (eqnType === "poly_cubic") {
      html = `
        <div class="eqn-poly-row">
          <label>a: <input type="number" id="poly-a" value="1" step="any" /></label>
          <label>b: <input type="number" id="poly-b" value="-6" step="any" /></label>
          <label>c: <input type="number" id="poly-c" value="11" step="any" /></label>
          <label>d: <input type="number" id="poly-d" value="-6" step="any" /></label>
          <button type="button" class="btn-execute-special" id="btn-solve-eqn">Solve Roots</button>
        </div>
      `;
    } else if (eqnType === "linear_2x2") {
      html = `
        <div class="eqn-linear-grid">
          <div class="linear-row">a₁ <input type="number" id="l-a1" value="2" /> x + b₁ <input type="number" id="l-b1" value="3" /> y = c₁ <input type="number" id="l-c1" value="8" /></div>
          <div class="linear-row">a₂ <input type="number" id="l-a2" value="1" /> x + b₂ <input type="number" id="l-b2" value="-1" /> y = c₂ <input type="number" id="l-c2" value="-1" /></div>
          <button type="button" class="btn-execute-special" id="btn-solve-eqn">Solve (x, y)</button>
        </div>
      `;
    } else if (eqnType === "linear_3x3") {
      html = `
        <div class="eqn-linear-grid">
          <div class="linear-row"><input type="number" id="l-a1" value="1" />x + <input type="number" id="l-b1" value="1" />y + <input type="number" id="l-c1" value="1" />z = <input type="number" id="l-d1" value="6" /></div>
          <div class="linear-row"><input type="number" id="l-a2" value="0" />x + <input type="number" id="l-b2" value="2" />y + <input type="number" id="l-c2" value="5" />z = <input type="number" id="l-d2" value="-4" /></div>
          <div class="linear-row"><input type="number" id="l-a3" value="2" />x + <input type="number" id="l-b3" value="5" />y + <input type="number" id="l-c3" value="-1" />z = <input type="number" id="l-d3" value="27" /></div>
          <button type="button" class="btn-execute-special" id="btn-solve-eqn">Solve (x, y, z)</button>
        </div>
      `;
    }
    container.innerHTML = html;
    var solveBtn = container.querySelector("#btn-solve-eqn");
    if (solveBtn) {
      solveBtn.addEventListener("click", executeEqnSolve);
    }
  }

  function executeMatrixOp(op) {
    var matA = document.getElementById("mat-a-text").value;
    var matB = document.getElementById("mat-b-text").value;
    var payload = {
      calc_mode: "matrix",
      mat_op: op,
      mat_a: matA,
      mat_b: matB
    };

    fetch("/api/scientific/eval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          showScreenError(data.error);
          return;
        }
        var head = (data.groups && data.groups[0] && data.groups[0].rows && data.groups[0].rows[0])
          ? data.groups[0].rows[0].display : "Success";
        var resEl = document.getElementById("screen-result-value");
        if (resEl) {
          resEl.innerHTML = "\\(" + head + "\\)";
          if (window.renderMathInElement) window.renderMathInElement(resEl, { throwOnError: false });
        }
        renderStepTray(data.steps || []);
      })
      .catch(function (e) { showScreenError(e); });
  }

  function executeEqnSolve() {
    var activeBtn = document.querySelector(".btn-eqn-type.active");
    var eqnType = activeBtn ? activeBtn.getAttribute("data-eqn") : "poly_quad";
    var payload = {
      calc_mode: "eqn",
      eqn_type: eqnType
    };

    if (eqnType.startsWith("poly")) {
      payload.poly_a = parseFloat(document.getElementById("poly-a").value || 1);
      payload.poly_b = parseFloat(document.getElementById("poly-b").value || 0);
      payload.poly_c = parseFloat(document.getElementById("poly-c").value || 0);
      if (eqnType === "poly_cubic") {
        payload.poly_d = parseFloat(document.getElementById("poly-d").value || 0);
      }
    } else if (eqnType === "linear_2x2") {
      payload.a1 = parseFloat(document.getElementById("l-a1").value || 0);
      payload.b1 = parseFloat(document.getElementById("l-b1").value || 0);
      payload.c1 = parseFloat(document.getElementById("l-c1").value || 0);
      payload.a2 = parseFloat(document.getElementById("l-a2").value || 0);
      payload.b2 = parseFloat(document.getElementById("l-b2").value || 0);
      payload.c2 = parseFloat(document.getElementById("l-c2").value || 0);
    } else if (eqnType === "linear_3x3") {
      payload.a1 = parseFloat(document.getElementById("l-a1").value || 0);
      payload.b1 = parseFloat(document.getElementById("l-b1").value || 0);
      payload.c1 = parseFloat(document.getElementById("l-c1").value || 0);
      payload.d1 = parseFloat(document.getElementById("l-d1").value || 0);
      payload.a2 = parseFloat(document.getElementById("l-a2").value || 0);
      payload.b2 = parseFloat(document.getElementById("l-b2").value || 0);
      payload.c2 = parseFloat(document.getElementById("l-c2").value || 0);
      payload.d2 = parseFloat(document.getElementById("l-d2").value || 0);
      payload.a3 = parseFloat(document.getElementById("l-a3").value || 0);
      payload.b3 = parseFloat(document.getElementById("l-b3").value || 0);
      payload.c3 = parseFloat(document.getElementById("l-c3").value || 0);
      payload.d3 = parseFloat(document.getElementById("l-d3").value || 0);
    }

    fetch("/api/scientific/eval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          showScreenError(data.error);
          return;
        }
        var resStr = "";
        (data.groups || []).forEach(function (g) {
          (g.rows || []).forEach(function (r) {
            if (r.highlight) resStr += r.symbol + " = " + r.display + "; ";
          });
        });
        var resEl = document.getElementById("screen-result-value");
        if (resEl) {
          resEl.innerHTML = "\\(" + (resStr || "Solved") + "\\)";
          if (window.renderMathInElement) window.renderMathInElement(resEl, { throwOnError: false });
        }
        renderStepTray(data.steps || []);
      })
      .catch(function (e) { showScreenError(e); });
  }

  function executeSetsOp(op) {
    var setA = document.getElementById("set-a-input").value;
    var setB = document.getElementById("set-b-input").value;
    var payload = {
      calc_mode: "sets",
      set_a: setA,
      set_b: setB
    };

    fetch("/api/scientific/eval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          showScreenError(data.error);
          return;
        }
        var targetSymbol = "A \\cup B";
        if (op === "inter") targetSymbol = "A \\cap B";
        if (op === "diff_ab") targetSymbol = "A \\setminus B";
        if (op === "diff_ba") targetSymbol = "B \\setminus A";
        if (op === "sym") targetSymbol = "A \\triangle B";
        if (op === "power") targetSymbol = "\\mathcal{P}(A)";

        var resVal = "";
        (data.groups || []).forEach(function (g) {
          (g.rows || []).forEach(function (r) {
            if (r.symbol === targetSymbol) resVal = r.display;
          });
        });
        var resEl = document.getElementById("screen-result-value");
        if (resEl) {
          resEl.innerHTML = "\\(" + (resVal || "Computed") + "\\)";
          if (window.renderMathInElement) window.renderMathInElement(resEl, { throwOnError: false });
        }
        renderStepTray(data.steps || []);
      })
      .catch(function (e) { showScreenError(e); });
  }

  function executeSpecialMode() {
    if (currentMode === "matrix") {
      executeMatrixOp("det_a");
    } else if (currentMode === "eqn") {
      executeEqnSolve();
    } else if (currentMode === "sets") {
      executeSetsOp("union");
    } else if (currentMode === "table") {
      executeCalculusAction();
    } else if (currentMode === "base_n") {
      updateBaseNReadouts();
    }
  }

  function executeCalculusAction() {
    var activeSub = document.querySelector(".btn-calc-sub.active");
    var sub = activeSub ? activeSub.getAttribute("data-sub") : "table";
    var payload = {
      calc_mode: "table",
      calc_submode: sub,
      calc_func: document.getElementById("calc-fx-input").value,
      x_start: parseFloat(document.getElementById("calc-xstart").value || 0),
      x_end: parseFloat(document.getElementById("calc-xend").value || 3),
      x_step: parseFloat(document.getElementById("calc-xstep").value || 0.5),
      x_eval: parseFloat(document.getElementById("calc-xpoint").value || 1.0),
      int_a: parseFloat(document.getElementById("calc-int-a").value || 0),
      int_b: parseFloat(document.getElementById("calc-int-b").value || 2)
    };

    fetch("/api/scientific/eval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          showScreenError(data.error);
          return;
        }
        var head = (data.groups && data.groups[0] && data.groups[0].rows && data.groups[0].rows[0])
          ? data.groups[0].rows[0].display : "Done";
        var resEl = document.getElementById("screen-result-value");
        if (resEl) {
          resEl.innerHTML = "\\(" + head + "\\)";
          if (window.renderMathInElement) window.renderMathInElement(resEl, { throwOnError: false });
        }
        renderStepTray(data.steps || []);
      })
      .catch(function (e) { showScreenError(e); });
  }

  function updateBaseNReadouts() {
    var val = parseInt(document.getElementById("base-a-input").value || "0", 10);
    var decEl = document.getElementById("base-dec");
    var hexEl = document.getElementById("base-hex");
    var binEl = document.getElementById("base-bin");
    var octEl = document.getElementById("base-oct");
    if (decEl) decEl.textContent = val.toString(10);
    if (hexEl) hexEl.textContent = "0x" + val.toString(16).toUpperCase();
    if (binEl) binEl.textContent = "0b" + val.toString(2);
    if (octEl) octEl.textContent = "0o" + val.toString(8);
  }

  function setupKeyboardListeners() {
    window.addEventListener("keydown", function (e) {
      var modal = document.getElementById("phys-calc-modal");
      if (!modal || !modal.classList.contains("is-open")) return;

      if (e.key === "Escape") {
        toggleModal();
        return;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

