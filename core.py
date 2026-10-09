"""core.py - Thu thập dữ liệu DNSE cho TOÀN THỊ TRƯỜNG + phân tích vĩ mô / ngành / cổ phiếu."""
import os, time, pickle, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data_cache"); os.makedirs(CACHE, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0"}
ENTRADE = "https://services.entrade.com.vn/chart-api/v2/ohlcs/{}"   # API dữ liệu giá công khai của DNSE
POS = ["tăng", "lãi", "kỷ lục", "vượt", "tích cực", "mua ròng", "khởi sắc", "cổ tức", "tăng trưởng", "bứt phá"]
NEG = ["giảm", "lỗ", "bán ròng", "vi phạm", "thanh tra", "khởi tố", "nợ xấu", "sụt", "cảnh báo", "đình chỉ", "phạt"]
LABEL = {"price": "Giá", "ret1d": "% 1 ngày", "ret1m": "% 1 tháng", "ret3m": "% 3 tháng", "ret6m": "% 6 tháng",
         "ret12m": "% 12 tháng", "vol": "Biến động", "beta": "Beta", "dd": "Cách đỉnh 52T", "rsi": "RSI",
         "gtgd": "GTGD 20D (tỷ)", "flow": "Dòng tiền (20D/60D)", "score": "Điểm"}


# ------------------------------ 1. DỮ LIỆU DNSE ------------------------------
def dnse_ohlc(sym, days=800, kind="stock", retry=3):
    to = int(time.time()); fr = to - days * 86400
    for k in range(retry):
        try:
            j = requests.get(ENTRADE.format(kind), headers=H, timeout=15,
                             params={"from": fr, "to": to, "symbol": sym, "resolution": "1D"}).json()
            if not j.get("t"):
                return None
            df = pd.DataFrame({"open": j["o"], "high": j["h"], "low": j["l"], "close": j["c"], "volume": j["v"]},
                              index=(pd.to_datetime(j["t"], unit="s") + pd.Timedelta(hours=7)).normalize())
            df = df[~df.index.duplicated()].astype(float).dropna().sort_index()
            if kind == "stock" and df["close"].median() > 1000:   # thống nhất: nghìn đồng
                df[["open", "high", "low", "close"]] /= 1000
            return df
        except Exception:
            time.sleep(.5 * (k + 1))
    return None


def load_universe():
    """Danh sách TẤT CẢ mã cổ phiếu (+ ngành ICB nếu lấy được). Ưu tiên file symbols.txt (xuất từ DNSE)."""
    base, icb = None, None
    try:
        from vnstock import Listing
        L = Listing(source="VCI")
        try:
            a = L.symbols_by_industries(); a.columns = [c.lower() for c in a.columns]
            col = next(c for c in ("icb_name2", "icb_name3", "icb_name4") if c in a.columns)
            icb = a[["symbol", col]].rename(columns={col: "icb"})
        except Exception:
            pass
        try:
            b = L.symbols_by_exchange(); b.columns = [c.lower() for c in b.columns]
            if "type" in b:
                b = b[b["type"].astype(str).str.upper() == "STOCK"]
            base = b[["symbol", "exchange"]] if "exchange" in b else b[["symbol"]].assign(exchange="")
        except Exception:
            pass
    except Exception:
        pass
    if base is None:
        try:
            j = requests.get("https://api-finfo.vndirect.com.vn/v4/stocks", headers=H, timeout=20,
                             params={"q": "type:STOCK~status:LISTED", "fields": "code,floor", "size": 3000}).json()["data"]
            base = pd.DataFrame(j).rename(columns={"code": "symbol", "floor": "exchange"})
        except Exception:
            pass
    sf = os.path.join(HERE, "symbols.txt")
    if os.path.exists(sf):
        syms = [s.strip().upper() for s in open(sf, encoding="utf-8").read().replace(",", "\n").split() if s.strip()]
        base = pd.DataFrame({"symbol": syms, "exchange": ""})
    if base is None and icb is not None:
        base = icb[["symbol"]].assign(exchange="")
    if base is None:
        raise RuntimeError("Không lấy được danh sách mã. Hãy tạo file symbols.txt (mỗi dòng 1 mã) cạnh app.py.")
    u = base.drop_duplicates("symbol")
    u = u.merge(icb, on="symbol", how="left") if icb is not None else u.assign(icb=np.nan)
    return u[u["symbol"].str.fullmatch(r"[A-Z0-9]{3}")].reset_index(drop=True)


def load_market(refresh=False, progress=None, workers=12, days=800):
    f = os.path.join(CACHE, "market.pkl")
    if os.path.exists(f) and not refresh and time.time() - os.path.getmtime(f) < 12 * 3600:
        return pickle.load(open(f, "rb"))
    u = load_universe(); syms = u["symbol"].tolist(); raw = {}
    with ThreadPoolExecutor(workers) as ex:
        for i, (s, d) in enumerate(zip(syms, ex.map(lambda s: dnse_ohlc(s, days), syms))):
            if d is not None and len(d) > 120:
                raw[s] = d
            if progress:
                progress((i + 1) / len(syms))
    idx = dnse_ohlc("VNINDEX", days, "index")
    if idx is None or not raw:
        raise RuntimeError("Không gọi được API DNSE (kiểm tra kết nối mạng).")
    close = pd.DataFrame({s: d["close"] for s, d in raw.items()}).sort_index()
    vol = pd.DataFrame({s: d["volume"] for s, d in raw.items()}).sort_index()
    alive = close.tail(5).notna().any()                       # bỏ mã đã ngừng giao dịch
    close, vol = close.loc[:, alive], vol.loc[:, alive]
    uni = u[u["symbol"].isin(close.columns)].set_index("symbol")
    data = {"close": close, "vol": vol, "raw": {s: raw[s] for s in close.columns}, "idx": idx, "uni": uni, "time": time.time()}
    pickle.dump(data, open(f, "wb"))
    return data


# ------------------------------ 2. PHÂN NGÀNH TỰ ĐỘNG ------------------------------
def cluster_industries(close, val, icb=None, k=18):
    """Phân cụm phân cấp theo tương quan lợi suất (đã loại thành phần thị trường chung)."""
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
    r = np.log(close.ffill()).diff().tail(252)
    good = r.columns[(r.notna().sum() >= 200) & (val.tail(60).mean() > 0)]
    r = r[good].fillna(0); r = r.sub(r.mean(axis=1), axis=0)
    d = np.sqrt(np.clip(0.5 * (1 - r.corr().fillna(0).values), 0, None)); np.fill_diagonal(d, 0)
    lab = pd.Series(fcluster(linkage(squareform(d, checks=False), "average"), k, "maxclust"), index=good)
    names = {}
    for g in sorted(lab.unique()):
        mem = lab[lab == g].index
        top = ", ".join(val[mem].tail(60).mean().sort_values(ascending=False).head(3).index)
        dom = ""
        if icb is not None and icb.reindex(mem).notna().any():
            dom = icb.reindex(mem).mode().iloc[0] + " · "
        names[g] = f"{dom}Cụm {g} ({top})"
    return lab.map(names).reindex(close.columns).fillna("Khác (thiếu dữ liệu)")


def assign_industry(data, mode="ICB", k=18):
    uni, close = data["uni"], data["close"]
    val = (close * data["vol"]).fillna(0)
    icb = uni["icb"].reindex(close.columns)
    if mode == "ICB" and icb.notna().mean() > 0.5:
        return icb.fillna("Khác"), val
    return cluster_industries(close, val, icb if icb.notna().any() else None, k), val


# ------------------------------ 3. CHỈ SỐ & CHẤM ĐIỂM ------------------------------
def build_metrics(close, val, idx):
    c = close.ffill(); r = c.pct_change(); n = len(c)
    m = pd.DataFrame(index=c.columns)
    m["price"], m["ret1d"] = c.iloc[-1], r.iloc[-1]
    for k, nn in (("ret1m", 21), ("ret3m", 63), ("ret6m", 126), ("ret12m", min(252, n - 1))):
        m[k] = c.iloc[-1] / c.iloc[-nn - 1] - 1
    rr = r.tail(252); ir = idx["close"].pct_change().reindex(rr.index)
    m["vol"] = rr.std() * np.sqrt(252)
    m["beta"] = rr.apply(lambda s: s.cov(ir)) / ir.var()
    m["dd"] = c.iloc[-1] / c.tail(252).max() - 1
    m["sma50"], m["sma200"] = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
    m["a50"], m["a200"] = (m.price > m.sma50).astype(float), (m.price > m.sma200).astype(float)
    m.loc[m.sma200.isna(), "a200"] = np.nan
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    m["rsi"] = (100 - 100 / (1 + up / dn)).iloc[-1]
    m["gtgd"] = val.tail(20).mean() / 1e6                                  # tỷ đồng
    m["flow"] = val.tail(20).mean() / val.tail(60).mean().replace(0, np.nan) - 1
    return m


def score_stocks(m, ind):
    p = lambda s: s.rank(pct=True) * 100
    rel = m["ret3m"] - m.groupby(ind.reindex(m.index))["ret3m"].transform("median")
    f = pd.DataFrame({
        "Động lượng giá": (p(m.ret3m) + p(m.ret6m) + p(m.ret12m)) / 3,
        "Sức mạnh so với ngành": p(rel),
        "Xu hướng (SMA)": 40 * m.a50 + 30 * m.a200.fillna(0) + 30 * (m.sma50 > m.sma200),
        "Vùng RSI": (100 - (m.rsi - 58).abs() * 2.5).clip(0, 100),
        "Ổn định / rủi ro": .5 * (100 - p(m.vol)) + .5 * p(m.dd),
        "Thanh khoản & dòng tiền": .6 * p(m.gtgd) + .4 * p(m.flow)})
    w = pd.Series({"Động lượng giá": .25, "Sức mạnh so với ngành": .20, "Xu hướng (SMA)": .20,
                   "Vùng RSI": .10, "Ổn định / rủi ro": .15, "Thanh khoản & dòng tiền": .10})
    return f, (f * w).sum(axis=1)


def industry_table(close, val, m, ind, idx):
    r = close.pct_change(); rows, curves = [], {}; ic = idx["close"]
    for g, syms in ind.groupby(ind).groups.items():
        syms = [s for s in syms if s in close.columns]
        if len(syms) < 2:
            continue
        ew = (1 + r[syms].mean(axis=1).fillna(0)).cumprod(); curves[g] = ew / ew.iloc[0] * 100
        vv = val[syms].sum(axis=1)
        row = {"Ngành": g, "n": len(syms), "a50": m.loc[syms, "a50"].mean(), "gtgd": m.loc[syms, "gtgd"].sum(),
               "vol": m.loc[syms, "vol"].median(), "flow": vv.tail(20).mean() / vv.tail(60).mean() - 1}
        for k, nn in (("ret1m", 21), ("ret3m", 63), ("ret6m", 126)):
            row[k] = ew.iloc[-1] / ew.iloc[-nn - 1] - 1
        rows.append(row)
    t = pd.DataFrame(rows).set_index("Ngành")
    t["rs1m"] = t.ret1m - (ic.iloc[-1] / ic.iloc[-22] - 1); t["rs3m"] = t.ret3m - (ic.iloc[-1] / ic.iloc[-64] - 1)
    p = lambda s: s.rank(pct=True) * 100
    t["score"] = .3 * p(t.rs3m) + .2 * p(t.rs1m) + .2 * p(t.a50) + .15 * p(t.flow) + .15 * (100 - p(t.vol))
    t["share"] = t.gtgd / t.gtgd.sum()
    t["rating"] = pd.cut(t.score, [-1, 35, 50, 70, 101], labels=["Yếu", "Trung lập", "Khả quan", "Dẫn dắt"]).astype(str)
    return t.sort_values("score", ascending=False), curves


# ------------------------------ 4. VĨ MÔ ------------------------------
def global_macro():
    out = {}
    try:
        import yfinance as yf
        for name, tk in {"USD/VND": "VND=X", "Lợi suất TPCP Mỹ 10Y (%)": "^TNX", "Chỉ số USD (DXY)": "DX-Y.NYB",
                         "Vàng (USD/oz)": "GC=F", "Dầu WTI (USD/thùng)": "CL=F", "S&P 500": "^GSPC"}.items():
            try:
                d = yf.download(tk, period="1y", progress=False, auto_adjust=True)
                if isinstance(d.columns, pd.MultiIndex):
                    d.columns = d.columns.get_level_values(0)
                s = d["Close"].dropna()
                out[name] = {"last": float(s.iloc[-1]), "1m": float(s.iloc[-1] / s.iloc[-22] - 1), "3m": float(s.iloc[-1] / s.iloc[-64] - 1)}
            except Exception:
                pass
    except Exception:
        pass
    return out


def macro_view(idx, close, m, val, glob):
    c = idx["close"]; L = c.iloc[-1]; s50, s200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
    r = np.log(c).diff(); v20, v1y = r.tail(20).std() * np.sqrt(252), r.tail(252).std() * np.sqrt(252)
    tot = val.sum(axis=1); liq = tot.tail(20).mean() / tot.tail(60).mean() - 1
    day = close.pct_change().iloc[-1]; adv, dec = int((day > 0).sum()), int((day < 0).sum())
    hi = int((close.iloc[-1] >= close.tail(252).max() * .98).sum()); lo = int((close.iloc[-1] <= close.tail(252).min() * 1.02).sum())
    b50, b200 = m.a50.mean(), m.a200.mean()
    score = 25 * (L > s50) + 15 * (s50 > s200) + 20 * b50 + 15 * b200 + 10 * (liq > 0) + 10 * (v20 < v1y) + 5 * (adv > dec)
    regime = "THUẬN LỢI" if score >= 70 else "TRUNG TÍNH / PHÂN HÓA" if score >= 45 else "RỦI RO CAO"
    txt = [f"VN-Index {L:,.1f} điểm, {'trên' if L > s50 else 'dưới'} SMA50 ({s50:,.0f}) và {'trên' if L > s200 else 'dưới'} SMA200 ({s200:,.0f}); "
           f"cách đỉnh 52 tuần {L / c.tail(252).max() - 1:.1%}.",
           f"Độ rộng thị trường: {b50:.0%} cổ phiếu trên SMA50, {b200:.0%} trên SMA200; phiên gần nhất {adv} mã tăng/{dec} mã giảm; "
           f"{hi} mã gần đỉnh 52 tuần so với {lo} mã gần đáy.",
           f"Thanh khoản 20 phiên {'cao hơn' if liq > 0 else 'thấp hơn'} trung bình 60 phiên {abs(liq):.0%}; "
           f"biến động 20 phiên {v20:.0%} ({'thấp hơn' if v20 < v1y else 'cao hơn'} mức 1 năm {v1y:.0%})."]
    g = glob
    if "USD/VND" in g:
        txt.append(f"Tỷ giá USD/VND {g['USD/VND']['last']:,.0f} ({g['USD/VND']['3m']:+.1%} trong 3 tháng): "
                   + ("áp lực lên VND, bất lợi cho dòng vốn ngoại." if g['USD/VND']['3m'] > .01 else "tương đối ổn định."))
    if "Lợi suất TPCP Mỹ 10Y (%)" in g:
        y = g["Lợi suất TPCP Mỹ 10Y (%)"]; txt.append(f"Lợi suất TPCP Mỹ 10Y {y['last']:.2f}% ({y['3m']:+.1%} trong 3 tháng): "
                   + ("tăng, gây sức ép định giá tài sản rủi ro." if y['3m'] > .03 else "giảm/đi ngang, hỗ trợ khẩu vị rủi ro." if y['3m'] < -.03 else "đi ngang."))
    if "Dầu WTI (USD/thùng)" in g:
        txt.append(f"Giá dầu WTI {g['Dầu WTI (USD/thùng)']['last']:.1f} USD ({g['Dầu WTI (USD/thùng)']['3m']:+.1%} 3 tháng), "
                   f"vàng {g.get('Vàng (USD/oz)', {}).get('last', float('nan')):,.0f} USD/oz – tác động tới nhóm dầu khí, hóa chất, tiêu dùng.")
    return {"score": score, "regime": regime, "text": txt, "b50": b50, "b200": b200, "adv": adv, "dec": dec, "hi": hi, "lo": lo, "liq": liq, "v20": v20, "v1y": v1y}


# ------------------------------ 5. CỔ PHIẾU ------------------------------
def add_ind(df):
    df = df.copy(); c = df["close"]
    for w in (20, 50, 200):
        df[f"sma{w}"] = c.rolling(w).mean()
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14).mean()
    df["rsi"] = 100 - 100 / (1 + up / dn)
    df["macd"] = c.ewm(span=12).mean() - c.ewm(span=26).mean(); df["sig"] = df["macd"].ewm(span=9).mean()
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(); df["bbu"], df["bbl"] = mid + 2 * sd, mid - 2 * sd
    tr = pd.concat([df.high - df.low, (df.high - c.shift()).abs(), (df.low - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    return df


def levels(df):
    L = df.iloc[-1]
    return {"Hỗ trợ gần (đáy 20 phiên)": df.low.tail(20).min(), "Kháng cự gần (đỉnh 60 phiên)": df.high.tail(60).max(),
            "Đỉnh 52 tuần": df.high.tail(252).max(), "Đáy 52 tuần": df.low.tail(252).min(),
            "Cắt lỗ gợi ý (giá - 2×ATR)": L.close - 2 * L.atr, "ATR(14)": L.atr}


def get_fund(sym):
    keys = ["longName", "sector", "marketCap", "trailingPE", "priceToBook", "returnOnEquity", "profitMargins",
            "debtToEquity", "dividendYield", "revenueGrowth", "earningsGrowth", "trailingEps"]
    try:
        import yfinance as yf
        i = yf.Ticker(sym + ".VN").info
        return {k: i.get(k) for k in keys}
    except Exception:
        return {k: None for k in keys}


def get_news(sym, n=10):
    out = []
    try:
        r = requests.get(f"https://news.google.com/rss/search?q=cổ+phiếu+{sym}&hl=vi&gl=VN&ceid=VN:vi", timeout=10, headers=H)
        for it in ET.fromstring(r.content).findall(".//item")[:n]:
            t = it.findtext("title") or ""; low = t.lower()
            out.append({"Tiêu đề": t, "Ngày": (it.findtext("pubDate") or "")[5:16], "Link": it.findtext("link"),
                        "Điểm": sum(w in low for w in POS) - sum(w in low for w in NEG)})
    except Exception:
        pass
    return pd.DataFrame(out, columns=["Tiêu đề", "Ngày", "Link", "Điểm"])


def combine(stock_score, ind_score, mkt_score, news_s=0):
    """Điểm cơ hội 3 tầng: cổ phiếu 70% + ngành 20% + thị trường 10% (± tin tức)."""
    tot = .7 * stock_score + .2 * ind_score + .1 * mkt_score + float(np.clip(news_s, -3, 3))
    rec = "TÍCH CỰC – ưu tiên tích lũy" if tot >= 70 else "KHẢ QUAN – theo dõi mua" if tot >= 58 else "TRUNG LẬP" if tot >= 45 else "THẬN TRỌNG"
    return float(tot), rec


def thesis(sym, m, factors, ind_name, ind_row, reg, lv, f, news_s):
    r = m.loc[sym]; pros, cons = [], []
    (pros if r.a50 == 1 and r.a200 == 1 else cons).append("Giá nằm trên cả SMA50 và SMA200 (xu hướng tăng)." if r.a50 == 1 and r.a200 == 1 else "Giá chưa vượt đồng thời SMA50/SMA200 – xu hướng chưa rõ.")
    if r.ret3m > 0.1: pros.append(f"Động lượng 3 tháng mạnh ({r.ret3m:+.1%}).")
    if r.ret3m < -0.1: cons.append(f"Suy yếu 3 tháng ({r.ret3m:+.1%}).")
    if factors["Sức mạnh so với ngành"] >= 70: pros.append("Vượt trội so với mặt bằng ngành.")
    if factors["Sức mạnh so với ngành"] <= 30: cons.append("Kém hơn mặt bằng ngành.")
    if r.rsi > 70: cons.append(f"RSI {r.rsi:.0f} – vùng quá mua, rủi ro điều chỉnh ngắn hạn.")
    elif r.rsi < 30: pros.append(f"RSI {r.rsi:.0f} – vùng quá bán, có thể kỳ vọng nhịp hồi.")
    if r.flow > .2: pros.append(f"Thanh khoản 20 phiên tăng {r.flow:.0%} so với 60 phiên (dòng tiền vào).")
    if r.flow < -.3: cons.append("Thanh khoản suy giảm mạnh (dòng tiền rút).")
    if r.vol > .45: cons.append(f"Biến động cao ({r.vol:.0%}/năm).")
    if r.dd < -.3: cons.append(f"Đang cách đỉnh 52 tuần {r.dd:.0%}.")
    if r.gtgd < 1: cons.append(f"Thanh khoản thấp (~{r.gtgd:.1f} tỷ/phiên) – khó vào/ra lệnh lớn.")
    if ind_row is not None:
        (pros if ind_row["score"] >= 60 else cons if ind_row["score"] < 40 else pros).append(
            f"Ngành {ind_name} đang ở nhóm '{ind_row['rating']}' (điểm {ind_row['score']:.0f}, vượt/thua VN-Index 3T {ind_row['rs3m']:+.1%}).")
    if reg["score"] < 45: cons.append("Thị trường chung đang ở trạng thái rủi ro cao – nên giảm tỷ trọng giải ngân.")
    if news_s > 1: pros.append("Tin tức gần đây nghiêng tích cực.")
    if news_s < -1: cons.append("Tin tức gần đây nghiêng tiêu cực.")
    pe, roe = f.get("trailingPE"), f.get("returnOnEquity")
    if pe: (pros if 0 < pe < 15 else cons if pe > 25 or pe < 0 else pros).append(f"P/E {pe:.1f}" + (" – định giá hấp dẫn." if 0 < pe < 15 else " – định giá cao/không có lãi." if pe > 25 or pe < 0 else " – định giá hợp lý."))
    if roe: (pros if roe > .15 else cons if roe < .08 else pros).append(f"ROE {roe:.1%}.")
    return pros, cons
