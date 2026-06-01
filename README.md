# 私募基金资金看板

OKX 私募基金（GP/LP 合伙制，份额制）资金看板与投资人报表系统。Python + ccxt + Parquet + Streamlit。

## 功能
- 每日总净值 / 单位净值（NAV）曲线
- 持仓列表（成本、盈亏、质押收益、集中度预警）
- 份额制：按 LP/GP 记录出资、份额、单位净值
- 收益分配瀑布（先回本 → 8% 复利优先收益 → 超额 LP80/GP20，GP 自有资金不抽 carry）
- 定期报表：月 / 季 / 半年 / 年（TWR、年化、最大回撤、资产配置），LP 对账单
- 赎回测算器（满 1 年、月末 NAV、折价 10%）
- 自起投 XIRR

## 安装
```bash
pip install -r requirements.txt
```

## 先看演示效果（无需 OKX 密钥）
```bash
python seed_demo.py        # 生成 180 天演示数据到 data/
streamlit run dashboard.py # 浏览器打开看板
```

## 接真实账户
1. 复制并填入只读 API 凭据：
   ```bash
   cp .env.example .env     # 填 OKX_API_KEY / OKX_SECRET / OKX_PASSWORD(passphrase)
   ```
   ⚠ API Key 务必只授予「只读」权限，不要开交易/提现。
2. 删除演示数据（如有）：`rm -rf data/`
3. 验证读数：`python networth.py`（打印当前净值与持仓，先和 OKX App 对一遍）
4. 每日快照（东八区 0 点 cron）：
   ```bash
   python collector.py      # 手动跑一次
   ```
   crontab：
   ```
   CRON_TZ=Asia/Shanghai
   0 0 * * * cd /path/to/fund-dashboard && python collector.py >> collector.log 2>&1
   ```
5. 看板：`streamlit run dashboard.py`

## 参数
基金参数集中在 `config.py`：起投日、优先收益率/复利、超额分成、carry 池权重、赎回折价、初始出资台账等。

## 待实现确认项
质押收益在 OKX 账单里的确切 `type/subType` 码：`staking.py` 用启发式（`earnAmt` 非空或备注含 earn/staking/interest 等）识别；接真实账户后打印 `fetch_ledger` 返回，按实际码收紧 `classify_is_reward()`。

## 文件
| 文件 | 作用 |
| --- | --- |
| config.py | 配置与基金参数 |
| okx_client.py | ccxt 只读封装 |
| networth.py | M1：打印当前净值/持仓 |
| storage.py | Parquet 读写（幂等/去重） |
| cost.py | 加权成本 + 手动覆盖 |
| staking.py | 质押收益账单累计 |
| units.py | 单位净值 / 份额 / 申购赎回 |
| distribution.py | 收益分配瀑布 |
| metrics.py | XIRR / TWR / 回撤 / 集中度 |
| collector.py | 每日快照（cron） |
| reports.py | 定期报表 + LP 对账单 |
| dashboard.py | Streamlit 看板 |
| seed_demo.py | 演示数据生成 |
