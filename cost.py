"""买入加权平均成本；手动成本优先。"""
import storage


def weighted_avg_cost(trades):
    """从成交列表算加权平均成本（含手续费折 USD）与净买入数量。

    trades: ccxt 统一成交结构列表（含 side/amount/price/cost/fee）。
    返回 (avg_cost, net_qty, cost_basis)。卖出按当前均价结转、不改均价。
    """
    qty = 0.0
    cost_basis = 0.0
    for t in sorted(trades, key=lambda x: x.get("timestamp") or 0):
        side = t.get("side")
        amount = float(t.get("amount") or 0)
        price = float(t.get("price") or 0)
        fee = 0.0
        f = t.get("fee") or {}
        if f and f.get("cost"):
            # 手续费可能以计价币或基础币计；这里粗略折成 USD（以成交价估）
            fcost = float(f["cost"])
            fee = fcost if (f.get("currency") in (None, "USDT", "USDC", "USD")) else fcost * price
        if amount <= 0:
            continue
        if side == "buy":
            cost_basis += amount * price + fee
            qty += amount
        elif side == "sell":
            if qty > 0:
                avg = cost_basis / qty
                sell_qty = min(amount, qty)
                cost_basis -= avg * sell_qty
                qty -= sell_qty
    avg_cost = (cost_basis / qty) if qty > 0 else 0.0
    return avg_cost, qty, cost_basis


def resolve_cost(asset, auto_cost):
    """手动成本优先，否则用自动计算值。"""
    ov = storage.load("cost_overrides")
    if not ov.empty and asset in set(ov["asset"]):
        row = ov[ov["asset"] == asset].iloc[-1]
        return float(row["cost_price_usd"])
    return auto_cost
