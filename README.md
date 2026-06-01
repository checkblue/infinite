# 无限私募金资金看板

无限私募金 · OKX 私募基金（GP/LP 合伙制，份额制）资金看板与投资人报表系统。Python + ccxt + Parquet + Streamlit。

## 功能
- 每日总净值 / 单位净值（NAV）曲线
- 持仓列表（成本、盈亏、质押收益、集中度预警），盈亏数值红绿着色
- 持仓页「当前持仓 / 历史快照」切换：当前持仓实时套用最新手动成本；历史快照查看过往原始记录
- 份额制：按 LP/GP 记录出资、份额、单位净值
- 收益分配瀑布（先回本 → 8% 复利优先收益 → 超额 LP80/GP20，GP 自有资金不抽 carry）
- 定期报表：月 / 季 / 半年 / 年（TWR、年化、最大回撤、资产配置），LP 对账单
- 赎回测算器（满 1 年、月末 NAV、折价 10%）
- 自起投 XIRR

## 安装
```bash
pip install -r requirements.txt
```

## 网络 / 代理
OKX 在部分地区（含中国大陆）需走代理，否则连接 `www.okx.com` 超时。在 `.env` 配置代理地址即可：
```bash
OKX_PROXY=http://127.0.0.1:7890      # 改成你本机代理端口；为空则直连
```
代理也可用标准环境变量 `HTTPS_PROXY` / `HTTP_PROXY`，`config.OKX_PROXY` 会自动回退读取。

## 先看演示效果（无需 OKX 密钥）
```bash
python seed_demo.py              # 生成 180 天演示数据到 data/
python -m streamlit run dashboard.py   # 浏览器打开看板（http://localhost:8501）
```
> `streamlit` 命令若不在 PATH，统一用 `python -m streamlit ...`。

## 接真实账户
1. 复制并填入只读 API 凭据：
   ```bash
   cp .env.example .env     # 填 OKX_API_KEY / OKX_SECRET / OKX_PASSWORD(passphrase)，并按需填 OKX_PROXY
   ```
   ⚠ API Key 务必只授予「只读」权限，不要开交易/提现。
2. 删除演示数据（如有）：`rm -rf data/`
3. 验证读数：`python networth.py`（打印当前净值与持仓，先和 OKX App 对一遍）
4. 跑一次每日快照：`python collector.py`
5. 看板：`python -m streamlit run dashboard.py`

## 启动看板（pm2 常驻）
看板用 pm2 守护进程常驻、崩溃自动重启：
```bash
# 0) 如未安装 pm2（需 Node.js）
npm install -g pm2

# 1) 启动（streamlit 不在 PATH，用 python3 -m；-- 之后是传给 python3 的参数）
cd /Users/chicheng/Work/fund/git/infinite
pm2 start python3 --name fund-dashboard -- -m streamlit run dashboard.py --server.port 8501 --server.headless true

# 2) 常用运维
pm2 logs fund-dashboard       # 看实时日志
pm2 restart fund-dashboard    # 改代码后重启
pm2 stop fund-dashboard       # 停止
pm2 delete fund-dashboard     # 移除

# 3) 开机自启（保存当前进程列表 + 生成启动脚本）
pm2 save
pm2 startup                   # 按提示执行它输出的那条命令
```
启动后浏览器访问 `http://localhost:8501`。

## 每日快照（crontab）
快照采集器 `collector.py` 每天东八区 0:00 跑一次（幂等，同日覆盖）。本机系统时区已是 `Asia/Shanghai`，本地 0 点即东八区 0 点。

编辑 crontab：`crontab -e`，加入：
```cron
# 每日 0:00 跑基金快照（用 asdf python 直连 bin，免依赖 asdf 环境）
0 0 * * * cd /Users/chicheng/Work/fund/git/infinite && /Users/chicheng/.asdf/installs/python/3.10.9/bin/python3 collector.py >> collector.log 2>&1
```
查看与验证：
```bash
crontab -l                    # 查看已配置的任务
python collector.py           # 手动跑一次，确认能联网拿数（需代理在运行）
tail -f collector.log         # 跟踪每日运行日志
```
> 说明：`collector.py` 内部按东八区计算快照日期（`today_cst`），即使触发时刻有偏差，落库日期也始终是东八区当日。macOS 自带 cron 不支持 `CRON_TZ` 变量，故依赖系统时区（已是 UTC+8）。代理需保持运行，否则采集会因连不上 OKX 失败（失败不污染历史）。

## 质押收益口径（已确认）
> 这是原「待实现确认项」的最终结论，接真实账户后已对实际返回逐项核实。

- **来源**：质押/理财收益以收益币种发放到**资金账户**，只在资金账户账单 `asset/bills` 可见；交易账户账单（`fetch_ledger`）里只有买卖、没有收益条目。
- **类型码**（已确认）：
  | type | notes | 含义 | 收益币种 |
  | --- | --- | --- | --- |
  | 328 | SOL Staking earnings | SOL 质押收益 | OKSOL |
  | 139 | ETH Staking earnings | ETH 质押收益 | BETH |
  | 89 | On-chain Earn earnings | 链上理财收益 | USDT 等 |

  识别用「type 码命中 `config.STAKING_REWARD_BILL_TYPES` **或** notes 含 `earning`」双保险（见 `staking.py`）。
- **累计口径**：账单仅近 3 个月，会漏早期收益。故 OKSOL/BETH 这类有 Earn 持仓的，**以 Earn `staking-defi` 余额接口的 `totalInterestAccrual`（lifetime 权威值）为准**；无对应 Earn 接口的币种（如 USDT 链上理财）回退账单累计。账单仍按 `billId` 去重持久化到 `staking_rewards` 作审计流水。
- **流动质押币**（`config.STAKING_TOKENS = {OKSOL, BETH}`）：整笔持仓即质押本金（复投，1 SOL=1 OKSOL，收益滚入本金再生息）。其「已质押数量」= 该资产总持仓（交易账户 + 资金账户）。
- **成本**：`成本基数 = 成本价 ×（总持仓 − 累计质押收益）`，质押收益部分按 0 成本计入。

## 参数
基金参数集中在 `config.py`：起投日、优先收益率/复利、超额分成、carry 池权重、赎回折价、初始出资台账、代理、质押币与收益类型码等。

## 文件
| 文件 | 作用 |
| --- | --- |
| config.py | 配置与基金参数（含代理、质押币/收益类型码、Earn 接口映射） |
| okx_client.py | ccxt 只读封装（余额/行情/成交/资金账单/Earn 收益） |
| networth.py | M1：打印当前净值/持仓 |
| storage.py | Parquet 读写（幂等/去重） |
| cost.py | 加权成本 + 手动覆盖 |
| staking.py | 质押收益账单识别、去重持久化、累计 |
| units.py | 单位净值 / 份额 / 申购赎回 |
| distribution.py | 收益分配瀑布 |
| metrics.py | XIRR / TWR / 回撤 / 集中度 |
| collector.py | 每日快照（cron） |
| reports.py | 定期报表 + LP 对账单 |
| dashboard.py | Streamlit 看板 |
| seed_demo.py | 演示数据生成 |

## 数据表（data/*.parquet）
| 表 | 说明 |
| --- | --- |
| snapshots | 每日 1 行：总净值、单位净值、份额、累计出资、盈亏 |
| holdings | 每日多行：资产、数量、现价、市值、成本、未实现盈亏、已质押数量、累计质押收益、占比 |
| investors | 投资人台账（GP/LP、出资、份额、carry 权重） |
| unit_transactions | 份额变动（申购/赎回） |
| cost_overrides | 手动成本价（看板可编辑） |
| staking_rewards | 质押收益账单流水（按 billId 去重，审计用） |
```
