"""质押/理财收益：从资金账户账单(asset/bills)识别收益条目，按 billId 去重持久化、累计。

OKX 账单仅近 3 个月，故每日增量抓取累计到本地 staking_rewards 表（永久保留，用于后续计算）。
收益类型码已对实际返回确认（见 config.STAKING_REWARD_BILL_TYPES）；
另以 notes 含 "earning" 作兜底，避免新增产品时漏判。收益按 0 成本计入。
"""
import pandas as pd

import config
import storage


def is_reward_bill(bill):
    """资金账单是否为质押/理财收益（0 成本）：类型码命中 或 notes 含 earning。"""
    if str(bill.get("type")) in config.STAKING_REWARD_BILL_TYPES:
        return True
    return "earning" in str(bill.get("notes") or "").lower()


def ingest_funding_bills(bills):
    """把资金账单中的收益条目，按 bill_id 去重写入 staking_rewards 表。"""
    rows = []
    for b in bills:
        if not is_reward_bill(b):
            continue
        amount = float(b.get("balChg") or 0)
        if amount <= 0:  # 收益为入账（正），划转/赎回（负）不计
            continue
        rows.append({
            "bill_id": str(b.get("billId") or ""),
            "ts": pd.to_datetime(int(b.get("ts")), unit="ms"),
            "asset": b.get("ccy"),
            "amount": amount,
            "bill_type": str(b.get("type")),
            "notes": str(b.get("notes") or ""),
            "value_usd_at_receipt": None,
        })
    if not rows:
        return storage.load("staking_rewards")
    df = pd.DataFrame(rows)
    df = df[df["bill_id"] != ""]
    return storage.append_dedup("staking_rewards", df, key="bill_id")


def cumulative_by_asset():
    """各币种累计质押收益数量（0 成本部分）。"""
    df = storage.load("staking_rewards")
    if df.empty:
        return {}
    return df.groupby("asset")["amount"].sum().to_dict()
