"""
市场情绪热度数据（A股上证指数）
基于 akshare 公开行情构造「主要情绪 / 敏感情绪」与按日情绪序列，用于可视化参考。
说明：与第三方付费「自在量化」等指标口径可能不同，图表布局与解读逻辑可参考其展示方式。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def get_intraday_emotion(symbol: str = "000001") -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    获取日内情绪序列。
    - 主要情绪：相对当日开盘的累计涨跌幅（%），表征日内强弱。
    - 敏感情绪：1 分钟收益率的 5 期滚动波动，映射到 0–100，表征短线敏感度。

    使用东方财富指数分时 ``index_zh_a_hist_min_em``，symbol=000001 为上证综指（勿与个股 000001 混淆）。

    Returns:
        (DataFrame[时间, primary_pct, sensitive_0_100], meta)
    """
    import akshare as ak

    meta: Dict[str, Any] = {"symbol": symbol, "date": None, "pre_close": None, "error": None}

    min_df = None
    trade_date = None
    last_err = None
    for delta in range(0, 8):
        day = datetime.now() - timedelta(days=delta)
        if day.weekday() >= 5:
            continue
        dstr = day.strftime("%Y-%m-%d")
        try:
            chunk = ak.index_zh_a_hist_min_em(
                symbol=symbol,
                period="1",
                start_date=f"{dstr} 09:25:00",
                end_date=f"{dstr} 15:10:00",
            )
            if chunk is not None and not chunk.empty:
                min_df = chunk
                trade_date = dstr
                break
        except Exception as e:
            last_err = str(e)

    if min_df is None or min_df.empty:
        meta["error"] = last_err or "分钟行情为空（或非交易时段）"
        return pd.DataFrame(), meta

    time_col = "时间" if "时间" in min_df.columns else min_df.columns[0]
    close_col = "收盘" if "收盘" in min_df.columns else None
    if close_col is None:
        for c in min_df.columns:
            if "收盘" in str(c) or str(c).lower() == "close":
                close_col = c
                break
    if close_col is None:
        meta["error"] = "无法识别收盘价列"
        return pd.DataFrame(), meta

    df = min_df.copy()
    df["time"] = pd.to_datetime(df[time_col])
    df["close"] = df[close_col].astype(float)

    open_col = "开盘" if "开盘" in df.columns else None
    if open_col:
        day_open = _safe_float(df.iloc[0][open_col])
    else:
        day_open = _safe_float(df.iloc[0]["close"])

    pre_close = None
    try:
        daily_idx = ak.stock_zh_index_daily(symbol="sh000001")
        if daily_idx is not None and len(daily_idx) >= 2:
            dc = "close" if "close" in daily_idx.columns else "收盘"
            dtcol = "date" if "date" in daily_idx.columns else "日期"
            daily_idx = daily_idx.copy()
            daily_idx["_dt"] = pd.to_datetime(daily_idx[dtcol])
            # 取交易日当天或之前最近一条日线收盘价作为「昨收」参考：用 strict 昨天
            td = pd.to_datetime(trade_date)
            prev = daily_idx[daily_idx["_dt"] < td].tail(1)
            if not prev.empty:
                pre_close = _safe_float(prev.iloc[0][dc])
    except Exception:
        pass

    if not pre_close or pre_close <= 0:
        pre_close = day_open

    meta["pre_close"] = pre_close
    meta["date"] = trade_date or df["time"].iloc[-1].strftime("%Y-%m-%d")

    # 主要情绪：相对今开涨跌幅%
    df["primary_pct"] = (df["close"] / day_open - 1.0) * 100.0

    # 1 分钟收益率
    df["ret1"] = df["close"].pct_change().fillna(0.0)
    roll = df["ret1"].rolling(window=5, min_periods=1).std().fillna(0.0)
    # 映射到 0–100：日内分位缩放，避免极端值
    if roll.max() > roll.min():
        sens = (roll - roll.min()) / (roll.max() - roll.min() + 1e-9) * 100.0
    else:
        sens = pd.Series(50.0, index=df.index)
    df["sensitive_0_100"] = sens.clip(0, 100)

    out = df[["time", "primary_pct", "sensitive_0_100"]].copy()
    return out, meta


def get_daily_emotion(
    index_symbol: str = "sh000001",
    days: int = 120,
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    按日情绪：用上证指数日涨跌幅构造 0–100 的「按天情绪」曲线，并给出振幅条用于副图。

    index_symbol: ak.stock_zh_index_daily 所用代码，默认上证综指 sh000001
    """
    import akshare as ak

    err = None
    try:
        daily = ak.stock_zh_index_daily(symbol=index_symbol)
    except Exception as e:
        return pd.DataFrame(), str(e)

    if daily is None or daily.empty:
        return pd.DataFrame(), "指数日线为空"

    df = daily.tail(int(days) + 5).copy()
    if "date" not in df.columns:
        if "日期" in df.columns:
            df = df.rename(columns={"日期": "date"})
        else:
            df["date"] = df.iloc[:, 0]

    df["date"] = pd.to_datetime(df["date"])

    close_c = "close" if "close" in df.columns else "收盘"
    high_c = "high" if "high" in df.columns else "最高"
    low_c = "low" if "low" in df.columns else "最低"
    for c in (close_c, high_c, low_c):
        if c not in df.columns:
            return pd.DataFrame(), f"缺少列: {c}"

    df["close"] = df[close_c].astype(float)
    df["prev_close"] = df["close"].shift(1)
    df["daily_pct"] = (df["close"] / df["prev_close"] - 1.0) * 100.0
    df["daily_pct"] = df["daily_pct"].fillna(0.0)

    # 情绪分数：涨跌幅压缩映射到 0–100，中性约 50
    pct = df["daily_pct"].values
    emotion = 50.0 + 25.0 * np.tanh(pct / 2.5)
    df["emotion_0_100"] = np.clip(emotion, 5.0, 95.0)

    # 5 日均线（情绪）
    df["emotion_ma5"] = df["emotion_0_100"].rolling(5, min_periods=1).mean()

    prev = df["prev_close"].replace(0, np.nan)
    amp = ((df[high_c].astype(float) - df[low_c].astype(float)) / prev) * 100.0
    df["amplitude_pct"] = amp.fillna(0.0)

    out = df[["date", "emotion_0_100", "emotion_ma5", "daily_pct", "amplitude_pct"]].tail(days).copy()
    return out, err


def _format_yyyymmdd(d: pd.Timestamp) -> str:
    if hasattr(d, "strftime"):
        return d.strftime("%Y%m%d")
    return pd.Timestamp(d).strftime("%Y%m%d")


def enrich_daily_with_zt_stats(
    emotion_df: pd.DataFrame,
    sleep_sec: float = 0.12,
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    按交易日拉取东方财富涨停池/跌停池，补充：
    - zt_count: 涨停家数
    - lb_height: 当日连板高度 max(连板数)
    - dt_count: 跌停家数（作「亏钱效应」参考）
    """
    import time

    import akshare as ak

    if emotion_df is None or emotion_df.empty or "date" not in emotion_df.columns:
        return emotion_df, None

    df = emotion_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    zt_list: list[int] = []
    lb_list: list[int] = []
    dt_list: list[int] = []

    warn: Optional[str] = None
    for idx, row in df.iterrows():
        dstr = _format_yyyymmdd(row["date"])
        zt_n = 0
        lb_max = 0
        dt_n = 0
        try:
            zdf = ak.stock_zt_pool_em(date=dstr)
            if zdf is not None and not zdf.empty:
                zt_n = len(zdf)
                col_lb = "连板数" if "连板数" in zdf.columns else None
                if col_lb is None:
                    for c in zdf.columns:
                        if "连板" in str(c):
                            col_lb = c
                            break
                if col_lb:
                    lb_max = int(
                        pd.to_numeric(zdf[col_lb], errors="coerce").fillna(0).max()
                    )
        except Exception:
            pass
        try:
            ddf = ak.stock_zt_pool_dtgc_em(date=dstr)
            if ddf is not None and not ddf.empty:
                dt_n = len(ddf)
        except Exception:
            pass

        zt_list.append(zt_n)
        lb_list.append(lb_max)
        dt_list.append(dt_n)

        if sleep_sec > 0 and idx < len(df) - 1:
            time.sleep(sleep_sec)

    df["zt_count"] = zt_list
    df["lb_height"] = lb_list
    df["dt_count"] = dt_list
    # 亏钱效应参考：跌停压制强度（与参考站 tooltip 口径不同，仅作盘面参照）
    df["loss_effect"] = df["dt_count"].clip(lower=0)

    if df["zt_count"].sum() == 0 and len(df) > 5:
        warn = "涨停池接口连续为空，可能为非交易日区间或数据源异常"

    return df, warn
