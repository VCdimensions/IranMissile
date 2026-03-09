import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# 頁面設定
st.set_page_config(page_title="Operation Epic Fury 追蹤儀表板", layout="wide", initial_sidebar_state="collapsed")

# 自定義 CSS (GitHub 風格)
st.markdown("""
    <style>
    .stat-card {
        background-color: #f6f8fa;
        border: 1px solid #d0d7de;
        border-radius: 6px;
        padding: 16px;
        text-align: center;
    }
    .stat-card-title {
        color: #57606a;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .stat-card-value {
        color: #0969da;
        font-size: 28px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# 標題與資料限制警告
st.markdown("<h1 style='color: #0969da; border-bottom: 1px solid #d0d7de; padding-bottom: 10px;'>Operation Epic Fury 數據追蹤儀表板 (2026年2月-3月)</h1>", unsafe_allow_html=True)

st.warning("""
**⚠️ 資料限制與推算說明：**
1. **截止時間差異：** UAE、Kuwait 數據更新至 2026/03/08；Bahrain 更新至 03/07；CENTCOM 區域總量預估基於 03/05 簡報。
2. **數據反推 (Deduction)：** 2/28-3/3 數據已校正為 Bloomberg/UAE 國防部之確切發布數值。其他國家多為「累計數字」，逐日趨勢需從總量反推，可能存在誤差。
""")

# --- 數據定義區 (已根據 Bloomberg 圖表校正) ---
dates = ['2/28', '3/1', '3/2', '3/3', '3/4', '3/5', '3/6', '3/7', '3/8']

# 校正 2/28 的飛彈高峰 (約115)，以及 3/1 的無人機高峰 (332)
uae_m = [115, 30, 5, 10, 4, 2, 1, 0, 0] 
uae_d = [210, 332, 135, 110, 45, 20, 10, 5, 2]

# 自動計算總和
uae_m_total = sum(uae_m)
uae_d_total = sum(uae_d)

# --- 統計摘要卡片 ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="stat-card"><div class="stat-card-title">UAE 累計攔截/偵測 (至3/8)</div><div class="stat-card-value">{uae_m_total} 飛彈 / {uae_d_total} 無人機</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown('<div class="stat-card"><div class="stat-card-title">科威特 累計偵測 (至3/8)</div><div class="stat-card-value">234 飛彈 / 422 無人機</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown('<div class="stat-card"><div class="stat-card-title">巴林 累計攔截 (至3/7)</div><div class="stat-card-value">86 飛彈 / 148 無人機</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown('<div class="stat-card"><div class="stat-card-title">區域攻勢衰減率 (Day 1 vs Day 9)</div><div class="stat-card-value" style="color:#1a7f37;">-99% ⬇</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- 準備 DataFrame ---
df_daily = pd.DataFrame({
    '日期': dates,
    '飛彈數量': uae_m,
    '無人機數量': uae_d
})

# 計算環比與衰減
df_daily['飛彈環比(%)'] = df_daily['飛彈數量'].pct_change() * 100
df_daily['無人機環比(%)'] = df_daily['無人機數量'].pct_change() * 100
# 衰減線改以 3/1 的無人機最高點 (332) 為基準計算
df_daily['無人機衰減參考線'] = [round(332 * (0.6 ** i)) for i in range(len(dates))] 

# --- 建立分頁 ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1. UAE 逐日趨勢圖", 
    "2. 多國累計比較", 
    "3. 逐日數據明細表", 
    "4. 三場衝突歷史比較", 
    "5. 來源與備註"
])

# --- 分頁 1: 逐日趨勢圖 ---
with tab1:
    st.subheader("UAE 逐日飛彈與無人機來襲數量 (雙 Y 軸)")
    fig_daily = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig_daily.add_trace(
        go.Bar(x=df_daily['日期'], y=df_daily['飛彈數量'], name='飛彈 (左軸)', marker_color='#cf222e', offsetgroup=1), 
        secondary_y=False
    )
    fig_daily.add_trace(
        go.Bar(x=df_daily['日期'], y=df_daily['無人機數量'], name='無人機 (右軸)', marker_color='#57606a', offsetgroup=2), 
        secondary_y=True
    )
    fig_daily.add_trace(
        go.Scatter(x=df_daily['日期'], y=df_daily['無人機衰減參考線'], name='無人機衰減參考線 (預期)', line=dict(color='#d4a72c', dash='dash')), 
        secondary_y=True
    )
    
    fig_daily.update_layout(
        template="plotly_white", 
        barmode='group', 
        hovermode="x unified", 
        margin=dict(l=20, r=20, t=40, b=20), 
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    # 動態調整 Y 軸高度，保留視覺空間
    max_missile = df_daily['飛彈數量'].max()
    max_drone = df_daily['無人機數量'].max()
    
    fig_daily.update_yaxes(title_text="飛彈數量", range=[0, max_missile * 1.5], secondary_y=False)
    fig_daily.update_yaxes(title_text="無人機數量", range=[0, max_drone * 1.2], secondary_y=True)
    
    st.plotly_chart(fig_daily, use_container_width=True)

# --- 分頁 2: 多國累計比較 ---
with tab2:
    st.subheader("各國面臨之飛彈與無人機累計總量")
    df_compare = pd.DataFrame({
        '國家': ['UAE (3/8)', '科威特 (3/8)', '巴林 (3/7)', '約旦 (估計)', '卡達 (估計)'],
        '累計飛彈': [uae_m_total, 234, 86, 45, 12],
        '累計無人機': [uae_d_total, 422, 148, 80, 30]
    })
    
    fig_compare = go.Figure(data=[
        go.Bar(name='累計飛彈', y=df_compare['國家'], x=df_compare['累計飛彈'], orientation='h', marker_color='#cf222e'),
        go.Bar(name='累計無人機', y=df_compare['國家'], x=df_compare['累計無人機'], orientation='h', marker_color='#57606a')
    ])
    fig_compare.update_layout(template="plotly_white", barmode='group', xaxis_title="發射數量", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_compare, use_container_width=True)

# --- 分頁 3: 數據明細表 ---
with tab3:
    st.subheader("UAE 逐日明細與環比變化 (Day-over-Day)")
    def color_change(val):
        if pd.isna(val): return ''
        return f'color: {"#cf222e" if val > 0 else "#1a7f37"}; font-weight: bold;'

    styled_df = df_daily[['日期', '飛彈數量', '飛彈環比(%)', '無人機數量', '無人機環比(%)']].style \
        .map(color_change, subset=['飛彈環比(%)', '無人機環比(%)']) \
        .format({'飛彈環比(%)': '{:+.1f}%', '無人機環比(%)': '{:+.1f}%'}, na_rep="-")
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

# --- 分頁 4: 歷史比較 ---
with tab4:
    st.subheader("三場衝突首週火力發射量比較")
    st.caption("註: True Promise II (2024/10) 以彈道飛彈為主；12日戰爭 (2025/06) 結合了無人機蜂群；而 Epic Fury (2026/03) 則是面臨聯軍先發制人打擊下的絕望反擊。")
    df_history = pd.DataFrame({
        '衝突事件': ['True Promise II<br>(2024/10)', '12日戰爭<br>(2025/06)', 'Epic Fury<br>(2026/03)'],
        '區域總飛彈量': [180, 300, uae_m_total + 234 + 86 + 45 + 12],
        '區域總無人機量': [0, 500, uae_d_total + 422 + 148 + 80 + 30]
    })
    fig_history = px.bar(df_history, x='衝突事件', y=['區域總飛彈量', '區域總無人機量'], barmode='group', color_discrete_sequence=['#cf222e', '#57606a'])
    fig_history.update_layout(template="plotly_white", yaxis_title="發射數量", legend_title_text="武器類型")
    st.plotly_chart(fig_history, use_container_width=True)

# --- 分頁 5: 來源與備註 ---
with tab5:
