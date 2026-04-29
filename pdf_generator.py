#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF报告生成器
只生成PDF格式的完整分析报告
"""

import streamlit as st
import base64
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import tempfile
import os
from xml.sax.saxutils import escape

def register_chinese_fonts():
    """注册中文字体 - 支持Windows和Linux系统"""
    try:
        # 检查是否已经注册过
        if 'ChineseFont' in pdfmetrics.getRegisteredFontNames():
            return 'ChineseFont'
        
        # Windows系统字体路径
        windows_font_paths = [
            'C:/Windows/Fonts/simsun.ttc',  # 宋体
            'C:/Windows/Fonts/simhei.ttf',  # 黑体
            'C:/Windows/Fonts/msyh.ttc',    # 微软雅黑
            'C:/Windows/Fonts/msyh.ttf',    # 微软雅黑（TTF格式）
        ]
        
        # Linux系统字体路径（Docker环境）
        linux_font_paths = [
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',  # 文泉驿正黑
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',  # 文泉驿微米黑
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',  # Noto Sans CJK
            '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',  # Noto Serif CJK
            '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',  # Droid字体
        ]
        
        # 合并所有可能的字体路径
        all_font_paths = windows_font_paths + linux_font_paths
        
        # 尝试注册字体
        for font_path in all_font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                    print(f"✅ 成功注册中文字体: {font_path}")
                    return 'ChineseFont'
                except Exception as e:
                    print(f"⚠️ 尝试注册字体 {font_path} 失败: {e}")
                    continue
        
        # 如果没有找到中文字体，打印警告并使用默认字体
        print("⚠️ 警告：未找到中文字体，PDF中文可能显示为方框")
        print("建议：在Docker中安装中文字体包")
        return 'Helvetica'
    except Exception as e:
        print(f"❌ 注册中文字体时出错: {e}")
        return 'Helvetica'

def create_pdf_report(stock_info, agents_results, discussion_result, final_decision):
    """创建PDF格式的分析报告"""
    
    # 注册中文字体
    chinese_font = register_chinese_fonts()
    
    # 创建内存中的PDF文档
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # 获取样式
    styles = getSampleStyleSheet()
    
    # 创建自定义样式
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=chinese_font,
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=chinese_font,
        fontSize=16,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.darkblue
    )
    
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontName=chinese_font,
        fontSize=14,
        spaceAfter=8,
        spaceBefore=12,
        textColor=colors.darkgreen
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=chinese_font,
        fontSize=11,
        spaceAfter=6,
        alignment=TA_JUSTIFY
    )

    # 表格单元格样式：开启自动换行，避免长文本被截断
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=normal_style,
        alignment=TA_LEFT,
        spaceAfter=0,
        leading=14,
        wordWrap='CJK'
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=table_cell_style,
        fontName=chinese_font,
        textColor=colors.whitesmoke
    )

    def as_cell_paragraph(value, is_header=False):
        text = "N/A" if value is None else str(value)
        text = escape(text).replace("\n", "<br/>")
        return Paragraph(text, table_header_style if is_header else table_cell_style)
    
    # 开始构建PDF内容
    story = []
    
    # 标题
    current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    story.append(Paragraph("AI股票分析报告", title_style))
    story.append(Paragraph(f"生成时间: {current_time}", normal_style))
    story.append(Spacer(1, 20))
    
    # 股票基本信息
    story.append(Paragraph("股票基本信息", heading_style))
    
    # 创建股票信息表格
    stock_data_raw = [
        ['项目', '值'],
        ['股票代码', stock_info.get('symbol', 'N/A')],
        ['股票名称', stock_info.get('name', 'N/A')],
        ['当前价格', str(stock_info.get('current_price', 'N/A'))],
        ['涨跌幅', f"{stock_info.get('change_percent', 'N/A')}%"],
        ['市盈率(PE)', str(stock_info.get('pe_ratio', 'N/A'))],
        ['市净率(PB)', str(stock_info.get('pb_ratio', 'N/A'))],
        ['市值', str(stock_info.get('market_cap', 'N/A'))],
        ['市场', stock_info.get('market', 'N/A')],
        ['交易所', stock_info.get('exchange', 'N/A')]
    ]
    stock_data = [[as_cell_paragraph(col, i == 0) for col in row] for i, row in enumerate(stock_data_raw)]
    
    stock_table = Table(stock_data, colWidths=[2*inch, 3*inch])
    stock_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(stock_table)
    story.append(Spacer(1, 20))
    
    # 各分析师分析结果
    story.append(Paragraph("AI分析师团队分析", heading_style))
    
    agent_names = {
        'technical': '技术分析师',
        'fundamental': '基本面分析师',
        'fund_flow': '资金面分析师',
        'risk_management': '风险管理师',
        'market_sentiment': '市场情绪分析师'
    }
    
    for agent_key, agent_name in agent_names.items():
        if agent_key in agents_results:
            story.append(Paragraph(f"{agent_name}分析", subheading_style))
            
            agent_result = agents_results[agent_key]
            if isinstance(agent_result, dict):
                analysis_text = agent_result.get('analysis', '暂无分析')
            else:
                analysis_text = str(agent_result)
            
            # 处理长文本，确保在PDF中正确显示
            analysis_text = analysis_text.replace('\n', '<br/>')
            story.append(Paragraph(analysis_text, normal_style))
            story.append(Spacer(1, 12))
    
    # 团队讨论
    story.append(Paragraph("团队综合讨论", heading_style))
    discussion_text = str(discussion_result).replace('\n', '<br/>')
    story.append(Paragraph(discussion_text, normal_style))
    story.append(Spacer(1, 20))
    
    # 最终投资决策
    story.append(Paragraph("最终投资决策", heading_style))
    
    if isinstance(final_decision, dict) and "decision_text" not in final_decision:
        # JSON格式的决策
        decision_data_raw = [
            ['项目', '内容'],
            ['投资评级', final_decision.get('rating', '未知')],
            ['目标价位', str(final_decision.get('target_price', 'N/A'))],
            ['操作建议', final_decision.get('operation_advice', '暂无建议')],
            ['进场区间', final_decision.get('entry_range', 'N/A')],
            ['止盈位', str(final_decision.get('take_profit', 'N/A'))],
            ['止损位', str(final_decision.get('stop_loss', 'N/A'))],
            ['持有周期', final_decision.get('holding_period', 'N/A')],
            ['仓位建议', final_decision.get('position_size', 'N/A')],
            ['信心度', f"{final_decision.get('confidence_level', 'N/A')}/10"],
            ['风险提示', final_decision.get('risk_warning', '无')]
        ]
        decision_data = [[as_cell_paragraph(col, i == 0) for col in row] for i, row in enumerate(decision_data_raw)]
        
        decision_table = Table(decision_data, colWidths=[1.5*inch, 3.5*inch])
        decision_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(decision_table)
    else:
        # 文本格式的决策
        decision_text = final_decision.get('decision_text', str(final_decision))
        decision_text = decision_text.replace('\n', '<br/>')
        story.append(Paragraph(decision_text, normal_style))
    
    story.append(Spacer(1, 20))
    
    # 免责声明
    story.append(Paragraph("免责声明", heading_style))
    disclaimer_text = """
    本报告由AI系统生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。
    请在做出投资决策前咨询专业的投资顾问。本系统不对任何投资损失承担责任。
    """
    story.append(Paragraph(disclaimer_text, normal_style))
    
    # 生成PDF
    doc.build(story)
    
    # 获取PDF内容
    pdf_content = buffer.getvalue()
    buffer.close()
    
    return pdf_content

def create_download_link(pdf_content, filename):
    """创建PDF下载链接"""
    b64 = base64.b64encode(pdf_content).decode()
    href = f'<a href="data:application/pdf;base64,{b64}" download="{filename}" style="display: inline-block; padding: 15px 30px; background-color: #e74c3c; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; margin: 10px;">📄 下载PDF报告</a>'
    return href

def generate_markdown_report(stock_info, agents_results, discussion_result, final_decision):
    """生成Markdown格式的分析报告"""
    
    # 获取当前时间
    current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    
    markdown_content = f"""
# AI股票分析报告

**生成时间**: {current_time}

---

## 📊 股票基本信息

| 项目 | 值 |
|------|-----|
| **股票代码** | {stock_info.get('symbol', 'N/A')} |
| **股票名称** | {stock_info.get('name', 'N/A')} |
| **当前价格** | {stock_info.get('current_price', 'N/A')} |
| **涨跌幅** | {stock_info.get('change_percent', 'N/A')}% |
| **市盈率(PE)** | {stock_info.get('pe_ratio', 'N/A')} |
| **市净率(PB)** | {stock_info.get('pb_ratio', 'N/A')} |
| **市值** | {stock_info.get('market_cap', 'N/A')} |
| **市场** | {stock_info.get('market', 'N/A')} |
| **交易所** | {stock_info.get('exchange', 'N/A')} |

---

## 🔍 各分析师详细分析

"""

    # 添加各分析师的分析结果
    agent_names = {
        'technical': '📈 技术分析师',
        'fundamental': '📊 基本面分析师',
        'fund_flow': '💰 资金面分析师',
        'risk_management': '⚠️ 风险管理师',
        'market_sentiment': '📈 市场情绪分析师'
    }
    
    for agent_key, agent_name in agent_names.items():
        if agent_key in agents_results:
            agent_result = agents_results[agent_key]
            if isinstance(agent_result, dict):
                analysis_text = agent_result.get('analysis', '暂无分析')
            else:
                analysis_text = str(agent_result)
            
            markdown_content += f"""
### {agent_name}

{analysis_text}

---

"""

    # 添加团队讨论结果
    markdown_content += f"""
## 🤝 团队综合讨论

{discussion_result}

---

## 📋 最终投资决策

"""
    
    # 处理最终决策的显示
    if isinstance(final_decision, dict) and "decision_text" not in final_decision:
        # JSON格式的决策
        markdown_content += f"""
**投资评级**: {final_decision.get('rating', '未知')}

**目标价位**: {final_decision.get('target_price', 'N/A')}

**操作建议**: {final_decision.get('operation_advice', '暂无建议')}

**进场区间**: {final_decision.get('entry_range', 'N/A')}

**止盈位**: {final_decision.get('take_profit', 'N/A')}

**止损位**: {final_decision.get('stop_loss', 'N/A')}

**持有周期**: {final_decision.get('holding_period', 'N/A')}

**仓位建议**: {final_decision.get('position_size', 'N/A')}

**信心度**: {final_decision.get('confidence_level', 'N/A')}/10

**风险提示**: {final_decision.get('risk_warning', '无')}
"""
    else:
        # 文本格式的决策
        decision_text = final_decision.get('decision_text', str(final_decision))
        markdown_content += decision_text

    markdown_content += """

---

## 📝 免责声明

本报告由AI系统生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。请在做出投资决策前咨询专业的投资顾问。

---

*报告生成时间: {current_time}*
*AI股票分析系统 v1.0*
"""

    return markdown_content

def create_markdown_download_link(markdown_content, filename):
    """创建Markdown下载链接"""
    b64 = base64.b64encode(markdown_content.encode()).decode()
    href = f'<a href="data:text/markdown;base64,{b64}" download="{filename}" style="display: inline-block; padding: 15px 30px; background-color: #9b59b6; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; margin: 10px;">📝 下载Markdown报告</a>'
    return href

def display_pdf_export_section(stock_info, agents_results, discussion_result, final_decision):
    """显示PDF导出区域"""
    
    st.markdown("---")
    st.markdown("## 📄 导出分析报告")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # 生成PDF报告按钮（使用股票代码作为key的一部分，确保唯一性）
        pdf_button_key = f"pdf_btn_{stock_info.get('symbol', 'unknown')}"
        markdown_button_key = f"markdown_btn_{stock_info.get('symbol', 'unknown')}"
        
        # 生成PDF报告按钮
        if st.button("📄 生成并下载PDF报告", type="primary", width='content', key=pdf_button_key):
            with st.spinner("正在生成PDF报告..."):
                try:
                    # 生成PDF内容
                    pdf_content = create_pdf_report(stock_info, agents_results, discussion_result, final_decision)
                    
                    # 生成文件名
                    stock_symbol = stock_info.get('symbol', 'unknown')
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"股票分析报告_{stock_symbol}_{timestamp}.pdf"
                    
                    st.success("✅ PDF报告生成成功！")
                    st.balloons()
                    
                    # 显示下载链接
                    st.markdown("### 📄 报告下载")
                    
                    download_link = create_download_link(pdf_content, filename)
                    st.markdown(f"""
                    <div style="text-align: center; margin: 20px 0;">
                        {download_link}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.info("💡 提示：点击上方按钮即可下载PDF格式的完整分析报告")
                    
                except Exception as e:
                    st.error(f"❌ 生成PDF报告时出错: {str(e)}")
                    import traceback
                    st.error(f"详细错误信息: {traceback.format_exc()}")
        
        # 生成Markdown报告按钮
        if st.button("📝 生成并下载Markdown报告", type="secondary", width='content', key=markdown_button_key):
            with st.spinner("正在生成Markdown报告..."):
                try:
                    # 生成Markdown内容
                    markdown_content = generate_markdown_report(stock_info, agents_results, discussion_result, final_decision)
                    
                    # 生成文件名
                    stock_symbol = stock_info.get('symbol', 'unknown')
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"股票分析报告_{stock_symbol}_{timestamp}.md"
                    
                    st.success("✅ Markdown报告生成成功！")
                    st.balloons()
                    
                    # 显示下载链接
                    st.markdown("### 📄 报告下载")
                    
                    download_link = create_markdown_download_link(markdown_content, filename)
                    st.markdown(f"""
                    <div style="text-align: center; margin: 20px 0;">
                        {download_link}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.info("💡 提示：点击上方按钮即可下载Markdown格式的完整分析报告")
                    
                except Exception as e:
                    st.error(f"❌ 生成Markdown报告时出错: {str(e)}")
                    import traceback
                    st.error(f"详细错误信息: {traceback.format_exc()}")

