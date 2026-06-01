"""生成演示数据（无需连 OKX），便于本地预览看板。

写入：investors / unit_transactions / snapshots / holdings / staking_rewards。
真实使用时无需运行此文件，改跑 collector.py。
"""
import math
import random
from datetime import timedelta, datetime, timezone

import pandas as pd

import config
import storage
import units

random.seed(7)
CST = timezone(timedelta(hours=8))


def gen(days=180):
    # 1) 初始化 GP 台账与起投申购
    for n in ("investors", "unit_transactions", "snapshots", "holdings", "staking_rewards"):
        storage.save(n, pd.DataFrame())
    units.seed_investors_if_empty()

    start = config.INCEPTION_DATE
    # 2) 第 90 天加入一个外部 LP（演示份额制 + carry）
    lp_join = start + timedelta(days=90)

    # 资产与初始数量（用 10 万配置：BTC/ETH/SOL/OKSOL/USDT）
    base_prices = {"BTC": 42000.0, "ETH": 2300.0, "SOL": 95.0, "OKSOL": 98.0, "USDT": 1.0}
    qty = {"BTC": 1.05, "ETH": 8.0, "SOL": 180.0, "OKSOL": 120.0, "USDT": 8000.0}

    snaps, holds, stak = [], [], []
    px = dict(base_prices)
    oksol_reward_cum = 0.0
    lp_added = False

    for i in range(days + 1):
        d = start + timedelta(days=i)
        # 价格随机游走（带轻微上行漂移）
        for a in px:
            if a == "USDT":
                continue
            px[a] *= (1 + random.uniform(-0.03, 0.035))
        # OKSOL 每 7 天质押发放 ~0.6% 收益（同币种）
        if i > 0 and i % 7 == 0:
            reward = qty["OKSOL"] * 0.006
            qty["OKSOL"] += reward
            oksol_reward_cum += reward
            stak.append({
                "bill_id": f"demo-bill-{i}", "ts": pd.Timestamp(d),
                "asset": "OKSOL", "amount": reward, "bill_type": "earn/staking",
                "value_usd_at_receipt": reward * px["OKSOL"],
            })

        # 第 90 天外部 LP 申购 5 万
        flow = 0.0
        if (not lp_added) and d >= lp_join:
            # 用当天净值前的估值算 NAV/份
            pre_total = sum(qty[a] * px[a] for a in qty)
            pre_units = units.total_units_as_of(d)
            navps_now = pre_total / pre_units if pre_units else 1.0
            new_units = 50000.0 / navps_now
            qty["USDT"] += 50000.0
            flow = 50000.0
            storage.upsert_by_key("unit_transactions", pd.DataFrame([{
                "txn_id": "LP1-sub", "date": d, "investor_id": "LP1",
                "type": "subscribe", "amount_usd": 50000.0, "nav_per_unit": navps_now,
                "units_delta": new_units, "discount": 0.0, "note": "外部LP增资",
            }]), key="txn_id")
            inv = storage.load("investors")
            storage.save("investors", pd.concat([inv, pd.DataFrame([{
                "investor_id": "LP1", "name": "外部投资人A", "role": "LP",
                "join_date": d, "gp_carry_weight": 0.0, "note": "",
            }])], ignore_index=True))
            lp_added = True

        total = sum(qty[a] * px[a] for a in qty)
        tu = units.total_units_as_of(d)
        navps = total / tu if tu else 1.0

        for a in qty:
            value = qty[a] * px[a]
            if value < config.DUST_THRESHOLD_USD:
                continue
            staked_amt = oksol_reward_cum if a == "OKSOL" else 0.0
            bought = max(qty[a] - staked_amt, 0.0)
            cost_price = base_prices[a]
            holds.append({
                "date": d, "asset": a, "amount": qty[a], "price_usd": px[a],
                "value_usd": value, "cost_price_usd": cost_price,
                "cost_basis_usd": cost_price * bought,
                "unrealized_pnl_usd": value - cost_price * bought,
                "staking_amount": staked_amt, "staking_value_usd": staked_amt * px[a],
                "weight": 0.0,
            })

        cum_inflow = 100000.0 + (50000.0 if lp_added else 0.0)
        snaps.append({
            "date": d, "total_value_usd": total,
            "trading_value_usd": total * 0.7, "funding_value_usd": total * 0.3,
            "total_units": tu, "nav_per_unit": navps,
            "net_external_flow_usd": flow, "cumulative_inflow_usd": cum_inflow,
            "pnl_usd": total - cum_inflow, "created_at": datetime.now(CST),
        })

    snaps_df = pd.DataFrame(snaps)
    holds_df = pd.DataFrame(holds)
    # 计算每日 weight
    holds_df["weight"] = holds_df.groupby("date")["value_usd"].transform(lambda s: s / s.sum())
    storage.save("snapshots", snaps_df)
    storage.save("holdings", holds_df)
    if stak:
        storage.save("staking_rewards", pd.DataFrame(stak))

    last = snaps_df.iloc[-1]
    print(f"演示数据已生成：{days+1} 天，期末净值 {last['total_value_usd']:,.0f} USDT，"
          f"NAV/份 {last['nav_per_unit']:.4f}，份额 {last['total_units']:,.0f}")


if __name__ == "__main__":
    gen()
