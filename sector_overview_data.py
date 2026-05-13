"""
Sector overview data service.

This module builds a lightweight market review from public AKShare data:
sector strength, limit-up themes, and recent theme rotation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from time_utils import now_local_str


@dataclass
class SectorOverviewService:
    """Fetch and aggregate sector overview data for the Streamlit page."""

    lookback_days: int = 7

    def build_overview(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        import akshare as ak

        target_date = trade_date or date.today()
        date_text = target_date.strftime("%Y%m%d")
        warnings: List[str] = []

        industry_df = self._safe_call(ak.stock_board_industry_name_em, warnings, "行业板块行情")
        concept_df = self._safe_call(ak.stock_board_concept_name_em, warnings, "概念板块行情")
        fund_df = self._safe_call(
            ak.stock_sector_fund_flow_rank,
            warnings,
            "行业资金流",
            indicator="今日",
        )
        spot_df = self._safe_call(ak.stock_zh_a_spot_em, warnings, "A股实时行情")
        limit_up_df = self._safe_call(ak.stock_zt_pool_em, warnings, "涨停池", date=date_text)
        limit_down_df = self._safe_call(ak.stock_zt_pool_dtgc_em, warnings, "跌停池", date=date_text)

        industry_df = self._fallback_cached_frame(industry_df, "sectors", warnings)
        concept_df = self._fallback_cached_frame(concept_df, "concepts", warnings)
        fund_df = self._fallback_cached_frame(fund_df, "fund_flow", warnings)

        strong_sectors = self._build_strong_sectors(industry_df, concept_df, fund_df)
        limit_themes = self._build_limit_themes(limit_up_df, concept_df, industry_df)
        market_stats = self._build_market_stats(spot_df, limit_up_df, limit_down_df)
        rotation = self._build_rotation(ak, target_date, concept_df, industry_df, warnings)
        review = self._build_review(strong_sectors, limit_themes, rotation, market_stats)

        return {
            "success": True,
            "trade_date": target_date.strftime("%Y-%m-%d"),
            "generated_at": now_local_str(),
            "data_updated_at": self._guess_update_time(industry_df, concept_df, fund_df),
            "warnings": warnings,
            "review": review,
            "market_stats": market_stats,
            "strong_sectors": strong_sectors,
            "limit_themes": limit_themes,
            "rotation_days": rotation["days"],
            "rotation_table": rotation["table"],
        }

    def _safe_call(self, func, warnings: List[str], label: str, *args, **kwargs) -> pd.DataFrame:
        try:
            df = func(*args, **kwargs)
            if df is None or df.empty:
                warnings.append(f"{label}为空")
                return pd.DataFrame()
            return df.copy()
        except Exception as exc:
            warnings.append(f"{label}获取失败: {self._short_error(exc)}")
            return pd.DataFrame()

    def _fallback_cached_frame(
        self,
        live_df: pd.DataFrame,
        cache_key: str,
        warnings: List[str],
    ) -> pd.DataFrame:
        if live_df is not None and not live_df.empty:
            return live_df

        try:
            from sector_strategy_db import SectorStrategyDatabase

            cached = SectorStrategyDatabase().get_latest_raw_data(cache_key, within_hours=24 * 14)
        except Exception as exc:
            warnings.append(f"{cache_key}缓存读取失败: {self._short_error(exc)}")
            return pd.DataFrame()

        if not cached or not cached.get("data_content"):
            warnings.append(f"{cache_key}无可用缓存")
            return pd.DataFrame()

        data = cached["data_content"]
        if cache_key in ("sectors", "concepts"):
            rows = []
            for item in data.values():
                rows.append(
                    {
                        "板块名称": item.get("name", ""),
                        "涨跌幅": item.get("change_pct", 0),
                        "换手率": item.get("turnover", 0),
                        "上涨家数": item.get("up_count", 0),
                        "下跌家数": item.get("down_count", 0),
                        "领涨股票": item.get("top_stock", ""),
                        "领涨股票-涨跌幅": item.get("top_stock_change", 0),
                    }
                )
            warnings.append(f"{cache_key}实时数据不可用，已使用 {cached.get('data_date', '最近')} 缓存")
            return pd.DataFrame(rows)

        if cache_key == "fund_flow":
            rows = []
            for item in data.get("today", []):
                rows.append(
                    {
                        "名称": item.get("sector", ""),
                        "今日主力净流入-净额": item.get("main_net_inflow", 0),
                        "今日主力净流入-净占比": item.get("main_net_inflow_pct", 0),
                    }
                )
            warnings.append(f"资金流实时数据不可用，已使用 {cached.get('data_date', '最近')} 缓存")
            return pd.DataFrame(rows)

        return pd.DataFrame()

    def _build_strong_sectors(
        self,
        industry_df: pd.DataFrame,
        concept_df: pd.DataFrame,
        fund_df: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        market_rows = []
        for source, df in (("行业", industry_df), ("概念", concept_df)):
            if df.empty:
                continue
            name_col = self._find_col(df, ["板块名称", "名称"])
            if not name_col:
                continue
            for _, row in df.iterrows():
                market_rows.append(
                    {
                        "type": source,
                        "name": str(row.get(name_col, "")).strip(),
                        "change_pct": self._num(row, ["涨跌幅", "今日涨跌幅"]),
                        "turnover": self._num(row, ["换手率"]),
                        "up_count": int(self._num(row, ["上涨家数"], 0)),
                        "down_count": int(self._num(row, ["下跌家数"], 0)),
                        "top_stock": self._text(row, ["领涨股票", "领涨股"]),
                        "top_stock_change": self._num(row, ["领涨股票-涨跌幅", "领涨股涨跌幅"]),
                    }
                )

        fund_map: Dict[str, Dict[str, float]] = {}
        if not fund_df.empty:
            fund_name_col = self._find_col(fund_df, ["名称", "板块名称"])
            if fund_name_col:
                for _, row in fund_df.iterrows():
                    name = str(row.get(fund_name_col, "")).strip()
                    fund_map[name] = {
                        "main_net_inflow": self._num(row, ["今日主力净流入-净额", "主力净流入净额"]),
                        "main_net_inflow_pct": self._num(row, ["今日主力净流入-净占比", "主力净流入净占比"]),
                    }

        rows: List[Dict[str, Any]] = []
        max_abs_flow = max((abs(v["main_net_inflow"]) for v in fund_map.values()), default=1.0) or 1.0
        for item in market_rows:
            fund = fund_map.get(item["name"], {})
            flow = fund.get("main_net_inflow", 0.0)
            score = (
                item["change_pct"] * 20
                + item["top_stock_change"] * 8
                + item["up_count"] * 1.5
                - item["down_count"] * 0.8
                + (flow / max_abs_flow) * 25
            )
            rows.append(
                {
                    **item,
                    "main_net_inflow": flow,
                    "main_net_inflow_pct": fund.get("main_net_inflow_pct", 0.0),
                    "score": round(score, 2),
                }
            )

        rows.sort(key=lambda x: x["score"], reverse=True)
        return rows[:30]

    def _build_limit_themes(
        self,
        limit_up_df: pd.DataFrame,
        concept_df: pd.DataFrame,
        industry_df: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        if limit_up_df.empty:
            return []

        theme_counter: Counter[str] = Counter()
        theme_stocks: Dict[str, List[str]] = defaultdict(list)
        theme_boards: Dict[str, int] = defaultdict(int)
        concept_names = self._extract_names(concept_df)
        industry_names = self._extract_names(industry_df)

        name_col = self._find_col(limit_up_df, ["名称", "股票简称", "证券简称"])
        reason_col = self._find_col(limit_up_df, ["涨停原因类别", "涨停原因", "所属行业"])
        board_col = self._find_col(limit_up_df, ["连板数", "连续涨停天数"])

        for _, row in limit_up_df.iterrows():
            stock_name = self._text(row, [name_col]) if name_col else ""
            reasons = self._split_themes(self._text(row, [reason_col]) if reason_col else "")
            if not reasons:
                reasons = self._infer_themes(stock_name, concept_names, industry_names)
            if not reasons:
                reasons = ["未分类"]

            board_count = int(self._num(row, [board_col], 1)) if board_col else 1
            for theme in reasons[:4]:
                theme_counter[theme] += 1
                if stock_name and len(theme_stocks[theme]) < 8:
                    theme_stocks[theme].append(stock_name)
                theme_boards[theme] = max(theme_boards[theme], board_count)

        rows = []
        for theme, count in theme_counter.most_common(20):
            boards = theme_boards.get(theme, 0)
            rows.append(
                {
                    "theme": theme,
                    "limit_up_count": count,
                    "board_count": boards,
                    "max_board": boards,
                    "core_stocks": "、".join(theme_stocks.get(theme, [])[:6]),
                }
            )
        return rows

    def _build_market_stats(
        self,
        spot_df: pd.DataFrame,
        limit_up_df: pd.DataFrame,
        limit_down_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        stats = {
            "total": 0,
            "up": 0,
            "down": 0,
            "flat": 0,
            "limit_up": len(limit_up_df) if not limit_up_df.empty else 0,
            "limit_down": len(limit_down_df) if not limit_down_df.empty else 0,
            "max_board": 0,
        }
        if not spot_df.empty:
            pct_col = self._find_col(spot_df, ["涨跌幅"])
            if pct_col:
                pct = pd.to_numeric(spot_df[pct_col], errors="coerce").fillna(0)
                stats["total"] = int(len(pct))
                stats["up"] = int((pct > 0).sum())
                stats["down"] = int((pct < 0).sum())
                stats["flat"] = int((pct == 0).sum())
        if not limit_up_df.empty:
            board_col = self._find_col(limit_up_df, ["连板数", "连续涨停天数"])
            if board_col:
                stats["max_board"] = int(pd.to_numeric(limit_up_df[board_col], errors="coerce").fillna(0).max())
        return stats

    def _build_rotation(
        self,
        ak,
        target_date: date,
        concept_df: pd.DataFrame,
        industry_df: pd.DataFrame,
        warnings: List[str],
    ) -> Dict[str, Any]:
        concept_names = self._extract_names(concept_df)
        industry_names = self._extract_names(industry_df)
        day_cards: List[Dict[str, Any]] = []
        theme_daily: Dict[str, List[int]] = defaultdict(list)
        dates: List[str] = []

        day = target_date
        attempts = 0
        rotation_errors = 0
        while len(day_cards) < self.lookback_days and attempts < 16:
            attempts += 1
            if day.weekday() >= 5:
                day -= timedelta(days=1)
                continue
            date_text = day.strftime("%Y%m%d")
            df = self._safe_call_quiet(ak.stock_zt_pool_em, date=date_text)
            if df.empty:
                rotation_errors += 1
            if not df.empty:
                themes = self._build_limit_themes(df, concept_df, industry_df)
                top = themes[:4]
                day_label = day.strftime("%Y-%m-%d")
                dates.append(day_label)
                day_cards.append(
                    {
                        "date": day_label,
                        "top_theme": top[0]["theme"] if top else "无明显主线",
                        "limit_up_count": len(df),
                        "themes": top,
                    }
                )
                for theme in top:
                    theme_daily[theme["theme"]].append(theme["limit_up_count"])
                for theme in set(theme_daily) - {t["theme"] for t in top}:
                    theme_daily[theme].append(0)
            day -= timedelta(days=1)

        if not day_cards and rotation_errors:
            warnings.append("最近涨停池轮动数据不可用，请检查网络/代理或稍后重试")

        day_cards = list(reversed(day_cards))
        table = []
        for theme, counts in theme_daily.items():
            if len(counts) < len(day_cards):
                counts = [0] * (len(day_cards) - len(counts)) + counts
            active_days = sum(1 for x in counts if x > 0)
            latest = counts[-1] if counts else 0
            prev = counts[-2] if len(counts) > 1 else 0
            if latest > prev and latest > 0:
                status = "升温"
            elif latest > 0 and active_days >= 3:
                status = "持续"
            elif latest > 0:
                status = "启动"
            elif prev > 0:
                status = "退潮"
            else:
                status = "观察"
            table.append(
                {
                    "theme": theme,
                    "active_days": active_days,
                    "total_limit_up": sum(counts),
                    "latest_limit_up": latest,
                    "status": status,
                    "recent_path": " / ".join(str(x) for x in counts[-7:]),
                }
            )
        table.sort(key=lambda x: (x["latest_limit_up"], x["total_limit_up"], x["active_days"]), reverse=True)
        return {"days": day_cards, "table": table[:30], "dates": dates}

    def _safe_call_quiet(self, func, *args, **kwargs) -> pd.DataFrame:
        try:
            df = func(*args, **kwargs)
            if df is None or df.empty:
                return pd.DataFrame()
            return df.copy()
        except Exception:
            return pd.DataFrame()

    def _build_review(
        self,
        strong_sectors: List[Dict[str, Any]],
        limit_themes: List[Dict[str, Any]],
        rotation: Dict[str, Any],
        market_stats: Dict[str, Any],
    ) -> List[str]:
        top_sector = strong_sectors[0]["name"] if strong_sectors else "暂无明确强势板块"
        top_theme = limit_themes[0]["theme"] if limit_themes else "暂无明确涨停主线"
        up = market_stats.get("up", 0)
        down = market_stats.get("down", 0)
        limit_up = market_stats.get("limit_up", 0)
        limit_down = market_stats.get("limit_down", 0)

        hot_rotation = next((x for x in rotation.get("table", []) if x["status"] in ("升温", "持续")), None)
        rotation_text = (
            f"{hot_rotation['theme']}呈现{hot_rotation['status']}，近几日涨停分布为 {hot_rotation['recent_path']}"
            if hot_rotation
            else "近期主线仍在切换，暂未形成连续性特别强的方向"
        )

        risk_text = "跌停家数偏多，需留意高位题材退潮风险" if limit_down >= 10 else "跌停压力可控，短线风险主要来自强势题材分化"
        breadth_text = "上涨家数占优" if up >= down else "下跌家数占优"

        return [
            f"盘面{breadth_text}，涨停 {limit_up} 家、跌停 {limit_down} 家，最高连板 {market_stats.get('max_board', 0)} 板。",
            f"资金强势方向集中在 {top_sector}，可结合主力净流入和领涨股强度观察持续性。",
            f"当日涨停主线以 {top_theme} 为代表，核心股的连板高度决定题材弹性。",
            f"板块轮动上，{rotation_text}。",
            risk_text,
        ]

    def _extract_names(self, df: pd.DataFrame) -> List[str]:
        if df.empty:
            return []
        col = self._find_col(df, ["板块名称", "名称"])
        if not col:
            return []
        return [str(x).strip() for x in df[col].dropna().tolist() if str(x).strip()]

    def _infer_themes(self, stock_name: str, concept_names: Iterable[str], industry_names: Iterable[str]) -> List[str]:
        # Direct inference from stock name is intentionally conservative.
        matches = [name for name in concept_names if stock_name and stock_name in name]
        if matches:
            return matches[:3]
        return list(industry_names)[:1] if industry_names else []

    def _split_themes(self, value: str) -> List[str]:
        if not value or value in ("nan", "None"):
            return []
        separators = ["+", "，", ",", "；", ";", "/", "\\", "|", "、"]
        items = [value]
        for sep in separators:
            next_items = []
            for item in items:
                next_items.extend(item.split(sep))
            items = next_items
        cleaned = []
        for item in items:
            text = item.strip()
            if text and text not in cleaned:
                cleaned.append(text[:18])
        return cleaned

    def _guess_update_time(self, *dfs: pd.DataFrame) -> str:
        for df in dfs:
            if df is None or df.empty:
                continue
            for col in df.columns:
                if "时间" in str(col):
                    value = df.iloc[0].get(col)
                    if pd.notna(value):
                        return str(value)
        return now_local_str()

    def _find_col(self, df: pd.DataFrame, names: Iterable[Optional[str]]) -> Optional[str]:
        columns = list(df.columns)
        for name in names:
            if not name:
                continue
            if name in columns:
                return name
        for name in names:
            if not name:
                continue
            for col in columns:
                if str(name) in str(col):
                    return col
        return None

    def _num(self, row: pd.Series, names: Iterable[Optional[str]], default: float = 0.0) -> float:
        for name in names:
            if not name:
                continue
            if name in row.index:
                return self._to_float(row.get(name), default)
            for col in row.index:
                if str(name) in str(col):
                    return self._to_float(row.get(col), default)
        return default

    def _text(self, row: pd.Series, names: Iterable[Optional[str]]) -> str:
        for name in names:
            if not name:
                continue
            if name in row.index and pd.notna(row.get(name)):
                return str(row.get(name)).strip()
            for col in row.index:
                if str(name) in str(col) and pd.notna(row.get(col)):
                    return str(row.get(col)).strip()
        return ""

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if pd.isna(value):
                return default
            if isinstance(value, str):
                value = value.replace("%", "").replace(",", "").strip()
                if value.endswith("亿"):
                    return float(value[:-1]) * 100000000
                if value.endswith("万"):
                    return float(value[:-1]) * 10000
            return float(value)
        except Exception:
            return default

    def _short_error(self, exc: Exception) -> str:
        text = str(exc)
        if "ProxyError" in text or "Unable to connect to proxy" in text:
            return "网络代理连接失败"
        if "RemoteDisconnected" in text:
            return "远端连接中断"
        if "Max retries exceeded" in text or "Connection" in text:
            return "网络连接失败"
        if "Expecting value" in text:
            return "接口返回为空或格式异常"
        if len(text) > 120:
            return text[:120] + "..."
        return text
