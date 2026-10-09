"""StockLab VN - chạy: streamlit run app.py"""
import datetime as dt
import numpy as np, pandas as pd, streamlit as st
import plotly.express as px, plotly.graph_objects as go
from plotly.subplots import make_subplots
import core
from report import make_report

st.set_page_config(page_title="StockLab VN", page_icon="📈", layout="wide")
st.markdown("""<style>.hdr{background:#0d47a1;color:#fff;padding:10px 18px;border-radius:6px;font-size:21px;font-weight:700}
.sub{font-size:13px;font-weight:400;opacity:.85}.tag{display:inline-block;padding:2px 10px;border-radius:12px;background:#e8f0fe;color:#0d47a1;font-weight:600}
</style><div class="hdr">📈 StockLab VN <span class="sub">– Vĩ mô · Ngành · Cơ hội đầu tư toàn thị trường (dữ liệu DNSE)</span></div>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_glob(): return core.global_macro()
@st.cache_data(show_spinner=False, ttl=900)
def cached_news(s): return core.get_news(s)
@st.cache_data(show_spinner=False, ttl=86400)
def cached_fund(s): return core.get_fund(s)


# ---------------- Sidebar & dữ liệu ----------------
with st.sidebar:
    st.header("Dữ liệu")
    refresh = st.button("🔄 Tải lại toàn bộ dữ liệu DNSE", use_container_width=True)
    mode = st.radio("Cách phân ngành", ["ICB (chuẩn)", "Tự động theo tương quan giá"])
    k = st.slider("Số cụm (khi phân tự động)", 8, 30, 18)
    min_liq = st.number_input("Lọc thanh khoản tối thiểu (tỷ/phiên)", 0.0, 100.0, 2.0)

if "data" not in st.session_state or refresh:
    bar = st.progress(0.0, "Đang tải dữ liệu toàn thị trường từ DNSE (lần đầu mất vài phút, sau đó dùng cache 12 giờ)...")
    try:
        st.session_state["data"] = core.load_market(refresh=refresh, progress=lambda p: bar.progress(p))
    except Exception as e:
        bar.empty(); st.error(str(e)); st.stop()
    bar.empty()
data = st.session_state["data"]
close, idx = data["close"], data["idx"]
ind, val = core.assign_industry(data, "ICB" if mode.startswith("ICB") else "AUTO", k)
m = core.build_metrics(close, val, idx)
factors, score = core.score_stocks(m, ind)
m["score"], m["ind"] = score, ind.reindex(m.index)
it_all, curves = core.industry_table(close, val, m, ind, idx)
glob = cached_glob()
reg = core.macro_view(idx, close, m, val, glob)
asof = close.index[-1]
st.caption(f"{close.shape[1]:,} cổ phiếu có dữ liệu · {len(it_all)} nhóm ngành · phiên cuối {asof:%d/%m/%Y}")

c = st.columns(5)
i1 = idx["close"]
c[0].metric("VN-Index", f"{i1.iloc[-1]:,.1f}", f"{i1.iloc[-1] / i1.iloc[-2] - 1:+.2%}")
c[1].metric("Tăng / Giảm", f"{reg['adv']} / {reg['dec']}")
c[2].metric("% mã trên SMA50", f"{reg['b50']:.0%}")
c[3].metric("Điểm thị trường", f"{reg['score']:.0f}/100")
c[4].metric("Trạng thái", reg["regime"])

tabs = st.tabs(["🌐 Vĩ mô & Thị trường", "🏭 Ngành", "🔎 Cổ phiếu", "🎯 Bộ lọc cơ hội", "📄 Báo cáo PDF"])

# ---------------- Tab 1: vĩ mô ----------------
with tabs[0]:
    a, b = st.columns([3, 2])
    with a:
        h = m[m.gtgd >= max(min_liq, .5)].reset_index(names="Mã")
        fig = px.treemap(h, path=[px.Constant("Thị trường"), "ind", "Mã"], values="gtgd", color="ret1d", color_continuous_scale="RdYlGn",
                         range_color=(-.07, .07))
        fig.update_layout(height=520, margin=dict(l=0, r=0, t=25, b=0), title="Bản đồ nhiệt thị trường (kích thước = GTGD, màu = % 1 ngày)")
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.subheader("Nhận định vĩ mô")
        for t in reg["text"]:
            st.write("• " + t)
        if glob:
            st.dataframe(pd.DataFrame(glob).T.rename(columns={"last": "Hiện tại", "1m": "1 tháng", "3m": "3 tháng"})
                         .style.format({"Hiện tại": "{:,.2f}", "1 tháng": "{:+.1%}", "3 tháng": "{:+.1%}"}), use_container_width=True)
    ic = idx.tail(300)
    f2 = go.Figure(go.Candlestick(x=ic.index, open=ic.open, high=ic.high, low=ic.low, close=ic.close, name="VN-Index"))
    f2.add_trace(go.Scatter(x=ic.index, y=idx.close.rolling(50).mean().tail(300), name="SMA50"))
    f2.add_trace(go.Scatter(x=ic.index, y=idx.close.rolling(200).mean().tail(300), name="SMA200"))
    f2.update_layout(height=380, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=20, b=0)); st.plotly_chart(f2, use_container_width=True)

# ---------------- Tab 2: ngành ----------------
with tabs[1]:
    show = it_all.rename(columns={"n": "Số mã", "a50": "% mã >SMA50", "gtgd": "GTGD (tỷ)", "vol": "Biến động", "flow": "Dòng tiền", "ret1m": "% 1T",
                                  "ret3m": "% 3T", "ret6m": "% 6T", "rs1m": "Vượt VNI 1T", "rs3m": "Vượt VNI 3T", "score": "Điểm", "share": "Tỷ trọng GTGD", "rating": "Xếp loại"})
    st.dataframe(show.style.format({"% mã >SMA50": "{:.0%}", "GTGD (tỷ)": "{:,.0f}", "Biến động": "{:.0%}", "Dòng tiền": "{:+.0%}", "% 1T": "{:+.1%}", "% 3T": "{:+.1%}",
                                    "% 6T": "{:+.1%}", "Vượt VNI 1T": "{:+.1%}", "Vượt VNI 3T": "{:+.1%}", "Điểm": "{:.0f}", "Tỷ trọng GTGD": "{:.1%}"})
                 .background_gradient(subset=["Điểm"], cmap="RdYlGn"), use_container_width=True, height=420)
    a, b = st.columns(2)
    q = it_all.reset_index()
    a.plotly_chart(px.scatter(q, x="rs3m", y="rs1m", size="gtgd", color="rating", hover_name="Ngành", title="Vòng xoay ngành: vượt VN-Index 3T (x) vs 1T (y)")
                   .add_hline(y=0).add_vline(x=0), use_container_width=True)
    sel = b.multiselect("So sánh chỉ số ngành", list(it_all.index), default=list(it_all.index[:3]))
    f3 = go.Figure()
    for g in sel:
        f3.add_trace(go.Scatter(x=curves[g].tail(250).index, y=curves[g].tail(250) / curves[g].tail(250).iloc[0] * 100, name=g[:30]))
    f3.add_trace(go.Scatter(x=idx.tail(250).index, y=idx.close.tail(250) / idx.close.tail(250).iloc[0] * 100, name="VN-Index", line=dict(color="black", dash="dot")))
    b.plotly_chart(f3, use_container_width=True)

# ---------------- Tab 3: cổ phiếu ----------------
with tabs[2]:
    syms = sorted(close.columns)
    sym = st.selectbox("Mã cổ phiếu (toàn bộ mã có dữ liệu DNSE)", syms, index=syms.index("FPT") if "FPT" in syms else 0)
    df = core.add_ind(data["raw"][sym]); r = m.loc[sym]; ind_name = ind[sym]
    it = it_all.loc[ind_name] if ind_name in it_all.index else None
    f = cached_fund(sym); nw = cached_news(sym); ns = nw["Điểm"].sum() if len(nw) else 0
    total, rec = core.combine(score[sym], it["score"] if it is not None else 50, reg["score"], ns)
    pros, cons = core.thesis(sym, m, factors.loc[sym], ind_name, it, reg, core.levels(df), f, ns)
    c = st.columns(5)
    c[0].metric(f"{sym} (nghìn đ)", f"{r.price:,.2f}", f"{r.ret1d:+.2%}")
    c[1].metric("Điểm cổ phiếu", f"{score[sym]:.0f}"); c[2].metric("Điểm ngành", f"{it['score']:.0f}" if it is not None else "n/a")
    c[3].metric("ĐIỂM TỔNG HỢP", f"{total:.0f}/100"); c[4].metric("Đánh giá", rec.split(" – ")[0])
    st.markdown(f"Ngành: <span class='tag'>{ind_name}</span> · xếp hạng ngành {list(it_all.index).index(ind_name) + 1 if it is not None else '-'}/{len(it_all)}", unsafe_allow_html=True)
    d = df.tail(300)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[.6, .2, .2], vertical_spacing=.03)
    fig.add_trace(go.Candlestick(x=d.index, open=d.open, high=d.high, low=d.low, close=d.close, name=sym), 1, 1)
    for w in (20, 50, 200):
        fig.add_trace(go.Scatter(x=d.index, y=d[f"sma{w}"], name=f"SMA{w}", line=dict(width=1)), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.bbu, line=dict(width=.5, dash="dot", color="gray"), name="BB"), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.bbl, line=dict(width=.5, dash="dot", color="gray"), showlegend=False), 1, 1)
    fig.add_trace(go.Bar(x=d.index, y=d.volume, name="KLGD", marker_color="#90a4ae"), 2, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.rsi, name="RSI"), 3, 1); fig.add_hline(y=70, line_dash="dash", row=3, col=1); fig.add_hline(y=30, line_dash="dash", row=3, col=1)
    fig.update_layout(height=640, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=20, b=0)); st.plotly_chart(fig, use_container_width=True)
    a, b = st.columns(2)
    a.subheader("✅ Điểm hỗ trợ"); [a.write("• " + x) for x in pros]
    b.subheader("⚠️ Rủi ro"); [b.write("• " + x) for x in cons]
    a, b = st.columns(2)
    fs = factors.loc[sym].rename("Điểm").reset_index().rename(columns={"index": "Yếu tố"})
    a.plotly_chart(px.bar(fs, x="Điểm", y="Yếu tố", orientation="h", range_x=[0, 100], title="Điểm theo nhóm yếu tố"), use_container_width=True)
    b.subheader("Vùng giá tham khảo"); b.table(pd.Series(core.levels(df)).map("{:,.2f}".format).rename("Nghìn đồng"))
    peers = m[(m.ind == ind_name) & (m.gtgd >= .5)].sort_values("score", ascending=False).head(10)
    if sym not in peers.index:
        peers = pd.concat([peers, m.loc[[sym]]])
    st.subheader("So sánh cùng ngành"); st.dataframe(peers[["price", "ret1m", "ret3m", "ret12m", "vol", "beta", "gtgd", "score"]].rename(columns=core.LABEL)
        .style.format({"Giá": "{:,.2f}", "% 1 tháng": "{:+.1%}", "% 3 tháng": "{:+.1%}", "% 12 tháng": "{:+.1%}", "Biến động": "{:.0%}", "Beta": "{:.2f}", "GTGD 20D (tỷ)": "{:,.1f}", "Điểm": "{:.0f}"}), use_container_width=True)
    st.subheader("Chỉ số cơ bản"); st.write({k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()})
    st.subheader("Tin tức")
    for _, n in nw.iterrows():
        st.markdown(f"{'🟢' if n['Điểm'] > 0 else '🔴' if n['Điểm'] < 0 else '⚪'} [{n['Tiêu đề']}]({n['Link']})")

# ---------------- Tab 4: bộ lọc ----------------
with tabs[3]:
    cols = st.columns(4)
    sel_ind = cols[0].multiselect("Ngành", list(it_all.index))
    min_sc = cols[1].slider("Điểm tối thiểu", 0, 100, 60)
    only_up = cols[2].checkbox("Chỉ mã trên SMA50 & SMA200", True)
    rsi_max = cols[3].slider("RSI tối đa", 30, 100, 75)
    s = m[(m.gtgd >= min_liq) & (m.score >= min_sc) & (m.rsi <= rsi_max)]
    if sel_ind: s = s[s.ind.isin(sel_ind)]
    if only_up: s = s[(s.a50 == 1) & (s.a200 == 1)]
    s = s.sort_values("score", ascending=False)
    st.write(f"**{len(s)}** mã thỏa điều kiện")
    st.dataframe(s[["ind", "price", "ret1m", "ret3m", "ret12m", "vol", "rsi", "gtgd", "flow", "score"]].rename(columns={**core.LABEL, "ind": "Ngành"})
                 .style.format({"Giá": "{:,.2f}", "% 1 tháng": "{:+.1%}", "% 3 tháng": "{:+.1%}", "% 12 tháng": "{:+.1%}", "Biến động": "{:.0%}", "RSI": "{:.0f}",
                                "GTGD 20D (tỷ)": "{:,.1f}", "Dòng tiền (20D/60D)": "{:+.0%}", "Điểm": "{:.0f}"}).background_gradient(subset=["Điểm"], cmap="RdYlGn"),
                 use_container_width=True, height=560)

# ---------------- Tab 5: PDF ----------------
with tabs[4]:
    st.write(f"Báo cáo PDF cho **{sym}**: tóm tắt & luận điểm, vĩ mô, phân tích ngành, kỹ thuật, rủi ro, so sánh cùng ngành, top cơ hội, tin tức.")
    if st.button("Tạo báo cáo PDF", type="primary"):
        with st.spinner("Đang dựng báo cáo..."):
            scr = m[m.gtgd >= 2].sort_values("score", ascending=False).head(10)
            pdf = make_report(dict(sym=sym, df=df, m=m, ind_name=ind_name, it=it, reg=reg, glob=glob, idx=idx, asof=asof, fund=f, news=nw,
                                   stock_score=score[sym], total=total, rec=rec, pros=pros, cons=cons, lv=core.levels(df), factors=factors.loc[sym],
                                   ind_table=it_all, curves=curves, peers=peers, screen=scr))
        st.download_button("⬇️ Tải PDF", pdf, f"BaoCao_{sym}_{dt.date.today():%Y%m%d}.pdf", "application/pdf")
