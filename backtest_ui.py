#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Streamlit UI for deterministic strategy backtesting."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backtest_engine import BacktestEngine
from strategy_signals import SignalConfig


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def display_backtest():
    st.markdown("## 策略回测")
    st.caption("使用确定性规则生成信号，回测按 T 日信号、T+1 开盘成交，计入滑点和交易成本。")
    st.markdown("---")

    with st.form("backtest_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            symbol = st.text_input("股票代码", value="000001", help="支持 A股、港股、美股代码")
            period = st.selectbox("回测周期", ["1y", "6mo", "3mo"], index=0)
            initial_capital = st.number_input("初始资金", min_value=10000.0, value=100000.0, step=10000.0)
        with col2:
            position_pct = st.slider("单次仓位", 0.05, 1.0, 0.25, 0.05)
            stop_loss_pct = st.slider("止损比例", 0.02, 0.30, 0.08, 0.01)
            take_profit_pct = st.slider("止盈比例", 0.03, 0.60, 0.15, 0.01)
        with col3:
            volume_ratio_min = st.slider("最低量比", 0.5, 5.0, 1.3, 0.1)
            max_holding_days = st.slider("最长持有天数", 3, 120, 20, 1)
            slippage_pct = st.slider("滑点", 0.0, 0.02, 0.001, 0.001)

        advanced = st.expander("高级参数", expanded=False)
        with advanced:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                rsi_buy_min = st.number_input("RSI买入下限", value=45.0, step=1.0)
            with c2:
                rsi_buy_max = st.number_input("RSI买入上限", value=70.0, step=1.0)
            with c3:
                rsi_sell_max = st.number_input("RSI卖出上限", value=80.0, step=1.0)
            with c4:
                commission_rate = st.number_input("佣金率", value=0.0003, step=0.0001, format="%.4f")
            stamp_tax_rate = st.number_input("卖出印花税/费用率", value=0.0005, step=0.0001, format="%.4f")

        submitted = st.form_submit_button("运行回测", type="primary", width="stretch")

    if not submitted:
        st.info("当前内置策略：Close > MA20、MA5 > MA20、RSI处于买入区间、MACD强于信号线、量比达标时形成买入评分；持仓后按止损、止盈、持有期、跌破MA20、RSI过热退出。")
        return

    config = SignalConfig(
        rsi_buy_min=rsi_buy_min,
        rsi_buy_max=rsi_buy_max,
        rsi_sell_max=rsi_sell_max,
        volume_ratio_min=volume_ratio_min,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        max_holding_days=max_holding_days,
    )
    engine = BacktestEngine(
        initial_capital=initial_capital,
        position_pct=position_pct,
        commission_rate=commission_rate,
        stamp_tax_rate=stamp_tax_rate,
        slippage_pct=slippage_pct,
    )

    with st.spinner("正在获取数据并执行回测..."):
        result = engine.run(symbol.strip(), period=period, signal_config=config)

    if not result.get("success"):
        st.error(result.get("error", "回测失败"))
        return

    metrics = result["metrics"]
    name = result.get("stock_info", {}).get("name", symbol)
    st.success(f"{symbol} {name} 回测完成")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总收益", _pct(metrics["total_return"]))
    c2.metric("年化收益", _pct(metrics["annual_return"]))
    c3.metric("最大回撤", _pct(metrics["max_drawdown"]))
    c4.metric("夏普比率", f"{metrics['sharpe']:.2f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("胜率", _pct(metrics["win_rate"]))
    c6.metric("盈亏比", f"{metrics['profit_loss_ratio']:.2f}")
    c7.metric("完成交易", metrics["trade_count"])
    c8.metric("期末权益", f"{metrics['final_equity']:,.2f}")

    equity_df = result["equity_curve"]
    price_df = result["price_data"]
    trades_df = result["trades"]
    signals_df = result["signals"]

    tab1, tab2, tab3, tab4 = st.tabs(["权益曲线", "价格与买卖点", "交易明细", "信号日志"])

    with tab1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=equity_df["date"], y=equity_df["equity"], name="权益"))
        fig.update_layout(height=420, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=price_df.index,
            open=price_df["Open"],
            high=price_df["High"],
            low=price_df["Low"],
            close=price_df["Close"],
            name="K线",
        ))
        if not trades_df.empty:
            buys = trades_df[trades_df["action"] == "BUY"]
            sells = trades_df[trades_df["action"] == "SELL"]
            fig.add_trace(go.Scatter(x=buys["date"], y=buys["price"], mode="markers", name="买入",
                                     marker=dict(color="red", size=10, symbol="triangle-up")))
            fig.add_trace(go.Scatter(x=sells["date"], y=sells["price"], mode="markers", name="卖出",
                                     marker=dict(color="green", size=10, symbol="triangle-down")))
        fig.update_layout(height=520, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        if trades_df.empty:
            st.warning("本次回测没有产生交易。")
        else:
            display_df = trades_df.copy()
            display_df["date"] = pd.to_datetime(display_df["date"]).dt.strftime("%Y-%m-%d")
            st.dataframe(display_df, use_container_width=True)
            st.download_button(
                "下载交易明细CSV",
                data=display_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"backtest_trades_{symbol}.csv",
                mime="text/csv",
            )

    with tab4:
        display_signals = signals_df.copy()
        display_signals["date"] = pd.to_datetime(display_signals["date"]).dt.strftime("%Y-%m-%d")
        display_signals["execution_date"] = pd.to_datetime(display_signals["execution_date"]).dt.strftime("%Y-%m-%d")
        st.dataframe(display_signals.tail(200), use_container_width=True)

    with st.expander("本次策略参数", expanded=False):
        st.json({"signal_config": result["config"], "costs": result["costs"]})
