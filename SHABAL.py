import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import requests
from datetime import datetime, date
from streamlit_gsheets import GSheetsConnection

# =====================================================================
# [상편] 시스템 설정, DB 연동 및 실시간 리밸런싱 관제
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
    
    /* 사이드바 프로토콜 강조용 CSS */
    .protocol-level-1 { background-color: rgba(57,255,20,0.1); border-left: 4px solid #39FF14; padding: 10px; margin-top:10px; }
    .protocol-level-2 { background-color: rgba(255,165,0,0.1); border-left: 4px solid #FFA500; padding: 10px; margin-top:10px; }
    .protocol-level-3 { background-color: rgba(255,0,229,0.1); border-left: 4px solid #FF00E5; padding: 10px; margin-top:10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. 실시간 환율 호출 함수
def fetch_realtime_usd_krw():
    try:
        url = "https://api.frankfurter.app/latest?from=USD&to=KRW"
        response = requests.get(url, timeout=5)
        data = response.json()
        return float(data['rates']['KRW'])
    except:
        try:
            ticker = yf.Ticker("USDKRW=X")
            return float(ticker.fast_info['last_price'])
        except:
            return 1380.0 

# [v3.1 수정] QQQ MDD 탐색 컬럼 무결성 확보 알고리즘
@st.cache_data(ttl=3600)
def get_qqq_mdd():
    try:
        data = yf.download("QQQ", period="6mo", progress=False)
        if data.empty: 
            return 0.0, 0.0
            
        # 구조 다변화에 대응하는 컬럼 스캐너
        close_col = None
        for col in data.columns:
            col_str = str(col).lower()
            if 'close' in col_str and 'adj' not in col_str:
                close_col = col
                break
                
        if close_col is None:
            return 0.0, 0.0
            
        hist = data[close_col].squeeze()
        
        current_price = float(hist.iloc[-1])
        high_1m = float(hist.tail(21).max())
        high_6m = float(hist.max())
        
        mdd_1m = ((current_price / high_1m) - 1) * 100 if high_1m > 0 else 0.0
        mdd_6m = ((current_price / high_6m) - 1) * 100 if high_6m > 0 else 0.0
        return mdd_1m, mdd_6m
    except:
        return 0.0, 0.0

# 3. DB 연동 및 데이터 보정
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
            
        for col in ['Quantity', 'Buy_Price', 'Sell_Price', 'Fees', 'Realized_Profit']:
            if col in trade_log.columns: 
                trade_log[col] = pd.to_numeric(trade_log[col], errors='coerce').fillna(0.0)
                
        return holdings, trade_log
    except Exception as e:
        st.error(f"DB 로딩 오류: {e}")
        return pd.DataFrame(), pd.DataFrame()

holdings_df, trade_log_df = load_and_fix_data()

# 기본 QLD 단가 추출 (사이드바 편의성 용도)
default_qld_price = 0.0
if not holdings_df.empty:
    qld_row = holdings_df[holdings_df['티커'] == 'QLD']
    if not qld_row.empty:
        default_qld_price = float(pd.to_numeric(qld_row['현재가'], errors='coerce').fillna(0.0).iloc[0])

# 4. 사이드바: 🎛️ CONTROL PANEL & 패닉 방지 프로토콜
if 'usd_krw' not in st.session_state:
    st.session_state['usd_krw'] = 1450.0 

with st.sidebar:
    st.title("🎛️ CONTROL PANEL")
    
    st.subheader("🌐 Currency Control")
    col_rate_val, col_rate_btn = st.columns([1.5, 1])
    with col_rate_btn:
        if st.button("🔄 FETCH LIVE"):
            st.session_state['usd_krw'] = fetch_realtime_usd_krw()
            st.toast(f"환율 업데이트 완료: {st.session_state['usd_krw']}원")
    with col_rate_val:
        usd_krw_live = st.number_input("현재 환율 (USD/KRW)", value=st.session_state['usd_krw'], step=0.1)

    monthly_cash = st.number_input("당월 적립액 (KRW)", value=2500000, step=100000)
    
    # 침착한 하락장 (Anti-Panic Rebalancing Protocol)
    with st.expander("🛡️ 침착한 하락장 (Anti-Panic Protocol)"):
        st.caption("MDD와 괴리율을 교차 검증하여 SGOV 낭비를 막습니다.")
        
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            input_qld_current = st.number_input("현재 QLD 단가 ($)", value=default_qld_price, step=1.0)
        with col_q2:
            input_qld_avg = st.number_input("QLD 평단가액 ($)", value=default_qld_price, step=1.0)
            
        # 실시간 복구된 데이터 연산
        qqq_mdd_1m, qqq_mdd_6m = get_qqq_mdd()
        disparity = ((input_qld_current / input_qld_avg) - 1) * 100 if input_qld_avg > 0 else 0.0
        
        # 지표 출력
        st.write(f"**현재 QQQ MDD (1M):** {qqq_mdd_1m:.2f}%")
        st.write(f"**현재 QQQ MDD (6M):** {qqq_mdd_6m:.2f}%")
        st.write(f"**현재 괴리율 (G):** {disparity:.2f}%")
        
        # 프로토콜 판별
        if (qqq_mdd_6m <= -20 or qqq_mdd_1m <= -15) and disparity <= -30:
            st.markdown("""
            <div class="protocol-level-3">
                <b>🚨 Level 3 (시스템적 폭락)</b><br>
                <b>목표:</b> 평단가 인하율 T≥15% 달성<br>
                <b>지침 [SGOV 전량 격리 해제]:</b><br>
                SGOV를 전량 매도하여 QLD 매수에 스위칭 투입, 평단가를 공격적으로 낮추십시오.
            </div>
            """, unsafe_allow_html=True)
        elif -20 < qqq_mdd_6m <= -10 and disparity <= -15:
            st.markdown("""
            <div class="protocol-level-2">
                <b>⚠️ Level 2 (구조적 조정)</b><br>
                <b>목표:</b> 평단가 인하율 T≥5% 달성<br>
                <b>지침 [SGOV 1차 부분 해제]:</b><br>
                신규 투자금 투입 후에도 8:2 비율이 부족할 경우, 예수금 <b>가용 질량의 최대 30%까지</b> 떼서 QLD를 추가 매수하십시오.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="protocol-level-1">
                <b>🟢 Level 1 (평시 노이즈)</b><br>
                <b>목표:</b> 평단가 인하 요구량 없음<br>
                <b>지침 [SGOV 보존]:</b><br>
                신규 투자금만을 활용하여, 엔진 제안에 따라 QLD 비중을 늘려가는 데에 집중하십시오.
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.subheader("📋 통합 자산 관리")
    edited_holdings = st.data_editor(holdings_df, num_rows="dynamic", key="holdings_editor", use_container_width=True,
        column_config={
            "시장": st.column_config.SelectboxColumn("시장", options=["해외", "국내"]),
            "구분": st.column_config.SelectboxColumn("구분", options=["Leverage", "Dividend", "예수현금"]),
            "종목": st.column_config.TextColumn("종목"), 
            "티커": st.column_config.TextColumn("티커"),
            "수량": st.column_config.NumberColumn("수량", min_value=0.0), 
            "현재가": st.column_config.NumberColumn("현재가", min_value=0.0)
        })
        
    if st.button("💾 Sync Holdings to DB"):
        conn.update(worksheet="Current_Holdings", data=edited_holdings)
        st.success("동기화 완료!")
        st.cache_data.clear()

# 5. 코어 엔진 로직
def run_shabal_v31_logic(df, cash_krw, rate, target_ratio_pct):
    val_lev, val_div, val_cash = 0.0, 0.0, 0.0
    target_ratio = target_ratio_pct / 100.0
    
    if not df.empty:
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0.0)
        df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce').fillna(0.0)
        df['Value_KRW'] = df.apply(lambda x: x['수량'] * x['현재가'] * (rate if x['시장'] == "해외" else 1.0), axis=1)
        val_lev = df[df['구분'] == 'Leverage']['Value_KRW'].sum()
        val_div = df[df['구분'] == 'Dividend']['Value_KRW'].sum()
        val_cash = df[df['구분'] == '예수현금']['Value_KRW'].sum()
    
    shannon_total = val_lev + val_div
    total_asset = shannon_total + val_cash
    
    future_shannon_total = shannon_total + cash_krw
    target_lev_amt = future_shannon_total * target_ratio
    required_lev = target_lev_amt - val_lev
    
    cur_ratio = (val_lev / shannon_total * 100) if shannon_total > 0 else 0.0
    
    return total_asset, cur_ratio, required_lev, cash_krw


# =====================================================================
# [하편] 시각화 대시보드, 동적 비중 조절 및 MDD Tracker
# =====================================================================

st.title("⚡ SHABAL: SHANNON'S REBALANCING")

col_m1, col_m2 = st.columns([1.5, 1])
with col_m1: 
    goal_amt = st.number_input("🎯 2031 목표 확보액 (KRW)", value=250000000, step=10000000)
with col_m2: 
    st.metric("D-DAY TO 2031", f"{(date(2031,12,31)-date.today()).days} Days")

st.divider()

# 리밸런싱 관제 및 동적 비중 슬라이더
t1, t2 = st.columns([1, 1.2])
with t1:
    st.subheader("🎯 Portfolio Drift")
    
    target_weight = st.slider("Target Leverage Weight (%)", min_value=0, max_value=100, value=80, step=5)
    
    total_asset_krw, cur_ratio, required_lev, cash_krw = run_shabal_v31_logic(edited_holdings, monthly_cash, usd_krw_live, target_weight)
    
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta", 
        value=cur_ratio, 
        delta={'reference': target_weight, 'position': "top", 'suffix': "%"},
        number={'suffix': "%", 'font': {'color': '#00F3FF'}},
        gauge={
            'axis': {'range': [0, 100], 'tickcolor': "#FFFFFF"}, 
            'bar': {'color': "#00F3FF"}, 
            'bgcolor': "#161B22",
            'steps': [
                {'range': [target_weight - 1.5, target_weight + 1.5], 'color': '#39FF14'}
            ],
            'threshold': {'line': {'color': "white", 'width': 4}, 'thickness': 0.75, 'value': target_weight}
        }
    ))
    fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor='rgba(0,0,0,0)', font={'family': "Orbitron"})
    st.plotly_chart(fig_gauge, use_container_width=True)

with t2:
    st.subheader("📝 Action Instruction")
    
    if required_lev > cash_krw:
        shortfall = required_lev - cash_krw
        instruction_html = f"""
        <div class="instruction-card" style="border-left-color: #FF00E5; box-shadow: 0 0 15px rgba(255,0,229,0.2);">
            <h3 style="color: #FF00E5; margin:0;">NEXT STEP (Target {target_weight}:{100-target_weight})</h3>
            <p style="color: #CCC;">신규 예수금 {cash_krw:,.0f}원 기준 지침</p>
            <p style="font-size: 22px; color: #FFFFFF; line-height: 1.4;">
            Leverage 군에 <b>예수금 전액 투입</b> 요망<br>
            <span style="font-size: 16px; color: #FF00E5;">⚠️ 목표 비중 달성을 위해 추가로 <b>Dividend 군 ₩{shortfall:,.0f} 매도 후 Leverage 매수</b>가 필요합니다.<br>(좌측 사이드바의 '침착한 하락장' 프로토콜을 확인하여 SGOV 매도 여부를 결정하세요.)</span>
            </p>
        </div>
        """
    elif required_lev > 0:
        instruction_html = f"""
        <div class="instruction-card">
            <h3 style="color: #39FF14; margin:0;">NEXT STEP (Target {target_weight}:{100-target_weight})</h3>
            <p style="color: #CCC;">신규 예수금 {cash_krw:,.0f}원 기준 지침</p>
            <p style="font-size: 22px; color: #FFFFFF; line-height: 1.4;">
            Leverage 군에 <span class="neon-blue">₩{required_lev:,.0f}</span> 우선 투입<br>
            잔액 <span style="color:#39FF14;">₩{cash_krw - required_lev:,.0f}</span>은 Dividend 군에 배분하십시오.
            </p>
        </div>
        """
    else:
        overage = abs(required_lev)
        instruction_html = f"""
        <div class="instruction-card" style="border-left-color: #00F3FF; box-shadow: 0 0 15px rgba(0,243,255,0.2);">
            <h3 style="color: #00F3FF; margin:0;">NEXT STEP (Target {target_weight}:{100-target_weight})</h3>
            <p style="color: #CCC;">신규 예수금 {cash_krw:,.0f}원 기준 지침</p>
            <p style="font-size: 22px; color: #FFFFFF; line-height: 1.4;">
            Dividend 군에 <b>예수금 전액 투입</b> 요망<br>
            <span style="font-size: 16px; color: #00F3FF;">✅ Leverage 군이 이미 목표치 대비 <b>₩{overage:,.0f}</b> 초과 상태입니다.</span>
            </p>
        </div>
        """
    
    st.markdown(instruction_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# 6. QQQ MDD Tracker (멀티인덱스 컬럼 구조 방어 완료)
# ---------------------------------------------------------------------
st.divider()
st.subheader("📉 QQQ MDD & Value Averaging Tracker")
st.caption("기초 지수인 QQQ의 고점 대비 하락폭(MDD)을 추적하여 하락장 시 기계적 저가 매수 타점을 관제합니다.")

col_mdd1, col_mdd2 = st.columns([1, 2.5])
with col_mdd1:
    period_options = {'1개월': '1mo', '3개월': '3mo', '6개월': '6mo', '1년': '1y', '최대': 'max'}
    selected_period = st.selectbox("전고점 탐색 기간", list(period_options.keys()), index=0)
    
    @st.cache_data(ttl=3600)
    def fetch_qqq_high(p):
        try:
            d = yf.download("QQQ", period=p, progress=False)
            if d.empty:
                return 450.0
                
            # 멀티레이어 컬럼 구조 방어용 스캐너
            high_col = None
            for col in d.columns:
                if 'high' in str(col).lower():
                    high_col = col
                    break
            if high_col is not None:
                return float(np.nanmax(d[high_col]))
            return 450.0
        except: 
            return 450.0
            
    fetched_high = fetch_qqq_high(period_options[selected_period])
    target_high = st.number_input("QQQ 기준 고점 (USD)", value=fetched_high if fetched_high > 0 else 450.0, step=1.0)

with col_mdd2:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("MDD -5%", f"${target_high * 0.95:,.2f}")
    m2.metric("MDD -10%", f"${target_high * 0.90:,.2f}")
    m3.metric("MDD -15%", f"${target_high * 0.85:,.2f}")
    m4.metric("MDD -20%", f"${target_high * 0.80:,.2f}")

# ---------------------------------------------------------------------
# 7. Mission 2031 & Serial Portfolio Analysis
# ---------------------------------------------------------------------
st.divider()
st.subheader("🚀 Mission 2031: Asset Burn-up")
years_idx = pd.date_range(start=date.today(), end="2031-12-31", freq='ME')
fig_burnup = go.Figure()
fig_burnup.add_trace(go.Scatter(x=years_idx, y=np.linspace(total_asset_krw, goal_amt, len(years_idx)), name="Target", line=dict(color='#888', dash='dash')))
fig_burnup.add_trace(go.Scatter(x=[datetime.now()], y=[total_asset_krw], name="Actual", mode='markers+text', text=[f"₩{total_asset_krw/100000000:.2f}억"], marker=dict(color='#39FF14', size=15)))
fig_burnup.update_layout(height=350, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis_title="KRW", margin=dict(l=0, r=0, t=30, b=0))
st.plotly_chart(fig_burnup, use_container_width=True)

st.divider()
st.subheader("📊 Serial Portfolio Analysis")
bench_start = st.date_input("Backtest Start", date(2023, 1, 1))

@st.cache_data(ttl=86400)
def run_serial_analysis_v31(start_date, monthly_inv_krw, rate):
    data = yf.download(["QLD", "QQQ", "SPYM", "SGOV"], start=start_date)['Close'].ffill()
    
    if 'SGOV' in data.columns and data['SGOV'].isna().any():
        first_valid_date = data['SGOV'].first_valid_index()
        if first_valid_date is not None:
            first_pos_int = data.index.get_loc(first_valid_date)
            daily_discount_rate = (1 + 0.04)**(1/252) - 1
            
            n_days_before = first_pos_int
            days_array = np.arange(n_days_before, 0, -1)
            base_price = data.iloc[first_pos_int, data.columns.get_loc('SGOV')]
            data.iloc[:first_pos_int, data.columns.get_loc('SGOV')] = base_price / ((1 + daily_discount_rate) ** days_array)
            
    data = data.bfill()
    
    rebal_dates = []
    for y_m, group in data.groupby([data.index.year, data.index.month]):
        after_21 = group[group.index.day >= 21]
        if not after_21.empty:
            rebal_dates.append(after_21.index[0])
        else:
            rebal_dates.append(group.index[-1])
            
    monthly_usd = monthly_inv_krw / rate

    def simulate(t_eq, t_cash, w_eq, is_shannon):
        eq_qty, cash_qty, history = 0.0, 0.0, []
        for d in data.index:
            p_eq = float(data[t_eq].loc[d])
            p_cash = float(data[t_cash].loc[d]) if t_cash else 0.0
            if d in rebal_dates:
                v_eq, v_cash = eq_qty * p_eq, cash_qty * p_cash
                if is_shannon and t_cash:
                    tot = v_eq + v_cash + monthly_usd
                    eq_qty = (tot * w_eq) / p_eq if p_eq > 0 else 0
                    cash_qty = (tot * (1-w_eq)) / p_cash if p_cash > 0 else 0
                else:
                    eq_qty += (monthly_usd * w_eq) / p_eq if p_eq > 0 else 0
                    if t_cash:
                        cash_qty += (monthly_usd * (1-w_eq)) / p_cash if p_cash > 0 else 0
            history.append(((eq_qty * p_eq) + (cash_qty * p_cash)) * rate)
        return pd.Series(history, index=data.index)

    def sim_bench(annual_rate):
        history, balance = [], 0.0
        daily_rate = (1 + annual_rate)**(1/252) - 1 if annual_rate > 0 else 0.0
        for d in data.index:
            if d in rebal_dates: 
                balance += monthly_inv_krw
            balance *= (1 + daily_rate)
            history.append(balance)
        return pd.Series(history, index=data.index)

    res = pd.DataFrame(index=data.index)
    res['월 급여 순수량'] = sim_bench(0.0)
    res['연 4% 복리'] = sim_bench(0.04)
    res['연 8% 복리'] = sim_bench(0.08)
    
    res['QLD 전액'] = simulate('QLD', None, 1.0, False)
    res['QQQ 전액'] = simulate('QQQ', None, 1.0, False)
    res['SPYM 전액'] = simulate('SPYM', None, 1.0, False)
    
    res['QQQ/SGOV B&H 7:3'] = simulate('QQQ', 'SGOV', 0.7, False)
    res['QQQ/SGOV SHANNON 8:2'] = simulate('QQQ', 'SGOV', 0.8, True)
    
    res['QLD/SGOV B&H 7:3'] = simulate('QLD', 'SGOV', 0.7, False)
    res['QLD/SGOV SHANNON 8:2'] = simulate('QLD', 'SGOV', 0.8, True)
    
    return res

bench_res = run_serial_analysis_v31(bench_start, monthly_cash, usd_krw_live)

if not bench_res.empty:
    group = st.radio("Display Group", ["Full (100%)", "QQQ/SGOV Mix", "QLD/SGOV Mix"], horizontal=True)
    
    mapping = {
        "Full (100%)": ['QLD 전액', 'QQQ 전액', 'SPYM 전액'], 
        "QQQ/SGOV Mix": ['QQQ/SGOV B&H 7:3', 'QQQ/SGOV SHANNON 8:2'], 
        "QLD/SGOV Mix": ['QLD/SGOV B&H 7:3', 'QLD/SGOV SHANNON 8:2']
    }
    
    baseline_styles = {
        '월 급여 순수량': dict(color='#888888', dash='dot', width=2), 
        '연 4% 복리': dict(color='#FFA500', dash='dash', width=2), 
        '연 8% 복리': dict(color='#FF4500', dash='dash', width=2)
    }
    
    all_lines = list(baseline_styles.keys()) + mapping[group]
    sorted_lines = sorted(all_lines, key=lambda c: bench_res[c].iloc[-1], reverse=True)
    
    global_max = bench_res.max().max()
    x_min, x_max = bench_res.index.min(), bench_res.index.max()
    
    fig_bench = go.Figure()
    
    for col in sorted_lines:
        style = baseline_styles[col] if col in baseline_styles else dict(width=2.5)
        fig_bench.add_trace(go.Scatter(x=bench_res.index, y=bench_res[col], mode='lines', name=col, line=style))
        
    fig_bench.update_layout(
        height=500, 
        template="plotly_dark", 
        yaxis_title="Total Asset (KRW)", 
        xaxis=dict(range=[x_min, x_max]), 
        yaxis=dict(range=[0, global_max * 1.05]), 
        hovermode="x unified",
        legend_traceorder="normal"
    )
    st.plotly_chart(fig_bench, use_container_width=True)

# ---------------------------------------------------------------------
# 8. Trade Log Viewer
# ---------------------------------------------------------------------
st.divider()
st.subheader("📁 Trade Log Viewer")
st.caption("BUY 선택 시 매도가(Sell_Price) 및 실현차익은 비활성화됩니다.")

edited_trade_log = st.data_editor(
    trade_log_df, 
    num_rows="dynamic", 
    use_container_width=True,
    column_config={
        "Date": st.column_config.DateColumn(
            "Date", 
            format="YYYY-MM-DD", 
            min_value=date(2000,1,1), 
            max_value=date(2050,12,31)
        ), 
        "Action": st.column_config.SelectboxColumn("Action", options=["BUY", "SELL", "EXIT_LEGACY"]),
        "Currency": st.column_config.SelectboxColumn("Currency", options=["USD", "KRW"]), 
        "Quantity": st.column_config.NumberColumn("수량"),
        "Buy_Price": st.column_config.NumberColumn("체결/평단가"),
        "Sell_Price": st.column_config.NumberColumn("매도가"),
        "Fees": st.column_config.NumberColumn("제비용 (통화기준)"),
        "Realized_Profit": st.column_config.NumberColumn("실현차익(KRW)", disabled=True)
    }
)

def calc_realized_profit(row, rate):
    if row['Action'] in ["SELL", "EXIT_LEGACY"]:
        raw = (row['Sell_Price'] - row['Buy_Price']) * row['Quantity'] - row['Fees']
        return raw * rate if row['Currency'] == 'USD' else raw
    return 0.0

edited_trade_log['Realized_Profit'] = edited_trade_log.apply(lambda x: calc_realized_profit(x, usd_krw_live), axis=1)

st.metric("누적 실현 차익 (현재 환율 기준)", f"₩{edited_trade_log['Realized_Profit'].sum():,.0f}")

if st.button("💾 Sync Trade Log"):
    conn.update(worksheet="Trade_Log", data=edited_trade_log)
    st.success("동기화 완료!")
    st.cache_data.clear()

st.caption("© 2026 SHABAL v3.1 | Engineered by Modulus2512")
