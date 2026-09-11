"""
Small shared HTML-rendering helpers for Streamlit pages -- things that
don't fit neatly as a plain st.dataframe (custom multi-column grids etc).
"""
import pandas as pd


def percentile_grid_html(pct_table: pd.DataFrame, title: str = "Percentiles") -> str:
    """Render a 1st-99th percentile table as a compact 3-pair-column grid:
    1%-15% in steps of 1, 20%-80% in steps of 5, 85%-99% in steps of 1 --
    fine detail at the tails (where stop/target decisions actually live),
    coarser in the middle where it matters less. Matches the layout the
    user asked for, rather than a single long 99-row table or a dropdown.
    """
    lookup = dict(zip(pct_table["Percentile"], pct_table["Value"]))
    col_a = list(range(1, 16))
    col_b = list(range(20, 81, 5))
    col_c = list(range(85, 100))
    n = max(len(col_a), len(col_b), len(col_c))
    col_a += [None] * (n - len(col_a))
    col_b += [None] * (n - len(col_b))
    col_c += [None] * (n - len(col_c))

    row_html = []
    for a, b, c in zip(col_a, col_b, col_c):
        cells = []
        for p in (a, b, c):
            if p is None:
                cells.append("<td></td><td></td>")
            else:
                v = lookup.get(p)
                val_str = f"{v:.2%}" if v is not None and v == v else "—"
                cells.append(f"<td class='jse-pct-p'>{p}%</td><td class='jse-pct-v'>{val_str}</td>")
        row_html.append(f"<tr>{''.join(cells)}</tr>")

    return (
        "<table class='jse-percentile-table'>"
        f"<thead><tr><th colspan='6'>{title}</th></tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody>"
        "</table>"
    )
