"""业绩指标：XIRR（自起投，资金加权）、TWR（期间，时间加权）、最大回撤、集中度。"""
import pandas as pd

import storage


def _xirr(dates, amounts):
    """自实现 XIRR（Newton + bisection 兜底），无需外部依赖。"""
    try:
        from pyxirr import xirr
        return xirr(dates, amounts)
    except Exception:
        pass
    d0 = pd.to_datetime(dates[0])
    ts = [(pd.to_datetime(d) - d0).days / 365.0 for d in dates]

    def npv(rate):
        return sum(a / (1 + rate) ** t for a, t in zip(amounts, ts))

    lo, hi = -0.9999, 10.0
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fmid = npv(mid)
        if abs(fmid) < 1e-6:
            return mid
        if flo * fmid < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return (lo + hi) / 2


def xirr_inception(current_value, as_of=None):
    """从 unit_transactions 构造外部现金流 + 末尾当前净值，求 XIRR。"""
    txns = storage.load("unit_transactions")
    if txns.empty:
        return None
    d = txns.copy()
    if as_of is not None:
        d = d[pd.to_datetime(d["date"]) <= pd.to_datetime(as_of)]
    dates, amounts = [], []
    for _, t in d.sort_values("date").iterrows():
        amt = float(t["amount_usd"])
        # 申购=出资=流出(负)；赎回=流入(正)
        amounts.append(-amt if t["type"] == "subscribe" else amt)
        dates.append(pd.to_datetime(t["date"]))
    dates.append(pd.to_datetime(as_of) if as_of is not None else pd.Timestamp.today())
    amounts.append(current_value)
    return _xirr(dates, amounts)


def twr(snapshots, start, end):
    """期间时间加权收益：按外部现金流分段链接。snapshots 需含 date/total_value/net_external_flow。"""
    df = snapshots.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))].sort_values("date")
    if len(df) < 2:
        return 0.0
    factor = 1.0
    prev_v = float(df.iloc[0]["total_value"])
    for _, row in df.iloc[1:].iterrows():
        flow = float(row.get("net_external_flow", 0) or 0)
        v_before = float(row["total_value"]) - flow   # 剔除当日流入后的期末值
        if prev_v > 0:
            factor *= v_before / prev_v
        prev_v = float(row["total_value"])
    return factor - 1.0


def max_drawdown(series):
    """series: 净值序列(list/Series)，返回最大回撤(正数)。"""
    s = pd.Series(list(series)).astype(float)
    if s.empty:
        return 0.0
    peak = s.cummax()
    dd = (peak - s) / peak.replace(0, pd.NA)
    return float(dd.max() or 0.0)


def concentration(holdings):
    """holdings: DataFrame 含 value 列。返回最大单一资产占比。"""
    if holdings.empty:
        return 0.0
    total = holdings["value"].sum()
    return float(holdings["value"].max() / total) if total else 0.0
