"""
Shared helpers for the Screener page's two tree-style visualisations:
  - a market-cap "decomposition tree": click-to-drill, ranked horizontal
    bar lists (one uniform-coloured level at a time -- see
    ranked_groups/drilldown_bar_figure/clicked_bar_label below), by
    sector -> a second dimension of your choice -> individual stocks
  - a sector/industry performance treemap (size = market cap, colour =
    today's % move), in the style of a Finviz/market-map heatmap, built
    from build_hierarchy/format_rand below

An earlier version of the decomposition tree used a single Plotly Icicle
trace instead -- a partition chart whose tile *area* is proportional to
value. That gave wildly uneven row heights (small categories squeezed into
illegible slivers) and arbitrary per-branch colours, and didn't hold up:
it was replaced with the ranked-bar approach so every row is the same
height and every bar is the same colour, matching a Power-BI-style
decomposition tree far more closely. build_hierarchy/format_rand are still
used for the (unrelated) performance treemap below, where tile area
genuinely should be proportional to market cap.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.theme import ACCENT_2, BORDER


def _node_id(*parts) -> str:
    """A stable, unique node id built from a path of values. Using the
    full path (not just the leaf label) avoids id collisions when the
    same label -- e.g. an industry name -- could in principle appear
    under more than one parent."""
    return " / ".join(str(p) for p in parts)


def build_hierarchy(
    df: pd.DataFrame,
    path: list,
    leaf_id_col: str,
    leaf_label_col: str,
    value_col: str,
    color_col: str = None,
    root_label: str = "JSE Universe",
) -> dict:
    """Build parallel ids/labels/parents/values[/colors] arrays for a
    go.Icicle(...) or go.Treemap(...) trace (use with
    branchvalues="total"), covering:
      - a single root node
      - one node per unique combination at every level of `path`, each
        valued at the sum of value_col across its descendants
      - one leaf node per row of `df`

    If `color_col` is given, also returns a parallel 'colors' list: each
    leaf's own color_col value, and each branch/root node's value_col
    -weighted average of its descendants' color_col -- rows with a NaN
    color_col are excluded from both the weight and the average (so e.g.
    one stock with no live price data doesn't drag its whole sector's
    colour to zero, it's just left out of that sector's average).
    """
    work = df.copy()
    weighting = color_col is not None
    if weighting:
        has_color = work[color_col].notna()
        work["_wcolor"] = np.where(has_color, work[value_col] * work[color_col], 0.0)
        work["_w"] = np.where(has_color, work[value_col], 0.0)

    def _agg_color(w_sum, wcolor_sum):
        return float(wcolor_sum / w_sum) if w_sum else None

    ids, labels, parents, values = [], [], [], []
    colors = [] if weighting else None

    ids.append("root")
    labels.append(root_label)
    parents.append("")
    values.append(float(work[value_col].sum()))
    if weighting:
        colors.append(_agg_color(work["_w"].sum(), work["_wcolor"].sum()))

    for i in range(len(path)):
        cols = path[: i + 1]
        agg = {value_col: "sum"}
        if weighting:
            agg["_wcolor"] = "sum"
            agg["_w"] = "sum"
        grouped = work.groupby(cols, dropna=False).agg(agg).reset_index()
        for _, row in grouped.iterrows():
            node_id = _node_id(*[row[c] for c in cols])
            parent_id = "root" if i == 0 else _node_id(*[row[c] for c in cols[:-1]])
            ids.append(node_id)
            labels.append(str(row[cols[-1]]))
            parents.append(parent_id)
            values.append(float(row[value_col]))
            if weighting:
                colors.append(_agg_color(row["_w"], row["_wcolor"]))

    for _, row in work.iterrows():
        parent_id = _node_id(*[row[c] for c in path]) if path else "root"
        ids.append("s:" + str(row[leaf_id_col]))
        labels.append(str(row[leaf_label_col]))
        parents.append(parent_id)
        values.append(float(row[value_col]) if pd.notna(row[value_col]) else 0.0)
        if weighting:
            colors.append(float(row[color_col]) if pd.notna(row[color_col]) else None)

    out = {"ids": ids, "labels": labels, "parents": parents, "values": values}
    if weighting:
        out["colors"] = colors
    return out


def format_rand(value: float) -> str:
    """Compact Rand formatting for tree/treemap labels -- billions for
    anything large, millions otherwise, so labels stay short regardless
    of company size."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    if abs(value) >= 1e9:
        return f"R{value / 1e9:,.1f}bn"
    return f"R{value / 1e6:,.0f}m"


# --------------------------------------------------------------------------
# Click-to-drill "decomposition tree" replacement: instead of an Icicle
# chart's area-proportional tiles (uneven heights, arbitrary branch colours
# -- the version the user rejected), each level is drawn as a ranked list of
# uniform-height horizontal bars in a single accent colour, with a light
# "track" bar behind every row so the bar length alone conveys relative
# size. This matches the reference decomposition-tree image far more
# closely than a partition chart ever could; clicking a bar drills into it,
# exactly like clicking a branch in that image expands it.
# --------------------------------------------------------------------------
def disambiguated_names(df: pd.DataFrame, name_col: str = "name", id_col: str = "symbol") -> pd.Series:
    """`name_col` values, aligned to df's index, with the id appended in
    parentheses wherever a name isn't unique within df -- e.g. the JSE's
    several dual-listed share classes (Investec Group trades as both INL
    and INP, Sasol Limited as both SOL and SOLBE1, etc.) would otherwise
    collide: showing "Investec Group" twice with no way to tell the bars
    apart, or -- worse -- getting summed into one bar by a groupby keyed
    on the name column instead of the ticker."""
    dup_mask = df[name_col].duplicated(keep=False)
    return pd.Series(
        np.where(dup_mask, df[name_col].astype(str) + " (" + df[id_col].astype(str) + ")", df[name_col].astype(str)),
        index=df.index,
    )


def ranked_groups(df: pd.DataFrame, group_col: str, value_col: str, max_rows: int = None):
    """Group df by group_col, sum value_col, sort descending by value.

    Returns (labels, values, n_omitted): labels/values are parallel lists
    ready for drilldown_bar_figure, and n_omitted is how many smaller
    groups were cut off by max_rows (0 if nothing was cut)."""
    agg = df.groupby(group_col, dropna=False)[value_col].sum().sort_values(ascending=False)
    n_omitted = 0
    if max_rows is not None and len(agg) > max_rows:
        n_omitted = len(agg) - max_rows
        agg = agg.head(max_rows)
    labels = [str(x) for x in agg.index]
    values = agg.values.tolist()
    return labels, values, n_omitted


def drilldown_bar_figure(labels, values, texts=None, color=None, track_color=None, height=None):
    """A ranked, uniform-row-height horizontal bar list in a single accent
    colour -- one level of a click-to-drill decomposition tree.

    `labels`/`values`/`texts` should already be sorted the way you want
    them to appear top-to-bottom; Plotly draws y-categories bottom-to-top,
    so this reverses the y-axis to match. Each row is two overlaid bars: a
    light "track" the same length as the biggest value (so every row's
    full extent is visible and clickable, like a bullet chart), and the
    actual value bar on top in a single accent colour -- no per-branch
    qualitative colour-coding, which is what made the rejected Icicle
    version look arbitrary.
    """
    color = color or ACCENT_2
    track_color = track_color or BORDER
    n = len(labels)
    texts = texts if texts is not None else [str(v) for v in values]
    max_val = max(values) if values else 1.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[max_val] * n, y=labels, orientation="h",
        marker=dict(color=track_color), hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=color), text=texts, textposition="outside",
        hovertemplate="%{y}<br>%{text}<extra></extra>", showlegend=False,
    ))
    fig.update_layout(
        barmode="overlay",
        height=height or max(130, 44 * n + 50),
        margin=dict(t=10, l=10, r=70, b=10),
        yaxis=dict(autorange="reversed", showgrid=False),
        xaxis=dict(visible=False, range=[0, max_val * 1.22 if max_val else 1]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
        bargap=0.3,
        clickmode="event+select",
    )
    return fig


def clicked_bar_label(event):
    """Pull the category label (the clicked row's y-value) out of a Plotly
    selection event from st.plotly_chart(..., on_select="rerun", ...), or
    None if nothing is currently selected.

    Tolerant of `event`, `.selection`, or `.selection.points` being
    missing/falsy, and of each point being a plain dict or an
    attribute-style object -- so it's safe to call every rerun regardless
    of selection state, and easy to unit test with a plain stand-in object
    instead of a real Streamlit widget."""
    selection = getattr(event, "selection", None) if event is not None else None
    points = getattr(selection, "points", None) if selection is not None else None
    if not points:
        return None
    point = points[0]
    if isinstance(point, dict):
        return point.get("y")
    return getattr(point, "y", None)
