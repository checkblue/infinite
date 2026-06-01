"""份额制：单位净值（NAV/份）、份额、申购与赎回。"""
import pandas as pd

import config
import storage


def seed_investors_if_empty():
    """首次初始化：写入 PP/CC 台账 + 起投日申购记录（NAV/份=1.0）。"""
    inv = storage.load("investors")
    if not inv.empty:
        return
    rows = [{
        "investor_id": s["investor_id"], "name": s["name"], "role": s["role"],
        "join_date": config.INCEPTION_DATE, "gp_carry_weight": s["gp_carry_weight"], "note": "",
    } for s in config.INVESTORS_SEED]
    storage.save("investors", pd.DataFrame(rows))

    txns = []
    for s in config.INVESTORS_SEED:
        units = s["amount"] / config.INITIAL_NAV_PER_UNIT
        txns.append({
            "txn_id": f'{s["investor_id"]}-inception',
            "date": config.INCEPTION_DATE, "investor_id": s["investor_id"],
            "type": "subscribe", "amount_usd": s["amount"],
            "nav_per_unit": config.INITIAL_NAV_PER_UNIT, "units_delta": units,
            "discount": 0.0, "note": "起投",
        })
    storage.save("unit_transactions", pd.DataFrame(txns))


def total_units_as_of(as_of=None):
    df = storage.load("unit_transactions")
    if df.empty:
        return 0.0
    d = df.copy()
    if as_of is not None:
        d = d[pd.to_datetime(d["date"]) <= pd.to_datetime(as_of)]
    return float(d["units_delta"].sum())


def units_by_investor(as_of=None):
    df = storage.load("unit_transactions")
    if df.empty:
        return {}
    d = df.copy()
    if as_of is not None:
        d = d[pd.to_datetime(d["date"]) <= pd.to_datetime(as_of)]
    return d.groupby("investor_id")["units_delta"].sum().to_dict()


def nav_per_unit(total_value, as_of=None):
    units = total_units_as_of(as_of)
    return (total_value / units) if units > 0 else config.INITIAL_NAV_PER_UNIT


def register_subscription(investor_id, the_date, amount_usd, navps):
    """新申购/增资：按当时 NAV/份折算份额。"""
    units = amount_usd / navps
    row = pd.DataFrame([{
        "txn_id": f"{investor_id}-{the_date}-sub", "date": the_date,
        "investor_id": investor_id, "type": "subscribe", "amount_usd": amount_usd,
        "nav_per_unit": navps, "units_delta": units, "discount": 0.0, "note": "增资",
    }])
    storage.upsert_by_key("unit_transactions", row, key="txn_id")
    return units


def redemption_quote(investor_id, month_end_navps, discount=None, as_of=None):
    """赎回测算：份额 × 月末NAV × (1-折价)。"""
    discount = config.REDEEM_DISCOUNT if discount is None else discount
    units = units_by_investor(as_of).get(investor_id, 0.0)
    gross = units * month_end_navps
    net = gross * (1 - discount)
    return {"units": units, "gross": gross, "discount": discount, "net": net}
