"""Server-side chart generation.

All graphs are rendered with Matplotlib in a worker-safe Agg context and
returned as base64 PNG data URIs, so the browser never needs a plotting
library and the numbers on screen always come from the same code that drew
the curve.
"""

from __future__ import annotations

import base64
import io
import math
import os
import tempfile

# Hosted environments often have a read-only or missing home directory, which
# makes Matplotlib warn and re-scan the font list on every request. Point its
# cache somewhere writable before it is imported.
os.environ.setdefault("MPLCONFIGDIR",
                      os.path.join(tempfile.gettempdir(), "aerocalc-mpl"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import (LogFormatterSciNotation, LogLocator,  # noqa: E402
                               NullFormatter, ScalarFormatter)

# Palette mirrors the frontend design tokens in static/css/style.css
INK = "#101519"
MUTED = "#5A6673"
RULE = "#DFE3E9"
GRID = "#E8EBF0"
SURFACE = "#FFFFFF"

SERIES = ["#16497E", "#B26B00", "#0E7C6B", "#B3242B", "#5B4B8A",
          "#2C7BE5", "#8A6D1F", "#3F7A34"]

_BASE_RC = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans",
    "font.size": 9.5,
    "axes.edgecolor": "#C7CDD6",
    "axes.linewidth": 0.8,
    "axes.labelcolor": INK,
    "axes.labelsize": 9.5,
    "axes.titlesize": 10.5,
    "axes.titleweight": "semibold",
    "axes.titlecolor": INK,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.7,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "legend.frameon": True,
    "legend.framealpha": 0.94,
    "legend.edgecolor": RULE,
    "legend.fontsize": 8.5,
    "lines.linewidth": 1.9,
    "lines.solid_capstyle": "round",
}

DPI = 168


# Applied once at import. Every figure is created after this point and reads
# the same values, so there is never a reason to mutate rcParams at request
# time -- which is what made chart rendering unsafe across threads.
matplotlib.rcParams.update(_BASE_RC)


def _figure(figsize, nrows=1, ncols=1, **kw):
    """A figure built without pyplot, so it touches no global state.

    Every chart in the application goes through here. Using the
    object-oriented API rather than pyplot is what makes concurrent requests
    safe: pyplot keeps a process-wide registry of open figures and a
    process-wide rcParams dict, and two threads drawing at once will corrupt
    each other's work.
    """
    fig = Figure(figsize=figsize, dpi=DPI)
    FigureCanvasAgg(fig)
    axes = fig.subplots(nrows, ncols, **kw)
    return fig, axes


def _format_log_axis(ax, which):
    """Label a logarithmic axis legibly.

    ScalarFormatter writes plain numbers, which is what you want across a
    decade or two (a Reynolds sweep from 1000 to 50000 should not read
    "10^3"). Across many decades it collapses to a shared "1e8" multiplier
    with ticks of 0.00, 0.02, ... which is useless -- a Moody chart spans six
    decades. So the span picks the formatter, and only the log axis is touched.
    """
    axis = ax.xaxis if which == "x" else ax.yaxis
    lo, hi = ax.get_xlim() if which == "x" else ax.get_ylim()
    if lo <= 0 or hi <= 0:
        return
    decades = math.log10(hi / lo)

    if decades <= 2.2:
        axis.set_major_locator(LogLocator(base=10, subs=(1.0,)))
        axis.set_minor_locator(LogLocator(base=10, subs=(2.0, 3.0, 5.0)))
        fmt = ScalarFormatter()
        fmt.set_scientific(False)
        fmt.set_useOffset(False)
        axis.set_major_formatter(fmt)
        if decades <= 1.3:
            minor = ScalarFormatter()
            minor.set_scientific(False)
            minor.set_useOffset(False)
            axis.set_minor_formatter(minor)
            ax.tick_params(axis=which, which="minor", labelsize=7.5)
        else:
            axis.set_minor_formatter(NullFormatter())
    else:
        axis.set_major_locator(LogLocator(base=10, numticks=12))
        axis.set_major_formatter(LogFormatterSciNotation(base=10))
        axis.set_minor_locator(LogLocator(base=10, subs=tuple(range(2, 10)),
                                          numticks=99))
        axis.set_minor_formatter(NullFormatter())


def new_axes(figsize=(7.4, 4.3), nrows=1, ncols=1, **kw):
    """A styled figure/axes pair for calculators that draw something bespoke."""
    return _figure(figsize, nrows, ncols, **kw)


def render(fig, *, pad=0.25) -> str:
    """Serialise a figure to a PNG data URI and release it."""
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight",
                    pad_inches=pad, facecolor=SURFACE)
    finally:
        fig.clear()
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def style_axes(ax, *, xlabel="", ylabel="", title="", xlog=False, ylog=False,
               legend=False, xlim=None, ylim=None):
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, pad=9, loc="left")
    if xlog:
        ax.set_xscale("log")
    if ylog:
        ax.set_yscale("log")
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    if legend:
        ax.legend(loc="best")
    return ax


def chart(series, *, xlabel="", ylabel="", title="", xlog=False, ylog=False,
          xlim=None, ylim=None, points=None, hlines=None, vlines=None,
          bands=None, figsize=(7.4, 4.3), legend=None, caption="",
          annotations=None, equal=False):
    """The workhorse line chart.

    ``series``      list of {x, y, label, color, style, width, fill}
    ``points``      operating-point markers: {x, y, label}
    ``hlines``/``vlines``  reference lines: {value, label, color, style}
    ``bands``       shaded x-ranges: {x0, x1, label, color, alpha}
    """
    fig, ax = _figure(figsize)

    for band in bands or []:
        ax.axvspan(band["x0"], band["x1"],
                   color=band.get("color", "#16497E"),
                   alpha=band.get("alpha", 0.07), lw=0,
                   label=band.get("label"))

    for i, s in enumerate(series):
        ax.plot(s["x"], s["y"],
                color=s.get("color", SERIES[i % len(SERIES)]),
                linestyle=s.get("style", "-"),
                linewidth=s.get("width", 1.9),
                label=s.get("label"),
                marker=s.get("marker"),
                markersize=s.get("markersize", 4),
                zorder=s.get("zorder", 3))
        if s.get("fill"):
            ax.fill_between(s["x"], s["y"], s.get("fill_to", 0),
                            color=s.get("color", SERIES[i % len(SERIES)]),
                            alpha=0.10, lw=0, zorder=1)

    for h in hlines or []:
        ax.axhline(h["value"], color=h.get("color", MUTED),
                   linestyle=h.get("style", "--"), linewidth=1.0,
                   zorder=2, label=h.get("label"))
    for v in vlines or []:
        ax.axvline(v["value"], color=v.get("color", MUTED),
                   linestyle=v.get("style", "--"), linewidth=1.0,
                   zorder=2, label=v.get("label"))

    for p in points or []:
        ax.plot([p["x"]], [p["y"]], marker=p.get("marker", "o"),
                markersize=p.get("size", 7),
                markerfacecolor=p.get("color", "#B3242B"),
                markeredgecolor=SURFACE, markeredgewidth=1.4,
                linestyle="none", zorder=6, label=p.get("label"))
        if p.get("annotate"):
            ax.annotate(p["annotate"], (p["x"], p["y"]),
                        textcoords="offset points",
                        xytext=p.get("offset", (9, 7)),
                        fontsize=8.5, color=INK, zorder=7)

    for a in annotations or []:
        ax.annotate(a["text"], (a["x"], a["y"]),
                    textcoords="offset points",
                    xytext=a.get("offset", (0, 0)),
                    fontsize=a.get("size", 8.5),
                    color=a.get("color", MUTED),
                    ha=a.get("ha", "left"), va=a.get("va", "bottom"),
                    zorder=7)

    if equal:
        ax.set_aspect("equal", adjustable="datalim")

    show_legend = legend
    if show_legend is None:
        show_legend = any(s.get("label") for s in series) or bool(points)
    style_axes(ax, xlabel=xlabel, ylabel=ylabel, title=title,
               xlog=xlog, ylog=ylog, legend=show_legend,
               xlim=xlim, ylim=ylim)
    if xlog:
        _format_log_axis(ax, "x")
    if ylog:
        _format_log_axis(ax, "y")

    return {"image": render(fig), "title": title, "caption": caption}


def stack(panels, *, title="", figsize=None, caption="", sharey=False):
    """Side-by-side panels sharing one caption — used for profile plots.

    Each panel is a dict accepted by :func:`chart` (minus figure-level keys).
    """
    n = len(panels)
    figsize = figsize or (3.0 * n + 1.2, 4.4)
    fig, axes = _figure(figsize, 1, n, sharey=sharey)
    if n == 1:
        axes = [axes]
    for ax, panel in zip(axes, panels):
        for i, s in enumerate(panel["series"]):
            ax.plot(s["x"], s["y"],
                    color=s.get("color", SERIES[i % len(SERIES)]),
                    linestyle=s.get("style", "-"),
                    linewidth=s.get("width", 1.9),
                    label=s.get("label"))
        for p in panel.get("points", []):
            ax.plot([p["x"]], [p["y"]], marker="o", markersize=6,
                    markerfacecolor="#B3242B", markeredgecolor=SURFACE,
                    markeredgewidth=1.3, linestyle="none", zorder=6)
        style_axes(ax, xlabel=panel.get("xlabel", ""),
                   ylabel=panel.get("ylabel", ""),
                   title=panel.get("title", ""),
                   xlog=panel.get("xlog", False),
                   ylog=panel.get("ylog", False),
                   legend=panel.get("legend", False),
                   xlim=panel.get("xlim"), ylim=panel.get("ylim"))
        if panel.get("xlog"):
            _format_log_axis(ax, "x")
        if panel.get("ylog"):
            _format_log_axis(ax, "y")
    if title:
        fig.suptitle(title, fontsize=10.5, fontweight="semibold", color=INK,
                     x=0.02, ha="left")
    fig.tight_layout()
    return {"image": render(fig), "title": title, "caption": caption}


def polar_orbit_figure(figsize=(6.4, 6.0)):
    """Square axes with no grid, for orbit and geometry sketches."""
    fig, ax = _figure(figsize)
    ax.grid(False)
    ax.set_aspect("equal")
    for spine in ax.spines.values():
        spine.set_visible(False)
    return fig, ax


def deg_ticks(ax, axis="x"):
    """Label an axis in degrees with a degree sign."""
    getattr(ax, f"{axis}axis").set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}\u00b0"))


def safe(seq):
    """Replace non-finite values with NaN so Matplotlib breaks the line."""
    return [v if isinstance(v, (int, float)) and math.isfinite(v) else float("nan")
            for v in seq]
