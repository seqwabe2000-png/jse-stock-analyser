"""
Beta-neutral long/short position sizing -- reproduces beta_neutral_template.xlsx
(Basket Calculator + Pair-by-Pair sheets) for the Stops & Targets page's
third tab.

The maths (same in both calculators, just applied once per side vs. once
per pair):
    Beta-neutral condition:  L x beta_long = S x beta_short
    Gross budget:            L + S = G
    Solution:                L = G x beta_short / (beta_long + beta_short)
                             S = G x beta_long  / (beta_long + beta_short)
Basket beta = sum(weight_i x beta_i) across a side's stocks, weights summing
to 100% on that side. Position in stock i = side dollars x weight_i.

Needs positive basket betas on both sides -- it only removes market risk,
not sector/style/single-stock risk, and no costs (borrow, financing,
margin, spreads) are modelled. General education / calculation aid, not
investment advice.
"""
import numpy as np
import pandas as pd

MAX_PER_SIDE = 8  # matches the template's Basket Calculator (8 rows per side)
MAX_PAIRS = 16


# --------------------------------------------------------------------------
# Basket Calculator
# --------------------------------------------------------------------------
def _effective_weights(beta: pd.Series, custom_weight: pd.Series, weighting: str) -> pd.Series:
    """One side's effective weight per row -- mirrors column D in the
    template: 0 for any row without a numeric beta; otherwise an equal
    share of however many rows DO have a numeric beta (Equal mode), or
    that row's own custom weight normalised against the sum of all custom
    weights on rows with a numeric beta (Custom mode)."""
    has_beta = beta.notna()
    n = int(has_beta.sum())
    if weighting == "Equal":
        return pd.Series(np.where(has_beta, (1.0 / n) if n else 0.0, 0.0), index=beta.index)
    cw = pd.to_numeric(custom_weight, errors="coerce").fillna(0.0).where(has_beta, 0.0)
    total = cw.sum()
    return cw / total if total > 0 else pd.Series(0.0, index=beta.index)


def _side_beta(beta: pd.Series, weight: pd.Series) -> float:
    return float((beta.fillna(0.0) * weight).sum())


def basket_calculator(
    long_df: pd.DataFrame,
    short_df: pd.DataFrame,
    gross_budget: float,
    weighting: str = "Equal",
    total_capital: float = None,
) -> dict:
    """long_df/short_df need 'beta' and (Custom mode only) 'custom_weight'
    columns, one row per stock. Returns a dict with each side's rows
    (annotated with effective weight / position / beta-weighted position)
    plus the Results and Checks blocks from the template."""
    long_df = long_df.copy()
    short_df = short_df.copy()
    long_df["beta"] = pd.to_numeric(long_df.get("beta"), errors="coerce")
    short_df["beta"] = pd.to_numeric(short_df.get("beta"), errors="coerce")

    long_df["weight"] = _effective_weights(long_df["beta"], long_df.get("custom_weight", pd.Series(dtype=float)), weighting)
    short_df["weight"] = _effective_weights(short_df["beta"], short_df.get("custom_weight", pd.Series(dtype=float)), weighting)

    beta_long = _side_beta(long_df["beta"], long_df["weight"])
    beta_short = _side_beta(short_df["beta"], short_df["weight"])

    both_positive = beta_long > 0 and beta_short > 0
    denom = beta_long + beta_short
    long_dollars = gross_budget * beta_short / denom if both_positive and denom else 0.0
    short_dollars = gross_budget * beta_long / denom if both_positive and denom else 0.0

    long_df["position"] = long_dollars * long_df["weight"]
    short_df["position"] = short_dollars * short_df["weight"]
    long_df["beta_weighted"] = long_df["position"] * long_df["beta"].fillna(0.0)
    short_df["beta_weighted"] = short_df["position"] * short_df["beta"].fillna(0.0)

    beta_weighted_long = float(long_df["beta_weighted"].sum())
    beta_weighted_short = float(short_df["beta_weighted"].sum())
    net_beta = round(beta_weighted_long - beta_weighted_short, 2)
    gross_exposure = long_dollars + short_dollars
    cash_left = (total_capital - gross_exposure) if total_capital is not None else None

    n_long = int(long_df["beta"].notna().sum())
    n_short = int(short_df["beta"].notna().sum())
    custom_sum_long = pd.to_numeric(long_df.get("custom_weight"), errors="coerce").fillna(0.0).where(long_df["beta"].notna(), 0.0).sum()
    custom_sum_short = pd.to_numeric(short_df.get("custom_weight"), errors="coerce").fillna(0.0).where(short_df["beta"].notna(), 0.0).sum()

    checks = {
        "Each side has at least one stock": n_long > 0 and n_short > 0,
        "Both basket betas are positive": both_positive,
        "Net beta is zero": abs(net_beta) < 0.5,
        "Custom weights add to 100% (Custom mode only)": (
            None if weighting == "Equal" else bool(abs(custom_sum_long - 1) < 1e-4 and abs(custom_sum_short - 1) < 1e-4)
        ),
        "Gross within capital (no leverage)": (cash_left is None) or cash_left >= 0,
    }

    return {
        "long_df": long_df,
        "short_df": short_df,
        "beta_long": beta_long,
        "beta_short": beta_short,
        "long_dollars": long_dollars,
        "short_dollars": short_dollars,
        "long_share_of_gross": (long_dollars / gross_budget) if gross_budget else 0.0,
        "net_dollar_exposure": long_dollars - short_dollars,
        "beta_weighted_long": beta_weighted_long,
        "beta_weighted_short": beta_weighted_short,
        "net_beta": net_beta,
        "gross_exposure": gross_exposure,
        "cash_left": cash_left,
        "checks": checks,
    }


# --------------------------------------------------------------------------
# Pair-by-Pair
# --------------------------------------------------------------------------
def pair_by_pair(pairs_df: pd.DataFrame, default_slot: float, total_capital: float = None) -> dict:
    """pairs_df needs 'long_ticker', 'long_beta', 'short_ticker', 'short_beta',
    and optional 'slot_override' columns, one row per pair. Returns the
    annotated rows plus the Summary block from the template."""
    df = pairs_df.copy()
    df["long_beta"] = pd.to_numeric(df.get("long_beta"), errors="coerce")
    df["short_beta"] = pd.to_numeric(df.get("short_beta"), errors="coerce")
    override = pd.to_numeric(df.get("slot_override"), errors="coerce")

    has_both_betas = df["long_beta"].notna() & df["short_beta"].notna()
    slot = override.where(override.notna(), default_slot)
    df["slot_used"] = np.where(has_both_betas, slot.fillna(0.0), 0.0)

    beta_sum = df["long_beta"].fillna(0.0) + df["short_beta"].fillna(0.0)
    usable = (df["slot_used"] > 0) & (beta_sum > 0)
    df["long_position"] = np.where(usable, df["slot_used"] * df["short_beta"].fillna(0.0) / beta_sum.replace(0, np.nan), 0.0)
    df["short_position"] = np.where(usable, df["slot_used"] * df["long_beta"].fillna(0.0) / beta_sum.replace(0, np.nan), 0.0)
    df["long_position"] = df["long_position"].fillna(0.0)
    df["short_position"] = df["short_position"].fillna(0.0)
    df["beta_check"] = (df["long_position"] * df["long_beta"].fillna(0.0) - df["short_position"] * df["short_beta"].fillna(0.0)).round(2)
    df["long_share_of_slot"] = np.where(df["slot_used"] > 0, df["long_position"] / df["slot_used"], 0.0)

    slot_total = float(df["slot_used"].sum())
    long_total = float(df["long_position"].sum())
    short_total = float(df["short_position"].sum())
    beta_check_total = float(df["beta_check"].sum())
    gross_exposure = long_total + short_total
    cash_left = (total_capital - gross_exposure) if total_capital is not None else None

    checks = {
        "Check: no leverage": (cash_left is None) or cash_left >= 0,
        "Check: every pair is beta-neutral": float(df["beta_check"].abs().sum()) < 1,
    }

    return {
        "rows": df,
        "slot_total": slot_total,
        "long_total": long_total,
        "short_total": short_total,
        "beta_check_total": beta_check_total,
        "long_share_total": (long_total / slot_total) if slot_total else 0.0,
        "gross_exposure": gross_exposure,
        "cash_left": cash_left,
        "net_beta": beta_check_total,
        "checks": checks,
    }
