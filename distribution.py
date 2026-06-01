"""收益分配瀑布：先回本 → 优先收益(8%复利, 按出资人持有期) → 超额 LP80/GP20。

GP 自有资金不抽 carry；carry 池在 GP 间按权重(PP:CC=8:2)分。
"""
from datetime import date

import pandas as pd

import config
import storage


def _years(d0, d1):
    return max((pd.to_datetime(d1) - pd.to_datetime(d0)).days, 0) / 365.0


def _preferred(amount, years):
    r = config.PREF_RETURN_RATE
    if config.PREF_COMPOUNDING == "compound":
        return amount * ((1 + r) ** years - 1)
    return amount * r * years


def waterfall(total_value, as_of=None):
    """返回分配结果：每位出资人的本金/优先收益/超额，及 GP carry 明细。"""
    as_of = as_of or date.today()
    txns = storage.load("unit_transactions")
    inv = storage.load("investors")
    if txns.empty or inv.empty:
        return {"investors": [], "total_value": total_value, "excess_pool": 0.0, "gp_carry": {}}

    role = dict(zip(inv["investor_id"], inv["role"]))

    # 各出资人本金、优先收益（按每笔申购的持有期分别累计）
    cap, pref = {}, {}
    subs = txns[txns["type"] == "subscribe"]
    for _, t in subs.iterrows():
        iid = t["investor_id"]
        amt = float(t["amount_usd"])
        yrs = _years(t["date"], as_of)
        cap[iid] = cap.get(iid, 0.0) + amt
        pref[iid] = pref.get(iid, 0.0) + _preferred(amt, yrs)

    total_cap = sum(cap.values())
    total_pref = sum(pref.values())
    excess_total = max(total_value - total_cap - total_pref, 0.0)

    # 按出资比例把超额归因到各出资人
    results = []
    gp_carry = {g: 0.0 for g in config.GP_CARRY_SPLIT}
    for iid in cap:
        share = cap[iid] / total_cap if total_cap else 0.0
        excess_i = excess_total * share
        is_gp = role.get(iid) == "GP"
        if is_gp and not config.GP_CAPITAL_CARRY:
            lp_excess, carry = excess_i, 0.0           # GP 自有资金不抽 carry
        else:
            lp_excess = excess_i * config.EXCESS_LP_SHARE
            carry = excess_i * config.EXCESS_GP_SHARE   # LP 超额的 20% 进 GP 池
            for g, w in config.GP_CARRY_SPLIT.items():
                gp_carry[g] += carry * w
        results.append({
            "investor_id": iid, "role": role.get(iid),
            "capital": cap[iid], "preferred": pref[iid],
            "excess_to_investor": lp_excess, "carry_to_gp": carry,
            "payout": cap[iid] + pref[iid] + lp_excess,
        })

    # GP 还要加上各自从 carry 池分得的部分
    for r in results:
        r["payout"] += gp_carry.get(r["investor_id"], 0.0)
        r["gp_carry_received"] = gp_carry.get(r["investor_id"], 0.0)

    return {
        "investors": results, "total_value": total_value,
        "total_capital": total_cap, "total_preferred": total_pref,
        "excess_pool": excess_total, "gp_carry": gp_carry,
    }
