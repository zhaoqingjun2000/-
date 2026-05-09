#!/usr/bin/env python3
"""
每日美股日报分析生成器
- 自动拉取主要指数、板块ETF、波动率与利率数据
- 计算涨跌、动量、成交量与风险偏好信号
- 生成“资深华尔街交易师”风格中文日报（Markdown）

依赖：
    pip install yfinance pandas

用法：
    python daily_us_market_report.py
    python daily_us_market_report.py --date 2026-05-08 --output report.md
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
import yfinance as yf


INDEX_MAP = {
    "标普500": "^GSPC",
    "纳斯达克100": "^NDX",
    "道琼斯工业": "^DJI",
    "罗素2000": "^RUT",
    "VIX波动率": "^VIX",
    "10Y美债收益率": "^TNX",
}

SECTOR_ETF = {
    "科技": "XLK",
    "金融": "XLF",
    "能源": "XLE",
    "可选消费": "XLY",
    "必选消费": "XLP",
    "医疗": "XLV",
    "工业": "XLI",
    "公用事业": "XLU",
    "通信服务": "XLC",
    "半导体": "SOXX",
}

STYLE_ETF = {
    "成长": "IWF",
    "价值": "IWD",
    "高收益债": "HYG",
    "投资级债": "LQD",
    "黄金": "GLD",
    "美元指数代理": "UUP",
}


@dataclass
class TickerStats:
    name: str
    ticker: str
    close: float
    pct_1d: float
    pct_5d: float
    pct_20d: float
    vol_ratio: float | None



def download_prices(tickers: List[str], start: dt.date, end: dt.date) -> pd.DataFrame:
    df = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError("未获取到行情数据，请检查网络或Ticker是否有效。")
    close = df["Close"] if "Close" in df.columns else df
    vol = df["Volume"] if "Volume" in df.columns else pd.DataFrame(index=close.index)
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    if isinstance(vol, pd.Series):
        vol = vol.to_frame(name=tickers[0])
    return pd.concat({"Close": close, "Volume": vol}, axis=1)



def build_stats(name: str, ticker: str, data: pd.DataFrame) -> TickerStats:
    c = data[("Close", ticker)].dropna()
    v = data[("Volume", ticker)].dropna() if ("Volume", ticker) in data.columns else pd.Series(dtype=float)
    if len(c) < 21:
        raise RuntimeError(f"{ticker} 数据不足，至少需要21个交易日")

    close = float(c.iloc[-1])
    pct_1d = float(c.pct_change().iloc[-1] * 100)
    pct_5d = float((c.iloc[-1] / c.iloc[-6] - 1) * 100)
    pct_20d = float((c.iloc[-1] / c.iloc[-21] - 1) * 100)

    vol_ratio = None
    if len(v) >= 21 and v.iloc[-20:].mean() > 0:
        vol_ratio = float(v.iloc[-1] / v.iloc[-20:].mean())

    return TickerStats(name, ticker, close, pct_1d, pct_5d, pct_20d, vol_ratio)



def risk_regime(vix: float, hyg_lqd_20d: float, growth_value_20d: float) -> str:
    score = 0
    score += 1 if vix < 18 else -1 if vix > 24 else 0
    score += 1 if hyg_lqd_20d > 0 else -1
    score += 1 if growth_value_20d > 0 else -1
    if score >= 2:
        return "Risk-On（风险偏好）"
    if score <= -2:
        return "Risk-Off（风险规避）"
    return "中性震荡"



def fmt_stat(s: TickerStats) -> str:
    vol_text = f"，量比 {s.vol_ratio:.2f}x" if s.vol_ratio is not None else ""
    return (
        f"- **{s.name}** ({s.ticker})：收于 `{s.close:.2f}`，"
        f"日涨跌 `{s.pct_1d:+.2f}%`，5日 `{s.pct_5d:+.2f}%`，20日 `{s.pct_20d:+.2f}%`{vol_text}"
    )



def generate_report(target_date: dt.date) -> str:
    start = target_date - dt.timedelta(days=70)
    end = target_date + dt.timedelta(days=1)

    all_map: Dict[str, str] = {}
    all_map.update(INDEX_MAP)
    all_map.update(SECTOR_ETF)
    all_map.update(STYLE_ETF)

    data = download_prices(list(set(all_map.values())), start, end)

    index_stats = [build_stats(k, v, data) for k, v in INDEX_MAP.items()]
    sector_stats = [build_stats(k, v, data) for k, v in SECTOR_ETF.items()]
    style_stats = [build_stats(k, v, data) for k, v in STYLE_ETF.items()]

    spx = next(x for x in index_stats if x.name == "标普500")
    ndx = next(x for x in index_stats if x.name == "纳斯达克100")
    vix = next(x for x in index_stats if x.name == "VIX波动率")
    hyg = next(x for x in style_stats if x.name == "高收益债")
    lqd = next(x for x in style_stats if x.name == "投资级债")
    growth = next(x for x in style_stats if x.name == "成长")
    value = next(x for x in style_stats if x.name == "价值")

    hyg_lqd_20d = hyg.pct_20d - lqd.pct_20d
    growth_value_20d = growth.pct_20d - value.pct_20d

    regime = risk_regime(vix.close, hyg_lqd_20d, growth_value_20d)

    sector_sorted = sorted(sector_stats, key=lambda x: x.pct_1d, reverse=True)
    leaders = "、".join([f"{x.name}({x.pct_1d:+.2f}%)" for x in sector_sorted[:3]])
    laggards = "、".join([f"{x.name}({x.pct_1d:+.2f}%)" for x in sector_sorted[-3:]])

    strategy_bias = (
        "逢回调布局高Beta与成长主线，关注半导体/AI链条" if regime.startswith("Risk-On")
        else "降低净多敞口，增配防御与现金流资产，优先风险控制" if regime.startswith("Risk-Off")
        else "维持均衡配置，采用区间交易与事件驱动结合"
    )

    md = []
    md.append(f"# 每日美股交易日报（{target_date.isoformat()}）")
    md.append("")
    md.append("## 一、核心结论（Trader's Take）")
    md.append(
        f"- 当前市场状态：**{regime}**。标普500 20日表现 `{spx.pct_20d:+.2f}%`，纳指100 20日表现 `{ndx.pct_20d:+.2f}%`，VIX 位于 `{vix.close:.2f}`。"
    )
    md.append(f"- 板块强弱：领涨 {leaders}；承压 {laggards}。")
    md.append(f"- 交易偏向：**{strategy_bias}**。")

    md.append("")
    md.append("## 二、主要指数与宏观风险定价")
    for s in index_stats:
        md.append(fmt_stat(s))

    md.append("")
    md.append("## 三、板块轮动")
    for s in sector_sorted:
        md.append(fmt_stat(s))

    md.append("")
    md.append("## 四、风格与跨资产信号")
    for s in style_stats:
        md.append(fmt_stat(s))
    md.append(f"- **成长-价值 20日差**：`{growth_value_20d:+.2f}%`（>0 表示成长相对占优）")
    md.append(f"- **HYG-LQD 20日差**：`{hyg_lqd_20d:+.2f}%`（>0 表示信用风险偏好改善）")

    md.append("")
    md.append("## 五、明日交易计划")
    md.append("1. 盘前：跟踪美债收益率与美元方向是否共振，确认风险资产开盘基调。")
    md.append("2. 盘中：聚焦领涨板块是否放量延续；若缩量冲高，防止日内回落。")
    md.append("3. 风控：单笔交易风险不超过账户净值1%，触发止损严格执行。")

    md.append("")
    md.append("---")
    md.append("*注：本报告为量化信号汇总示例，不构成投资建议。*")

    return "\n".join(md)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成每日美股日报分析")
    parser.add_argument("--date", type=str, default=str(dt.date.today()), help="报告日期（YYYY-MM-DD）")
    parser.add_argument("--output", type=str, default="daily_us_report.md", help="输出Markdown文件名")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report_date = dt.date.fromisoformat(args.date)
    report = generate_report(report_date)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"已生成报告：{args.output}")
