"""M1：读取 OKX 交易账户 + 资金账户余额，估值并打印总净值与持仓列表。

用法：
    1. cp .env.example .env  并填入只读 API 凭据
    2. pip install -r requirements.txt
    3. python networth.py
"""
import config
from okx_client import make_exchange, fetch_account_balances, fetch_prices


def merge_balances(trading, funding):
    merged = dict(trading)
    for ccy, amt in funding.items():
        merged[ccy] = merged.get(ccy, 0.0) + amt
    return merged


def account_value(balances, prices):
    """某账户的可估值市值合计（无价格的币种跳过）。"""
    total = 0.0
    for ccy, amt in balances.items():
        px = prices.get(ccy)
        if px is not None:
            total += amt * px
    return total


def build_rows(merged, prices):
    rows = []
    for ccy, amt in merged.items():
        px = prices.get(ccy)
        value = amt * px if px is not None else None
        rows.append({"asset": ccy, "amount": amt, "price": px, "value": value})
    return rows


def main():
    ex = make_exchange()

    trading, funding = fetch_account_balances(ex)
    merged = merge_balances(trading, funding)
    prices = fetch_prices(ex, set(merged))

    trading_value = account_value(trading, prices)
    funding_value = account_value(funding, prices)

    rows = build_rows(merged, prices)
    unpriced = [r for r in rows if r["value"] is None]
    priced = [r for r in rows if r["value"] is not None]

    keep = [r for r in priced if r["value"] >= config.DUST_THRESHOLD_USD]
    dust = [r for r in priced if r["value"] < config.DUST_THRESHOLD_USD]
    keep.sort(key=lambda r: r["value"], reverse=True)

    total = sum(r["value"] for r in keep)  # 总净值（剔除灰尘）

    print("=" * 64)
    print("OKX 私募基金 — 资金概览 (M1)")
    print("=" * 64)
    print(f"交易账户市值 : {trading_value:>16,.2f} USDT")
    print(f"资金账户市值 : {funding_value:>16,.2f} USDT")
    print(f"总净值       : {total:>16,.2f} USDT  (剔除 <{config.DUST_THRESHOLD_USD:g} USDT 灰尘)")
    print("-" * 64)
    print(f"{'资产':<8}{'数量':>20}{'价格USDT':>14}{'市值USDT':>15}{'占比':>8}")
    print("-" * 64)
    for r in keep:
        weight = r["value"] / total if total else 0.0
        flag = "  ⚠超50%" if weight >= config.CONCENTRATION_ALERT else ""
        print(
            f"{r['asset']:<8}{r['amount']:>20.8f}{r['price']:>14.6f}"
            f"{r['value']:>15,.2f}{weight * 100:>7.1f}%{flag}"
        )

    if dust:
        names = ", ".join(r["asset"] for r in dust)
        print("-" * 64)
        print(f"已忽略灰尘({len(dust)}): {names}")
    if unpriced:
        names = ", ".join(r["asset"] for r in unpriced)
        print(f"⚠ 无 {config.QUOTE} 行情、未估值: {names}")
    print("=" * 64)


if __name__ == "__main__":
    main()
