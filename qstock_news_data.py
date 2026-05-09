"""
新闻数据获取模块
使用akshare获取股票的最新新闻信息（替代qstock）
"""

import pandas as pd
import sys
import io
import json
import re
import warnings
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import quote
import akshare as ak
import requests

warnings.filterwarnings('ignore')

# 设置标准输出编码为UTF-8（仅在命令行环境，避免streamlit冲突）
def _setup_stdout_encoding():
    """仅在命令行环境设置标准输出编码"""
    if sys.platform == 'win32' and not hasattr(sys.stdout, '_original_stream'):
        try:
            # 检测是否正在streamlit脚本上下文中；仅安装streamlit不代表正在其中运行
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            if get_script_run_ctx() is not None:
                return
        except Exception:
            pass

        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='ignore')
        except:
            pass

_setup_stdout_encoding()


class QStockNewsDataFetcher:
    """新闻数据获取类（使用akshare作为数据源）"""
    
    def __init__(self):
        self.max_items = 30  # 最多获取的新闻数量
        self.available = True
        self.timeout = 8
        self.free_news_base_urls = [
            "https://orz.ai/api/v1/dailynews/",
            "https://newsapi.ws4.cn/api/v1/dailynews/",
        ]
        self.free_news_platforms = [
            ("eastmoney", "东方财富热榜"),
            ("sina_finance", "新浪财经热榜"),
            ("cls", "财联社热榜"),
            ("xueqiu", "雪球热榜"),
            ("wallstreetcn", "华尔街见闻热榜"),
        ]
        print("✓ 新闻数据获取器初始化成功（akshare + 免费备用源）")
    
    def get_stock_news(self, symbol):
        """
        获取股票的新闻数据
        
        Args:
            symbol: 股票代码（6位数字）
            
        Returns:
            dict: 包含新闻数据的字典
        """
        data = {
            "symbol": symbol,
            "news_data": None,
            "data_success": False,
            "source": "akshare+free_fallback"
        }
        
        if not self.available:
            data["error"] = "新闻数据获取器不可用"
            return data
        
        # 只支持中国股票
        if not self._is_chinese_stock(symbol):
            data["error"] = "新闻数据仅支持中国A股股票"
            return data
        
        try:
            # 获取新闻数据
            print(f"📰 正在获取 {symbol} 的最新新闻...")
            news_data = self._get_news_data(symbol)
            
            if news_data:
                data["news_data"] = news_data
                print(f"   ✓ 成功获取 {len(news_data.get('items', []))} 条新闻")
                data["data_success"] = True
                print("✅ 新闻数据获取完成")
            else:
                print("⚠️ 未能获取到新闻数据")
                
        except Exception as e:
            print(f"❌ 获取新闻数据失败: {e}")
            data["error"] = str(e)
        
        return data
    
    def _is_chinese_stock(self, symbol):
        """判断是否为中国股票"""
        return symbol.isdigit() and len(symbol) == 6
    
    def _get_news_data(self, symbol):
        """获取新闻数据（优先akshare，失败后使用免费热榜接口兜底）"""
        try:
            print(f"   使用 akshare 获取新闻...")
            
            news_items = []
            stock_name = self._get_stock_name(symbol)
            
            # 方法1: 尝试获取个股新闻（东方财富）
            try:
                # stock_news_em(symbol="600519") - 东方财富个股新闻
                df = ak.stock_news_em(symbol=symbol)
                
                if df is not None and not df.empty:
                    print(f"   ✓ 从东方财富获取到 {len(df)} 条新闻")
                    
                    # 处理DataFrame，提取新闻
                    for idx, row in df.head(self.max_items).iterrows():
                        item = {'source': '东方财富'}
                        
                        # 提取所有列
                        for col in df.columns:
                            value = row.get(col)
                            
                            # 跳过空值
                            if value is None or (isinstance(value, float) and pd.isna(value)):
                                continue
                            
                            # 保存字段
                            try:
                                item[col] = str(value)
                            except:
                                item[col] = "无法解析"
                        
                        if len(item) > 1:  # 如果有数据才添加
                            news_items.append(item)
            
            except Exception as e:
                print(f"   ⚠ 从东方财富获取失败: {e}")

            # 方法1备用: 直接请求东方财富公开搜索接口，绕开akshare和环境代理
            if not news_items:
                direct_items = self._get_eastmoney_search_direct(symbol, self.max_items)
                if direct_items:
                    news_items.extend(direct_items)

            if stock_name and len(news_items) < 5:
                direct_items = self._get_eastmoney_search_direct(
                    stock_name,
                    self.max_items - len(news_items),
                )
                if direct_items:
                    news_items.extend(direct_items)

            # 方法1备用: 新浪财经个股资讯网页，免费且不依赖akshare
            if not news_items or len(news_items) < 5:
                sina_page_items = self._get_sina_stock_news_page(
                    symbol,
                    stock_name,
                    self.max_items - len(news_items),
                )
                if sina_page_items:
                    news_items.extend(sina_page_items)
            
            # 方法2: 如果没有获取到，尝试获取新浪财经新闻
            if not news_items:
                try:
                    # 使用股票名称搜索新闻
                    if stock_name:
                        # stock_news_sina - 新浪财经新闻
                        try:
                            df = ak.stock_news_sina(symbol=stock_name)
                            if df is not None and not df.empty:
                                print(f"   ✓ 从新浪财经获取到 {len(df)} 条新闻")
                                
                                for idx, row in df.head(self.max_items).iterrows():
                                    item = {'source': '新浪财经'}
                                    
                                    for col in df.columns:
                                        value = row.get(col)
                                        if value is None or (isinstance(value, float) and pd.isna(value)):
                                            continue
                                        try:
                                            item[col] = str(value)
                                        except:
                                            item[col] = "无法解析"
                                    
                                    if len(item) > 1:
                                        news_items.append(item)
                        except:
                            pass
                
                except Exception as e:
                    print(f"   ⚠ 从新浪财经获取失败: {e}")
            
            # 方法3: 尝试获取财联社电报
            if not news_items or len(news_items) < 5:
                try:
                    if not hasattr(ak, "stock_news_cls"):
                        raise AttributeError("当前akshare版本不支持 stock_news_cls")

                    # stock_news_cls() - 财联社电报
                    df = ak.stock_news_cls()
                    
                    if df is not None and not df.empty:
                        # 筛选包含股票代码或名称的新闻
                        title_col = "标题" if "标题" in df.columns else None
                        content_col = "内容" if "内容" in df.columns else None
                        mask = pd.Series(False, index=df.index)
                        if title_col:
                            mask = mask | df[title_col].astype(str).str.contains(symbol, na=False)
                        if content_col:
                            mask = mask | df[content_col].astype(str).str.contains(symbol, na=False)
                        if stock_name:
                            if title_col:
                                mask = mask | df[title_col].astype(str).str.contains(stock_name, na=False)
                            if content_col:
                                mask = mask | df[content_col].astype(str).str.contains(stock_name, na=False)
                        df_filtered = df[mask]
                        
                        if not df_filtered.empty:
                            print(f"   ✓ 从财联社获取到 {len(df_filtered)} 条相关新闻")
                            
                            for idx, row in df_filtered.head(self.max_items - len(news_items)).iterrows():
                                item = {'source': '财联社'}
                                
                                for col in df_filtered.columns:
                                    value = row.get(col)
                                    if value is None or (isinstance(value, float) and pd.isna(value)):
                                        continue
                                    try:
                                        item[col] = str(value)
                                    except:
                                        item[col] = "无法解析"
                                
                                if len(item) > 1:
                                    news_items.append(item)
                
                except Exception as e:
                    print(f"   ⚠ 从财联社获取失败: {e}")

            # 方法4: 非akshare免费备用源，来自项目新闻流量接口
            if not news_items or len(news_items) < 5:
                remaining = self.max_items - len(news_items)
                fallback_items = self._get_free_hot_news_fallback(symbol, stock_name, remaining)
                if fallback_items:
                    news_items.extend(fallback_items)
            
            if not news_items:
                print(f"   未找到股票 {symbol} 的新闻")
                return None
            
            # 限制数量
            news_items = news_items[:self.max_items]
            
            return {
                "items": news_items,
                "count": len(news_items),
                "query_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "date_range": "最近新闻",
                "stock_name": stock_name or ""
            }
            
        except Exception as e:
            print(f"   获取新闻数据异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_stock_name(self, symbol: str) -> Optional[str]:
        """尽量获取股票名称，供新闻源按名称过滤。"""
        try:
            from data_source_manager import data_source_manager
            basic_info = data_source_manager.get_stock_basic_info(symbol)
            stock_name = (basic_info or {}).get("name")
            if stock_name and stock_name != "未知":
                print(f"   找到股票名称: {stock_name}")
                return str(stock_name)
        except Exception as e:
            print(f"   ⚠ 从数据源管理器获取股票名称失败: {e}")

        try:
            df = ak.stock_individual_info_em(symbol=symbol)
            if df is not None and not df.empty:
                match = df[df["item"] == "股票简称"]
                if not match.empty:
                    stock_name = str(match.iloc[0]["value"])
                    print(f"   找到股票名称: {stock_name}")
                    return stock_name
        except Exception as e:
            print(f"   ⚠ 从东方财富个股信息获取股票名称失败: {e}")

        try:
            df_info = ak.stock_zh_a_spot_em()
            if df_info is not None and not df_info.empty:
                match = df_info[df_info["代码"].astype(str) == symbol]
                if not match.empty:
                    stock_name = str(match.iloc[0]["名称"])
                    print(f"   找到股票名称: {stock_name}")
                    return stock_name
        except Exception as e:
            print(f"   ⚠ 从A股列表获取股票名称失败: {e}")

        return None

    def _get_eastmoney_search_direct(self, keyword: str, limit: int) -> List[Dict[str, str]]:
        """直接调用东方财富公开搜索接口，作为akshare失败时的个股新闻备用源。"""
        if not keyword or limit <= 0:
            return []

        print(f"   使用东方财富搜索备用源获取新闻: {keyword}")
        callback = f"jQuery351_{int(time.time() * 1000)}"
        inner_param = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": min(max(limit, 10), 30),
                    "preTag": "<em>",
                    "postTag": "</em>",
                }
            },
        }
        params = {
            "cb": callback,
            "param": json.dumps(inner_param, ensure_ascii=False),
            "_": str(int(time.time() * 1000)),
        }

        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get(
                "https://search-api-web.eastmoney.com/search/jsonp",
                params=params,
                timeout=self.timeout,
                headers={
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Referer": f"https://so.eastmoney.com/news/s?keyword={quote(keyword)}",
                    "Cookie": (
                        "qgqp_b_id=652bf4c98a74e210088f372a17d4e27b; "
                        "st_inirUrl=https%3A%2F%2Fso.eastmoney.com%2Fnews%2Fs"
                    ),
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    ),
                },
            )
            response.raise_for_status()

            match = re.search(r"^[^(]+\((.*)\)\s*$", response.text, flags=re.S)
            if not match:
                raise ValueError("东方财富搜索返回格式无法解析")

            payload = json.loads(match.group(1))
            rows = payload.get("result", {}).get("cmsArticleWebOld", []) or []

            items = []
            for row in rows[:limit]:
                code = row.get("code") or ""
                title = self._clean_html_text(row.get("title") or "")
                content = self._clean_html_text(row.get("content") or "")
                items.append({
                    "source": "东方财富搜索备用",
                    "title": title,
                    "content": content,
                    "time": str(row.get("date") or ""),
                    "url": f"http://finance.eastmoney.com/a/{code}.html" if code else "",
                    "关键词": keyword,
                })

            if items:
                print(f"   ✓ 从东方财富搜索备用源获取到 {len(items)} 条新闻")
            return items
        except Exception as e:
            print(f"   ⚠ 东方财富搜索备用源获取失败: {e}")
            return []

    def _clean_html_text(self, text: str) -> str:
        """清理搜索接口返回的高亮标签和空白。"""
        text = re.sub(r"</?em>", "", str(text))
        text = text.replace("\u3000", "").replace("\r\n", " ")
        return re.sub(r"\s+", " ", text).strip()

    def _get_sina_stock_news_page(
        self,
        symbol: str,
        stock_name: Optional[str],
        limit: int,
    ) -> List[Dict[str, str]]:
        """抓取新浪财经个股资讯页，作为免费网页备用源。"""
        if limit <= 0:
            return []

        market = self._get_market_prefix(symbol)
        url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{market}{symbol}.phtml"
        keywords = [symbol]
        if stock_name:
            keywords.append(stock_name)

        print("   使用新浪财经网页备用源获取新闻...")
        try:
            from bs4 import BeautifulSoup

            session = requests.Session()
            session.trust_env = False
            response = session.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "gbk"

            soup = BeautifulSoup(response.text, "html.parser")
            items = []
            seen = set()

            for link in soup.select("a[href]"):
                title = self._clean_html_text(link.get_text(" ", strip=True))
                href = link.get("href") or ""
                if not title or href in seen:
                    continue
                if title in {symbol, stock_name}:
                    continue
                if stock_name and re.fullmatch(
                    rf"{re.escape(stock_name)}\s*\({symbol}\.(SZ|SH|BJ)\)",
                    title,
                ):
                    continue
                if "finance.sina.com.cn" not in href and "stock.finance.sina.com.cn" not in href:
                    continue
                if not any(keyword and keyword in title for keyword in keywords):
                    continue

                seen.add(href)
                date_match = re.search(r"/(\d{4})-(\d{2})-(\d{2})/", href)
                publish_time = "-".join(date_match.groups()) if date_match else ""
                items.append({
                    "source": "新浪财经网页备用",
                    "title": title,
                    "content": "",
                    "time": publish_time,
                    "url": href,
                })

                if len(items) >= limit:
                    break

            if items:
                print(f"   ✓ 从新浪财经网页备用源获取到 {len(items)} 条新闻")
            return items
        except Exception as e:
            print(f"   ⚠ 新浪财经网页备用源获取失败: {e}")
            return []

    def _get_market_prefix(self, symbol: str) -> str:
        """转换为新浪财经股票代码前缀。"""
        if symbol.startswith("6"):
            return "sh"
        if symbol.startswith(("8", "4", "9")):
            return "bj"
        return "sz"

    def _get_free_hot_news_fallback(
        self,
        symbol: str,
        stock_name: Optional[str],
        limit: int,
    ) -> List[Dict[str, str]]:
        """从免费财经热榜接口获取备用新闻，并按股票代码/名称过滤。"""
        if limit <= 0:
            return []

        keywords = [symbol]
        if stock_name:
            keywords.append(stock_name)

        results = []
        seen = set()
        print("   使用免费备用新闻源获取新闻...")

        for base_url in self.free_news_base_urls:
            if len(results) >= limit:
                break

            for platform, platform_name in self.free_news_platforms:
                if len(results) >= limit:
                    break

                try:
                    payload = self._request_free_news_platform(base_url, platform)
                    for raw_item in payload:
                        item = self._normalize_free_news_item(raw_item, platform_name)
                        title = item.get("title", "")
                        content = item.get("content", "")
                        text = f"{title} {content}"

                        if not any(keyword and keyword in text for keyword in keywords):
                            continue

                        dedupe_key = (title, item.get("url", ""))
                        if dedupe_key in seen:
                            continue

                        seen.add(dedupe_key)
                        results.append(item)

                        if len(results) >= limit:
                            break
                except Exception as e:
                    print(f"   ⚠ 备用源 {platform_name} 获取失败: {e}")

        if results:
            print(f"   ✓ 从免费备用源获取到 {len(results)} 条相关新闻")
        return results

    def _request_free_news_platform(self, base_url: str, platform: str) -> List[Dict]:
        """请求免费新闻热榜接口；忽略环境代理，避免本机代理异常导致失败。"""
        session = requests.Session()
        session.trust_env = False
        response = session.get(
            base_url,
            params={"platform": platform},
            timeout=self.timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        data = response.json()
        status = str(data.get("status", ""))
        if status not in {"200", "0"}:
            raise ValueError(data.get("msg") or data.get("message") or "接口返回失败")
        news_list = data.get("data", [])
        return news_list if isinstance(news_list, list) else []

    def _normalize_free_news_item(self, raw_item: Dict, platform_name: str) -> Dict[str, str]:
        """统一免费热榜接口字段，供AI分析和展示复用。"""
        title = (
            raw_item.get("title")
            or raw_item.get("word")
            or raw_item.get("name")
            or raw_item.get("desc")
            or ""
        )
        content = (
            raw_item.get("content")
            or raw_item.get("summary")
            or raw_item.get("desc")
            or raw_item.get("abstract")
            or ""
        )
        publish_time = (
            raw_item.get("publish_time")
            or raw_item.get("time")
            or raw_item.get("datetime")
            or raw_item.get("date")
            or ""
        )

        return {
            "source": platform_name,
            "title": str(title),
            "content": str(content),
            "url": str(raw_item.get("url") or raw_item.get("link") or raw_item.get("mobileUrl") or ""),
            "time": str(publish_time),
        }
    
    def format_news_for_ai(self, data):
        """
        将新闻数据格式化为适合AI阅读的文本
        """
        if not data or not data.get("data_success"):
            return "未能获取新闻数据"
        
        text_parts = []
        
        # 新闻数据
        if data.get("news_data"):
            news_data = data["news_data"]
            text_parts.append(f"""
【最新新闻 - akshare/免费备用源】
查询时间：{news_data.get('query_time', 'N/A')}
时间范围：{news_data.get('date_range', 'N/A')}
新闻数量：{news_data.get('count', 0)}条

""")
            
            for idx, item in enumerate(news_data.get('items', []), 1):
                text_parts.append(f"新闻 {idx}:")
                
                # 优先显示的字段
                priority_fields = ['title', 'date', 'time', 'source', 'content', 'url']
                
                # 先显示优先字段
                for field in priority_fields:
                    if field in item:
                        value = item[field]
                        # 限制content长度
                        if field == 'content' and len(str(value)) > 500:
                            value = str(value)[:500] + "..."
                        text_parts.append(f"  {field}: {value}")
                
                # 再显示其他字段
                for key, value in item.items():
                    if key not in priority_fields and key != 'source':
                        # 跳过过长的字段
                        if len(str(value)) > 300:
                            value = str(value)[:300] + "..."
                        text_parts.append(f"  {key}: {value}")
                
                text_parts.append("")  # 空行分隔
        
        return "\n".join(text_parts)


# 测试函数
if __name__ == "__main__":
    print("测试新闻数据获取（akshare数据源）...")
    print("="*60)
    
    fetcher = QStockNewsDataFetcher()
    
    if not fetcher.available:
        print("❌ 新闻数据获取器不可用")
        sys.exit(1)
    
    # 测试股票
    test_symbols = ["000001", "600519"]  # 平安银行、贵州茅台
    
    for symbol in test_symbols:
        print(f"\n{'='*60}")
        print(f"正在测试股票: {symbol}")
        print(f"{'='*60}\n")
        
        data = fetcher.get_stock_news(symbol)
        
        if data.get("data_success"):
            print("\n" + "="*60)
            print("新闻数据获取成功！")
            print("="*60)
            
            formatted_text = fetcher.format_news_for_ai(data)
            print(formatted_text)
        else:
            print(f"\n获取失败: {data.get('error', '未知错误')}")
        
        print("\n")

