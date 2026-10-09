"""report.py - Xuất báo cáo PDF (font DejaVu nhúng, bảng tự xuống dòng, nhiều biểu đồ)."""
import io, os, datetime as dt
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                Image, PageBreak, KeepTogether)

FD = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
pdfmetrics.registerFont(TTFont("VN", os.path.join(FD, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("VN-B", os.path.join(FD, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("VN-I", os.path.join(FD, "DejaVuSans-Oblique.ttf")))
for b, i, f in ((0, 0, "VN"), (1, 0, "VN-B"), (0, 1, "VN-I"), (1, 1, "VN-B")):
    addMapping("VN", b, i, f)
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False, "font.size": 8})

BLUE, LIGHT = colors.HexColor("#0d47a1"), colors.HexColor("#e8f0fe")
S = {"t": ParagraphStyle("t", fontName="VN-B", fontSize=20, leading=25, textColor=BLUE),
     "h": ParagraphStyle("h", fontName="VN-B", fontSize=13, leading=17, textColor=BLUE, spaceBefore=10, spaceAfter=5),
     "h2": ParagraphStyle("h2", fontName="VN-B", fontSize=10, leading=13, spaceBefore=6, spaceAfter=3),
     "n": ParagraphStyle("n", fontName="VN", fontSize=9, leading=13.5, spaceAfter=3),
     "b": ParagraphStyle("b", fontName="VN", fontSize=9, leading=13, leftIndent=10, bulletIndent=0, spaceAfter=2),
     "c": ParagraphStyle("c", fontName="VN", fontSize=7.6, leading=9.5),
     "ch": ParagraphStyle("ch", fontName="VN-B", fontSize=7.6, leading=9.5, textColor=colors.white),
     "s": ParagraphStyle("s", fontName="VN-I", fontSize=7.5, leading=10, textColor=colors.grey)}
W = 17 * cm


def P(t, s="n"): return Paragraph(str(t), S[s])
def bullets(items): return [Paragraph(str(x), S["b"], bulletText="•") for x in items]


def tbl(rows, widths, hl_row=None):
    data = [[Paragraph(str(c), S["ch"]) for c in rows[0]]] + [[Paragraph(str(c), S["c"]) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), BLUE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#b0bec5")),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if hl_row:
        st.append(("BACKGROUND", (0, hl_row), (-1, hl_row), colors.HexColor("#fff3cd")))
    t.setStyle(TableStyle(st)); return t


def img(fig, h_cm, w_cm=17):
    b = io.BytesIO(); fig.tight_layout(); fig.savefig(b, format="png", dpi=150); plt.close(fig); b.seek(0)
    return Image(b, width=w_cm * cm, height=h_cm * cm)


def pct(x, d=1): return "n/a" if x is None or pd.isna(x) else f"{x * 100:+.{d}f}%"
def num(x, d=2): return "n/a" if x is None or pd.isna(x) else f"{x:,.{d}f}"


def footer(c, d):
    c.saveState(); c.setFont("VN", 7.5); c.setFillColor(colors.grey)
    c.drawString(2 * cm, 1.1 * cm, "StockLab VN – báo cáo tự động, chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.")
    c.drawRightString(19 * cm, 1.1 * cm, f"Trang {d.page}"); c.setStrokeColor(BLUE); c.line(2 * cm, 1.5 * cm, 19 * cm, 1.5 * cm)
    c.restoreState()


def make_report(x):
    """x: dict ngữ cảnh do app.py dựng sẵn."""
    sym, df, m, ind_name, it, reg, glob = x["sym"], x["df"], x["m"], x["ind_name"], x["it"], x["reg"], x["glob"]
    r = m.loc[sym]; S_ = []
    # ---------- Trang 1: tóm tắt ----------
    S_ += [P(f"BÁO CÁO PHÂN TÍCH CƠ HỘI ĐẦU TƯ: {sym}", "t"),
           P(f"{x['fund'].get('longName') or ''} · Ngành: {ind_name} · Ngày lập {dt.date.today():%d/%m/%Y} · Dữ liệu giá: DNSE (cập nhật {x['asof']:%d/%m/%Y})", "s"),
           Spacer(1, 6)]
    S_.append(tbl([["Điểm cổ phiếu", "Điểm ngành", "Điểm thị trường", "ĐIỂM TỔNG HỢP", "Đánh giá"],
                   [f"{x['stock_score']:.0f}/100", f"{it['score']:.0f}/100" if it is not None else "n/a", f"{reg['score']:.0f}/100",
                    f"<b>{x['total']:.0f}/100</b>", f"<b>{x['rec']}</b>"]], [3, 3, 3, 3.5, 4.5]))
    S_ += [P("1. Luận điểm đầu tư", "h"), P("Điểm hỗ trợ", "h2")] + bullets(x["pros"] or ["Chưa có điểm hỗ trợ nổi bật."])
    S_ += [P("Rủi ro cần lưu ý", "h2")] + bullets(x["cons"] or ["Chưa ghi nhận rủi ro nổi bật."])
    lv = x["lv"]
    S_ += [P("Vùng giá tham khảo (đơn vị: nghìn đồng)", "h2"),
           tbl([["Chỉ tiêu", "Giá trị"]] + [[k, num(v)] for k, v in lv.items()] + [["Giá hiện tại", num(r.price)]], [10, 4])]
    # ---------- Vĩ mô ----------
    S_ += [P("2. Bối cảnh vĩ mô & thị trường chung", "h"), P(f"Trạng thái thị trường: <b>{reg['regime']}</b> (điểm {reg['score']:.0f}/100)")] + bullets(reg["text"])
    ic = x["idx"]["close"].tail(300)
    fig, ax = plt.subplots(1, 2, figsize=(9, 3), gridspec_kw={"width_ratios": [2, 1]})
    ax[0].plot(ic.index, ic, color=BLUE.hexval().replace("0x", "#"), lw=1.2, label="VN-Index")
    ax[0].plot(ic.index, x["idx"]["close"].rolling(50).mean().tail(300), lw=.9, label="SMA50")
    ax[0].plot(ic.index, x["idx"]["close"].rolling(200).mean().tail(300), lw=.9, label="SMA200"); ax[0].legend(); ax[0].set_title("VN-Index")
    k = ["% mã trên SMA50", "% mã trên SMA200", "% mã tăng giá (phiên cuối)"]
    v = [reg["b50"] * 100, reg["b200"] * 100, reg["adv"] / max(reg["adv"] + reg["dec"], 1) * 100]
    ax[1].barh(k, v, color=["#2e7d32" if a >= 50 else "#c62828" for a in v]); ax[1].axvline(50, color="grey", ls="--"); ax[1].set_xlim(0, 100); ax[1].set_title("Độ rộng thị trường")
    S_.append(img(fig, 5.6))
    if glob:
        S_.append(tbl([["Chỉ báo toàn cầu", "Hiện tại", "1 tháng", "3 tháng"]] + [[k, num(v["last"]), pct(v["1m"]), pct(v["3m"])] for k, v in glob.items()], [7, 3.5, 3, 3.5]))
    # ---------- Ngành ----------
    t = x["ind_table"]
    S_ += [P("3. Phân tích ngành", "h"),
           P(f"Hệ thống phân {len(t)} nhóm ngành từ mẫu các mã cùng ngành và mã đại diện các ngành khác (dữ liệu DNSE). Chỉ số ngành là chỉ số bình quân đều của các mã trong ngành.")]
    if it is not None:
        S_.append(P(f"Ngành <b>{ind_name}</b> xếp hạng <b>{list(t.index).index(ind_name) + 1}/{len(t)}</b>, nhóm <b>{it['rating']}</b>: "
                    f"lợi suất 3 tháng {pct(it['ret3m'])} (so với VN-Index {pct(it['rs3m'])}), {it['a50']:.0%} số mã trên SMA50, "
                    f"thanh khoản 20 phiên {pct(it['flow'], 0)} so với 60 phiên, chiếm {it['share']:.1%} giá trị giao dịch toàn thị trường."))
    top = t.head(10)
    if ind_name in t.index and ind_name not in top.index:
        top = pd.concat([top, t.loc[[ind_name]]])
    rows = [["Ngành", "Số mã", "% 1T", "% 3T", "Vượt VNI 3T", "% mã >SMA50", "Dòng tiền", "Điểm", "Xếp loại"]]
    for g, a in top.iterrows():
        rows.append([g, int(a.n), pct(a.ret1m), pct(a.ret3m), pct(a.rs3m), f"{a.a50:.0%}", pct(a.flow, 0), f"{a.score:.0f}", a.rating])
    S_.append(tbl(rows, [4.5, 1.1, 1.4, 1.4, 1.7, 1.7, 1.5, 1.6, 1.9], hl_row=(list(top.index).index(ind_name) + 1) if ind_name in top.index else None))
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4), gridspec_kw={"width_ratios": [1, 1.2]})
    tt = t.sort_values("rs3m").tail(12); lab = [g[:26] for g in tt.index]
    ax[0].barh(lab, tt.rs3m * 100, color=["#f9a825" if g == ind_name else "#2e7d32" if v > 0 else "#c62828" for g, v in zip(tt.index, tt.rs3m)])
    ax[0].set_title("Vượt/thua VN-Index 3T (%) – 12 ngành đầu"); ax[0].tick_params(axis="y", labelsize=6.5)
    ax[1].plot(ic.index, ic / ic.iloc[0] * 100, color="k", lw=1.2, label="VN-Index")
    for g in list(t.head(3).index) + ([ind_name] if ind_name in t.index and ind_name not in t.head(3).index else []):
        cv = x["curves"][g].reindex(ic.index).ffill(); ax[1].plot(ic.index, cv / cv.dropna().iloc[0] * 100, lw=1, label=g[:22])
    ax[1].legend(fontsize=6); ax[1].set_title("Chỉ số ngành (quy về 100)")
    S_.append(img(fig, 6.2))
    # ---------- Cổ phiếu ----------
    S_ += [PageBreak(), P(f"4. Phân tích cổ phiếu {sym}", "h")]
    d = df.tail(250)
    fig, ax = plt.subplots(3, 1, figsize=(9, 6.2), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]})
    ax[0].plot(d.index, d.close, color="#0d47a1", lw=1.3, label="Giá"); ax[0].plot(d.index, d.sma50, lw=.9, label="SMA50"); ax[0].plot(d.index, d.sma200, lw=.9, label="SMA200")
    ax[0].fill_between(d.index, d.bbl, d.bbu, alpha=.12, color="grey"); ax[0].legend(ncol=3); ax[0].set_title(f"{sym} – giá, SMA, Bollinger (nghìn đồng)")
    ax[1].bar(d.index, d.volume, color="#90a4ae"); ax[1].set_ylabel("KLGD")
    ax[2].plot(d.index, d.rsi, color="purple"); ax[2].axhline(70, c="r", ls="--", lw=.7); ax[2].axhline(30, c="g", ls="--", lw=.7); ax[2].set_ylabel("RSI")
    S_.append(img(fig, 11.2))
    f = x["factors"]
    fig, ax = plt.subplots(figsize=(9, 2.6))
    ax.barh(list(f.index)[::-1], list(f.values)[::-1], color=["#2e7d32" if v >= 60 else "#f9a825" if v >= 40 else "#c62828" for v in list(f.values)[::-1]])
    ax.set_xlim(0, 100); ax.set_title("Điểm từng nhóm yếu tố (0-100, xếp hạng phần trăm trên toàn thị trường)")
    S_.append(img(fig, 4.9))
    S_ += [P("Chỉ tiêu rủi ro – hiệu suất", "h2"),
           tbl([["% 1T", "% 3T", "% 6T", "% 12T", "Biến động", "Beta", "Cách đỉnh 52T", "RSI", "GTGD 20D (tỷ)"],
                [pct(r.ret1m), pct(r.ret3m), pct(r.ret6m), pct(r.ret12m), f"{r.vol:.0%}", num(r.beta), pct(r.dd), num(r.rsi, 0), num(r.gtgd, 1)]],
               [1.6, 1.6, 1.6, 1.6, 1.8, 1.4, 2.4, 1.4, 3.6])]
    fu = x["fund"]
    S_ += [P("Chỉ số cơ bản (nguồn Yahoo Finance, có thể thiếu với một số mã)", "h2"),
           tbl([["P/E", "P/B", "ROE", "Biên LN ròng", "Nợ/Vốn CSH", "Tăng trưởng DT", "Cổ tức"],
                [num(fu.get("trailingPE")), num(fu.get("priceToBook")), pct(fu.get("returnOnEquity")), pct(fu.get("profitMargins")),
                 num(fu.get("debtToEquity")), pct(fu.get("revenueGrowth")), pct(fu.get("dividendYield"))]], [2, 2, 2, 2.6, 2.6, 3.2, 2.6])]
    # ---------- So sánh ngành + cơ hội ----------
    pe = x["peers"]
    S_ += [P("5. So sánh với các mã cùng ngành (theo điểm cơ hội)", "h")]
    S_.append(tbl([["Mã", "Giá", "% 3T", "% 12T", "Biến động", "GTGD (tỷ)", "Điểm"]] +
                  [[i, num(a.price), pct(a.ret3m), pct(a.ret12m), f"{a.vol:.0%}", num(a.gtgd, 1), f"{a.score:.0f}"] for i, a in pe.iterrows()],
                  [2, 2.4, 2.4, 2.4, 2.6, 3, 2.2], hl_row=(list(pe.index).index(sym) + 1) if sym in pe.index else None))
    S_ += [P("6. Mã nổi bật trong mẫu thị trường đã phân tích (thanh khoản ≥ 2 tỷ/phiên)", "h")]
    sc = x["screen"]
    S_.append(tbl([["Mã", "Ngành", "Giá", "% 3T", "% 12T", "Điểm"]] +
                  [[i, str(a.ind)[:34], num(a.price), pct(a.ret3m), pct(a.ret12m), f"{a.score:.0f}"] for i, a in sc.iterrows()], [1.8, 7, 2, 2, 2, 2.2]))
    nw = x["news"]
    if len(nw):
        S_ += [P("7. Tin tức gần đây", "h")] + bullets([f"{a['Tiêu đề']} <font color='grey'>({a['Ngày']})</font>" for _, a in nw.head(8).iterrows()])
    S_ += [P("8. Phương pháp & nguồn dữ liệu", "h"),
           P("Giá/khối lượng: API dữ liệu DNSE (Entrade). Danh sách mã & ngành ICB: vnstock/VNDirect (nếu có) hoặc phân cụm tương quan tự động. "
             "Tin tức: Google News. Vĩ mô toàn cầu & chỉ số cơ bản: Yahoo Finance. Điểm cổ phiếu = 6 nhóm yếu tố xếp hạng phần trăm; "
             "điểm tổng hợp = 70% cổ phiếu + 20% ngành + 10% thị trường ± tin tức. Báo cáo mang tính tham khảo, không phải khuyến nghị đầu tư.", "s")]
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm,
                          title=f"Báo cáo {sym}", author="StockLab VN")
    doc.addPageTemplates([PageTemplate("p", [Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")], onPage=footer)])
    doc.build(S_)
    return buf.getvalue()
