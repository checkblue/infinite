"""OKX (ccxt) 只读封装：余额、行情、成交、账单、出入金。"""
import ccxt

import config


def make_exchange():
    if not (config.OKX_API_KEY and config.OKX_SECRET and config.OKX_PASSWORD):
        raise RuntimeError(
            "缺少 OKX API 凭据：请在 .env 配置 OKX_API_KEY / OKX_SECRET / OKX_PASSWORD（passphrase），只读权限。"
        )
    ex = ccxt.okx({
        "apiKey": config.OKX_API_KEY,
        "secret": config.OKX_SECRET,
        "password": config.OKX_PASSWORD,
        "enableRateLimit": True,
    })
    if config.OKX_PROXY:
        ex.httpsProxy = config.OKX_PROXY  # OKX 在部分地区需走代理
    return ex


def _nonzero_totals(balance):
    out = {}
    for ccy, amt in (balance.get("total") or {}).items():
        try:
            amt = float(amt)
        except (TypeError, ValueError):
            continue
        if amt > 0:
            out[ccy] = out.get(ccy, 0.0) + amt
    return out


def fetch_account_balances(exchange):
    trading = _nonzero_totals(exchange.fetch_balance())
    funding = _nonzero_totals(exchange.fetch_balance({"type": "funding"}))
    return trading, funding


def fetch_prices(exchange, assets):
    prices = {}
    need = []
    for a in assets:
        if a in config.STABLES:
            prices[a] = 1.0
        else:
            need.append(a)
    if not need:
        return prices
    symbols = [f"{a}/{config.QUOTE}" for a in need]
    tickers = {}
    try:
        tickers = exchange.fetch_tickers(symbols)
    except Exception:
        for s in symbols:
            try:
                tickers[s] = exchange.fetch_ticker(s)
            except Exception:
                pass
    for a in need:
        t = tickers.get(f"{a}/{config.QUOTE}")
        last = t.get("last") if t else None
        prices[a] = float(last) if last else None
    return prices


def fetch_trades(exchange, asset):
    """某资产成交历史（币种/USDT）。OKX 历史窗口有限，需翻页。"""
    symbol = f"{asset}/{config.QUOTE}"
    out, since = [], None
    while True:
        try:
            batch = exchange.fetch_my_trades(symbol, since=since, limit=100)
        except Exception:
            break
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        since = batch[-1]["timestamp"] + 1
    return out


def fetch_ledger(exchange, code=None):
    """账单/流水（映射 OKX bills），用于识别质押收益。仅近 3 个月。"""
    try:
        return exchange.fetch_ledger(code=code, params={"paginate": True})
    except Exception:
        return []


def fetch_funding_bills(exchange, limit=100, max_pages=20):
    """资金账户账单（OKX asset/bills，含质押/理财收益）。

    质押收益以收益币种发放到资金账户（如 OKSOL/BETH），只在此接口可见，
    交易账户账单(fetch_ledger)里没有。按 billId 向更早翻页，OKX 仅保留近 3 个月。
    """
    out, after = [], None
    for _ in range(max_pages):
        params = {"limit": str(limit)}
        if after:
            params["after"] = after  # OKX: after = 返回 billId 更早的记录
        try:
            r = exchange.privateGetAssetBills(params)
        except Exception:
            break
        data = r.get("data", []) if isinstance(r, dict) else []
        if not data:
            break
        out.extend(data)
        if len(data) < limit:
            break
        after = data[-1].get("billId")
    return out


def fetch_earn_rewards(exchange):
    """从 OKX Earn (staking-defi) 余额接口取各币种 lifetime 累计收益 totalInterestAccrual。

    账单仅近 3 个月会漏早期收益，此接口给的是 lifetime 权威累计值。返回 {ccy: 累计收益数量}。
    """
    out = {}
    for ccy, method in config.EARN_BALANCE_ENDPOINTS.items():
        fn = getattr(exchange, method, None)
        if fn is None:
            continue
        try:
            data = fn().get("data", []) or []
        except Exception:
            continue
        for it in data:
            v = it.get("totalInterestAccrual")
            if v in (None, ""):
                continue
            c = it.get("ccy") or ccy
            out[c] = out.get(c, 0.0) + float(v)
    return out


def fetch_flows(exchange):
    deposits, withdrawals = [], []
    try:
        deposits = exchange.fetch_deposits()
    except Exception:
        pass
    try:
        withdrawals = exchange.fetch_withdrawals()
    except Exception:
        pass
    return deposits, withdrawals
