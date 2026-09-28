/* ============================================================
   AVARIX — Aerospace Intelligence & Knowledge Platform
   Frontend Controller
   ============================================================ */

(() => {
    "use strict";

    /* --------------------------------------------------------
       DOM
       -------------------------------------------------------- */

    const chat = document.getElementById("chat");
    const welcome = document.getElementById("welcome");
    const input = document.getElementById("input");
    const sendBtn = document.getElementById("send");
    const charCount = document.getElementById("char-count");
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    const rebuildBtn = document.getElementById("rebuild-btn");
    const sourceToggle = document.getElementById("source-toggle");
    const visualPanel = document.getElementById("visual-panel");
    const visualContent = document.getElementById("visual-content");

    const MAX_CHARS = 12000;

    /* --------------------------------------------------------
       Session
       -------------------------------------------------------- */

    let sessionId = sessionStorage.getItem("intellex_session_id");

    if (!sessionId) {
        sessionId =
            (window.crypto && crypto.randomUUID)
                ? crypto.randomUUID()
                : `avarix-${Date.now()}-${Math.random().toString(36).slice(2)}`;

        sessionStorage.setItem(
            "intellex_session_id",
            sessionId
        );
    }

    /* --------------------------------------------------------
       State
       -------------------------------------------------------- */

    let isSending = false;
    let showSources = true;
    let currentUser = null;

    /* Account profile and logout */
    function initialsFromName(name) {
        const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
        if (!parts.length) return "U";
        if (parts.length === 1) return Array.from(parts[0])[0].toUpperCase();
        return (Array.from(parts[0])[0] + Array.from(parts[parts.length - 1])[0]).toUpperCase();
    }

    function setProfile(user) {
        currentUser = user || null;
        const initials = initialsFromName(currentUser?.name);
        const triggerInitials = document.getElementById("profile-initials");
        const summaryInitials = document.getElementById("profile-summary-initials");
        const name = document.getElementById("profile-name");
        const email = document.getElementById("profile-email");
        if (triggerInitials) triggerInitials.textContent = initials;
        if (summaryInitials) summaryInitials.textContent = initials;
        if (name) name.textContent = currentUser?.name || "User";
        if (email) email.textContent = currentUser?.email || "";
    }

    async function loadCurrentUser() {
        try {
            const response = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
            if (response.status === 401) { window.location.replace("/"); return; }
            if (!response.ok) throw new Error("Unable to load account");
            setProfile(await response.json());
        } catch (error) {
            console.error("AVARIX account check failed:", error);
            window.location.replace("/");
        }
    }

    function initializeProfileMenu() {
        const trigger = document.getElementById("profile-trigger");
        const dropdown = document.getElementById("profile-dropdown");
        const logout = document.getElementById("logout-btn");
        if (!trigger || !dropdown || !logout) return;
        const closeMenu = () => {
            dropdown.hidden = true;
            trigger.setAttribute("aria-expanded", "false");
        };
        trigger.addEventListener("click", event => {
            event.stopPropagation();
            const opening = dropdown.hidden;
            dropdown.hidden = !opening;
            trigger.setAttribute("aria-expanded", String(opening));
        });
        document.addEventListener("click", event => {
            if (!event.target.closest("#profile-menu")) closeMenu();
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape") { closeMenu(); trigger.focus(); }
        });
        logout.addEventListener("click", async () => {
            logout.disabled = true;
            try {
                const response = await fetch("/api/auth/logout", {
                    method: "POST", credentials: "same-origin",
                    headers: { "Content-Type": "application/json" }, body: "{}"
                });
                if (!response.ok) throw new Error("Logout failed");
                sessionStorage.removeItem("intellex_session_id");
                window.location.replace("/");
            } catch (error) {
                console.error("AVARIX logout failed:", error);
                logout.disabled = false;
                alert("Unable to log out right now. Please try again.");
            }
        });
    }

    /* --------------------------------------------------------
       Utility
       -------------------------------------------------------- */

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function escapeAttribute(value) {
        return escapeHtml(value);
    }

    function normalizeArray(value) {
        if (!Array.isArray(value)) {
            return [];
        }

        return value.filter(
            item => item !== null && item !== undefined
        );
    }

    function safeUrl(value) {
        if (!value) {
            return null;
        }

        try {
            const url = new URL(
                String(value),
                window.location.origin
            );

            if (
                url.protocol === "http:" ||
                url.protocol === "https:"
            ) {
                return url.href;
            }

            return null;
        } catch {
            return null;
        }
    }

    function formatInline(text) {
        let value = String(text ?? "");

        /* Inline code */
        value = value.replace(
            /`([^`]+)`/g,
            "<code>$1</code>"
        );

        /* Bold */
        value = value.replace(
            /\*\*(.+?)\*\*/g,
            "<strong>$1</strong>"
        );

        /* Italic */
        value = value.replace(
            /(^|[^\*])\*([^*\n]+)\*(?!\*)/g,
            "$1<em>$2</em>"
        );

        return value;
    }

    /* --------------------------------------------------------
       Mathematical formatting
       -------------------------------------------------------- */

    function protectMath(text) {
        const math = [];

        const protectedText = String(text ?? "")
            .replace(
                /\$\$([\s\S]*?)\$\$/g,
                (_, content) => {
                    const index = math.length;
                    math.push(
                        `\\[${content.trim()}\\]`
                    );
                    return `@@MATH${index}@@`;
                }
            )
            .replace(
                /\\\[([\s\S]*?)\\\]/g,
                (_, content) => {
                    const index = math.length;
                    math.push(
                        `\\[${content.trim()}\\]`
                    );
                    return `@@MATH${index}@@`;
                }
            )
            .replace(
                /\\\(([\s\S]*?)\\\)/g,
                (_, content) => {
                    const index = math.length;
                    math.push(
                        `\\(${content.trim()}\\)`
                    );
                    return `@@MATH${index}@@`;
                }
            );

        return {
            text: protectedText,
            math
        };
    }

    function restoreMath(text, math) {
        let output = text;

        math.forEach((value, index) => {
            output = output.replace(
                `@@MATH${index}@@`,
                value
            );
        });

        return output;
    }

    function formatText(text) {
        if (!text) {
            return "";
        }

        const protectedData = protectMath(text);

        let value = protectedData.text;
        
        /*
         * Normalize basic HTML lists that may come from extracted PDF/DB text.
         * Convert them to Markdown-style bullets before HTML escaping.
         */
        value = value
            .replace(/<ul[^>]*>/gi, "")
            .replace(/<\/ul>/gi, "")
            .replace(/<ol[^>]*>/gi, "")
            .replace(/<\/ol>/gi, "")
            .replace(/<li[^>]*>/gi, "\n• ")
            .replace(/<\/li>/gi, "\n");

        /*
         * Escape first, then restore math.
         */
        value = escapeHtml(value);

        /* Basic inline formatting before structural HTML. */
        value = formatInline(value);

        /* Headings */
        value = value.replace(
            /^###\s+(.+)$/gm,
            "<h4>$1</h4>"
        );

        value = value.replace(
            /^##\s+(.+)$/gm,
            "<h3>$1</h3>"
        );

        value = value.replace(
            /^#\s+(.+)$/gm,
            "<h2>$1</h2>"
        );

        /* Bullet lists */
        value = value.replace(
            /(?:^|\n)[ \t]*[-•]\s+(.+)(?=\n|$)/g,
            "\n<li>$1</li>"
        );

        /*
         * Group consecutive <li> elements.
         */
        value = value.replace(
            /((?:\n<li>.*?<\/li>)+)/gs,
            match => `<ul>${match}</ul>`
        );

        /* Numbered lists */
        value = value.replace(
            /(?:^|\n)[ \t]*\d+\.\s+(.+)(?=\n|$)/g,
            "\n<li>$1</li>"
        );

        /*
         * Restore mathematical notation after HTML escaping.
         */
        value = restoreMath(
            value,
            protectedData.math
        );

        /*
         * Paragraph/newline handling.
         */
        value = value
            .split(/\n{2,}/)
            .map(block => {
                const trimmed = block.trim();

                if (!trimmed) {
                    return "";
                }

                if (
                    trimmed.startsWith("<h2>") ||
                    trimmed.startsWith("<h3>") ||
                    trimmed.startsWith("<h4>") ||
                    trimmed.startsWith("<ul>")
                ) {
                    return trimmed;
                }

                return `<p>${trimmed.replace(
                    /\n/g,
                    "<br>"
                )}</p>`;
            })
            .join("");

        return value;
    }

    function typesetMath(element) {
        if (
            window.MathJax &&
            typeof window.MathJax.typesetPromise === "function"
        ) {
            window.MathJax
                .typesetPromise([element])
                .catch(() => {});
        }
    }

    /* --------------------------------------------------------
       Intent
       -------------------------------------------------------- */

    function detectIntent(question) {
        const q = String(question || "")
            .toLowerCase()
            .trim();

        if (
            /\b(compare|difference|differentiate|versus|vs\.?)\b/
                .test(q)
        ) {
            return "comparison";
        }

        if (
            /\b(calculate|compute|find|determine|solve|what is the value)\b/
                .test(q)
        ) {
            return "calculation";
        }

        if (
            /\b(why|how does|how do|how is|explain)\b/
                .test(q)
        ) {
            return "explanation";
        }

        if (
            /\b(application|applications|used for|used in|used to|where is it used)\b/
                .test(q)
        ) {
            return "application";
        }

        if (
            /\b(what is|what are|define|definition|meaning)\b/
                .test(q)
        ) {
            return "definition";
        }

        return "general";
    }

    /* --------------------------------------------------------
       Structured answer
       -------------------------------------------------------- */

    function hasStructuredContent(structured) {
        if (!structured || typeof structured !== "object") {
            return false;
        }

        return Boolean(
            structured.answer ||
            structured.explanation ||
            normalizeArray(structured.key_points).length ||
            structured.formula ||
            normalizeArray(structured.applications).length ||
            normalizeArray(structured.examples).length
        );
    }

    function renderList(items) {
        const values = normalizeArray(items);

        if (!values.length) {
            return "";
        }

        return `
            <ul class="section-list">
                ${values.map(item => `
                    <li class="section-list-item">
                        ${formatText(
                            typeof item === "object"
                                ? (
                                    item.text ||
                                    item.description ||
                                    item.value ||
                                    ""
                                )
                                : item
                        )}
                    </li>
                `).join("")}
            </ul>
        `;
    }

    function renderFormula(formula) {
        if (!formula) {
            return "";
        }

        let content = "";

        if (
            typeof formula === "object" &&
            formula !== null
        ) {
            content =
                formula.latex ||
                formula.expression ||
                formula.formula ||
                formula.value ||
                "";
        } else {
            content = String(formula);
        }

        if (!content.trim()) {
            return "";
        }

        /*
         * Formula fields generated by AVARIX may already
         * contain LaTeX delimiters. If not, display them
         * as display mathematics.
         */
        let rendered = content.trim();

        if (
            !rendered.includes("\\[") &&
            !rendered.includes("\\(") &&
            !rendered.includes("$$")
        ) {
            rendered = `\\[${rendered}\\]`;
        }

        return `
            <div class="formula-box">
                <div class="section-heading">
                    <span class="section-icon">ƒ</span>
                    Formula
                </div>
                <div class="formula-content">
                    ${escapeHtml(rendered)}
                </div>
            </div>
        `;
    }

    function renderStructuredAnswer(
        structured,
        fallbackAnswer,
        question
    ) {
        if (!hasStructuredContent(structured)) {
            return `
                <div class="answer-body">
                    ${formatText(fallbackAnswer)}
                </div>
            `;
        }

        const intent = detectIntent(question);

        const answer =
            structured.answer ||
            fallbackAnswer ||
            "";

        const explanation =
            structured.explanation || "";

        const keyPoints =
            normalizeArray(
                structured.key_points
            );

        const applications =
            normalizeArray(
                structured.applications
            );

        const examples =
            normalizeArray(
                structured.examples
            );

        let html = `
            <div class="answer-body answer-direct">
                ${formatText(answer)}
            </div>
        `;

        /*
         * Explanation
         */
        if (explanation) {
            html += `
                <section class="answer-section">
                    <div class="section-heading">
                        <span class="section-icon">◈</span>
                        Explanation
                    </div>
                    <div class="section-content">
                        ${formatText(explanation)}
                    </div>
                </section>
            `;
        }

        /*
         * Key points
         */
        if (keyPoints.length) {
            html += `
                <section class="answer-section">
                    <div class="section-heading">
                        <span class="section-icon">✦</span>
                        Key Points
                    </div>
                    ${renderList(keyPoints)}
                </section>
            `;
        }

        /*
         * Formula
         */
        if (structured.formula) {
            html += renderFormula(
                structured.formula
            );
        }

        /*
         * Applications
         */
        if (applications.length) {
            html += `
                <section class="answer-section">
                    <div class="section-heading">
                        <span class="section-icon">✈</span>
                        Applications
                    </div>
                    ${renderList(applications)}
                </section>
            `;
        }

        /*
         * Examples
         */
        if (examples.length) {
            html += `
                <section class="answer-section">
                    <div class="section-heading">
                        <span class="section-icon">▣</span>
                        Examples
                    </div>
                    ${renderList(examples)}
                </section>
            `;
        }

        /*
         * Intent-specific visual emphasis.
         */
        if (intent === "calculation") {
            html = `
                <div class="structured-calculation">
                    ${html}
                </div>
            `;
        }

        return html;
    }

    /* --------------------------------------------------------
       Source normalization
       -------------------------------------------------------- */

    function collectSources(result) {
        const sources = [];

        const dbResults =
            normalizeArray(
                result.db_results
            );

        const webResults =
            normalizeArray(
                result.web_results
            );

        /*
         * Knowledge Base sources
         */
        dbResults.forEach(item => {
            if (!item || typeof item !== "object") {
                return;
            }

            sources.push({
                type: "db",
                title:
                    item.title ||
                    item.filename ||
                    item.file_name ||
                    "Knowledge Base",

                page:
                    item.page ||
                    item.page_number ||
                    null,

                url:
                    item.url ||
                    item.source_url ||
                    null,

                snippet:
                    item.snippet ||
                    item.text ||
                    "",

                source:
                    item.source ||
                    "Knowledge Base"
            });
        });

        /*
         * Web sources
         */
        webResults.forEach(item => {
            if (!item || typeof item !== "object") {
                return;
            }

            sources.push({
                type: "web",
                title:
                    item.title ||
                    "Web Research",

                page: null,

                url:
                    item.url ||
                    item.source_url ||
                    null,

                snippet:
                    item.snippet ||
                    item.description ||
                    "",

                source:
                    item.source ||
                    item.domain ||
                    "Web Research"
            });
        });

        /*
         * Remove duplicate URLs/titles.
         */
        const seen = new Set();

        return sources.filter(source => {
            const key =
                source.url ||
                `${source.type}:${source.title}:${source.page}`;

            if (seen.has(key)) {
                return false;
            }

            seen.add(key);
            return true;
        });
    }

    function sourceBadge(result) {
        const mode =
            String(result.mode || "")
                .toLowerCase();

        const source =
            String(result.source || "")
                .toLowerCase();

        if (
            mode.includes("aerocalc") ||
            result.aerocalc
        ) {
            return {
                icon: "🧮",
                text: "AeroCalc",
                className: "aerocalc"
            };
        }

        // General mathematical calculations
        if (
            source === "math" ||
            mode.includes("math")
        ) {
            return {
                icon: "∑",
                text: "Math Engine",
                className: "math"
            };
        }

        if (
            mode.includes("web") ||
            source.includes("web")
        ) {
            return {
                icon: "🌐",
                text: "Web Research",
                className: "web"
            };
        }

        return {
            icon: "📚",
            text: "Knowledge Base",
            className: "database"
        };
    }

    function renderSources(result) {
        if (!showSources) {
            return "";
        }

        const sources = collectSources(result);

        if (!sources.length) {
            return "";
        }

        return `
            <section class="sources-block" data-sources-block>

                <button
                    type="button"
                    class="sources-header"
                    data-source-expander
                    aria-expanded="false"
                >
                    <span class="sources-heading">
                        <span class="sources-heading-icon">▣</span>
                        <span>Sources</span>
                    </span>

                    <span class="sources-header-right">
                        <span class="sources-count">
                            ${sources.length}
                        </span>

                        <span
                            class="sources-chevron"
                            aria-hidden="true"
                        >›</span>
                    </span>
                </button>

                <div
                    class="source-list"
                    data-source-list
                    hidden
                >
                    ${sources.map(source => {

                        const url =
                            safeUrl(source.url);

                        const location =
                            source.page
                                ? `Page ${escapeHtml(source.page)}`
                                : "";

                        return `
                            <article
                                class="source-card ${source.type}"
                            >

                                <div class="source-card-top">

                                    <span class="source-type">
                                        ${
                                            source.type === "db"
                                                ? "📚 KNOWLEDGE BASE"
                                                : "🌐 WEB RESEARCH"
                                        }
                                    </span>

                                    ${
                                        location
                                            ? `
                                                <span class="source-page">
                                                    ${location}
                                                </span>
                                            `
                                            : ""
                                    }

                                </div>

                                <div class="source-title">
                                    ${escapeHtml(source.title)}
                                </div>

                                ${
                                    source.source
                                        ? `
                                            <div class="source-provider">
                                                ${escapeHtml(
                                                    source.source
                                                )}
                                            </div>
                                        `
                                        : ""
                                }

                                ${
                                    url
                                        ? `
                                            <a
                                                class="source-link"
                                                href="${escapeAttribute(url)}"
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >
                                                Open source ↗
                                            </a>
                                        `
                                        : ""
                                }

                            </article>
                        `;

                    }).join("")}
                </div>

            </section>
        `;
    }

    /* --------------------------------------------------------
       Visual panel
       -------------------------------------------------------- */

    function collectVisuals(result) {
        const candidates =
            result.visuals ||
            result.images ||
            result.related_visuals ||
            result.relatedVisuals ||
            [];

        if (!Array.isArray(candidates)) {
            return [];
        }

        return candidates
            .map(item => {
                if (typeof item === "string") {
                    return {
                        title: item,
                        image_url: item
                    };
                }

                if (
                    item &&
                    typeof item === "object"
                ) {
                    return item;
                }

                return null;
            })
            .filter(Boolean)
            .slice(0, 8);
    }

    function renderVisualPanel(result) {
        if (!visualPanel || !visualContent) {
            return;
        }

        const visuals =
            collectVisuals(result);

        if (!visuals.length) {
            visualPanel.classList.remove(
                "visible"
            );

            visualContent.innerHTML = "";
            return;
        }

        const usableVisuals =
            visuals.filter(visual => {
                return Boolean(
                    safeUrl(
                        visual.image_url ||
                        visual.url ||
                        visual.thumbnail_url
                    )
                );
            });

        if (!usableVisuals.length) {
            visualPanel.classList.remove(
                "visible"
            );

            visualContent.innerHTML = "";
            return;
        }

        visualContent.innerHTML = `
            <div class="visual-panel-header">
                <span class="visual-kicker">
                    Related Visuals
                </span>

                <span class="visual-count">
                    ${usableVisuals.length}
                </span>
            </div>

            <div class="visual-list">
                ${usableVisuals.map(visual => {
                    const imageUrl =
                        safeUrl(
                            visual.image_url ||
                            visual.url ||
                            visual.thumbnail_url
                        );

                    const title =
                        visual.title ||
                        visual.description ||
                        "Related visual";

                    const description =
                        visual.description || "";

                    const sourceUrl =
                        safeUrl(
                            visual.source_url
                        );

                    return `
                        <article class="visual-card">
                            <div class="visual-image-wrap">
                                <img
                                    src="${escapeAttribute(imageUrl)}"
                                    alt="${escapeAttribute(title)}"
                                    loading="lazy"
                                >
                            </div>

                            <div class="visual-card-body">
                                <div class="visual-title">
                                    ${escapeHtml(title)}
                                </div>

                                ${
                                    description
                                        ? `
                                            <div class="visual-description">
                                                ${escapeHtml(
                                                    description
                                                )}
                                            </div>
                                          `
                                        : ""
                                }

                                ${
                                    sourceUrl
                                        ? `
                                            <a
                                                href="${escapeAttribute(sourceUrl)}"
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                class="visual-source"
                                            >
                                                View source ↗
                                            </a>
                                          `
                                        : ""
                                }
                            </div>
                        </article>
                    `;
                }).join("")}
            </div>
        `;

        visualPanel.classList.add("visible");

        /*
         * Clicking an image opens it directly.
         */
        visualContent
            .querySelectorAll(".visual-card img")
            .forEach(img => {
                img.addEventListener(
                    "click",
                    () => {
                        const url =
                            safeUrl(img.src);

                        if (url) {
                            window.open(
                                url,
                                "_blank",
                                "noopener,noreferrer"
                            );
                        }
                    }
                );
            });
    }

    /* --------------------------------------------------------
       AeroCalc
       -------------------------------------------------------- */

    function renderAeroCalc(data) {
        if (!data || typeof data !== "object") return "";

        const title =
            data.match_name ||
            data.calculator?.name ||
            data.title ||
            data.name ||
            "AeroCalc Result";

        const payload =
            data.payload && typeof data.payload === "object"
                ? data.payload
                : {};

        const inputs = normalizeArray(data.calculator?.inputs);
        const groups = normalizeArray(data.groups);
        const plots = normalizeArray(data.plots);
        const tables = normalizeArray(data.tables);
        const notes = normalizeArray(data.notes);
        const steps = normalizeArray(data.steps);
        const suggestions = normalizeArray(data.suggestions);

        const textValue = value => {
            if (value === null || value === undefined) return "";
            if (typeof value === "object") {
                return String(
                    value.display ??
                    value.value ??
                    value.text ??
                    value.label ??
                    ""
                );
            }
            return String(value);
        };

        const renderMathValue = value => {
            const raw = textValue(value).trim();
            if (!raw) return "";
            if (
                raw.includes("\\(") || raw.includes("\\[") ||
                raw.includes("$$")
            ) {
                return formatText(raw);
            }
            return formatText(`\\(${raw}\\)`);
        };

        const suppliedInputs = inputs.filter(field =>
            Object.prototype.hasOwnProperty.call(payload, field.key) &&
            payload[field.key] !== null &&
            payload[field.key] !== undefined &&
            payload[field.key] !== ""
        );

        const resultGroups = groups.map(group => ({
            title: group?.title || group?.name || "Results",
            subtitle: group?.subtitle || "",
            rows: normalizeArray(group?.rows || group?.values).map(row => {
                if (Array.isArray(row)) {
                    return {
                        label: textValue(row[0]),
                        display: textValue(row[1]),
                        unit: textValue(row[2])
                    };
                }
                return row && typeof row === "object"
                    ? row
                    : { label: "", display: textValue(row), unit: "" };
            })
        })).filter(group => group.rows.length);

        const resultCount = resultGroups.reduce(
            (count, group) => count + group.rows.length,
            0
        );

        let html = `
            <section class="aerocalc-card">
                <header class="aerocalc-header">
                    <div>
                        <div class="aerocalc-badge">🧮 AEROCALC</div>
                        <div class="aerocalc-title">${escapeHtml(title)}</div>
                    </div>
                    <span class="aerocalc-status">COMPUTED RESULT</span>
                </header>
        `;

        if (data.error) {
            html += `<div class="aerocalc-error">${escapeHtml(data.error)}</div>`;
        }

        if (suggestions.length) {
            html += `
                <section class="aerocalc-section">
                    <div class="aerocalc-section-title">Additional inputs needed</div>
                    ${renderList(suggestions)}
                </section>
            `;
        }

        if (suppliedInputs.length) {
            html += `
                <section class="aerocalc-section">
                    <div class="aerocalc-section-title">Input parameters</div>
                    <div class="aerocalc-input-grid">
                        ${suppliedInputs.map(field => `
                            <div class="aerocalc-input">
                                <span>${escapeHtml(field.label || field.key)}</span>
                                <strong>
                                    ${escapeHtml(textValue(payload[field.key]))}
                                    ${field.unit ? `<small>${escapeHtml(field.unit)}</small>` : ""}
                                </strong>
                            </div>
                        `).join("")}
                    </div>
                </section>
            `;
        }

        if (resultGroups.length) {
            html += `
                <section class="aerocalc-section">
                    <div class="aerocalc-section-title">
                        Calculated results <span class="aerocalc-count">${resultCount}</span>
                    </div>
                    <div class="aerocalc-groups">
                        ${resultGroups.map(group => `
                            <section class="aerocalc-result-group">
                                <div class="aerocalc-group-title">${escapeHtml(group.title)}</div>
                                ${group.subtitle ? `<div class="aerocalc-group-subtitle">${escapeHtml(group.subtitle)}</div>` : ""}
                                <div class="aerocalc-result-rows">
                                    ${group.rows.map(row => {
                                        const label = row.label || row.name || row.key || "Result";
                                        const value = row.display ?? row.value ?? row.result ?? "";
                                        const unit = row.unit || "";
                                        const symbol = row.symbol || "";
                                        return `
                                            <div class="aerocalc-result-row${row.highlight ? " is-highlight" : ""}">
                                                <div class="aerocalc-row-label">
                                                    <span>${escapeHtml(label)}</span>
                                                    ${symbol ? `<small>${escapeHtml(symbol)}</small>` : ""}
                                                </div>
                                                <strong>
                                                    ${escapeHtml(textValue(value) || "—")}
                                                    ${unit ? `<small>${escapeHtml(unit)}</small>` : ""}
                                                </strong>
                                                ${row.note ? `<em>${escapeHtml(row.note)}</em>` : ""}
                                            </div>
                                        `;
                                    }).join("")}
                                </div>
                            </section>
                        `).join("")}
                    </div>
                </section>
            `;
        }

        const validPlots = plots.map(plot => {
            const source = String(
                plot?.image || plot?.data || plot?.url || plot?.src || ""
            ).trim();
            const safeImage = /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+$/i.test(source)
                ? source
                : safeUrl(source);
            return { ...plot, safeImage };
        }).filter(plot => plot.safeImage);

        if (validPlots.length) {
            html += `
                <section class="aerocalc-section">
                    <div class="aerocalc-section-title">Engineering plots</div>
                    <div class="aerocalc-plot-grid">
                        ${validPlots.map(plot => `
                            <figure class="aerocalc-plot">
                                <img src="${escapeAttribute(plot.safeImage)}"
                                     alt="${escapeAttribute(plot.title || "AeroCalc plot")}"
                                     loading="lazy">
                                ${plot.title ? `<figcaption>${escapeHtml(plot.title)}</figcaption>` : ""}
                                ${plot.caption ? `<p>${escapeHtml(plot.caption)}</p>` : ""}
                            </figure>
                        `).join("")}
                    </div>
                </section>
            `;
        }

        if (tables.length) {
            html += `
                <section class="aerocalc-section">
                    <div class="aerocalc-section-title">Data tables</div>
                    ${tables.map(table => `
                        <div class="aerocalc-table-block">
                            ${table.title ? `<div class="aerocalc-group-title">${escapeHtml(table.title)}</div>` : ""}
                            <div class="aerocalc-table-scroll">
                                <table class="aerocalc-table">
                                    ${Array.isArray(table.columns) ? `
                                        <thead><tr>${table.columns.map(col => `<th>${escapeHtml(textValue(col))}</th>`).join("")}</tr></thead>
                                    ` : ""}
                                    <tbody>
                                        ${normalizeArray(table.rows).map(row => `
                                            <tr>${normalizeArray(row).map(cell => `<td>${escapeHtml(textValue(cell))}</td>`).join("")}</tr>
                                        `).join("")}
                                    </tbody>
                                </table>
                            </div>
                            ${table.caption ? `<p class="aerocalc-table-caption">${escapeHtml(table.caption)}</p>` : ""}
                        </div>
                    `).join("")}
                </section>
            `;
        }

        const normalizedSteps = steps.map((step, index) => {
            if (typeof step === "string" || typeof step === "number") {
                return { title: `Step ${index + 1}`, explanation: String(step) };
            }
            if (!step || typeof step !== "object") return null;
            const pick = (...keys) => {
                for (const key of keys) {
                    if (step[key] !== undefined && step[key] !== null && step[key] !== "") {
                        return step[key];
                    }
                }
                return "";
            };
            const normalized = {
                title: textValue(pick("title", "name", "label", "heading")) || `Step ${index + 1}`,
                formula: pick("formula", "equation", "equation_latex", "formula_latex"),
                substitution: pick("substitution", "substituted", "working", "calculation"),
                result: pick("result", "final", "value", "answer"),
                explanation: pick("explanation", "description", "note", "details", "text")
            };
            return Object.values(normalized).some(Boolean) ? normalized : null;
        }).filter(Boolean);

        if (normalizedSteps.length) {
            html += `
                <details class="aerocalc-steps">
                    <summary class="aerocalc-section-title">
                        Calculation steps <span class="aerocalc-count">${normalizedSteps.length}</span>
                    </summary>
                    <div class="aerocalc-step-list">
                        ${normalizedSteps.map((step, index) => `
                            <article class="aerocalc-step">
                                <div class="aerocalc-step-title">Step ${index + 1}: ${escapeHtml(step.title)}</div>
                                ${step.formula ? `<div class="aerocalc-step-line"><span>Formula</span>${renderMathValue(step.formula)}</div>` : ""}
                                ${step.substitution ? `<div class="aerocalc-step-line"><span>Substitution</span>${renderMathValue(step.substitution)}</div>` : ""}
                                ${step.result ? `<div class="aerocalc-step-line"><span>Result</span>${renderMathValue(step.result)}</div>` : ""}
                                ${step.explanation ? `<p>${formatText(textValue(step.explanation))}</p>` : ""}
                            </article>
                        `).join("")}
                    </div>
                </details>
            `;
        } else if (resultCount && !data.error) {
            html += `
                <div class="aerocalc-steps-empty">
                    Calculation steps are not supplied for this calculator.
                    The computed results are shown above.
                </div>
            `;
        }

        if (notes.length) {
            html += `
                <section class="aerocalc-section">
                    <div class="aerocalc-section-title">Notes & assumptions</div>
                    ${renderList(notes)}
                </section>
            `;
        }

        html += "</section>";
        return html;
    }

    /* --------------------------------------------------------
       Answer actions
       -------------------------------------------------------- */

    function getAnswerText(messageElement) {
        const body =
            messageElement.querySelector(
                ".answer-content"
            );

        if (!body) {
            return "";
        }

        return body.innerText.trim();
    }

    async function copyText(text) {
        if (!text) {
            return false;
        }

        try {
            await navigator.clipboard.writeText(
                text
            );
            return true;
        } catch {
            return false;
        }
    }

    function addAnswerActions(
        messageElement
    ) {
        const actions =
            messageElement.querySelector(
                ".answer-actions"
            );

        if (!actions) {
            return;
        }

        const copyBtn =
            actions.querySelector(
                "[data-action='copy']"
            );

        if (copyBtn) {
            copyBtn.addEventListener(
                "click",
                async () => {
                    const text =
                        getAnswerText(
                            messageElement
                        );

                    const copied =
                        await copyText(text);

                    if (copied) {
                        const old =
                            copyBtn.innerHTML;

                        copyBtn.innerHTML =
                            "✓ Copied";

                        setTimeout(() => {
                            copyBtn.innerHTML =
                                old;
                        }, 1200);
                    }
                }
            );
        }
    }

    /* --------------------------------------------------------
       Message rendering
       -------------------------------------------------------- */

    function addUserMessage(text) {
        if (!chat) {
            return;
        }

        hideWelcome();

        const wrapper =
            document.createElement("div");

        wrapper.className =
            "message message-user";

        wrapper.innerHTML = `
            <div class="message-inner">
                <div class="message-avatar user-avatar" aria-label="Your profile">
                    ${escapeHtml(initialsFromName(currentUser?.name))}
                </div>

                <div class="message-bubble">
                    ${formatText(text)}
                </div>
            </div>
        `;

        chat.appendChild(wrapper);

        scrollToBottom();

        return wrapper;
    }

    function addAssistantMessage(
        result,
        question
    ) {
        if (!chat) {
            return;
        }

        hideWelcome();

        const badge =
            sourceBadge(result);

        const answer =
            result.answer || "";

        const structured =
            result.structured;

        const aeroCalc =
            renderAeroCalc(
                result.aerocalc
            );

        const content = aeroCalc
            ? ""
            : renderStructuredAnswer(
                structured,
                answer,
                question
            );

        const sources =
            renderSources(result);

        const wrapper =
            document.createElement("div");

        wrapper.className =
            "message message-assistant";

        wrapper.innerHTML = `
            <div class="message-inner">

                <div class="message-avatar avarix-avatar">
                    <img
                        src="/static/assets/avarix-emblem.png"
                        alt="AVARIX"
                        class="assistant-avatar-logo"
                    >
                </div>

                <div class="message-main">
                    <div class="answer-card">

                        <div class="answer-card-header">
                            <div class="answer-brand">
                                AVARIX
                            </div>

                            <div class="source-badge ${badge.className}">
                                <span>
                                    ${badge.icon}
                                </span>
                                ${badge.text}
                            </div>
                        </div>

                        <div class="answer-content">
                            ${content}
                        </div>

                        ${
                            aeroCalc
                                ? aeroCalc
                                : ""
                        }

                        ${
                            sources
                                ? sources
                                : ""
                        }

                        <div class="answer-actions">
                            <button
                                type="button"
                                class="answer-action"
                                data-action="copy"
                                title="Copy answer"
                            >
                                Copy
                            </button>
                        </div>

                    </div>
                </div>
            </div>
        `;

        chat.appendChild(wrapper);

        addAnswerActions(wrapper);

        typesetMath(wrapper);

        renderVisualPanel(result);

        scrollToBottom();

        return wrapper;
    }

    function addErrorMessage(message) {
        if (!chat) {
            return;
        }

        const wrapper =
            document.createElement("div");

        wrapper.className =
            "message message-assistant";

        wrapper.innerHTML = `
            <div class="message-inner">

                <div class="message-avatar avarix-avatar">
                    <img
                        src="/static/assets/avarix-emblem.png"
                        alt="AVARIX"
                        class="assistant-avatar-logo"
                    >
                </div>

                <div class="message-main">
                    <div class="answer-card error-card">
                        <div class="answer-card-header">
                            <div class="answer-brand">
                                AVARIX
                            </div>

                            <div class="source-badge error">
                                !
                            </div>
                        </div>

                        <div class="answer-content">
                            <p>
                                ${escapeHtml(message)}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        `;

        chat.appendChild(wrapper);

        scrollToBottom();
    }

    /* --------------------------------------------------------
       Typing indicator
       -------------------------------------------------------- */

    function showTyping() {
        if (!chat) {
            return null;
        }

        const wrapper =
            document.createElement("div");

        wrapper.className =
            "message message-assistant typing-message";

        wrapper.innerHTML = `
            <div class="message-inner">

                <div class="message-avatar avarix-avatar">
                    <img
                        src="/static/assets/avarix-emblem.png"
                        alt="AVARIX"
                        class="assistant-avatar-logo"
                    >
                </div>

                <div class="message-main">
                    <div class="typing-card">
                        <div class="typing-label">
                            AVARIX is thinking
                        </div>

                        <div class="typing-dots">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </div>
                </div>
            </div>
        `;

        chat.appendChild(wrapper);

        scrollToBottom();

        return wrapper;
    }

    function removeTyping(element) {
        if (
            element &&
            element.parentNode
        ) {
            element.parentNode.removeChild(
                element
            );
        }
    }

    /* --------------------------------------------------------
       Welcome screen
       -------------------------------------------------------- */

    function hideWelcome() {
        if (!welcome) {
            return;
        }

        welcome.classList.add("hidden");
    }

    function showWelcome() {
        if (!welcome) {
            return;
        }

        if (
            chat &&
            chat.children.length === 0
        ) {
            welcome.classList.remove(
                "hidden"
            );
        }
    }

    /* --------------------------------------------------------
       Scroll
       -------------------------------------------------------- */

    function scrollToBottom() {
        requestAnimationFrame(() => {
            if (!chat) {
                return;
            }

            const mobile = window.matchMedia("(max-width: 700px)").matches;
            const workspace = document.querySelector(".workspace");

            if (mobile && workspace) {
                workspace.scrollTo({
                    top: workspace.scrollHeight,
                    behavior: "smooth"
                });
            } else {
                chat.scrollTo({
                    top: chat.scrollHeight,
                    behavior: "smooth"
                });
            }
        });
    }

    /* --------------------------------------------------------
       API
       -------------------------------------------------------- */

    async function sendQuestion(
        questionOverride = null
    ) {
        if (isSending) {
            return;
        }

        const question =
            String(
                questionOverride ??
                input?.value ??
                ""
            ).trim();

        if (!question) {
            return;
        }

        if (question.length > MAX_CHARS) {
            addErrorMessage(
                `Please keep the question under ${MAX_CHARS.toLocaleString()} characters.`
            );
            return;
        }

        isSending = true;

        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.classList.add(
                "sending"
            );
        }

        if (input) {
            input.value = "";
            updateInputState();
        }

        addUserMessage(question);

        const typing =
            showTyping();

        // Keep the active question / thinking indicator in view on mobile.
        scrollToBottom();

        /*
         * Keep the right-side panel clean while a new
         * question is being processed.
         */
        if (visualPanel) {
            visualPanel.classList.remove(
                "visible"
            );
        }

        try {
            const response =
                await fetch(
                    "/api/chat",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body: JSON.stringify({
                            question,
                            session_id:
                                sessionId
                        })
                    }
                );

            if (!response.ok) {
                let detail =
                    `Request failed (${response.status})`;

                try {
                    const errorData =
                        await response.json();

                    if (
                        errorData.detail
                    ) {
                        detail =
                            String(
                                errorData.detail
                            );
                    }
                } catch {
                    /* Keep default error. */
                }

                throw new Error(detail);
            }

            const result =
                await response.json();

            removeTyping(typing);

            /*
             * The backend always returns answer,
             * while structured/visuals are optional.
             */
            addAssistantMessage(
                {
                    answer:
                        result.answer || "",

                    case:
                        result.case,

                    source:
                        result.source,

                    db_results:
                        result.db_results || [],

                    web_results:
                        result.web_results || [],

                    aerocalc:
                        result.aerocalc,

                    mode:
                        result.mode,

                    structured:
                        result.structured,

                    visuals:
                        result.visuals || []
                },
                question
            );

        } catch (error) {
            removeTyping(typing);

            console.error(
                "[AVARIX]",
                error
            );

            addErrorMessage(
                error?.message ||
                "Something went wrong while processing your question."
            );

        } finally {
            isSending = false;

            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.classList.remove(
                    "sending"
                );
            }

            if (input) {
                input.focus();
            }
        }
    }

    /* --------------------------------------------------------
       Input
       -------------------------------------------------------- */

    function updateInputState() {
        if (!input) {
            return;
        }

        const length =
            input.value.length;

        if (charCount) {
            charCount.textContent =
                `${length.toLocaleString()} / ${MAX_CHARS.toLocaleString()}`;
        }

        input.style.height =
            "auto";

        input.style.height =
            `${Math.min(
                input.scrollHeight,
                180
            )}px`;
    }

    if (input) {
        input.addEventListener(
            "input",
            updateInputState
        );

        input.addEventListener(
            "keydown",
            event => {
                /*
                 * Enter sends.
                 * Shift + Enter creates a newline.
                 */
                if (
                    event.key === "Enter" &&
                    !event.shiftKey
                ) {
                    event.preventDefault();

                    sendQuestion();
                }
            }
        );
    }

    if (sendBtn) {
        sendBtn.addEventListener(
            "click",
            () => sendQuestion()
        );
    }

    /* --------------------------------------------------------
       Quick questions
       -------------------------------------------------------- */

    document
        .querySelectorAll(
            "[data-question]"
        )
        .forEach(button => {
            button.addEventListener(
                "click",
                () => {
                    const question =
                        button.dataset.question;

                    if (!question) {
                        return;
                    }

                    // Submit the sample directly. Do not leave it in the composer.
                    sendQuestion(question);
                }
            );
        });

    /* --------------------------------------------------------
       Source toggle
       -------------------------------------------------------- */

    if (sourceToggle) {
        sourceToggle.addEventListener(
            "click",
            () => {
                showSources =
                    !showSources;

                sourceToggle.classList.toggle(
                    "active",
                    showSources
                );

                sourceToggle.setAttribute(
                    "aria-pressed",
                    String(showSources)
                );

                /*
                 * Existing source blocks are updated
                 * without rerunning the answer.
                 */
                document
                    .querySelectorAll(
                        ".sources-block"
                    )
                    .forEach(block => {
                        block.style.display =
                            showSources
                                ? ""
                                : "none";
                    });
            }
        );
    }

 /* --------------------------------------------------------
   Individual source accordion
   -------------------------------------------------------- */

   if (chat) {
    chat.addEventListener(
        "click",
        event => {

            const target =
                event.target instanceof Element
                    ? event.target.closest(
                        "[data-source-expander]"
                    )
                    : null;

            if (!target) {
                return;
            }

            const block =
                target.closest(
                    "[data-sources-block]"
                );

            if (!block) {
                return;
            }

            const list =
                block.querySelector(
                    "[data-source-list]"
                );

            const chevron =
                block.querySelector(
                    ".sources-chevron"
                );

            if (!list) {
                return;
            }

            const isOpen =
                target.getAttribute(
                    "aria-expanded"
                ) === "true";

            target.setAttribute(
                "aria-expanded",
                String(!isOpen)
            );

            list.hidden = isOpen;

            block.classList.toggle(
                "sources-open",
                !isOpen
            );

            if (chevron) {
                chevron.textContent =
                    isOpen
                        ? "›"
                        : "⌄";
            }
        }
    );
}

    /* --------------------------------------------------------
       Rebuild knowledge base
       -------------------------------------------------------- */

    if (rebuildBtn) {
        rebuildBtn.addEventListener(
            "click",
            async () => {
                if (
                    rebuildBtn.disabled
                ) {
                    return;
                }

                rebuildBtn.disabled =
                    true;

                const original =
                    rebuildBtn.innerHTML;

                rebuildBtn.innerHTML =
                    "Rebuilding…";

                setStatus(
                    "working",
                    "Updating knowledge base…"
                );

                try {
                    const response =
                        await fetch(
                            "/api/rebuild",
                            {
                                method: "POST"
                            }
                        );

                    if (!response.ok) {
                        throw new Error(
                            `Rebuild failed (${response.status})`
                        );
                    }

                    const data =
                        await response.json();

                    setStatus(
                        "online",
                        data.message ||
                        "Knowledge base ready"
                    );

                } catch (error) {
                    console.error(
                        "[AVARIX]",
                        error
                    );

                    setStatus(
                        "error",
                        "Knowledge base rebuild failed"
                    );

                } finally {
                    rebuildBtn.disabled =
                        false;

                    rebuildBtn.innerHTML =
                        original;
                }
            }
        );
    }

    /* --------------------------------------------------------
       Health
       -------------------------------------------------------- */

    function setStatus(
        state,
        text
    ) {
        if (statusDot) {
            statusDot.className =
                `status-dot ${state}`;
        }

        if (statusText) {
            statusText.textContent =
                text;
        }
    }

    async function checkHealth() {
        try {
            const response =
                await fetch(
                    "/api/health",
                    {
                        method: "GET",
                        cache: "no-store"
                    }
                );

            if (!response.ok) {
                throw new Error(
                    "Health check failed"
                );
            }

            const data =
                await response.json();

            if (
                data.docs_loaded === false
            ) {
                setStatus(
                    "warning",
                    "Knowledge base not loaded"
                );

                return;
            }

            setStatus(
                "online",
                "Systems online"
            );

        } catch {
            setStatus(
                "error",
                "Backend unavailable"
            );
        }
    }

    /* --------------------------------------------------------
       Initialization
       -------------------------------------------------------- */

    updateInputState();

    showWelcome();

    if (sourceToggle) {
        sourceToggle.classList.toggle(
            "active",
            showSources
        );

        sourceToggle.setAttribute(
            "aria-pressed",
            String(showSources)
        );
    }

    initializeProfileMenu();
    loadCurrentUser();

    checkHealth();

    /*
     * Re-run MathJax once the page is loaded.
     */
    if (
        window.MathJax &&
        typeof window.MathJax.typesetPromise ===
            "function"
    ) {
        window.MathJax
            .typesetPromise()
            .catch(() => {});
    }

})();