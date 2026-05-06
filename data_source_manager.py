"""
数据源管理器
实现akshare和tushare的自动切换机制
"""

import os
import json
import urllib.parse
import urllib.request
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class DataSourceManager:
    """数据源管理器 - 实现多数据源自动切换"""
    
    def __init__(self):
        self.tushare_token = os.getenv('TUSHARE_TOKEN', '')
        self.tushare_available = False
        self.tushare_api = None
        self.default_hist_priority = ["akshare", "eastmoney", "tushare"]
        self.default_realtime_priority = ["akshare", "eastmoney", "tencent", "tushare"]
        
        # 初始化tushare
        if self.tushare_token:
            try:
                import tushare as ts
                ts.set_token(self.tushare_token)
                self.tushare_api = ts.pro_api()
                self.tushare_available = True
                print("✅ Tushare数据源初始化成功")
            except Exception as e:
                print(f"⚠️ Tushare数据源初始化失败: {e}")
                self.tushare_available = False
        else:
            print("ℹ️ 未配置Tushare Token，将仅使用Akshare数据源")

        self.hist_source_priority = self._parse_source_priority(
            env_var_name="STOCK_HIST_SOURCE_PRIORITY",
            allowed_sources=self.default_hist_priority,
            default_priority=self.default_hist_priority
        )
        self.realtime_source_priority = self._parse_source_priority(
            env_var_name="STOCK_REALTIME_SOURCE_PRIORITY",
            allowed_sources=self.default_realtime_priority,
            default_priority=self.default_realtime_priority
        )

        print(f"ℹ️ 历史行情数据源优先级: {self.hist_source_priority}")
        print(f"ℹ️ 实时行情数据源优先级: {self.realtime_source_priority}")
    
    def get_stock_hist_data(self, symbol, start_date=None, end_date=None, adjust='qfq'):
        """
        获取股票历史数据（优先akshare，失败时自动切换到东方财富Web/tushare）
        
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期（格式：'20240101'或'2024-01-01'）
            end_date: 结束日期
            adjust: 复权类型（'qfq'前复权, 'hfq'后复权, ''不复权）
            
        Returns:
            DataFrame: 包含日期、开盘、收盘、最高、最低、成交量等列
        """
        # 标准化日期格式
        if start_date:
            start_date = start_date.replace('-', '')
        if end_date:
            end_date = end_date.replace('-', '')
        else:
            end_date = datetime.now().strftime('%Y%m%d')
        
        for source in self.hist_source_priority:
            df = self._fetch_hist_data_by_source(source, symbol, start_date, end_date, adjust)
            if df is not None and not df.empty:
                return df
        
        # 所有数据源都失败
        print("❌ 所有数据源均获取失败")
        return None
    
    def get_stock_basic_info(self, symbol):
        """
        获取股票基本信息（优先akshare，失败时使用tushare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票基本信息
        """
        info = {
            "symbol": symbol,
            "name": "未知",
            "industry": "未知",
            "market": "未知"
        }
        
        # 优先使用akshare
        try:
            import akshare as ak
            print(f"[Akshare] 正在获取 {symbol} 的基本信息...")
            
            stock_info = ak.stock_individual_info_em(symbol=symbol)
            if stock_info is not None and not stock_info.empty:
                for _, row in stock_info.iterrows():
                    key = row['item']
                    value = row['value']
                    
                    if key == '股票简称':
                        info['name'] = value
                    elif key == '所处行业':
                        info['industry'] = value
                    elif key == '上市时间':
                        info['list_date'] = value
                    elif key == '总市值':
                        info['market_cap'] = value
                    elif key == '流通市值':
                        info['circulating_market_cap'] = value
                
                print(f"[Akshare] ✅ 成功获取基本信息")
                return info
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")
        
        # akshare失败，尝试tushare
        if self.tushare_available:
            try:
                print(f"[Tushare] 正在获取 {symbol} 的基本信息（备用数据源）...")
                
                ts_code = self._convert_to_ts_code(symbol)
                df = self.tushare_api.stock_basic(
                    ts_code=ts_code,
                    fields='ts_code,name,area,industry,market,list_date'
                )
                
                if df is not None and not df.empty:
                    info['name'] = df.iloc[0]['name']
                    info['industry'] = df.iloc[0]['industry']
                    info['market'] = df.iloc[0]['market']
                    info['list_date'] = df.iloc[0]['list_date']
                    
                    print(f"[Tushare] ✅ 成功获取基本信息")
                    return info
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")
        
        return info
    
    def get_realtime_quotes(self, symbol):
        """
        获取实时行情数据（优先akshare，失败时自动切换到东方财富Web/腾讯/tushare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        
        for source in self.realtime_source_priority:
            quotes = self._fetch_realtime_quotes_by_source(source, symbol)
            if quotes:
                return quotes
        
        return quotes

    def _parse_source_priority(self, env_var_name, allowed_sources, default_priority):
        """
        解析环境变量中的数据源优先级配置（逗号分隔）
        """
        raw = os.getenv(env_var_name, "").strip()
        if not raw:
            return list(default_priority)

        parsed = []
        for item in raw.split(","):
            source = item.strip().lower()
            if source and source in allowed_sources and source not in parsed:
                parsed.append(source)
            elif source and source not in allowed_sources:
                print(f"⚠️ 环境变量 {env_var_name} 中存在未知数据源: {source}，将忽略")

        if not parsed:
            print(f"⚠️ 环境变量 {env_var_name} 未解析出有效数据源，使用默认顺序")
            return list(default_priority)

        return parsed

    def _fetch_hist_data_by_source(self, source, symbol, start_date, end_date, adjust):
        """
        按指定数据源获取历史行情
        """
        if source == "akshare":
            try:
                import akshare as ak
                print(f"[Akshare] 正在获取 {symbol} 的历史数据...")
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust
                )
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        "日期": "date",
                        "开盘": "open",
                        "收盘": "close",
                        "最高": "high",
                        "最低": "low",
                        "成交量": "volume",
                        "成交额": "amount",
                        "振幅": "amplitude",
                        "涨跌幅": "pct_change",
                        "涨跌额": "change",
                        "换手率": "turnover"
                    })
                    df["date"] = pd.to_datetime(df["date"])
                    print(f"[Akshare] ✅ 成功获取 {len(df)} 条数据")
                    return df
            except Exception as e:
                print(f"[Akshare] ❌ 获取失败: {e}")
            return None

        if source == "eastmoney":
            try:
                print(f"[EastMoney] 正在获取 {symbol} 的历史数据（备用数据源）...")
                df = self._get_hist_data_from_eastmoney(symbol, start_date, end_date, adjust)
                if df is not None and not df.empty:
                    print(f"[EastMoney] ✅ 成功获取 {len(df)} 条数据")
                    return df
            except Exception as e:
                print(f"[EastMoney] ❌ 获取失败: {e}")
            return None

        if source == "tushare":
            if not self.tushare_available:
                print("[Tushare] ⚠️ 未初始化，跳过")
                return None
            try:
                print(f"[Tushare] 正在获取 {symbol} 的历史数据（备用数据源）...")
                ts_code = self._convert_to_ts_code(symbol)
                adj_dict = {"qfq": "qfq", "hfq": "hfq", "": None}
                adj = adj_dict.get(adjust, "qfq")
                df = self.tushare_api.daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    adj=adj
                )
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        "trade_date": "date",
                        "vol": "volume",
                        "amount": "amount"
                    })
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date")
                    df["volume"] = df["volume"] * 100
                    df["amount"] = df["amount"] * 1000
                    print(f"[Tushare] ✅ 成功获取 {len(df)} 条数据")
                    return df
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")
            return None

        return None

    def _fetch_realtime_quotes_by_source(self, source, symbol):
        """
        按指定数据源获取实时行情
        """
        if source == "akshare":
            try:
                import akshare as ak
                print(f"[Akshare] 正在获取 {symbol} 的实时行情...")
                df = ak.stock_zh_a_spot_em()
                stock_df = df[df["代码"] == symbol]
                if not stock_df.empty:
                    row = stock_df.iloc[0]
                    quotes = {
                        "symbol": symbol,
                        "name": row["名称"],
                        "price": row["最新价"],
                        "change_percent": row["涨跌幅"],
                        "change": row["涨跌额"],
                        "volume": row["成交量"],
                        "amount": row["成交额"],
                        "high": row["最高"],
                        "low": row["最低"],
                        "open": row["今开"],
                        "pre_close": row["昨收"]
                    }
                    print("[Akshare] ✅ 成功获取实时行情")
                    return quotes
            except Exception as e:
                print(f"[Akshare] ❌ 获取失败: {e}")
            return {}

        if source == "eastmoney":
            try:
                print(f"[EastMoney] 正在获取 {symbol} 的实时行情（备用数据源）...")
                quotes = self._get_realtime_quotes_from_eastmoney(symbol)
                if quotes:
                    print("[EastMoney] ✅ 成功获取实时行情")
                    return quotes
            except Exception as e:
                print(f"[EastMoney] ❌ 获取失败: {e}")
            return {}

        if source == "tencent":
            try:
                print(f"[Tencent] 正在获取 {symbol} 的实时行情（备用数据源）...")
                quotes = self._get_realtime_quotes_from_tencent(symbol)
                if quotes:
                    print("[Tencent] ✅ 成功获取实时行情")
                    return quotes
            except Exception as e:
                print(f"[Tencent] ❌ 获取失败: {e}")
            return {}

        if source == "tushare":
            if not self.tushare_available:
                print("[Tushare] ⚠️ 未初始化，跳过")
                return {}
            try:
                print(f"[Tushare] 正在获取 {symbol} 的实时行情（备用数据源）...")
                ts_code = self._convert_to_ts_code(symbol)
                df = self.tushare_api.daily(
                    ts_code=ts_code,
                    start_date=datetime.now().strftime("%Y%m%d"),
                    end_date=datetime.now().strftime("%Y%m%d")
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    quotes = {
                        "symbol": symbol,
                        "price": row["close"],
                        "change_percent": row["pct_chg"],
                        "volume": row["vol"] * 100,
                        "amount": row["amount"] * 1000,
                        "high": row["high"],
                        "low": row["low"],
                        "open": row["open"],
                        "pre_close": row["pre_close"]
                    }
                    print("[Tushare] ✅ 成功获取实时行情")
                    return quotes
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")
            return {}

        return {}
    
    def get_financial_data(self, symbol, report_type='income'):
        """
        获取财务数据（优先akshare，失败时使用tushare）
        
        Args:
            symbol: 股票代码
            report_type: 报表类型（'income'利润表, 'balance'资产负债表, 'cashflow'现金流量表）
            
        Returns:
            DataFrame: 财务数据
        """
        # 优先使用akshare
        try:
            import akshare as ak
            print(f"[Akshare] 正在获取 {symbol} 的财务数据...")
            
            if report_type == 'income':
                df = ak.stock_financial_report_sina(stock=symbol, symbol="利润表")
            elif report_type == 'balance':
                df = ak.stock_financial_report_sina(stock=symbol, symbol="资产负债表")
            elif report_type == 'cashflow':
                df = ak.stock_financial_report_sina(stock=symbol, symbol="现金流量表")
            else:
                df = None
            
            if df is not None and not df.empty:
                print(f"[Akshare] ✅ 成功获取财务数据")
                return df
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")
        
        # akshare失败，尝试tushare
        if self.tushare_available:
            try:
                print(f"[Tushare] 正在获取 {symbol} 的财务数据（备用数据源）...")
                
                ts_code = self._convert_to_ts_code(symbol)
                
                if report_type == 'income':
                    df = self.tushare_api.income(ts_code=ts_code)
                elif report_type == 'balance':
                    df = self.tushare_api.balancesheet(ts_code=ts_code)
                elif report_type == 'cashflow':
                    df = self.tushare_api.cashflow(ts_code=ts_code)
                else:
                    df = None
                
                if df is not None and not df.empty:
                    print(f"[Tushare] ✅ 成功获取财务数据")
                    return df
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")
        
        return None
    
    def _convert_to_ts_code(self, symbol):
        """
        将6位股票代码转换为tushare格式（带市场后缀）
        
        Args:
            symbol: 6位股票代码
            
        Returns:
            str: tushare格式代码（如：000001.SZ）
        """
        if not symbol or len(symbol) != 6:
            return symbol
        
        # 根据代码判断市场
        if symbol.startswith('6'):
            # 上海主板
            return f"{symbol}.SH"
        elif symbol.startswith('0') or symbol.startswith('3'):
            # 深圳主板和创业板
            return f"{symbol}.SZ"
        elif symbol.startswith('8') or symbol.startswith('4'):
            # 北交所
            return f"{symbol}.BJ"
        else:
            # 默认深圳
            return f"{symbol}.SZ"

    def _convert_to_market_symbol(self, symbol):
        """
        将6位股票代码转换为带市场前缀代码（如：sz000001 / sh600000）
        """
        if not symbol or len(symbol) != 6:
            return symbol
        if symbol.startswith('6'):
            return f"sh{symbol}"
        if symbol.startswith('0') or symbol.startswith('3'):
            return f"sz{symbol}"
        if symbol.startswith('8') or symbol.startswith('4'):
            return f"bj{symbol}"
        return f"sz{symbol}"

    def _http_get_text(self, url, params=None, timeout=8):
        """
        轻量HTTP GET，统一超时与编码处理
        """
        if params:
            query = urllib.parse.urlencode(params)
            connector = '&' if '?' in url else '?'
            url = f"{url}{connector}{query}"

        req = urllib.request.Request(
            url=url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                "Referer": "https://quote.eastmoney.com/"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("gbk", errors="ignore")

    def _get_hist_data_from_eastmoney(self, symbol, start_date, end_date, adjust='qfq'):
        """
        东方财富K线接口（Web）历史行情
        """
        market_symbol = self._convert_to_market_symbol(symbol)
        secid = None
        if market_symbol.startswith("sh"):
            secid = f"1.{symbol}"
        elif market_symbol.startswith("sz"):
            secid = f"0.{symbol}"
        elif market_symbol.startswith("bj"):
            secid = f"0.{symbol}"
        else:
            return None

        fq_dict = {"": "0", "qfq": "1", "hfq": "2"}
        fqt = fq_dict.get(adjust, "1")
        beg = start_date if start_date else "19900101"
        end = end_date if end_date else datetime.now().strftime("%Y%m%d")

        text = self._http_get_text(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": fqt,
                "beg": beg,
                "end": end,
                "ut": "fa5fd1943c7b386f172d6893dbfba10b"
            },
            timeout=8
        )
        payload = json.loads(text)
        klines = (payload.get("data") or {}).get("klines") or []
        if not klines:
            return None

        rows = []
        for line in klines:
            arr = line.split(",")
            if len(arr) < 11:
                continue
            rows.append(
                {
                    "date": pd.to_datetime(arr[0]),
                    "open": pd.to_numeric(arr[1], errors="coerce"),
                    "close": pd.to_numeric(arr[2], errors="coerce"),
                    "high": pd.to_numeric(arr[3], errors="coerce"),
                    "low": pd.to_numeric(arr[4], errors="coerce"),
                    "volume": pd.to_numeric(arr[5], errors="coerce"),
                    "amount": pd.to_numeric(arr[6], errors="coerce"),
                    "amplitude": pd.to_numeric(arr[7], errors="coerce"),
                    "pct_change": pd.to_numeric(arr[8], errors="coerce"),
                    "change": pd.to_numeric(arr[9], errors="coerce"),
                    "turnover": pd.to_numeric(arr[10], errors="coerce")
                }
            )
        if not rows:
            return None

        df = pd.DataFrame(rows).sort_values("date")
        return df

    def _get_realtime_quotes_from_eastmoney(self, symbol):
        """
        东方财富实时行情接口（Web）
        """
        market_symbol = self._convert_to_market_symbol(symbol)
        if market_symbol.startswith("sh"):
            secid = f"1.{symbol}"
        elif market_symbol.startswith("sz"):
            secid = f"0.{symbol}"
        elif market_symbol.startswith("bj"):
            secid = f"0.{symbol}"
        else:
            return {}

        text = self._http_get_text(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": secid,
                "fields": "f57,f58,f43,f169,f170,f47,f48,f44,f45,f46,f60",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b"
            },
            timeout=5
        )
        payload = json.loads(text)
        data = payload.get("data") or {}
        if not data:
            return {}

        # 东财f43/f44/f45/f46/f60等价格类字段通常需除以100
        scale = 100
        return {
            "symbol": symbol,
            "name": data.get("f58", ""),
            "price": (data.get("f43") or 0) / scale,
            "change_percent": (data.get("f170") or 0) / 100,
            "change": (data.get("f169") or 0) / scale,
            "volume": data.get("f47", 0),
            "amount": data.get("f48", 0),
            "high": (data.get("f44") or 0) / scale,
            "low": (data.get("f45") or 0) / scale,
            "open": (data.get("f46") or 0) / scale,
            "pre_close": (data.get("f60") or 0) / scale
        }

    def _get_realtime_quotes_from_tencent(self, symbol):
        """
        腾讯实时行情接口（Web）
        """
        market_symbol = self._convert_to_market_symbol(symbol)
        text = self._http_get_text(
            f"https://qt.gtimg.cn/q={market_symbol}",
            timeout=5
        )
        if "~" not in text:
            return {}

        body = text.split('"', 2)[1] if '"' in text else text
        arr = body.split("~")
        if len(arr) < 40:
            return {}

        # 腾讯字段位置参考公开网页接口约定
        # 3最新价 4昨收 5今开 6成交量(手) 32涨跌 33涨跌幅 34最高 35最低 37成交额
        return {
            "symbol": symbol,
            "name": arr[1] if len(arr) > 1 else "",
            "price": pd.to_numeric(arr[3], errors="coerce"),
            "change_percent": pd.to_numeric(arr[33], errors="coerce"),
            "change": pd.to_numeric(arr[32], errors="coerce"),
            "volume": pd.to_numeric(arr[6], errors="coerce") * 100,
            "amount": pd.to_numeric(arr[37], errors="coerce"),
            "high": pd.to_numeric(arr[34], errors="coerce"),
            "low": pd.to_numeric(arr[35], errors="coerce"),
            "open": pd.to_numeric(arr[5], errors="coerce"),
            "pre_close": pd.to_numeric(arr[4], errors="coerce")
        }
    
    def _convert_from_ts_code(self, ts_code):
        """
        将tushare格式代码转换为6位代码
        
        Args:
            ts_code: tushare格式代码（如：000001.SZ）
            
        Returns:
            str: 6位股票代码
        """
        if '.' in ts_code:
            return ts_code.split('.')[0]
        return ts_code


# 全局数据源管理器实例
data_source_manager = DataSourceManager()

