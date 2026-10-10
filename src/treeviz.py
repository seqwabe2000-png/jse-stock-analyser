"""
Shared hierarchy-building helpers for the Screener page's two tree-style
visualisations:
  - a market-cap "decomposition tree" (an Icicle trace) you can drill into
    by sector -> a second dimension of your choice -> individual stocks
  - a sector/industry performance treemap (size = market cap, colour =
    today's % move), in the style of a Finviz/market-map heatmap

Both ultimately need the same thing: a flat list of (id, label, parent,
value[, colour]) rows covering every level of a drill-down path plus the
leaf stocks, with branch/root values and colours rolled up from their
children. That rollup is built once here so the two chart-building
functions in the Screener page don't duplicate the groupby logic.
"""
import numpy as np
import pandas as pd


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
