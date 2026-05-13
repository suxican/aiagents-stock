import pandas as pd
import plotly.graph_objects as go
import streamlit as st


RETRACEMENT_RATIOS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
EXTENSION_RATIOS = [1.272, 1.618, 2, 2.618]


@st.cache_data(ttl=300)
def load_fibonacci_stock_data(symbol, period):
    from stock_data import StockDataFetcher

    fetcher = StockDataFetcher()
    stock_info = fetcher.get_stock_info(symbol)
    stock_data = fetcher.get_stock_data(symbol, period)

    if isinstance(stock_data, dict) and "error" in stock_data:
        return stock_info, None, stock_data["error"]

    if stock_data is None or stock_data.empty:
        return stock_info, None, "无法获取股票历史数据"

    required_columns = {"Open", "High", "Low", "Close"}
    missing_columns = required_columns - set(stock_data.columns)
    if missing_columns:
        return stock_info, None, f"历史数据缺少必要字段: {', '.join(sorted(missing_columns))}"

    return stock_info, stock_data.sort_index(), None


def calculate_fibonacci_levels(stock_data):
    high_idx = stock_data["High"].idxmax()
    low_idx = stock_data["Low"].idxmin()
    swing_high = float(stock_data.loc[high_idx, "High"])
    swing_low = float(stock_data.loc[low_idx, "Low"])
    price_range = swing_high - swing_low

    if price_range <= 0:
        return None

    is_uptrend = low_idx < high_idx
    trend = "上涨波段" if is_uptrend else "下跌波段"

    retracements = []
    for ratio in RETRACEMENT_RATIOS:
        price = swing_high - price_range * ratio if is_uptrend else swing_low + price_range * ratio
        retracements.append({
            "type": "回撤",
            "ratio": ratio,
            "label": f"{ratio * 100:.1f}%",
            "price": price,
        })

    extensions = []
    for ratio in EXTENSION_RATIOS:
        price = swing_low + price_range * ratio if is_uptrend else swing_high - price_range * ratio
        extensions.append({
            "type": "扩展",
            "ratio": ratio,
            "label": f"{ratio * 100:.1f}%",
            "price": price,
        })

    return {
        "trend": trend,
        "is_uptrend": is_uptrend,
        "high_idx": high_idx,
        "low_idx": low_idx,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "price_range": price_range,
        "retracements": retracements,
        "extensions": extensions,
    }


def find_nearest_levels(levels, current_price):
    all_levels = levels["retracements"] + levels["extensions"]
    supports = [level for level in all_levels if level["price"] < current_price]
    resistances = [level for level in all_levels if level["price"] > current_price]

    nearest_support = max(supports, key=lambda item: item["price"], default=None)
    nearest_resistance = min(resistances, key=lambda item: item["price"], default=None)
    return nearest_support, nearest_resistance


def format_level(level):
    if not level:
        return "暂无"
    return f"{level['label']} / {level['price']:.2f}"


def build_level_table(levels, current_price, level_type):
    rows = []
    for level in levels:
        distance = level["price"] - current_price
        distance_percent = distance / current_price * 100 if current_price else 0
        if level["price"] < current_price:
            meaning = "支撑"
        elif level["price"] > current_price:
            meaning = "压力/目标"
        else:
            meaning = "当前价附近"

        rows.append({
            "类型": level_type,
            "比例": level["label"],
            "价格": round(level["price"], 2),
            "距当前价": f"{distance:+.2f}",
            "距离比例": f"{distance_percent:+.2f}%",
            "含义": meaning,
        })

    return pd.DataFrame(rows)


def build_fibonacci_chart(stock_data, stock_info, levels, current_price):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=stock_data.index,
        open=stock_data["Open"],
        high=stock_data["High"],
        low=stock_data["Low"],
        close=stock_data["Close"],
        name="K线",
        increasing_line_color="#16a34a",
        decreasing_line_color="#dc2626",
    ))

    for level in levels["retracements"]:
        fig.add_hline(
            y=level["price"],
            line_width=1,
            line_dash="dot",
            line_color="#2563eb",
            annotation_text=f"回撤 {level['label']} {level['price']:.2f}",
            annotation_position="right",
        )

    for level in levels["extensions"]:
        fig.add_hline(
            y=level["price"],
            line_width=1,
            line_dash="dash",
            line_color="#ea580c",
            annotation_text=f"扩展 {level['label']} {level['price']:.2f}",
            annotation_position="right",
        )

    fig.add_hline(
        y=current_price,
        line_width=2,
        line_color="#111827",
        annotation_text=f"当前价 {current_price:.2f}",
        annotation_position="left",
    )

    fig.add_trace(go.Scatter(
        x=[levels["high_idx"]],
        y=[levels["swing_high"]],
        mode="markers+text",
        name="波段高点",
        text=["High"],
        textposition="top center",
        marker=dict(size=10, color="#dc2626"),
    ))

    fig.add_trace(go.Scatter(
        x=[levels["low_idx"]],
        y=[levels["swing_low"]],
        mode="markers+text",
        name="波段低点",
        text=["Low"],
        textposition="bottom center",
        marker=dict(size=10, color="#16a34a"),
    ))

    stock_name = stock_info.get("name", "N/A") if isinstance(stock_info, dict) else "N/A"
    symbol = stock_info.get("symbol", "") if isinstance(stock_info, dict) else ""
    fig.update_layout(
        title=f"{stock_name} {symbol} 斐波那契回撤与扩展",
        height=620,
        margin=dict(l=20, r=20, t=60, b=20),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )

    return fig


def display_fibonacci_tool():
    st.title("📐 斐波那契回撤与扩展")
    st.caption("基于所选周期内的波段高低点自动计算关键回撤位和扩展目标位。")

    col_symbol, col_period, col_button = st.columns([2, 1, 1])
    with col_symbol:
        symbol = st.text_input("股票代码", value="600519", placeholder="如 600519 / 00700 / AAPL")
    with col_period:
        period = st.selectbox("数据周期", ["1y", "6mo", "3mo", "1mo"], index=0)
    with col_button:
        st.write("")
        st.write("")
        run_analysis = st.button("生成分析", type="primary", width="stretch")

    if not run_analysis and "fibonacci_last_symbol" not in st.session_state:
        st.info("输入股票代码后点击生成分析，即可查看斐波那契关键位。")
        return

    if run_analysis:
        st.session_state.fibonacci_last_symbol = symbol.strip()
        st.session_state.fibonacci_last_period = period

    symbol = st.session_state.get("fibonacci_last_symbol", symbol).strip()
    period = st.session_state.get("fibonacci_last_period", period)

    if not symbol:
        st.warning("请输入股票代码。")
        return

    with st.spinner("正在获取行情并计算斐波那契关键位..."):
        stock_info, stock_data, error = load_fibonacci_stock_data(symbol, period)

    if error:
        st.error(error)
        return

    levels = calculate_fibonacci_levels(stock_data)
    if not levels:
        st.warning("当前周期内高低点无有效价差，无法计算斐波那契位。")
        return

    current_price = float(stock_data["Close"].iloc[-1])
    latest_date = stock_data.index[-1]
    nearest_support, nearest_resistance = find_nearest_levels(levels, current_price)

    metric_cols = st.columns(5)
    metric_cols[0].metric("当前价", f"{current_price:.2f}")
    metric_cols[1].metric("趋势判断", levels["trend"])
    metric_cols[2].metric("波段高点", f"{levels['swing_high']:.2f}")
    metric_cols[3].metric("波段低点", f"{levels['swing_low']:.2f}")
    metric_cols[4].metric("最近交易日", latest_date.strftime("%Y-%m-%d") if hasattr(latest_date, "strftime") else str(latest_date))

    support_cols = st.columns(2)
    support_cols[0].info(f"最近支撑位：{format_level(nearest_support)}")
    support_cols[1].warning(f"最近压力位：{format_level(nearest_resistance)}")

    fig = build_fibonacci_chart(stock_data, stock_info, levels, current_price)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("关键位明细")
    col_retracement, col_extension = st.columns(2)
    with col_retracement:
        st.markdown("#### 回撤位")
        retracement_df = build_level_table(levels["retracements"], current_price, "回撤")
        st.dataframe(retracement_df, width="stretch", hide_index=True)

    with col_extension:
        st.markdown("#### 扩展位")
        extension_df = build_level_table(levels["extensions"], current_price, "扩展")
        st.dataframe(extension_df, width="stretch", hide_index=True)
