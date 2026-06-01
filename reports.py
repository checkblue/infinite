"""定期报表：从 snapshots 派生期间业绩；LP 对账单。"""
from datetime import date

import pandas as pd

import storage
import metrics
import distribution
import units as units_mod


def period_range(period_key):
    """'2026Q1' / '2026H1' / '2026FY' / '2026-03' → (start, end)。"""
    if "Q" in period_key:
        y, q = period_key.split("Q")
        y, q = int(y), int(q)
        start = date(y, 3 * (q - 1) + 1, 1)
        end_month = 3 * q
        end = date(y, end_month, 1) + pd.offsets.MonthEnd(0)
    elif "H" in period_key:
        y, h = period_key.split("H")
        y, h = int(y), int(h)
        start = date(y, 1 if h == 1 else 7, 1)
        end = date(y, 6 if h == 1 else 12, 1) + pd.offsets.MonthEnd(0)
    elif period_key.endswith("FY"):
        y = int(period_key[:4])
        start, end = date(y, 1, 1), date(y, 12, 31)
    else:  # 月 'YYYY-MM'
        y, m = map(int, period_key.split("-"))
        start = date(y, m, 1)
        end = start + pd.offsets.MonthEnd(0)
    return pd.to_datetime(start), pd.to_datetime(end)


def period_report(period_key):
    start, end = period_range(period_key)
    snaps = storage.load("snapshots")
    if snaps.empty:
        return None
    s = snaps.copy()
    s["date"] = pd.to_datetime(s["date"])
    s = s.rename(columns={"total_value_usd": "total_value", "net_external_flow_usd": "net_external_flow"})
    win = s[(s["date"] >= start) & (s["date"] <= end)].sort_values("date")
    if win.empty:
        return None

    nav_start = float(win.iloc[0]["total_value"])
    nav_end = float(win.iloc[-1]["total_value"])
    net_flow = float(win["net_external_flow"].sum())
    period_pnl = nav_end - nav_start - net_flow
    twr = metrics.twr(s, start, end)
    days = max((end - start).days, 1)
    ann = (1 + twr) ** (365 / days) - 1
    mdd = metrics.max_drawdown(win["total_value"])
    xirr = metrics.xirr_inception(nav_end, as_of=end)
    navps_start = float(win.iloc[0]["nav_per_unit"])
    navps_end = float(win.iloc[-1]["nav_per_unit"])

    # 期末资产配置
    hold = storage.load("holdings")
    alloc = {}
    if not hold.empty:
        h = hold.copy()
        h["date"] = pd.to_datetime(h["date"])
        last_day = h[h["date"] <= end]["date"].max()
        hl = h[h["date"] == last_day]
        tot = hl["value_usd"].sum()
        alloc = {r["asset"]: r["value_usd"] / tot for _, r in hl.iterrows()} if tot else {}

    return {
        "period": period_key, "start": start.date(), "end": end.date(),
        "nav_start": nav_start, "nav_end": nav_end, "net_flow": net_flow,
        "period_pnl": period_pnl, "twr": twr, "annualized": ann,
        "max_drawdown": mdd, "xirr_inception": xirr,
        "navps_start": navps_start, "navps_end": navps_end,
        "allocation": alloc,
    }


def lp_statement(investor_id, as_of=None):
    """单个出资人对账单：份额、出资、当前资产、按瀑布测算应得。"""
    snaps = storage.load("snapshots")
    if snaps.empty:
        return None
    s = snaps.copy()
    s["date"] = pd.to_datetime(s["date"])
    last = s.sort_values("date").iloc[-1]
    total_value = float(last["total_value_usd"])
    navps = float(last["nav_per_unit"])
    as_of = as_of or last["date"].date()

    held = units_mod.units_by_investor(as_of).get(investor_id, 0.0)
    wf = distribution.waterfall(total_value, as_of=as_of)
    me = next((r for r in wf["investors"] if r["investor_id"] == investor_id), None)
    return {
        "investor_id": investor_id, "as_of": as_of,
        "units": held, "current_value": held * navps, "nav_per_unit": navps,
        "waterfall": me,
    }
