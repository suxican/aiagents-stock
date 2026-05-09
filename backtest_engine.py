#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small deterministic single-symbol backtest engine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from stock_data import StockDataFetcher
from strategy_signals import SignalConfig, generate_signal


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        position_pct: float = 0.25,
        commission_rate: float = 0.0003,
        stamp_tax_rate: float = 0.0005,
        slippage_pct: float = 0.001,
        position_sizing: str = "current_equity",
        exit_execution: str = "intraday",
        annualization_days: int = 252,
    ):
        self.initial_capital = float(initial_capital)
        self.position_pct = float(position_pct)
        self.commission_rate = float(commission_rate)
        self.stamp_tax_rate = float(stamp_tax_rate)
        self.slippage_pct = float(slippage_pct)
        self.position_sizing = position_sizing
        self.exit_execution = exit_execution
        self.annualization_days = int(annualization_days)
        self.fetcher = StockDataFetcher()

    def load_price_data(self, symbol: str, period: str) -> Tuple[pd.DataFrame | None, Dict | None]:
        stock_info = self.fetcher.get_stock_info(symbol)
        raw = self.fetcher.get_stock_data(symbol, period)
        if isinstance(raw, dict) and raw.get("error"):
            return None, {"error": raw["error"], "stock_info": stock_info}

        data = self.fetcher.calculate_technical_indicators(raw.copy())
        if isinstance(data, dict) and data.get("error"):
            return None, {"error": data["error"], "stock_info": stock_info}

        data = data.dropna(subset=["Open", "High", "Low", "Close"])
        data = data.sort_index()
        return data, stock_info

    def run(self, symbol: str, period: str = "1y", signal_config: SignalConfig | None = None) -> Dict:
        config = signal_config or SignalConfig()
        data, stock_info = self.load_price_data(symbol, period)
        if data is None or data.empty:
            err = stock_info.get("error") if isinstance(stock_info, dict) else "No data"
            return {"success": False, "error": err}

        if len(data) < 80:
            return {"success": False, "error": "Not enough historical bars for backtest"}

        cash = self.initial_capital
        shares = 0
        position = None
        trades: List[Dict] = []
        signals: List[Dict] = []
        equity_curve: List[Dict] = []

        rows = list(data.iterrows())
        start_date, start_row = rows[60]
        equity_curve.append({
            "date": start_date,
            "cash": cash,
            "market_value": 0.0,
            "equity": cash,
            "close": float(start_row["Close"]),
        })

        for i in range(60, len(rows) - 1):
            date, row = rows[i]
            next_date, next_row = rows[i + 1]

            if position:
                position["holding_days"] += 1

            if self.exit_execution == "intraday" and shares > 0 and position:
                exit_trade = self._try_intraday_exit(date, row, shares, position, config, cash)
                if exit_trade:
                    cash = exit_trade.pop("_cash_after")
                    trades.append(exit_trade)
                    shares = 0
                    position = None

            signal = generate_signal(row, position, config)
            signals.append({
                "date": date,
                "execution_date": next_date,
                "signal": signal["signal"],
                "score": signal["score"],
                "reason": signal["reason"],
                "rules_triggered": "; ".join(signal["rules_triggered"]),
                "close": float(row["Close"]),
            })

            execution_open = float(next_row["Open"])

            if signal["signal"] == "BUY" and shares == 0 and execution_open > 0:
                buy_price = execution_open * (1 + self.slippage_pct)
                sizing_base = cash
                if self.position_sizing == "initial_capital":
                    sizing_base = self.initial_capital
                target_amount = sizing_base * self.position_pct
                affordable_amount = min(cash, target_amount)
                buy_shares = int(affordable_amount / buy_price / 100) * 100
                gross = buy_shares * buy_price
                fee = gross * self.commission_rate

                if buy_shares >= 100 and cash >= gross + fee:
                    cash -= gross + fee
                    shares = buy_shares
                    position = {
                        "entry_price": buy_price,
                        "entry_date": next_date,
                        "shares": shares,
                        "buy_fee": fee,
                        "holding_days": 0,
                    }
                    trades.append({
                        "date": next_date,
                        "action": "BUY",
                        "price": buy_price,
                        "shares": shares,
                        "amount": gross,
                        "fee": fee,
                        "cash_after": cash,
                        "reason": signal["reason"],
                        "rules": "; ".join(signal["rules_triggered"]),
                    })

            elif signal["signal"] == "SELL" and shares > 0 and execution_open > 0:
                sell_price = execution_open * (1 - self.slippage_pct)
                gross = shares * sell_price
                fee = gross * (self.commission_rate + self.stamp_tax_rate)
                cash += gross - fee
                cost = shares * float(position["entry_price"])
                total_cost = cost + float(position.get("buy_fee", 0.0))
                profit = gross - fee - total_cost
                trades.append({
                    "date": next_date,
                    "action": "SELL",
                    "price": sell_price,
                    "shares": shares,
                    "amount": gross,
                    "fee": fee,
                    "cash_after": cash,
                    "reason": signal["reason"],
                    "buy_fee": float(position.get("buy_fee", 0.0)),
                    "profit": profit,
                    "profit_pct": profit / total_cost if total_cost else 0,
                    "rules": "; ".join(signal["rules_triggered"]),
                })
                shares = 0
                position = None

            market_value = shares * float(next_row["Close"])
            equity_curve.append({
                "date": next_date,
                "cash": cash,
                "market_value": market_value,
                "equity": cash + market_value,
                "close": float(next_row["Close"]),
            })

        if shares > 0 and position:
            final_date, final_row = rows[-1]
            final_price = float(final_row["Close"]) * (1 - self.slippage_pct)
            gross = shares * final_price
            fee = gross * (self.commission_rate + self.stamp_tax_rate)
            cash += gross - fee
            cost = shares * float(position["entry_price"])
            total_cost = cost + float(position.get("buy_fee", 0.0))
            trades.append({
                "date": final_date,
                "action": "SELL",
                "price": final_price,
                "shares": shares,
                "amount": gross,
                "fee": fee,
                "cash_after": cash,
                "reason": "final_liquidation",
                "buy_fee": float(position.get("buy_fee", 0.0)),
                "profit": gross - fee - total_cost,
                "profit_pct": (gross - fee - total_cost) / total_cost if total_cost else 0,
                "rules": "Final liquidation",
            })
            equity_curve.append({
                "date": final_date,
                "cash": cash,
                "market_value": 0.0,
                "equity": cash,
                "close": float(final_row["Close"]),
            })

        equity_df = pd.DataFrame(equity_curve)
        trades_df = pd.DataFrame(trades)
        signals_df = pd.DataFrame(signals)
        metrics = self._calculate_metrics(equity_df, trades_df)

        return {
            "success": True,
            "symbol": symbol,
            "stock_info": stock_info,
            "period": period,
            "config": asdict(config),
            "costs": {
                "commission_rate": self.commission_rate,
                "stamp_tax_rate": self.stamp_tax_rate,
                "slippage_pct": self.slippage_pct,
                "position_pct": self.position_pct,
                "position_sizing": self.position_sizing,
                "exit_execution": self.exit_execution,
                "annualization_days": self.annualization_days,
            },
            "metrics": metrics,
            "trades": trades_df,
            "signals": signals_df,
            "equity_curve": equity_df,
            "price_data": data,
        }

    def _try_intraday_exit(self, date, row: pd.Series, shares: int, position: Dict,
                           config: SignalConfig, cash: float) -> Dict | None:
        entry_price = float(position["entry_price"])
        stop_price = entry_price * (1 - config.stop_loss_pct)
        take_price = entry_price * (1 + config.take_profit_pct)
        low = float(row["Low"])
        high = float(row["High"])

        exit_price = None
        reason = None
        rules = []

        # Conservative ordering for daily bars: when both stop and take-profit
        # are touched on the same bar, assume the stop is hit first.
        if low <= stop_price:
            exit_price = stop_price * (1 - self.slippage_pct)
            reason = "intraday_stop_loss"
            rules = [f"Low <= stop loss ({config.stop_loss_pct:.0%})"]
        elif high >= take_price:
            exit_price = take_price * (1 - self.slippage_pct)
            reason = "intraday_take_profit"
            rules = [f"High >= take profit ({config.take_profit_pct:.0%})"]

        if exit_price is None:
            return None

        gross = shares * exit_price
        fee = gross * (self.commission_rate + self.stamp_tax_rate)
        cash_after = cash + gross - fee
        cost = shares * entry_price
        total_cost = cost + float(position.get("buy_fee", 0.0))
        profit = gross - fee - total_cost

        return {
            "date": date,
            "action": "SELL",
            "price": exit_price,
            "shares": shares,
            "amount": gross,
            "fee": fee,
            "cash_after": cash_after,
            "_cash_after": cash_after,
            "reason": reason,
            "buy_fee": float(position.get("buy_fee", 0.0)),
            "profit": profit,
            "profit_pct": profit / total_cost if total_cost else 0,
            "rules": "; ".join(rules),
        }

    def _calculate_metrics(self, equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> Dict:
        if equity_df.empty:
            return {
                "total_return": 0.0,
                "annual_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
                "win_rate": 0.0,
                "profit_loss_ratio": 0.0,
                "trade_count": 0,
                "final_equity": self.initial_capital,
            }

        equity = equity_df["equity"].astype(float)
        returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        total_return = equity.iloc[-1] / self.initial_capital - 1
        periods = max(len(equity_df) - 1, 1)
        annual_return = (1 + total_return) ** (self.annualization_days / periods) - 1
        drawdown = equity / equity.cummax() - 1
        sharpe = 0.0
        if not returns.empty and returns.std() != 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252)

        sell_trades = trades_df[trades_df["action"] == "SELL"] if not trades_df.empty else pd.DataFrame()
        trade_count = int(len(sell_trades))
        wins = sell_trades[sell_trades.get("profit", 0) > 0] if not sell_trades.empty else pd.DataFrame()
        losses = sell_trades[sell_trades.get("profit", 0) < 0] if not sell_trades.empty else pd.DataFrame()
        win_rate = len(wins) / trade_count if trade_count else 0.0
        avg_win = wins["profit"].mean() if not wins.empty else 0.0
        avg_loss = abs(losses["profit"].mean()) if not losses.empty else 0.0

        return {
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "max_drawdown": float(drawdown.min()),
            "sharpe": float(sharpe),
            "win_rate": float(win_rate),
            "profit_loss_ratio": float(avg_win / avg_loss) if avg_loss else 0.0,
            "trade_count": trade_count,
            "final_equity": float(equity.iloc[-1]),
        }
