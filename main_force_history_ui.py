#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主力选股批量分析历史记录UI模块
"""

import streamlit as st
import re
from main_force_batch_db import batch_db


def _build_stock_rows(history_records):
    """将批次历史展开为单只股票记录"""
    rows = []
    for record in history_records:
        analysis_time = record.get('analysis_date', '')
        batch_id = record.get('id')
        results = record.get('results', []) or []
        for result in results:
            stock_info = result.get('stock_info', {}) or {}
            final_decision = result.get('final_decision', {}) or {}
            symbol = str(result.get('symbol') or stock_info.get('symbol') or '')
            name = str(stock_info.get('name') or stock_info.get('股票名称') or '')
            data_cycle = (
                result.get('period')
                or stock_info.get('period')
                or final_decision.get('investment_period')
                or final_decision.get('data_cycle')
                or '1y'
            )
            rating = final_decision.get('rating') or final_decision.get('investment_rating') or '未知'
            rows.append({
                'batch_id': batch_id,
                'symbol': symbol,
                'name': name,
                'analysis_time': analysis_time,
                'data_cycle': str(data_cycle),
                'rating': str(rating),
                'success': bool(result.get('success', False)),
                'result': result,
                'record': record
            })
    rows.sort(key=lambda x: x.get('analysis_time', ''), reverse=True)
    return rows


def _add_to_monitor_from_result(result):
    """根据分析结果加入监测列表"""
    stock_info = result.get('stock_info', {}) or {}
    final_decision = result.get('final_decision', {}) or {}
    symbol = str(result.get('symbol') or stock_info.get('symbol') or '')
    name = str(stock_info.get('name') or stock_info.get('股票名称') or '')
    rating = final_decision.get('rating', '未知')

    entry_range = final_decision.get('entry_range', '')
    entry_min, entry_max = None, None
    if entry_range and isinstance(entry_range, str) and "-" in entry_range:
        try:
            parts = entry_range.split("-")
            entry_min = float(parts[0].strip())
            entry_max = float(parts[1].strip())
        except Exception:
            pass

    take_profit = None
    take_profit_str = final_decision.get('take_profit', '')
    if take_profit_str:
        try:
            numbers = re.findall(r'\d+\.?\d*', str(take_profit_str))
            if numbers:
                take_profit = float(numbers[0])
        except Exception:
            pass

    stop_loss = None
    stop_loss_str = final_decision.get('stop_loss', '')
    if stop_loss_str:
        try:
            numbers = re.findall(r'\d+\.?\d*', str(stop_loss_str))
            if numbers:
                stop_loss = float(numbers[0])
        except Exception:
            pass

    from monitor_db import monitor_db

    entry_range_dict = {}
    if entry_min and entry_max:
        entry_range_dict = {"min": entry_min, "max": entry_max}

    monitor_db.add_monitored_stock(
        symbol=symbol,
        name=name,
        rating=rating,
        entry_range=entry_range_dict if entry_range_dict else None,
        take_profit=take_profit,
        stop_loss=stop_loss
    )


def display_batch_history():
    """显示批量分析历史记录"""
    
    # 返回按钮
    col_back, col_stats = st.columns([1, 4])
    with col_back:
        if st.button("← 返回主页"):
            st.session_state.main_force_view_history = False
            st.rerun()
    
    st.markdown("## 📚 主力选股批量分析历史记录")
    st.markdown("---")
    
    # 获取统计信息
    try:
        stats = batch_db.get_statistics()
        
        # 显示统计指标
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("总记录数", f"{stats['total_records']} 条")
        with col2:
            st.metric("分析股票总数", f"{stats['total_stocks_analyzed']} 只")
        with col3:
            st.metric("成功分析", f"{stats['total_success']} 只")
        with col4:
            st.metric("成功率", f"{stats['success_rate']}%")
        with col5:
            st.metric("平均耗时", f"{stats['average_time']:.1f}秒")
        
        st.markdown("---")
        
    except Exception as e:
        st.warning(f"⚠️ 无法获取统计信息: {str(e)}")
    
    # 获取历史记录
    try:
        history_records = batch_db.get_all_history(limit=50)

        if not history_records:
            st.info("📝 暂无批量分析历史记录")
            return

        stock_rows = _build_stock_rows(history_records)
        st.markdown(f"### 📋 共找到 {len(stock_rows)} 条分析记录")

        action_col1, action_col2 = st.columns([1, 5])
        with action_col1:
            if st.button("🗑️ 清空历史记录", key="clear_all_history_btn", type="secondary"):
                deleted_count = batch_db.clear_all_history()
                st.success(f"✅ 已清空历史记录（删除 {deleted_count} 条批次）")
                st.rerun()

        st.markdown("---")

        # 表头
        h1, h2, h3, h4, h5, h6 = st.columns([1.2, 1.8, 2.2, 1.0, 1.1, 2.2])
        h1.markdown("**股票代码**")
        h2.markdown("**股票名称**")
        h3.markdown("**分析时间**")
        h4.markdown("**数据周期**")
        h5.markdown("**投资评级**")
        h6.markdown("**操作**")
        st.markdown("---")

        for idx, row in enumerate(stock_rows):
            c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1.8, 2.2, 1.0, 1.1, 2.2])
            c1.write(row.get('symbol') or "N/A")
            c2.write(row.get('name') or "N/A")
            c3.write(row.get('analysis_time') or "N/A")
            c4.write(row.get('data_cycle') or "N/A")
            c5.write(row.get('rating') or "N/A")

            op1, op2, op3 = c6.columns([1, 1, 1])

            with op1:
                if st.button("详情", key=f"detail_{row['batch_id']}_{idx}"):
                    st.session_state[f"show_detail_{row['batch_id']}_{idx}"] = True

            with op2:
                if st.button("监测", key=f"monitor_history_{row['batch_id']}_{idx}"):
                    try:
                        _add_to_monitor_from_result(row['result'])
                        st.success(f"✅ {row.get('symbol', '')} 已加入监测列表")
                    except Exception as e:
                        st.error(f"❌ 加入监测失败: {str(e)}")

            with op3:
                if st.button("删除", key=f"delete_history_{row['batch_id']}_{idx}"):
                    if batch_db.delete_stock_record(row['batch_id'], row['symbol']):
                        st.success("✅ 删除成功")
                        st.rerun()
                    else:
                        st.error("❌ 删除失败")

            if st.session_state.get(f"show_detail_{row['batch_id']}_{idx}", False):
                result = row.get('result', {})
                final_decision = result.get('final_decision', {}) or {}
                stock_info = result.get('stock_info', {}) or {}
                with st.expander(f"📊 {row.get('symbol', '')} - {row.get('name', '')} 详情", expanded=True):
                    d1, d2, d3 = st.columns(3)
                    d1.metric("投资评级", final_decision.get('rating', 'N/A'))
                    d2.metric("信心度", final_decision.get('confidence_level', 'N/A'))
                    d3.metric("目标价", final_decision.get('target_price', 'N/A'))

                    d4, d5 = st.columns(2)
                    d4.metric("进场区间", final_decision.get('entry_range', 'N/A'))
                    d5.metric("止盈/止损", f"{final_decision.get('take_profit', 'N/A')} / {final_decision.get('stop_loss', 'N/A')}")

                    st.markdown("**投资建议**")
                    st.info(final_decision.get('operation_advice', final_decision.get('investment_advice', '暂无建议')))

                    if not result.get('success', False):
                        st.warning(f"分析失败原因: {result.get('error', '未知错误')}")

                    if stock_info:
                        st.markdown("**股票信息**")
                        st.json(stock_info)

                st.markdown("---")
    
    except Exception as e:
        st.error(f"❌ 获取历史记录失败: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

