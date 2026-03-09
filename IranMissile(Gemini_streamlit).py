from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Epic Fury Tracker – Streamlit",
    page_icon="📊",
    layout="wide",
)

BLUE = "#0969da"
BLUE_SOFT = "#58a6ff"
BG = "#ffffff"
CARD = "#f6f8fa"
TEXT = "#24292f"
MUTED = "#57606a"
LINE = "#d0d7de"
WARN_BG = "#fff8c5"
WARN_BORDER = "#d4a72c"

st.markdown(
    f"""
    <style>
    .stApp {{ background: {BG}; color: {TEXT}; }}
    .main .block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1360px; }}
    h1, h2, h3 {{ color: {TEXT}; letter-spacing: -0.02em; }}
    div[data-testid="stMetric"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: 10px 14px; }}
    .hero {{ border: 1px solid {LINE}; background: linear-gradient(180deg, #ffffff 0%, {CARD} 100%); border-radius: 18px; padding: 24px; margin-bottom: 18px; }}
    .muted {{ color: {MUTED}; font-size: 0.95rem; }}
    .warning-box {{ margin-top: 14px; border: 1px solid {WARN_BORDER}; background: {WARN_BG}; border-radius: 12px; padding: 12px 14px; font-size: 0.95rem; }}
    .note-box {{ border: 1px solid {LINE}; background: {CARD}; border-radius: 16px; padding: 16px 18px; height: 100%; }}
    .chip-row {{ display:flex; gap:10px; flex-wrap:wrap; margin: 4px 0 10px 0; }}
    .chip {{ border: 1px solid {LINE}; background: white; border-radius: 999px; padding: 7px 11px; font-size: 0.85rem; }}
    .small-muted {{ color: {MUTED}; font-size: 0.84rem; }}
    a {{ color: {BLUE}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    </style>
    """,
    unsafe_allow_html=True,
)

uae_daily = [{'date': '2026-02-28', 'missiles': 137, 'drones': 209, 'missiles_pct': None, 'drones_pct': None, 'note': '官方起始日累計。UAE MoD / WAM 3/1 聲明明載：自攻擊開始以來共偵測 137 枚彈道飛彈、209 架無人機。'}, {'date': '2026-03-01', 'missiles': 28, 'drones': 332, 'missiles_pct': -79.56204379562044, 'drones_pct': 58.851674641148335, 'note': '官方第二天分項。WAM 3/1 文內載明 second day morning 為 20 枚攔截＋8 枚落海；311 架擊落＋21 架落入/擊中。'}, {'date': '2026-03-02', 'missiles': 9, 'drones': 148, 'missiles_pct': -67.85714285714286, 'drones_pct': -55.42168674698795, 'note': '官方逐日公告。另有 6 枚巡弋飛彈遭攔截，但本頁主統計僅納入飛彈/無人機兩類。'}, {'date': '2026-03-03', 'missiles': 12, 'drones': 123, 'missiles_pct': 33.33333333333333, 'drones_pct': -16.8918918918919, 'note': '官方逐日公告。'}, {'date': '2026-03-04', 'missiles': 3, 'drones': 129, 'missiles_pct': -75.0, 'drones_pct': 4.878048780487809, 'note': '官方逐日公告。'}, {'date': '2026-03-05', 'missiles': 7, 'drones': 131, 'missiles_pct': 133.33333333333334, 'drones_pct': 1.5503875968992276, 'note': '官方逐日公告。'}, {'date': '2026-03-06', 'missiles': 9, 'drones': 112, 'missiles_pct': 28.57142857142858, 'drones_pct': -14.503816793893131, 'note': '官方逐日公告。'}, {'date': '2026-03-07', 'missiles': 16, 'drones': 121, 'missiles_pct': 77.77777777777777, 'drones_pct': 8.03571428571428, 'note': '官方逐日公告。'}, {'date': '2026-03-08', 'missiles': 17, 'drones': 117, 'missiles_pct': 6.25, 'drones_pct': -3.3057851239669422, 'note': '官方逐日公告與最新 UAE 累計。'}]
norm_series = [1.0, 1.0405, 0.4538, 0.3902, 0.3815, 0.3988, 0.3497, 0.396, 0.3873]
decay_series = [1.0, 0.8882, 0.7889, 0.7007, 0.6223, 0.5527, 0.4909, 0.436, 0.3873]
countries = [{'country': 'UAE', 'missiles': 238, 'drones': 1422, 'cutoff': '2026-03-08', 'method': '官方累計', 'note': '採 UAE MoD / WAM 3/8 累計。'}, {'country': 'Kuwait', 'missiles': 212, 'drones': 394, 'cutoff': '2026-03-06', 'method': '官方累計', 'note': '採 Kuwait MoD 3/6 對外簡報累計。3/7–3/8 有後續作戰更新，但公開可得來源未提供一致的新累計總表。'}, {'country': 'Bahrain', 'missiles': 95, 'drones': 164, 'cutoff': '2026-03-08', 'method': '官方累計', 'note': '採 Bahrain Defence Force / BNA 經 WAM、QNA 轉載之 3/8 累計。'}, {'country': 'Jordan', 'missiles': 60, 'drones': 59, 'cutoff': '2026-03-07', 'method': '官方累計', 'note': 'Jordan 官方記者會口徑為 119 枚/架，其中 60 rockets、59 drones；本頁將 rockets 歸為飛彈欄。'}, {'country': 'Qatar', 'missiles': 125, 'drones': 43, 'cutoff': '2026-03-08', 'method': '推估累計', 'note': '以 3/3 官方累計（101 飛彈、39 無人機）加上 3/5 日增（14、4）與 3/8 日增（10、0）反推。'}]
history_data = [{'conflict': '2024/10 True Promise II', 'missiles': 200, 'drones': 0, 'label_note': '約數；主要為彈道飛彈齊射'}, {'conflict': '2025/06 12日戰爭', 'missiles': 550, 'drones': 1000, 'label_note': 'IDF / Times of Israel 約數'}, {'conflict': '2026 Epic Fury', 'missiles': 500, 'drones': 2000, 'label_note': 'CENTCOM 口徑為『超過 500 枚飛彈、超過 2,000 架無人機』'}]
source_groups = [{'group': 'UAE（逐日 / 官方）', 'items': [{'title': 'UAE MoD / WAM – 2026-03-01 cumulative + day-two detail', 'url': 'https://www.wam.ae/en/article/byzgpgf-uae-air-defences-intercept-165-ballistic-two', 'use': '用於 3/1 官方 second day 分項（28 missiles / 332 drones）'}, {'title': 'UAE MoD / WAM – 2026-03-02', 'url': 'https://www.wam.ae/en/article/bz0257y-ministry-defense-uae%E2%80%99s-air-defenses-successfully', 'use': '3/2 官方逐日'}, {'title': 'UAE MoD / WAM – 2026-03-03', 'url': 'https://www.wam.ae/en/article/bz0nkqp-uae-air-defences-intercept-ballistic-missiles-123', 'use': '3/3 官方逐日'}, {'title': 'UAE MoD / WAM – 2026-03-04', 'url': 'https://www.wam.ae/en/article/bz190ft-uae-air-defences-intercept-ballistic-missiles-129', 'use': '3/4 官方逐日'}, {'title': 'UAE MoD / WAM – 2026-03-05', 'url': 'https://www.wam.ae/en/article/bz1ufvk-uae-air-defences-intercept-ballistic-missiles-125', 'use': '3/5 官方逐日'}, {'title': 'UAE MoD / WAM – 2026-03-06', 'url': 'https://www.wam.ae/en/article/bz2fvh8-uae-air-defences-intercept-nine-ballistic', 'use': '3/6 官方逐日'}, {'title': 'UAE MoD / WAM – 2026-03-07', 'url': 'https://www.wam.ae/en/article/bz31axa-uae-air-defences-intercept-ballistic-missiles-119', 'use': '3/7 官方逐日'}, {'title': 'UAE MoD / WAM – 2026-03-08', 'url': 'https://www.wam.ae/en/article/bz3mqg3-uae-air-defences-intercept-ballistic-missiles-113', 'use': '3/8 官方逐日與最新 UAE 累計'}, {'title': 'UAE MoD / WAM – 2026-02-28 opening-day cumulative', 'url': 'https://www.wam.ae/en/article/173jo13-uae-air-defences-intercept-137-missiles-209-drones', 'use': '2/28 官方起始日累計（137 missiles / 209 drones）'}]}, {'group': 'Kuwait（累計 / 官方）', 'items': [{'title': 'Kuwait MoD via QNA – 2026-03-06 cumulative', 'url': 'https://qna.org.qa/en/news/news-details?id=kuwaiti-defense-ministry-two-killed-67-injured-among-armed-forces-since-start-of-operations&date=6/03/2026', 'use': '212 missiles / 394 drones cumulative'}, {'title': 'KUNA – 2026-03-01 snippet', 'url': 'https://www.kuna.net.kw/ArticleDetails.aspx?id=3278224&language=en', 'use': '97 missiles / 283 drones prior cumulative checkpoint'}, {'title': 'KUNA – 2026-03-02 snippet', 'url': 'https://www.kuna.net.kw/ArticleDetails.aspx?id=3278843&language=en', 'use': '178 missiles / 384 drones prior cumulative checkpoint'}]}, {'group': 'Bahrain（累計 / 官方）', 'items': [{'title': 'Bahrain Defence Force / BNA via WAM – 2026-03-08 cumulative', 'url': 'https://www.wam.ae/en/article/bz3mqg4-bahrain-defence-force-general-command-missiles-164', 'use': '95 missiles / 164 drones cumulative'}, {'title': 'QNA relay – 2026-03-09', 'url': 'https://qna.org.qa/en/News-Area/News/2026-3/9/bahrain-says-95-missiles-164-drones-destroyed-since-start-of-iranian-attacks', 'use': '確認最新可見轉載數字未變'}]}, {'group': 'Jordan（累計 / 官方）', 'items': [{'title': 'Jordan Times quoting Brig. Gen. Mustafa Hiyari – 2026-03-07', 'url': 'https://jordantimes.com/news/local/army-downs-108-of-119-missiles-drones-targeting-vital-facilities-hiyari', 'use': '60 rockets / 59 drones cumulative'}, {'title': 'QNA relay – 2026-03-07', 'url': 'https://qna.org.qa/en/News-Area/News/2026-3/7/jordan-reports-engaging-119-missiles-drones-in-one-week', 'use': '交叉核對 119 total'}]}, {'group': 'Qatar（累計 / 推估）', 'items': [{'title': 'Qatar MoD / QNA cumulative summary – 2026-03-03', 'url': 'https://qna.org.qa/en/news/news-details?id=ministry-of-defense-unveils-summary-of-total-attacks-since-start-of-iranian-aggression&date=3/03/2026', 'use': '101 ballistic missiles / 39 drones cumulative baseline'}, {'title': 'Qatar MoD / QNA daily – 2026-03-05', 'url': 'https://qna.org.qa/en/News-Area/News/2026-3/5/ministry-of-defense-announces-interception-of-13-ballistic-missiles-four-drones-with-no-casualties', 'use': '+14 ballistic missiles / +4 drones'}, {'title': 'Qatar MoD / QNA daily – 2026-03-08', 'url': 'https://qna.org.qa/en/news/news-details?id=ministry-of-defense-intercepts-6-ballistic-missiles-2-cruise-missiles-without-casualties&date=8/03/2026', 'use': '+10 ballistic missiles / +0 drones'}]}, {'group': 'CENTCOM / FDD / 歷史比較', 'items': [{'title': 'DefenseScoop quoting CENTCOM Adm. Brad Cooper video – 2026-03-04', 'url': 'https://defensescoop.com/2026/03/04/iranian-attack-drone-launches-decrease-operation-epic-fury/', 'use': 'Epic Fury regional total >500 ballistic missiles and >2,000 drones'}, {'title': 'CENTCOM official press release – 2026-02-28', 'url': 'https://www.centcom.mil/MEDIA/PRESS-RELEASES/Press-Release-View/Article/4418396/us-forces-launch-operation-epic-fury/', 'use': '官方僅稱 defended against hundreds of missile and drone attacks'}, {'title': 'FDD – Why Iran’s ballistic missile launches are declining', 'url': 'https://www.fdd.org/analysis/2026/03/04/why-irans-ballistic-missile-launches-are-declining/', 'use': '彈道飛彈發射趨勢與歷史比較'}, {'title': 'U.S. DoD – Oct. 1, 2024 approximately 200 ballistic missiles', 'url': 'https://www.war.gov/News/News-Stories/Article/Article/3923123/us-assets-in-mediterranean-again-helped-defend-israel-against-iranian-missiles/', 'use': 'True Promise II 參考值'}, {'title': 'Times of Israel – Jun. 2025 war by the numbers', 'url': 'https://www.timesofisrael.com/the-israel-iran-war-by-the-numbers-after-12-days-of-fighting/', 'use': '12-day war 約 550 ballistic missiles / 約 1,000 drones'}]}]

df_daily = pd.DataFrame(uae_daily)
df_countries = pd.DataFrame(countries)
df_history = pd.DataFrame(history_data)

def pct_str(v):
    if pd.isna(v):
        return "—"
    return f"{v:+.1f}%"

def fmt_int(v):
    return f"{int(v):,}"

sum_missiles = int(df_daily['missiles'].sum())
sum_drones = int(df_daily['drones'].sum())
df_daily['total'] = df_daily['missiles'] + df_daily['drones']
peak_row = df_daily.loc[df_daily['total'].idxmax()]
country_total_m = int(df_countries['missiles'].sum())
country_total_d = int(df_countries['drones'].sum())
cutoff_label = " · ".join([f"{r.country}:{r.cutoff[5:]}" for r in df_countries.itertuples()])

st.markdown("""
<div class="hero">
  <h1>Operation Epic Fury：2026/02/28–03/08 伊朗飛彈 / 無人機統計追蹤</h1>
  <div class="muted">Streamlit 原生部署版本，整合 UAE 逐日官方公告、多國累計比較、逐日數據表、三場衝突歷史比較與來源連結。</div>
  <div class="warning-box"><strong>資料限制警告：</strong> 各國官方公布的截止時間不同，且公開口徑並不一致。UAE 為逐日官方公告；Kuwait、Bahrain、Jordan 多為累計口徑；Qatar 的最新累計需由 3/3 官方累計加上 3/5、3/8 逐日公告反推。比較圖請視為「截至各自最新可驗證 cutoff 的並列快照」，不可直接視為同一時間點的精確同步截面。</div>
</div>
""", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("UAE 累計飛彈（2/28–3/8）", fmt_int(sum_missiles), help="逐日官方統計合計")
m2.metric("UAE 累計無人機（2/28–3/8）", fmt_int(sum_drones), help="逐日官方統計合計")
m3.metric("UAE 峰值日", peak_row['date'][5:], help=f"{int(peak_row['missiles'])} 枚飛彈 / {int(peak_row['drones'])} 架無人機")
m4.metric("CENTCOM 區域總量（下限）", ">2,500", help=">500 missiles + >2,000 drones")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["1. Epic Fury 逐日圖表", "2. 多國比較", "3. 數據表", "4. 三場衝突歷史比較", "5. 來源連結"])

with tab1:
    left, right = st.columns([2, 1])
    with left:
        st.subheader("UAE 逐日圖表（2026/02/28–03/08）")
        st.caption("雙 Y 軸 bar chart：左軸 = 飛彈、右軸 = 無人機；另加上 normalized 日總量折線與指數衰減參考線，起點改為 2026/02/28。")
        fig = go.Figure()
        x = [d['date'][5:] for d in uae_daily]
        fig.add_bar(x=x, y=[d['missiles'] for d in uae_daily], name='飛彈（左軸）', marker_color=BLUE, yaxis='y')
        fig.add_bar(x=x, y=[d['drones'] for d in uae_daily], name='無人機（右軸）', marker_color=BLUE_SOFT, opacity=0.70, yaxis='y2')
        fig.add_trace(go.Scatter(x=x, y=norm_series, name='Normalized 日總量', mode='lines+markers', line=dict(color=TEXT, width=2), marker=dict(size=7), yaxis='y3'))
        fig.add_trace(go.Scatter(x=x, y=decay_series, name='指數衰減參考線', mode='lines', line=dict(color='#9a6700', width=2, dash='dash'), yaxis='y3'))
        fig.update_layout(barmode='group', paper_bgcolor=BG, plot_bgcolor=BG, hovermode='x unified', legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0), margin=dict(l=30, r=30, t=25, b=20), xaxis=dict(gridcolor='#eaeef2', linecolor=LINE), yaxis=dict(title='飛彈', gridcolor='#eaeef2', linecolor=LINE, rangemode='tozero'), yaxis2=dict(title='無人機', overlaying='y', side='right', showgrid=False, rangemode='tozero'), yaxis3=dict(title='Normalized', overlaying='y', side='right', position=0.94, showgrid=False, range=[0, 1.08]), height=520)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("""
        <div class="note-box">
          <h3>圖表解讀</h3>
          <ul>
            <li><strong>3/1 為高峰：</strong> 2/28 官方起始日為 137 枚飛彈、209 架無人機；3/1 第二天分項升至 28 枚飛彈、332 架無人機，單日總量 360 為目前全序列峰值。</li>
            <li><strong>之後快速鈍化：</strong> UAE 日總量從 3/1 的 360，降至 3/8 的 134；若以 2/28 為基準，normalized 由 1.00 先升至 1.04，之後回落至 0.39。</li>
            <li><strong>指數衰減線</strong> 僅為參考框架，方便觀察實際攻勢是否高於 / 低於單純衰減路徑，並非預測模型。</li>
          </ul>
        </div>
        <div class="note-box" style="margin-top:14px;">
          <h3>方法註記</h3>
          <ul>
            <li>本頁「飛彈」欄優先指彈道飛彈；若官方單獨列出巡弋飛彈，另在備註說明，不併入雙欄主統計。</li>
            <li>2/28 為官方起始日累計；3/1 為官方文內明示的 second day 分項，不需再由差額反推。</li>
            <li>normalized = 當日（飛彈 + 無人機）÷ 2/28 當日（飛彈 + 無人機）。</li>
            <li>指數衰減參考線以 2/28 與 3/8 兩端點校準。</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)

with tab2:
    st.subheader("多國比較（截至各國最新可驗證 cutoff）")
    st.caption("橫向 bar chart；UAE 為官方 3/8 累計，Kuwait 採 3/6 官方累計，Bahrain 採 3/8 官方累計，Jordan 採 3/7 官方記者會，Qatar 採 3/3 官方累計 + 3/5、3/8 日報反推。")
    st.markdown(f"<div class='chip-row'><div class='chip'>已追蹤國家合計飛彈：<strong>{country_total_m:,}</strong></div><div class='chip'>已追蹤國家合計無人機：<strong>{country_total_d:,}</strong></div><div class='chip'>cutoff：<strong>{cutoff_label}</strong></div></div>", unsafe_allow_html=True)
    compare = go.Figure()
    compare.add_bar(y=df_countries['country'], x=df_countries['missiles'], name='飛彈', orientation='h', marker_color=BLUE)
    compare.add_bar(y=df_countries['country'], x=df_countries['drones'], name='無人機', orientation='h', marker_color=BLUE_SOFT)
    compare.update_layout(barmode='group', paper_bgcolor=BG, plot_bgcolor=BG, hovermode='y unified', legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0), margin=dict(l=20, r=20, t=10, b=20), xaxis=dict(gridcolor='#eaeef2', linecolor=LINE, title='累計數量'), yaxis=dict(linecolor=LINE), height=480)
    st.plotly_chart(compare, use_container_width=True)
    show_df = df_countries.copy()
    show_df.columns = ['國家', '飛彈累計', '無人機累計', '截止時間', '方法', '備註']
    st.dataframe(show_df, use_container_width=True, hide_index=True)
    st.warning("UAE 是逐日數字，其他國家多為累計；Qatar 的 D3 之後需由累計基準加上後續日報反推。請勿將各國數字視為完全同步的同一時點截面。")

with tab3:
    st.subheader("UAE 逐日明細表（含 2/28 起始日）")
    st.caption("含飛彈 / 無人機日數與環比變化。可輸入關鍵字篩選日期或備註。")
    keyword = st.text_input("篩選關鍵字", placeholder="例如：巡弋、反推、2026-03-06", key='daily_filter')
    daily_show = df_daily.copy()
    daily_show['飛彈環比'] = daily_show['missiles_pct'].apply(pct_str)
    daily_show['無人機環比'] = daily_show['drones_pct'].apply(pct_str)
    daily_show = daily_show.rename(columns={'date':'日期','missiles':'飛彈','drones':'無人機','note':'備註'})
    daily_show = daily_show[['日期','飛彈','飛彈環比','無人機','無人機環比','備註']]
    if keyword.strip():
        mask = daily_show.apply(lambda s: s.astype(str).str.contains(keyword, case=False, regex=False)).any(axis=1)
        daily_show = daily_show[mask]
    st.dataframe(daily_show, use_container_width=True, hide_index=True)
    st.markdown("<div class='small-muted'>註：2/28 為官方起始日累計；3/1 為官方 second day 分項；3/2 官方另有 6 枚巡弋飛彈遭攔截，但主統計未併入飛彈欄。</div>", unsafe_allow_html=True)

with tab4:
    st.subheader("三場衝突歷史比較")
    st.caption("2026 Epic Fury 採 CENTCOM 相關公開口徑的下限值；與 2024/10、2025/06 的地理範圍與統計口徑並非完全相同，宜視為規模級距比較。")
    hist = go.Figure()
    hist.add_bar(x=df_history['conflict'], y=df_history['missiles'], name='飛彈', marker_color=BLUE)
    hist.add_bar(x=df_history['conflict'], y=df_history['drones'], name='無人機', marker_color=BLUE_SOFT)
    hist.update_layout(barmode='group', paper_bgcolor=BG, plot_bgcolor=BG, hovermode='x unified', legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0), margin=dict(l=20, r=20, t=10, b=20), xaxis=dict(linecolor=LINE), yaxis=dict(gridcolor='#eaeef2', linecolor=LINE, title='數量'), height=460)
    st.plotly_chart(hist, use_container_width=True)
    hist_show = df_history.copy()
    hist_show.columns = ['衝突', '飛彈', '無人機', '備註']
    st.dataframe(hist_show, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("來源連結")
    st.caption("列出本頁使用或交叉核對的核心來源。可用關鍵字過濾，例如輸入 UAE、Kuwait、CENTCOM、FDD。")
    q = st.text_input("來源關鍵字", placeholder="UAE / Kuwait / CENTCOM / FDD", key='source_filter').strip().lower()
    count = 0
    for group in source_groups:
        items = []
        for item in group['items']:
            hay = f"{group['group']} {item['title']} {item['use']} {item['url']}".lower()
            if not q or q in hay:
                items.append(item)
        if not items:
            continue
        st.markdown(f"### {group['group']}")
        for item in items:
            count += 1
            st.markdown(f"<div class='note-box' style='margin-bottom:10px;'><div><a href='{item['url']}' target='_blank'>{item['title']}</a></div><div class='small-muted'>{item['use']}</div></div>", unsafe_allow_html=True)
    if count == 0:
        st.info("沒有符合的來源，請換個關鍵字。")

st.markdown("<div class='small-muted' style='margin-top:14px;'>部署提醒：上傳到 Streamlit Community Cloud 時，主程式請選 app.py；theme 已透過 .streamlit/config.toml 預設為白底藍色系。</div>", unsafe_allow_html=True)
