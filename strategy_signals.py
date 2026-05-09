#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic trading signal rules.

The AI layer can explain these signals, but the signal itself must remain
reproducible from market data and fixed parameters.
"""

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd


@dataclass(frozen=True)
class SignalConfig:
    strategy_name: str = "ma_rsi_volume_v1"
    rsi_buy_min: float = 45.0
    rsi_buy_max: float = 70.0
    rsi_sell_max: float = 80.0
    volume_ratio_min: float = 1.3
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.15
    max_holding_days: int = 20


def _is_valid_number(value) -> bool:
    try:
        return pd.notna(value)
    except Exception:
        return False


def generate_signal(row: pd.Series, position: Dict | None, config: SignalConfig) -> Dict:
    """
    Generate a deterministic BUY/SELL/HOLD signal from one row of indicators.

    Position-aware exits are evaluated first. The backtest engine calls this on
    day T and executes at day T+1 open to avoid same-bar lookahead.
    """
    close = row.get("Close")
    ma5 = row.get("MA5")
    ma20 = row.get("MA20")
    rsi = row.get("RSI")
    macd = row.get("MACD")
    macd_signal = row.get("MACD_signal")
    volume_ratio = row.get("Volume_ratio")

    rules_triggered: List[str] = []
    score_parts = {
        "trend": 0,
        "momentum": 0,
        "volume": 0,
        "risk": 0,
    }

    if position:
        entry_price = float(position["entry_price"])
        holding_days = int(position.get("holding_days", 0))

        if _is_valid_number(close) and close <= entry_price * (1 - config.stop_loss_pct):
            return {
                "signal": "SELL",
                "score": 100,
                "rules_triggered": [f"Close <= stop loss ({config.stop_loss_pct:.0%})"],
                "reason": "stop_loss",
            }

        if _is_valid_number(close) and close >= entry_price * (1 + config.take_profit_pct):
            return {
                "signal": "SELL",
                "score": 100,
                "rules_triggered": [f"Close >= take profit ({config.take_profit_pct:.0%})"],
                "reason": "take_profit",
            }

        if holding_days >= config.max_holding_days:
            return {
                "signal": "SELL",
                "score": 90,
                "rules_triggered": [f"Holding days >= {config.max_holding_days}"],
                "reason": "max_holding_days",
            }

        if _is_valid_number(close) and _is_valid_number(ma20) and close < ma20:
            return {
                "signal": "SELL",
                "score": 75,
                "rules_triggered": ["Close < MA20"],
                "reason": "trend_break",
            }

        if _is_valid_number(rsi) and rsi > config.rsi_sell_max:
            return {
                "signal": "SELL",
                "score": 65,
                "rules_triggered": [f"RSI > {config.rsi_sell_max}"],
                "reason": "rsi_overbought",
            }

        return {
            "signal": "HOLD",
            "score": 50,
            "rules_triggered": ["Existing position still valid"],
            "reason": "hold_position",
        }

    if _is_valid_number(close) and _is_valid_number(ma20) and close > ma20:
        rules_triggered.append("Close > MA20")
        score_parts["trend"] += 15

    if _is_valid_number(ma5) and _is_valid_number(ma20) and ma5 > ma20:
        rules_triggered.append("MA5 > MA20")
        score_parts["trend"] += 20

    if _is_valid_number(rsi) and config.rsi_buy_min <= rsi <= config.rsi_buy_max:
        rules_triggered.append(f"RSI between {config.rsi_buy_min:g} and {config.rsi_buy_max:g}")
        score_parts["momentum"] += 20

    if _is_valid_number(macd) and _is_valid_number(macd_signal) and macd > macd_signal:
        rules_triggered.append("MACD > signal")
        score_parts["momentum"] += 20

    if _is_valid_number(volume_ratio) and volume_ratio >= config.volume_ratio_min:
        rules_triggered.append(f"Volume ratio >= {config.volume_ratio_min:g}")
        score_parts["volume"] += 15

    score = sum(score_parts.values())
    if score >= 70:
        return {
            "signal": "BUY",
            "score": score,
            "rules_triggered": rules_triggered,
            "reason": "rules_matched",
        }

    return {
        "signal": "HOLD",
        "score": score,
        "rules_triggered": rules_triggered or ["No entry setup"],
        "reason": "no_entry",
    }
