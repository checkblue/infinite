"""全局配置与基金参数（参数已按 v0.5 文档锁定）。密钥从 .env 读取。"""

import os
from datetime import date

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ---- OKX 只读 API 凭据 ----
OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_SECRET = os.getenv("OKX_SECRET", "")
OKX_PASSWORD = os.getenv("OKX_PASSWORD", "")

# ---- 代理（OKX 在部分地区需走代理；为空则直连）----
# 支持 .env 里写 OKX_PROXY=http://127.0.0.1:7890，或回退到标准 HTTPS_PROXY/HTTP_PROXY
OKX_PROXY = (
    os.getenv("OKX_PROXY")
    or os.getenv("HTTPS_PROXY")
    or os.getenv("https_proxy")
    or os.getenv("HTTP_PROXY")
    or os.getenv("http_proxy")
    or ""
)

# ---- 计价 ----
QUOTE = "USDT"
STABLES = {"USDT", "USDC", "USD"}

# ---- 阈值 ----
DUST_THRESHOLD_USD = 1.0  # 市值<此值的资产完全忽略
CONCENTRATION_ALERT = 0.50  # 单一资产占比预警

# ---- 质押 / Earn ----
# 流动质押币：整笔持仓即质押本金（复投，收益滚入本金再生息）。其「质押数量」= 该资产总持仓。
STAKING_TOKENS = {"OKSOL", "BETH"}
# 资金账户账单(asset/bills)中「质押/理财收益」的类型码——已对实际返回确认：
#   328 = SOL Staking earnings(OKSOL)，139 = ETH Staking earnings(BETH)，89 = On-chain Earn earnings(USDT)
# 收益按 0 成本计入；类型码 + notes 含 "earning" 双重判断（见 staking.py）。
STAKING_REWARD_BILL_TYPES = {"328", "139", "89"}

# Earn (staking-defi) 余额接口：取 totalInterestAccrual 作为各币种 lifetime 累计收益的权威值。
# 账单仅近 3 个月会丢早期收益，故 OKSOL/BETH 这类有 Earn 持仓的以此接口为准；
# 无对应接口的（如 USDT 链上理财）回退账单累计。形如 {收益币种: ccxt 隐式方法名}。
EARN_BALANCE_ENDPOINTS = {
    "OKSOL": "privateGetFinanceStakingDefiSolBalance",
    "BETH": "privateGetFinanceStakingDefiEthBalance",
}

# ---- 数据目录 ----
DATA_DIR = os.getenv("FUND_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

# ---- 基金参数 ----
INCEPTION_DATE = date(2026, 1, 31)  # 起投日（按需修改）
INITIAL_NAV_PER_UNIT = 1.0000  # 初始单位净值

# 分配参数
PREF_RETURN_RATE = 0.08  # 优先收益 年化
PREF_COMPOUNDING = "compound"  # 复利
EXCESS_LP_SHARE = 0.80  # 超额：LP 80%
EXCESS_GP_SHARE = 0.20  # 超额：GP 20%
GP_CAPITAL_CARRY = False  # GP 自有资金不抽 carry
GP_CARRY_SPLIT = {"PP": 0.80, "CC": 0.20}  # GP carry 池在 PP:CC 间 8:2
REDEEM_DISCOUNT = 0.10  # 提前赎回折价
MIN_HOLD_DAYS_FOR_REDEEM = 365  # 满 1 年方可赎回

# 初始出资台账（均为 GP）
INVESTORS_SEED = [
    {
        "investor_id": "PP",
        "name": "PP",
        "role": "GP",
        "amount": 80000.0,
        "gp_carry_weight": 0.80,
    },
    {
        "investor_id": "CC",
        "name": "CC",
        "role": "GP",
        "amount": 20000.0,
        "gp_carry_weight": 0.20,
    },
]
