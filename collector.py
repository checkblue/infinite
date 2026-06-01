"""每日快照采集器（cron 调用，东八区 0 点）。

流程：拉余额(交易+资金)/行情/账单 → 算成本/质押/净值/NAV → 幂等写 snapshots + holdings。
"""
from datetime import datetime, timezone, timedelta

import pandas as pd

import config
import storage
import units
import staking
import cost
from okx_client import (
    make_exchange, fetch_account_balances, fetch_prices,
    fetch_trades, fetch_funding_bills, fetch_earn_rewards,
)

CST = timezone(timedelta(hours=8))  # 东八区


def today_cst():
    return datetime.now(CST).date()


def run(as_of=None):
    as_of = as_of or today_cst()
    units.seed_investors_if_empty()

    ex = make_exchange()
    trading, funding = fetch_account_balances(ex)
    merged = {}
    for d in (trading, funding):
        for ccy, amt in d.items():
            merged[ccy] = merged.get(ccy, 0.0) + amt
    prices = fetch_prices(ex, set(merged))

    # 质押收益：账单(asset/bills)持久化作审计流水；累计值以 Earn 接口为准(覆盖账单)。
    # rewards=各币种 lifetime 累计收益(0 成本)；账单覆盖 USDT 理财等无 Earn 接口的币种。
    staking.ingest_funding_bills(fetch_funding_bills(ex))
    rewards = staking.cumulative_by_asset()
    rewards.update(fetch_earn_rewards(ex))  # Earn 接口为准：OKSOL/BETH lifetime 累计

    def acct_val(bal):
        return sum(amt * prices[c] for c, amt in bal.items() if prices.get(c) is not None)

    trading_value = acct_val(trading)
    funding_value = acct_val(funding)

    rows = []
    for ccy, amt in merged.items():
        px = prices.get(ccy)
        if px is None:
            continue
        value = amt * px
        if value < config.DUST_THRESHOLD_USD:
            continue
        # 成本：自动(成交) + 手动覆盖优先；成本仅算「非质押收益」部分（收益 0 成本）
        auto_cost = 0.0
        if ccy not in config.STABLES:
            avg, _, _ = cost.weighted_avg_cost(fetch_trades(ex, ccy))
            auto_cost = avg
        cost_price = cost.resolve_cost(ccy, auto_cost)
        reward_qty = rewards.get(ccy, 0.0)  # 累计质押收益数量（0 成本）
        bought_qty = max(amt - reward_qty, 0.0)
        cost_basis = cost_price * bought_qty
        # 已质押数量：流动质押币整仓即质押本金（复投），其余资产取累计收益数量
        staked_qty = amt if ccy in config.STAKING_TOKENS else reward_qty
        rows.append({
            "date": as_of, "asset": ccy, "amount": amt, "price_usd": px,
            "value_usd": value, "cost_price_usd": cost_price, "cost_basis_usd": cost_basis,
            "unrealized_pnl_usd": value - cost_basis,
            "staking_amount": staked_qty,
            "staking_value_usd": staked_qty * px,
            "staking_reward_amount": reward_qty,
            "staking_reward_value_usd": reward_qty * px,
        })

    holdings = pd.DataFrame(rows)
    total = float(holdings["value_usd"].sum()) if not holdings.empty else 0.0
    holdings["weight"] = holdings["value_usd"] / total if total else 0.0

    navps = units.nav_per_unit(total, as_of)
    total_units = units.total_units_as_of(as_of)
    cum_inflow = _cumulative_inflow(as_of)

    snap = pd.DataFrame([{
        "date": as_of, "total_value_usd": total,
        "trading_value_usd": trading_value, "funding_value_usd": funding_value,
        "total_units": total_units, "nav_per_unit": navps,
        "net_external_flow_usd": _flow_on(as_of),
        "cumulative_inflow_usd": cum_inflow, "pnl_usd": total - cum_inflow,
        "created_at": datetime.now(CST),
    }])

    # 幂等：覆盖当天
    holdings = holdings.assign(date=as_of)
    _replace_day("holdings", holdings, as_of)
    storage.upsert_by_key("snapshots", snap, key="date")
    print(f"[{as_of}] 快照完成：总净值 {total:,.2f} USDT，NAV/份 {navps:.4f}，份额 {total_units:,.0f}")


def _cumulative_inflow(as_of):
    txns = storage.load("unit_transactions")
    if txns.empty:
        return 0.0
    d = txns[pd.to_datetime(txns["date"]) <= pd.to_datetime(as_of)]
    inflow = d.loc[d["type"] == "subscribe", "amount_usd"].sum()
    outflow = d.loc[d["type"] == "redeem", "amount_usd"].sum()
    return float(inflow - outflow)


def _flow_on(as_of):
    txns = storage.load("unit_transactions")
    if txns.empty:
        return 0.0
    d = txns[pd.to_datetime(txns["date"]).dt.date == pd.to_datetime(as_of).date()]
    inflow = d.loc[d["type"] == "subscribe", "amount_usd"].sum()
    outflow = d.loc[d["type"] == "redeem", "amount_usd"].sum()
    return float(inflow - outflow)


def _replace_day(name, df_day, as_of):
    old = storage.load(name)
    if not old.empty:
        old = old[pd.to_datetime(old["date"]).dt.date != pd.to_datetime(as_of).date()]
        df_day = pd.concat([old, df_day], ignore_index=True)
    storage.save(name, df_day)


if __name__ == "__main__":
    run()
