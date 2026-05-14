import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, date
from streamlit_gsheets import GSheetsConnection

# =====================================================================
# 시스템 설정, DB 연동 및 실시간 리밸런싱 관제
# =====================================================================

# 1. 페이지 설정 및 네온 테마 (Dark Mode)
st.set_page_config(page_title="SHABAL: SHANNON'S REBALANCING", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');
    [data-testid="stAppViewContainer"] { background-color: #0E1117; color: #FFFFFF; }
    [data-testid="stSidebar"] { background-color: #161B22; border-right: 1px solid #00F3FF; }
    h1, h2, h3, .stMetric label { font-family: 'Orbitron', sans-serif; color: #00F3FF; text-shadow: 0 0 5px #00F3FF; }
    .stButton>button { background-color: transparent; color: #00F3FF; border: 2px solid #00F3FF; font-weight: bold; width: 100%; border-radius: 0; }
    .stButton>button:hover { background-color: #00F3FF; color: #0E1117; box-shadow: 0 0 20px #00F3FF; }
    .instruction-card { background: linear-gradient(135deg, #161B22 0%, #0E1117 100%); border: 1px solid #39FF14; padding: 25px; border-radius: 5px; margin: 10px 0; box-shadow: 0 0 15px rgba(57,255,20,0.2); }
    .neon-blue { color: #00F3FF; text-shadow: 0 0 5px #00F3FF; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# 2. DB 연동 및 데이터 타입 보정
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_and_fix_data():
    try:
        holdings = conn.read(worksheet="Current_Holdings")
        trade_log = conn.read(worksheet="Trade_Log")
        
        if holdings.empty:
            holdings = pd.DataFrame(columns=['시장', '구분', '종목', '티커', '수량', '현재가'])
        if trade_log.empty:
            trade_log = pd.DataFrame(columns=['Date', 'Ticker', 'Action', 'Quantity', 'Buy_Price', 'Sell_Price', 'Fees', 'Currency', 'Realized_Profit', 'Note'])

        if 'Date' in trade_log.columns:
            trade_log['Date'] = pd.to_datetime(trade_log['Date'], errors='coerce').dt.date
            
        numeric_cols = ['Quantity', 'Buy_Price', 'Sell_Price', 'Fees', 'Realized_Profit']
        for col in numeric_cols:
            if col in trade_log.columns:
                trade_log[col] = pd.to_numeric(trade_log[col], errors='coerce').fillna(0.0)
                
        return holdings, trade_log
    except Exception as e:
        st.error(f"DB 로딩 오류: {e}")
        return pd.DataFrame(), pd.DataFrame()

holdings_df, trade_log_df = load_and_fix_data()

# 3. 사이드바: 🎛️ CONTROL PANEL & 통합 자산 관리
with st.sidebar:
    st.title("🎛️ CONTROL PANEL")
    usd_krw_live = st.number_input("현재 환율 (USD/KRW)", value=1380.0, step=1.0)
    monthly_cash = st.number_input("당월 적립액 (KRW)", value=2500000, step=100000)
    
    st.divider()
    st.subheader("📋 통합 자산 관리")
    edited_holdings = st.data_editor(
        holdings_df,
        num_rows="dynamic",
        key="holdings_editor",
        use_container_width=True,
        column_config={
            "시장": st.column_config.SelectboxColumn("시장", options=["해외", "국내"]),
            "구분": st.column_config.SelectboxColumn("구분", options=["Leverage", "Dividend", "예수현금"]),
            "종목": st.column_config.TextColumn("종목"),
            "티커": st.column_config.TextColumn("티커"),
            "수량": st.column_config.NumberColumn("수량", min_value=0.0),
            "현재가": st.column_config.NumberColumn("현재가", min_value=0.0),
        }
    )
    
    if st.button("💾 Sync Holdings to DB"):
        conn.update(worksheet="Current_Holdings", data=edited_holdings)
        st.success("자산 현황 동기화 완료!")
        st.cache_data.clear()

# 4. 코어 엔진 로직
def run_shabal_logic(df, cash_krw, rate):
    val_lev, val_div, val_cash = 0.0, 0.0, 0.0
    if not df.empty:
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0.0)
        df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce').fillna(0.0)
        
        df['Value_KRW'] = df.apply(lambda x: x['수량'] * x['현재가'] * (rate if x['시장'] == "해외" else 1.0), axis=1)
        val_lev = df[df['구분'] == 'Leverage']['Value_KRW'].sum()
        val_div = df[df['구분'] == 'Dividend']['Value_KRW'].sum()
        val_cash = df[df['구분'] == '예수현금']['Value_KRW'].sum()
    
    shannon_total = val_lev + val_div
    total_asset = shannon_total + val_cash
    drift_lev = ((shannon_total + cash_krw) * 0.8) - val_lev
    cur_ratio = (val_lev / shannon_total * 100) if shannon_total > 0 else 80.0
    return total_asset, cur_ratio, drift_lev

total_asset_krw, cur_ratio, drift_lev = run_shabal_logic(edited_holdings, monthly_cash, usd_krw_live)


# =====================================================================
# 시각화 대시보드 및 정렬된 Serial Portfolio Analysis
# =====================================================================

st.title("⚡ SHABAL: SHANNON'S REBALANCING")

col_m1, col_m2 = st.columns([1.5, 1])
with col_m1:
    goal_amt = st.number_input("🎯 2031 목표 확보액 (KRW)", value=250000000, step=10000000)
with col_m2:
    st.metric("D-DAY TO 2031", f"{(date(2031,12,31)-date.today()).days} Days")

st.divider()

t1, t2 = st.columns([1, 1.2])
with t1:
    st.subheader("🎯 Portfolio Drift")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = cur_ratio, number = {'suffix': "%", 'font': {'color': '#00F3FF'}},
        gauge = {'axis': {'range': [0, 100], 'tickcolor': "#FFFFFF"}, 'bar': {'color': "#00F3FF"}, 'bgcolor': "#161B22",
                 'steps': [{'range': [0, 78], 'color': '#161B22'}, {'range': [78, 82], 'color': '#39FF14'}, {'range': [82, 100], 'color': '#FF00E5'}]}))
    fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor='rgba(0,0,0,0)', font={'family': "Orbitron"})
    st.plotly_chart(fig_gauge, use_container_width=True)

with t2:
    st.subheader("📝 Action Instruction")
    st.markdown(f"""<div class="instruction-card"><h3 style="color: #39FF14; margin:0;">NEXT STEP</h3><p style="color: #CCC;">신규 예수금 {monthly_cash:,.0f}원 포함 지침</p>
        <p style="font-size: 24px; color: #FFFFFF;">Leverage 군에 <span class="neon-blue">₩{max(0, drift_lev):,.0f}</span> 우선 투입<br>잔액은 Dividend 군 배분</p></div>""", unsafe_allow_html=True)

# 6. Mission 2031 차트
st.divider()
st.subheader("🚀 Mission 2031: Asset Burn-up")
years_idx = pd.date_range(start=date.today(), end="2031-12-31", freq='ME')
fig_burnup = go.Figure()
fig_burnup.add_trace(go.Scatter(x=years_idx, y=np.linspace(total_asset_krw, goal_amt, len(years_idx)), name="Target", line=dict(color='#888', dash='dash')))
fig_burnup.add_trace(go.Scatter(x=[datetime.now()], y=[total_asset_krw], name="Actual", mode='markers+text', text=[f"₩{total_asset_krw/100000000:.2f}억"], marker=dict(color='#39FF14', size=15)))
fig_burnup.update_layout(height=350, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis_title="KRW", margin=dict(l=0, r=0, t=30, b=0))
st.plotly_chart(fig_burnup, use_container_width=True)

# 7. Serial Portfolio Analysis (최종 달성 금액 기준 정렬 적용)
st.divider()
st.subheader("📊 Serial Portfolio Analysis")
bench_start = st.date_input("Backtest Start", date(2023, 1, 1))

@st.cache_data(ttl=86400)
def run_serial_analysis(start_date, monthly_inv_krw, rate):
    data = yf.download(["QLD", "QQQ", "SPYM", "SGOV"], start=start_date)['Close'].ffill().dropna()
    rebal_dates = [group.index[group.index.day >= 21][0] if not group[group.index.day >= 21].empty else group.index[-1] for _, group in data.groupby([data.index.year, data.index.month])]
    monthly_usd = monthly_inv_krw / rate

    # 주식 시뮬레이션 함수
    def simulate(t_eq, t_cash, w_eq, is_shannon):
        eq_qty, cash_qty, history = 0.0, 0.0, []
        for d in data.index:
            p_eq, p_cash = float(data[t_eq].loc[d]), (float(data[t_cash].loc[d]) if t_cash else 0.0)
            if d in rebal_dates:
                v_eq, v_cash = eq_qty * p_eq, cash_qty * p_cash
                if is_shannon and t_cash:
                    tot = v_eq + v_cash + monthly_usd
                    eq_qty, cash_qty = (tot * w_eq / p_eq), (tot * (1-w_eq) / p_cash) if p_cash > 0 else 0
                else:
                    eq_qty += (monthly_usd * w_eq / p_eq)
                    if t_cash: cash_qty += (monthly_usd * (1-w_eq) / p_cash) if p_cash > 0 else 0
            history.append(((eq_qty * p_eq) + (cash_qty * p_cash)) * rate)
        return pd.Series(history, index=data.index)

    # 기본 저축 및 복리 벤치마크 함수
    def simulate_benchmark(annual_rate):
        history = []
        balance = 0.0
        daily_rate = (1 + annual_rate) ** (1/252) - 1 if annual_rate > 0 else 0.0
        
        for d in data.index:
            if d in rebal_dates:
                balance += monthly_inv_krw
            balance *= (1 + daily_rate)
            history.append(balance)
        return pd.Series(history, index=data.index)

    res = pd.DataFrame(index=data.index)
    
    # 벤치마크 라인 (KRW 기준)
    res['월 급여 순수량'] = simulate_benchmark(0.0)
    res['연 4% 복리'] = simulate_benchmark(0.04)
    res['연 8% 복리'] = simulate_benchmark(0.08)
    
    # 전략 시리즈
    res['QLD 전액'] = simulate('QLD', None, 1.0, False)
    res['QQQ 전액'] = simulate('QQQ', None, 1.0, False)
    res['SPYM 전액'] = simulate('SPYM', None, 1.0, False)
    res['QQQ/SGOV B&H 7:3'] = simulate('QQQ', 'SGOV', 0.7, False); res['QQQ/SGOV SHANNON 8:2'] = simulate('QQQ', 'SGOV', 0.8, True)
    res['QLD/SGOV B&H 7:3'] = simulate('QLD', 'SGOV', 0.7, False); res['QLD/SGOV SHANNON 8:2'] = simulate('QLD', 'SGOV', 0.8, True)
    return res

bench_res = run_serial_analysis(bench_start, monthly_cash, usd_krw_live)

if not bench_res.empty:
    group = st.radio("Display Group", ["Full (100%)", "QQQ/SGOV Mix", "QLD/SGOV Mix"], horizontal=True)
    mapping = {"Full (100%)": ['QLD 전액', 'QQQ 전액', 'SPYM 전액'], 
               "QQQ/SGOV Mix": ['QQQ/SGOV B&H 7:3', 'QQQ/SGOV SHANNON 8:2'], 
               "QLD/SGOV Mix": ['QLD/SGOV B&H 7:3', 'QLD/SGOV SHANNON 8:2']}
    
    global_max = bench_res.max().max()
    x_min, x_max = bench_res.index.min(), bench_res.index.max()
    
    fig_bench = go.Figure()
    
    baseline_styles = {
        '월 급여 순수량': dict(color='#888888', dash='dot', width=2),
        '연 4% 복리': dict(color='#FFA500', dash='dash', width=2),
        '연 8% 복리': dict(color='#FF4500', dash='dash', width=2)
    }
    
    # [핵심 로직] 범례 및 툴팁을 '최종 달성 금액' 기준으로 내림차순 정렬
    all_lines_to_plot = list(baseline_styles.keys()) + mapping[group]
    sorted_lines = sorted(all_lines_to_plot, key=lambda col: bench_res[col].iloc[-1], reverse=True)
    
    # 정렬된 순서대로 Trace 추가 (범례 및 Hover 툴팁의 순서 결정)
    for col in sorted_lines:
        if col in baseline_styles:
            fig_bench.add_trace(go.Scatter(x=bench_res.index, y=bench_res[col], mode='lines', name=col, line=baseline_styles[col]))
        else:
            fig_bench.add_trace(go.Scatter(x=bench_res.index, y=bench_res[col], mode='lines', name=col, line=dict(width=2.5)))
        
    fig_bench.update_layout(
        height=500, template="plotly_dark", yaxis_title="Total Asset (KRW)", 
        xaxis=dict(range=[x_min, x_max]), yaxis=dict(range=[0, global_max * 1.05]), 
        hovermode="x unified", legend_traceorder="normal"
    )
    st.plotly_chart(fig_bench, use_container_width=True)

# 8. Trade Log (Date UI Bug Fix & BUY 액션 분리)
st.divider()
st.subheader("📁 Trade Log Viewer")
st.caption("BUY 액션 시 Sell_Price 및 Realized_Profit은 연산에서 제외됩니다.")

edited_trade_log = st.data_editor(
    trade_log_df, num_rows="dynamic", use_container_width=True,
    column_config={
        "Date": st.column_config.DateColumn(
            "Date", 
            format="YYYY-MM-DD", 
            min_value=date(2000, 1, 1), 
            max_value=date(2050, 12, 31)
        ), 
        "Action": st.column_config.SelectboxColumn("Action", options=["BUY", "SELL", "EXIT_LEGACY"]),
        "Currency": st.column_config.SelectboxColumn("Currency", options=["USD", "KRW"]), 
        "Quantity": st.column_config.NumberColumn("수량"),
        "Buy_Price": st.column_config.NumberColumn("체결/평단가"),
        "Sell_Price": st.column_config.NumberColumn("매도가"),
        "Fees": st.column_config.NumberColumn("제비용 (통화기준)"),
        "Realized_Profit": st.column_config.NumberColumn("실현차익(KRW 자동)", disabled=True)
    }
)

# 실현차익 조건부 자동 연산 로직
def calculate_profit(row, rate):
    if row['Action'] in ["SELL", "EXIT_LEGACY"]:
        profit_raw = (row['Sell_Price'] - row['Buy_Price']) * row['Quantity'] - row['Fees']
        return profit_raw * rate if row['Currency'] == 'USD' else profit_raw
    return 0.0

edited_trade_log['Realized_Profit'] = edited_trade_log.apply(lambda x: calculate_profit(x, usd_krw_live), axis=1)

st.metric("누적 실현 차익 (현재 가치)", f"₩{edited_trade_log['Realized_Profit'].sum():,.0f}")
if st.button("💾 Sync Trade Log"):
    conn.update(worksheet="Trade_Log", data=edited_trade_log)
    st.success("동기화 완료!"); st.cache_data.clear()

st.caption("© 2026 SHABAL v2.2 | Engineered by JHJ")
