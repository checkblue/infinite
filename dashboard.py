"""Streamlit 看板。运行：streamlit run dashboard.py"""
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

import config
import storage
import metrics
import distribution
import reports
import units as units_mod

st.set_page_config(page_title="私募基金资金看板", layout="wide")


@st.cache_data(ttl=60)
def load(name):
    return storage.load(name)


def latest_snapshot():
    s = load("snapshots")
    if s.empty:
        return None
    return s.sort_values("date").iloc[-1]


def latest_holdings():
    h = load("holdings")
    if h.empty:
        return h
    h = h.copy()
    h["date"] = pd.to_datetime(h["date"])
    return h[h["date"] == h["date"].max()].copy()


def color_pnl(v):
    """盈亏着色：盈利绿、亏损红、0 或空不着色。"""
    if pd.isna(v) or v == 0:
        return ""
    return "color: #16a34a" if v > 0 else "color: #dc2626"


def _sign_color(x):
    """正绿、负红、0/空不着色。"""
    if x is None or (isinstance(x, float) and pd.isna(x)) or x == 0:
        return "inherit"
    return "#16a34a" if x > 0 else "#dc2626"


def _metric_html(label, text, color, sub=None):
    html = (f"<div style='font-size:0.875rem;opacity:0.6'>{label}</div>"
            f"<div style='font-size:2.1rem;font-weight:400;color:{color}'>{text}</div>")
    if sub:
        html += f"<div style='font-size:0.95rem;font-weight:600;color:{color}'>{sub}</div>"
    return html


def metric_colored(col, label, text, sign, sub=None):
    """类 st.metric 指标，数值按 sign 正负着色；sub 为可选副行（同色）。"""
    col.markdown(_metric_html(label, text, _sign_color(sign), sub), unsafe_allow_html=True)


def metric_pct(col, label, frac, decimals=2):
    """类 st.metric 的指标，但数值按正负着色（盈绿亏红），用于 TWR/年化/XIRR 等收益率。"""
    txt = "—" if (frac is None or pd.isna(frac)) else f"{frac * 100:.{decimals}f}%"
    col.markdown(_metric_html(label, txt, _sign_color(frac)), unsafe_allow_html=True)


def apply_cost_overrides(h):
    """对持仓快照实时套用手动成本（仅显示用，不改 parquet）。

    返回 (h2, applied_assets)；按覆盖价重算 成本/持仓成本/未实现盈亏。
    """
    ov = load("cost_overrides")
    h2 = h.copy()
    applied = []
    if ov.empty:
        return h2, applied
    ovmap = {a: float(c) for a, c in zip(ov["asset"], ov["cost_price_usd"])}
    for i, r in h2.iterrows():
        cp = ovmap.get(r["asset"])
        if cp is None:
            continue
        # 成本只算非收益部分：扣掉累计质押收益（0 成本），不是扣已质押数量
        reward = float(r.get("staking_reward_amount", 0.0) or 0.0)
        bought = max(float(r["amount"]) - reward, 0.0)
        h2.at[i, "cost_price_usd"] = cp
        h2.at[i, "cost_basis_usd"] = cp * bought
        h2.at[i, "unrealized_pnl_usd"] = float(r["value_usd"]) - cp * bought
        applied.append(r["asset"])
    return h2, applied


st.sidebar.title("📊 基金看板")
page = st.sidebar.radio("导航", ["概览", "持仓", "投资人 / 份额", "定期报表", "收益分配", "赎回测算"])
snap = latest_snapshot()
if snap is None:
    st.warning("暂无数据。请先运行 `python seed_demo.py`（演示）或 `python collector.py`（真实账户）。")
    st.stop()

# ---------- 概览 ----------
if page == "概览":
    st.title("概览")
    total = float(snap["total_value_usd"])
    xirr = metrics.xirr_inception(total)
    navps = float(snap["nav_per_unit"])
    pnl = float(snap["pnl_usd"])
    inflow = float(snap["cumulative_inflow_usd"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总净值 (USDT)", f"{total:,.0f}")
    # NAV 相对初始 1.0 的涨跌、盈亏相对累计出资的回报率 → 绿涨红跌
    c2.metric("单位净值 NAV/份", f"{navps:.4f}",
              delta=f"{(navps - config.INITIAL_NAV_PER_UNIT) * 100:+.2f}%")
    metric_colored(c3, "累计盈亏", f"{pnl:,.0f}", pnl,
                   sub=(f"{pnl / inflow * 100:+.2f}%" if inflow else None))
    metric_pct(c4, "自起投 XIRR", xirr, 1)

    s = load("snapshots").copy()
    s["date"] = pd.to_datetime(s["date"])
    s = s.sort_values("date")
    metric = st.radio("曲线", ["总净值", "单位净值 NAV"], horizontal=True)
    col = "total_value_usd" if metric == "总净值" else "nav_per_unit"
    fig = px.area(s, x="date", y=col, title=metric)
    fig.update_traces(line_color="#2563eb")
    st.plotly_chart(fig)

# ---------- 持仓 ----------
elif page == "持仓":
    st.title("持仓")
    h_all = load("holdings")
    if h_all.empty:
        st.info("无持仓")
    else:
        h_all = h_all.copy()
        h_all["date"] = pd.to_datetime(h_all["date"])
        dates = sorted(h_all["date"].dt.date.unique(), reverse=True)
        view = st.radio("视图", ["当前持仓", "历史快照"], horizontal=True,
                        help="当前持仓＝最新快照并实时套用你最新的手动成本；历史快照＝查看过往某日的原始记录")
        if view == "当前持仓":
            h = h_all[h_all["date"].dt.date == dates[0]].copy()
            h, applied = apply_cost_overrides(h)
            st.caption(f"快照日 {dates[0]}（现价为该日收盘）")
            if applied:
                st.caption(f"✅ 已实时套用手动成本：{', '.join(applied)}　（仅显示用，落库以下次 collector 为准）")
        else:
            sel = st.selectbox("快照日期", dates, format_func=str)
            h = h_all[h_all["date"].dt.date == sel].copy()
            st.caption(f"历史快照 {sel}（按当时存储的原始成本/价格，未套用最新手动成本）")

        conc = metrics.concentration(h.rename(columns={"value_usd": "value"}))
        if conc >= config.CONCENTRATION_ALERT:
            top = h.loc[h["value_usd"].idxmax(), "asset"]
            st.error(f"⚠ 集中度预警：{top} 占比 {conc*100:.1f}% ≥ {config.CONCENTRATION_ALERT*100:.0f}%")
        for c in ("staking_amount", "staking_reward_amount", "staking_reward_value_usd"):
            if c not in h.columns:  # 兼容旧快照（缺新列）
                h[c] = 0.0
        show = h[["asset", "amount", "price_usd", "value_usd", "cost_price_usd",
                  "unrealized_pnl_usd", "staking_amount", "staking_reward_amount",
                  "staking_reward_value_usd", "weight"]].copy()
        show["pnl_pct"] = (h["unrealized_pnl_usd"] / h["cost_basis_usd"].replace(0, pd.NA) * 100)
        show = show.sort_values("value_usd", ascending=False)
        show = show.rename(columns={
            "asset": "资产", "amount": "数量", "price_usd": "现价(USDT)",
            "value_usd": "市值(USDT)", "cost_price_usd": "成本价(USDT)",
            "unrealized_pnl_usd": "未实现盈亏(USDT)", "staking_amount": "已质押数量",
            "staking_reward_amount": "累计质押收益", "staking_reward_value_usd": "质押收益(USDT)",
            "weight": "占比", "pnl_pct": "盈亏率",
        })
        styled = show.style.format({
            "数量": "{:,.6f}", "现价(USDT)": "{:,.4f}", "市值(USDT)": "{:,.2f}",
            "成本价(USDT)": "{:,.4f}", "未实现盈亏(USDT)": "{:,.2f}",
            "已质押数量": "{:,.4f}", "累计质押收益": "{:,.6f}", "质押收益(USDT)": "{:,.2f}",
            "占比": "{:.1%}", "盈亏率": "{:.1f}%",
        }).map(color_pnl, subset=["未实现盈亏(USDT)", "盈亏率"])
        st.dataframe(styled, width='stretch')

        st.subheader("手动成本价（覆盖自动计算）")
        st.caption("修改后点保存；下次快照将优先采用手动值。底部 ➕ 可新增一行。")
        ov = load("cost_overrides")
        if ov.empty:
            # 空表必须给明确 dtype，否则 data_editor 推断不出列类型 → 无法编辑
            ov = pd.DataFrame({
                "asset": pd.Series([], dtype="string"),
                "cost_price_usd": pd.Series([], dtype="float64"),
                "note": pd.Series([], dtype="string"),
            })
        else:
            ov = ov[["asset", "cost_price_usd", "note"]].copy()
        editor = st.data_editor(
            ov, num_rows="dynamic", width='stretch', key="cost_ed",
            column_config={
                "asset": st.column_config.TextColumn("资产", required=True),
                "cost_price_usd": st.column_config.NumberColumn(
                    "成本价(USDT)", min_value=0.0, format="%.4f", required=True),
                "note": st.column_config.TextColumn("备注"),
            })
        if st.button("保存手动成本"):
            editor = editor.copy()
            editor = editor[editor["asset"].notna() & (editor["asset"].astype(str).str.strip() != "")]
            editor["updated_at"] = pd.Timestamp.now()
            storage.save("cost_overrides", editor)
            load.clear()  # 清缓存，否则 ttl=60 内重新加载仍是旧空表 → 看似没保存
            st.success(f"已保存 {len(editor)} 条")
            st.rerun()

# ---------- 投资人 / 份额 ----------
elif page == "投资人 / 份额":
    st.title("投资人 / 份额")
    inv = load("investors")
    navps = float(snap["nav_per_unit"])
    ub = units_mod.units_by_investor()
    rows = []
    txns = load("unit_transactions")
    for _, r in inv.iterrows():
        iid = r["investor_id"]
        u = ub.get(iid, 0.0)
        cap = txns.loc[(txns["investor_id"] == iid) & (txns["type"] == "subscribe"), "amount_usd"].sum()
        rows.append({"投资人": r["name"], "角色": r["role"], "出资(USDT)": cap,
                     "份额": u, "当前价值(USDT)": u * navps,
                     "浮动收益": u * navps - cap})
    st.dataframe(pd.DataFrame(rows).style.format({
        "出资(USDT)": "{:,.0f}", "份额": "{:,.0f}", "当前价值(USDT)": "{:,.0f}", "浮动收益": "{:,.0f}"})
        .map(color_pnl, subset=["浮动收益"]),
        width='stretch')
    st.metric("总份额", f"{float(snap['total_units']):,.0f}")

# ---------- 定期报表 ----------
elif page == "定期报表":
    st.title("定期报表")
    s = load("snapshots").copy()
    s["date"] = pd.to_datetime(s["date"])
    years = sorted({d.year for d in s["date"]})
    y = st.selectbox("年份", years, index=len(years)-1)
    ptype = st.selectbox("周期", ["月度", "季度", "半年度", "年度"])
    if ptype == "月度":
        pk = st.selectbox("月份", [f"{y}-{m:02d}" for m in range(1, 13)])
    elif ptype == "季度":
        pk = st.selectbox("季度", [f"{y}Q{q}" for q in range(1, 5)])
    elif ptype == "半年度":
        pk = st.selectbox("半年", [f"{y}H1", f"{y}H2"])
    else:
        pk = f"{y}FY"

    r = reports.period_report(pk)
    if not r:
        st.info("该周期暂无数据")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("期末净值", f"{r['nav_end']:,.0f}")
        metric_pct(c2, "期间收益(TWR)", r["twr"], 2)
        metric_pct(c3, "期间年化", r["annualized"], 1)
        c4.metric("最大回撤", f"{r['max_drawdown']*100:.1f}%")
        c5, c6, c7 = st.columns(3)
        c5.metric("期初净值", f"{r['nav_start']:,.0f}")
        c6.metric("净申赎", f"{r['net_flow']:,.0f}")
        c7.metric("自起投XIRR", f"{r['xirr_inception']*100:.1f}%" if r['xirr_inception'] else "—")
        if r["allocation"]:
            pie = go.Figure(go.Pie(labels=list(r["allocation"]),
                                   values=list(r["allocation"].values()), hole=0.4))
            pie.update_layout(title="期末资产配置")
            st.plotly_chart(pie)

    st.subheader("LP 对账单")
    inv = load("investors")
    iid = st.selectbox("投资人", list(inv["investor_id"]))
    stt = reports.lp_statement(iid)
    if stt and stt["waterfall"]:
        w = stt["waterfall"]
        st.write(f"**份额** {stt['units']:,.0f} ｜ **当前价值** {stt['current_value']:,.0f} USDT")
        st.write(f"瀑布测算 → 本金 {w['capital']:,.0f}｜优先收益 {w['preferred']:,.0f}"
                 f"｜超额分配 {w['excess_to_investor']:,.0f}｜GP carry 入 {w['gp_carry_received']:,.0f}"
                 f"｜**应得合计 {w['payout']:,.0f}**")

# ---------- 收益分配 ----------
elif page == "收益分配":
    st.title("收益分配瀑布")
    total = st.number_input("以该总净值测算 (USDT)", value=float(snap["total_value_usd"]), step=1000.0)
    wf = distribution.waterfall(total)
    st.caption(f"优先收益 {config.PREF_RETURN_RATE*100:.0f}% 复利｜超额 LP {config.EXCESS_LP_SHARE*100:.0f}%/GP "
               f"{config.EXCESS_GP_SHARE*100:.0f}%｜GP自有资金不抽carry｜carry池 PP:CC=8:2")
    df = pd.DataFrame(wf["investors"])
    if not df.empty:
        st.dataframe(df.rename(columns={
            "investor_id": "投资人", "role": "角色", "capital": "本金", "preferred": "优先收益",
            "excess_to_investor": "超额分配", "gp_carry_received": "carry入账", "payout": "应得合计"})
            [["投资人", "角色", "本金", "优先收益", "超额分配", "carry入账", "应得合计"]]
            .style.format({"本金": "{:,.0f}", "优先收益": "{:,.0f}", "超额分配": "{:,.0f}",
                           "carry入账": "{:,.0f}", "应得合计": "{:,.0f}"}), width='stretch')
        st.write(f"超额池 {wf['excess_pool']:,.0f}｜GP carry 池 "
                 + "，".join(f"{k} {v:,.0f}" for k, v in wf["gp_carry"].items()))

# ---------- 赎回测算 ----------
elif page == "赎回测算":
    st.title("赎回测算器")
    st.caption(f"提前退出：持有满 {config.MIN_HOLD_DAYS_FOR_REDEEM} 天，按月末 NAV 折价 {config.REDEEM_DISCOUNT*100:.0f}%")
    inv = load("investors")
    iid = st.selectbox("投资人", list(inv["investor_id"]))
    navps = st.number_input("月末 NAV/份", value=float(snap["nav_per_unit"]), step=0.01, format="%.4f")
    disc = st.slider("折价率", 0.0, 0.2, config.REDEEM_DISCOUNT, 0.01)
    q = units_mod.redemption_quote(iid, navps, discount=disc)
    c1, c2, c3 = st.columns(3)
    c1.metric("持有份额", f"{q['units']:,.0f}")
    c2.metric("折前金额", f"{q['gross']:,.0f}")
    c3.metric("实退金额", f"{q['net']:,.0f}")
