"""
Streamlit UI for sector overview.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from sector_overview_data import SectorOverviewService


REPORT_DB_PATH = Path("sector_overview_reports.db")


@st.cache_data(ttl=600, show_spinner=False)
def _load_sector_overview(trade_date: date, lookback_days: int) -> Dict[str, Any]:
    service = SectorOverviewService(lookback_days=lookback_days)
    return service.build_overview(trade_date=trade_date)


def display_sector_overview() -> None:
    st.markdown("## 📌 板块概览")

    _inject_styles()

    col_title, col_history, col_refresh, col_date = st.columns([4.6, 1, 1, 1.4])
    with col_title:
        st.caption("自动复盘 · 资金强势板块 · 涨停主线 · 板块轮动")
    with col_history:
        if st.button("历史报告", width="stretch", key="sector_overview_history"):
            st.session_state.sector_overview_view = "history"
    with col_refresh:
        replay_clicked = st.button("复盘", type="primary", width="stretch", key="sector_overview_refresh")
    with col_date:
        selected_date = st.date_input("交易日", value=date.today(), key="sector_overview_date")

    if replay_clicked:
        _load_sector_overview.clear()
        st.session_state.sector_overview_view = "detail"
        with st.spinner("正在汇总板块行情、涨停池和轮动数据..."):
            st.session_state.sector_overview_result = _load_sector_overview(selected_date, 7)
            report_id = _save_report(st.session_state.sector_overview_result)
            st.session_state.sector_overview_selected_report_id = report_id
        st.success("复盘完成，报告已保存到历史报告。")

    if st.session_state.get("sector_overview_view") == "history":
        _render_history_reports()
        return

    data = st.session_state.get("sector_overview_result")
    if not data:
        st.info("请选择交易日后点击“复盘”，系统才会开始获取板块行情、涨停主线和轮动数据。")
        return

    if data.get("trade_date") != selected_date.strftime("%Y-%m-%d"):
        st.warning("当前展示的是上次复盘结果；如需查看所选交易日，请点击“复盘”。")

    _render_meta(data)
    _render_review(data.get("review", []))
    _render_metrics(data.get("market_stats", {}))

    left, right = st.columns([1, 1])
    with left:
        _render_strong_sectors(data.get("strong_sectors", []))
    with right:
        _render_limit_themes(data.get("limit_themes", []))

    _render_rotation(data.get("rotation_days", []), data.get("rotation_table", []))

    warnings = data.get("warnings") or []
    if warnings:
        with st.expander("数据提示", expanded=False):
            for item in warnings[:12]:
                st.caption(item)


def _render_report_detail(data: Dict[str, Any]) -> None:
    _render_meta(data)
    _render_review(data.get("review", []))
    _render_metrics(data.get("market_stats", {}))

    left, right = st.columns([1, 1])
    with left:
        _render_strong_sectors(data.get("strong_sectors", []))
    with right:
        _render_limit_themes(data.get("limit_themes", []))

    _render_rotation(data.get("rotation_days", []), data.get("rotation_table", []))

    warnings = data.get("warnings") or []
    if warnings:
        with st.expander("数据提示", expanded=False):
            for item in warnings[:12]:
                st.caption(item)


def _init_report_db() -> None:
    with sqlite3.connect(REPORT_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sector_overview_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                generated_at TEXT,
                summary TEXT,
                top_sector TEXT,
                top_theme TEXT,
                report_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sector_overview_trade_date ON sector_overview_reports(trade_date)"
        )


def _save_report(data: Dict[str, Any]) -> int:
    _init_report_db()
    review = data.get("review") or []
    strong = data.get("strong_sectors") or []
    themes = data.get("limit_themes") or []
    summary = review[0] if review else "板块概览复盘报告"
    top_sector = strong[0].get("name", "") if strong else ""
    top_theme = themes[0].get("theme", "") if themes else ""

    with sqlite3.connect(REPORT_DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO sector_overview_reports
            (trade_date, generated_at, summary, top_sector, top_theme, report_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("trade_date", ""),
                data.get("generated_at", ""),
                summary,
                top_sector,
                top_theme,
                json.dumps(data, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def _list_reports(limit: int = 50) -> List[Dict[str, Any]]:
    _init_report_db()
    with sqlite3.connect(REPORT_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, trade_date, generated_at, summary, top_sector, top_theme, created_at
            FROM sector_overview_reports
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _get_report(report_id: int) -> Dict[str, Any]:
    _init_report_db()
    with sqlite3.connect(REPORT_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT report_json FROM sector_overview_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["report_json"])
    except Exception:
        return {}


def _render_history_reports() -> None:
    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("返回", width="stretch", key="sector_overview_history_back"):
            st.session_state.sector_overview_view = "detail"
            st.rerun()
    with col_title:
        st.markdown("### 历史复盘报告")

    reports = _list_reports()
    if not reports:
        st.info("暂无历史复盘报告。点击“复盘”后会自动保存到这里。")
        return

    selected_id = st.session_state.get("sector_overview_selected_report_id")
    for report in reports:
        report_id = int(report["id"])
        title = f"{report['trade_date']}｜{report.get('top_theme') or '无明确主线'}｜{report.get('top_sector') or '无强势板块'}"
        with st.container():
            c1, c2, c3 = st.columns([4.2, 1.8, 1])
            with c1:
                marker = "● " if selected_id == report_id else ""
                st.markdown(f"**{marker}{title}**")
                st.caption(report.get("summary") or "板块概览复盘报告")
            with c2:
                st.caption(f"生成时间：{report.get('generated_at') or report.get('created_at')}")
            with c3:
                if st.button("查看详情", key=f"sector_overview_open_{report_id}", width="stretch"):
                    st.session_state.sector_overview_selected_report_id = report_id
                    st.session_state.sector_overview_history_detail = _get_report(report_id)
                    st.rerun()

    detail = st.session_state.get("sector_overview_history_detail")
    if detail:
        st.markdown("---")
        st.markdown("### 报告详情")
        _render_report_detail(detail)


def _render_meta(data: Dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="sector-overview-meta">
            <span>交易日：{data.get("trade_date", "-")}</span>
            <span>数据更新：{data.get("data_updated_at", "-")}</span>
            <span>复盘生成：{data.get("generated_at", "-")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_review(review: List[str]) -> None:
    st.markdown("### 复盘结论")
    if not review:
        st.info("暂无复盘结论")
        return

    html = ["<div class='sector-review'>"]
    for idx, item in enumerate(review, 1):
        html.append(
            f"<div class='sector-review-row'><span>{idx}</span><p>{item}</p></div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _render_metrics(stats: Dict[str, Any]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("涨停家数", stats.get("limit_up", 0))
    with col2:
        st.metric("跌停家数", stats.get("limit_down", 0))
    with col3:
        st.metric("上涨家数", stats.get("up", 0))
    with col4:
        st.metric("最高连板", stats.get("max_board", 0))


def _render_strong_sectors(rows: List[Dict[str, Any]]) -> None:
    st.markdown("### 资金强势板块")
    if not rows:
        st.info("暂无强势板块数据")
        return

    df = pd.DataFrame(rows[:12])
    display_df = pd.DataFrame(
        {
            "板块": df["name"],
            "类型": df["type"],
            "涨跌幅": df["change_pct"].map(lambda x: _fmt_pct(x)),
            "主力净流入": df["main_net_inflow"].map(_fmt_money),
            "上涨家数": df["up_count"],
            "领涨股": df["top_stock"],
            "领涨涨幅": df["top_stock_change"].map(lambda x: _fmt_pct(x)),
            "强势分": df["score"],
        }
    )
    st.dataframe(display_df, width="stretch", height=420, hide_index=True)


def _render_limit_themes(rows: List[Dict[str, Any]]) -> None:
    st.markdown("### 当日涨停主线")
    if not rows:
        st.info("暂无涨停主线数据")
        return

    df = pd.DataFrame(rows[:12])
    display_df = pd.DataFrame(
        {
            "题材": df["theme"],
            "涨停家数": df["limit_up_count"],
            "最高连板": df["max_board"],
            "核心个股": df["core_stocks"],
        }
    )
    st.dataframe(display_df, width="stretch", height=420, hide_index=True)


def _render_rotation(day_cards: List[Dict[str, Any]], table_rows: List[Dict[str, Any]]) -> None:
    st.markdown("### 板块轮动")

    if day_cards:
        cols = st.columns(min(len(day_cards), 7))
        for col, card in zip(cols, day_cards[-7:]):
            with col:
                tags = "".join(
                    f"<span>{theme['theme']} {theme['limit_up_count']}</span>"
                    for theme in card.get("themes", [])[:3]
                )
                st.markdown(
                    f"""
                    <div class="rotation-card">
                        <div class="rotation-date">{card.get("date", "-")}</div>
                        <strong>{card.get("top_theme", "-")}</strong>
                        <p>涨停 {card.get("limit_up_count", 0)} 家</p>
                        <div class="rotation-tags">{tags}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if not table_rows:
        st.info("暂无轮动明细")
        return

    df = pd.DataFrame(table_rows)
    display_df = pd.DataFrame(
        {
            "轮动题材": df["theme"],
            "活跃天数": df["active_days"],
            "累计涨停": df["total_limit_up"],
            "最新涨停": df["latest_limit_up"],
            "趋势": df["status"],
            "近几日分布": df["recent_path"],
        }
    )
    st.dataframe(display_df, width="stretch", height=360, hide_index=True)


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "-"


def _fmt_money(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:+.2f}亿"
    if abs(number) >= 10000:
        return f"{number / 10000:+.2f}万"
    return f"{number:+.0f}"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .sector-overview-meta {
            display: flex;
            gap: 18px;
            flex-wrap: wrap;
            color: #64748b;
            font-size: 13px;
            padding: 8px 0 12px;
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 10px;
        }
        .sector-review {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 12px;
        }
        .sector-review-row {
            display: flex;
            gap: 10px;
            align-items: flex-start;
            padding: 8px 10px;
            border-bottom: 1px solid #eef2f7;
            background: #ffffff;
        }
        .sector-review-row:last-child {
            border-bottom: 0;
        }
        .sector-review-row span {
            width: 20px;
            height: 20px;
            flex: 0 0 20px;
            border-radius: 50%;
            background: #eef2ff;
            color: #334155;
            text-align: center;
            line-height: 20px;
            font-size: 12px;
            font-weight: 700;
        }
        .sector-review-row p {
            margin: 0;
            color: #334155;
            line-height: 1.55;
            font-size: 14px;
        }
        .rotation-card {
            min-height: 118px;
            border: 1px solid #dbeafe;
            border-radius: 8px;
            padding: 10px;
            background: #f8fbff;
            margin-bottom: 12px;
        }
        .rotation-date {
            color: #64748b;
            font-size: 12px;
            margin-bottom: 6px;
        }
        .rotation-card strong {
            color: #1e3a8a;
            font-size: 15px;
            line-height: 1.3;
        }
        .rotation-card p {
            color: #475569;
            font-size: 12px;
            margin: 6px 0;
        }
        .rotation-tags {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
        }
        .rotation-tags span {
            background: #e0f2fe;
            color: #0369a1;
            border-radius: 4px;
            padding: 2px 5px;
            font-size: 11px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
