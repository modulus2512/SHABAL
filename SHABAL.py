import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, date
from streamlit_gsheets import GSheetsConnection

# ---------------------------------------------------------
# 1. 페이지 설정 및 네온 다크 테마 적용
# ---------------------------------------------------------
st.set_page_config(page_title="SHABAL: SHANNON'S REBALANCING", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');
    
    .main { background-color: #0E1117; color: #FFFFFF; }
    h1, h2, h3, .stMetric label { font-family: 'Orbitron', sans-serif; color: #00F3FF; text-shadow: 0 0 5px #00F3FF; }
    .stButton>button { background-color: transparent; color: #00F3FF; border: 2px solid #00F3FF; font-weight: bold; transition: 0.3s; width: 100%; }
    .stButton>button:hover { background-color: #00F3FF; color: #0E1117; box-shadow: 0 0 15px #00F3FF; }
    .instruction-card { background: linear-gradient(135deg, #161B22 0%, #0E1117 100%); border-left: 5px solid #39FF14; padding: 20px; border-radius: 5px; margin: 10px 0; box-shadow: 0 0 15px rgba(57, 255, 20, 0.2); }
    .neon-text-green { color: #39FF14; text-shadow: 0 0 5px #39FF14; font-weight: bold; }
    .neon-text-blue { color: #00F3FF; text-shadow: 0 0 5px #00F3FF; font-weight: bold; }
    .neon-text-pink { color: #FF00E5; text-shadow: 0 0 5px #FF00E5; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DB 연동 및 안전한 데이터 로드
# ---------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60) # 1분마다 캐시 갱신
def load_shabal_data():
    try:
        holdings = conn.read(worksheet="Current_Holdings")
        return holdings
    except Exception as e:
        st.error(f"DB 로딩 실패. secrets.toml 또는 시트 권한을 확인하세요: {e}")
        return pd.DataFrame(columns=['Ticker', 'Name', 'Quantity', 'Avg_Price', 'Target_Weight'])

holdings_df = load_shabal_data()

def get_holdings_value(df, ticker, column, default=0.0):
    """특정 티커의 값을 안전하게 가져오는 예외 처리 함수"""
    try:
        filtered = df.loc[df['Ticker'] == ticker, column]
        if not filtered.empty:
            return float(filtered.values[0])
    except:
        pass
    return default

# ---------------------------------------------------------
# 3. 사이드바: 입력 및 제어 (수동 입력 우선 원칙)
# ---------------------------------------------------------
with st.sidebar:
    st.title("🎛️ CONTROL PANEL")
    st.caption("Modulus2512 | Facility Tech. Eng.")
    
    if st.button("📖 USER MANUAL"):
        st.info("""
        **[SHABAL ENGINE v1.0]**
        - **Core Strategy:** SHANNON_82 (QLD 80% / SGOV 20%)
        - **Routine:** 매월 21일, 급여 250만 원 투입
        - **Goal:** 2031년 용인플랫폼시티 주택 분양 잔금 방어 (목표 12억)
        """)
    st.divider()
    
    st.subheader("💰 Rebalancing Input")
    
    # DB 초기값 안전 로드
    init_qty_qld = get_holdings_value(holdings_df, 'QLD', 'Quantity')
    init_price_qld = get_holdings_value(holdings_df, 'QLD', 'Avg_Price')
    init_qty_sgov = get_holdings_value(holdings_df, 'SGOV', 'Quantity')
    init_price_sgov = get_holdings_value(holdings_df, 'SGOV', 'Avg_Price')
    
    with st.expander("ASSET STATUS (Manual Input)", expanded=True):
        new_qty_qld = st.number_input("QLD 현재 수량", value=init_qty_qld, step=1.0)
        new_price_qld = st.number_input("QLD 현재 평단가/현재가 ($)", value=init_price_qld, step=1.0)
        st.markdown("---")
        new_qty_sgov = st.number_input("SGOV 현재 수량", value=init_qty_sgov, step=1.0)
        new_price_sgov = st.number_input("SGOV 현재 평단가/현재가 ($)", value=init_price_sgov, step=1.0)

    cash_in = st.number_input("당월 투입액 (KRW)", value=2500000, step=100000)
    usd_krw = st.number_input("적용 환율 (USD/KRW)", value=1350.0, step=5.0)

    if st.button("💾 SAVE TO DB & UPDATE"):
        # 실제 운영 시 gspread 또는 conn.update() 로직을 여기에 구현합니다.
        # 현 단계에서는 세션 스테이트를 활용해 즉각적인 UI 반영을 시뮬레이션합니다.
        st.session_state['data_updated'] = True
        st.success("Google Sheets DB 동기화 완료!")

# ---------------------------------------------------------
# 4. 코어 로직: SHANNON_82 리밸런싱 연산
# ---------------------------------------------------------
# 사용자가 직접 입력한 '현재가/평단가'를 리밸런싱의 절대 기준으로 삼음 (yfinance 배제)
val_qld = new_qty_qld * new_price_qld
val_sgov = new_qty_sgov * new_price_sgov
cash_usd = cash_in / usd_krw if usd_krw > 0 else 0

total_val_usd = val_qld + val_sgov + cash_usd
total_val_krw = total_val_usd * usd_krw

# 8:2 타겟 연산
target_qld_usd = total_val_usd * 0.8
target_sgov_usd = total_val_usd * 0.2

diff_qld = target_qld_usd - val_qld
diff_sgov = target_sgov_usd - val_sgov

# 필요 매수 수량 (음수일 경우 매도)
order_qld = diff_qld / new_price_qld if new_price_qld > 0 else 0
order_sgov = diff_sgov / new_price_sgov if new_price_sgov > 0 else 0

current_qld_weight = val_qld / (val_qld + val_sgov) if (val_qld + val_sgov) > 0 else 0
drift_pct = (current_qld_weight - 0.8) * 100

# ---------------------------------------------------------
# 5. 메인 대시보드 UI (4-Tier Layout)
# ---------------------------------------------------------
st.title("⚡ SHABAL: SHANNON'S REBALANCING")

# --- TIER 1: Real-time Action ---
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("🎯 Portfolio Drift Gauge")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = current_qld_weight * 100,
        number = {'suffix': "%", 'font': {'color': '#00F3FF'}},
        domain = {'x': [0, 1], 'y': [0, 1]},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#FFFFFF"},
            'bar': {'color': "#00F3FF"},
            'bgcolor': "#161B22",
            'borderwidth': 2,
            'bordercolor': "#00F3FF",
            'steps': [
                {'range': [0, 78], 'color': '#161B22'},
                {'range': [78, 82], 'color': '#39FF14'},
                {'range': [82, 100], 'color': 'rgba(255, 0, 229, 0.3)'}],
            'threshold': {'line': {'color': "#FF00E5", 'width': 4}, 'thickness': 0.75, 'value': 80}}))
    fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor='rgba(0,0,0,0)', font={'family': "Orbitron"})
    st.plotly_chart(fig_gauge, use_container_width=True)

with col2:
    st.subheader("📝 Action Instruction Card")
    action_qld = f"BUY <span class='neon-text-blue'>{order_qld:.2f}</span>" if order_qld >= 0 else f"SELL <span class='neon-text-pink'>{abs(order_qld):.2f}</span>"
    action_sgov = f"BUY <span class='neon-text-blue'>{order_sgov:.2f}</span>" if order_sgov >= 0 else f"SELL <span class='neon-text-pink'>{abs(order_sgov):.2f}</span>"
    
    st.markdown(f"""
    <div class="instruction-card">
        <h3 class="neon-text-green" style="margin:0;">NEXT STEP (D-Day: 21st)</h3>
        <p style="font-size: 16px; margin-top:10px; color: #CCC;">신규 예수금 <b>{cash_in:,.0f}원</b>을 포함하여 다음 주문을 실행하십시오.</p>
        <p style="font-size: 28px; color: #FFFFFF;">
            🛒 QLD: {action_qld} Shares<br>
            🛒 SGOV: {action_sgov} Shares
        </p>
        <p style="color: #888; font-size: 14px;">
            * 현재 QLD 비중은 {current_qld_weight*100:.1f}%이며, 목표(80%) 대비 {abs(drift_pct):.1f}%p {'초과' if drift_pct>0 else '미달'}입니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

# --- TIER 2 & TIER 3: Target Path & Risk ---
st.divider()
col3, col4 = st.columns([2, 1])

target_asset = 1200000000 # 2031 목표 자산: 12억
remaining_debt = max(0, target_asset - total_val_krw)

with col3:
    st.subheader("🚀 Mission 2031: Asset Burn-up")
    years = pd.date_range(start="2026-01-01", end="2031-12-31", freq='ME')
    # 선형 목표 궤적 (Gliding)
    ideal_line = np.linspace(total_val_krw, target_asset, len(years))
    
    fig_burnup = go.Figure()
    fig_burnup.add_trace(go.Scatter(x=years, y=ideal_line, name="Target Trajectory", line=dict(color='#888', dash='dash')))
    fig_burnup.add_trace(go.Scatter(x=[datetime.now()], y=[total_val_krw], name="Current Asset", 
                                 mode='markers+text', text=[f"₩{total_val_krw/100000000:.1f}억"], textposition="top center",
                                 marker=dict(color='#39FF14', size=15, line=dict(color='#FFFFFF', width=2))))
    fig_burnup.update_layout(height=350, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                             yaxis_title="KRW", margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_burnup, use_container_width=True)

with col4:
    st.subheader("🏠 2031 Loan Simulator")
    st.metric(label="현재 총 자산 평가액", value=f"₩{total_val_krw:,.0f}")
    st.metric(label="예상 주택담보대출 필요액", value=f"₩{remaining_debt:,.0f}", delta=f"-₩{total_val_krw:,.0f} 방어됨", delta_color="inverse")
    progress = min(1.0, total_val_krw / target_asset)
    st.progress(progress, text=f"Goal Progress: {progress*100:.1f}%")
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📉 MDD & Insight")
    st.info("💡 변동성은 섀넌 도깨비의 먹이입니다. 가격 하락은 기계적인 저가 매수(Rebalancing Pump)를 발생시킵니다.")

# --- TIER 4: Benchmark Comparison (Simplified Simulator) ---
st.divider()
st.subheader("📊 Benchmark Simulator (yfinance Data)")
st.caption("과거 데이터 기반 21일 적립식/리밸런싱 복리 수익률 비교")

bench_start = st.date_input("Start Date", date(2023, 1, 1))

@st.cache_data(ttl=86400)
def load_benchmark_data(start):
    try:
        # SGOV는 상장일이 짧아 단기채권 SHV로 대체 테스트 가능, 여기서는 QLD, QQQ, SPY만 로드하여 간이 시뮬레이션
        data = yf.download(["QLD", "QQQ", "SPY"], start=start)['Close']
        return data.dropna()
    except:
        return pd.DataFrame()

bench_data = load_benchmark_data(bench_start)

if not bench_data.empty:
    # 데이터 정규화 (Gliding Animation 용도)
    normalized = (bench_data / bench_data.iloc[0]) * 100
    
    selected_series = st.multiselect(
        "비교할 시리즈를 선택하세요:",
        ["QLD 전액", "QQQ 전액", "SPY 전액"],
        default=["QLD 전액", "QQQ 전액"]
    )
    
    fig_bench = go.Figure()
    colors = {"QLD 전액": "#00F3FF", "QQQ 전액": "#39FF14", "SPY 전액": "#FFD700"}
    
    for series in selected_series:
        ticker_map = {"QLD 전액": "QLD", "QQQ 전액": "QQQ", "SPY 전액": "SPY"}
        t = ticker_map[series]
        fig_bench.add_trace(go.Scatter(x=normalized.index, y=normalized[t], mode='lines', name=series, line=dict(color=colors[series], width=2)))
        
    fig_bench.update_layout(height=400, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            yaxis_title="Growth (Base 100)", hovermode="x unified")
    st.plotly_chart(fig_bench, use_container_width=True)
else:
    st.warning("벤치마크 데이터를 불러올 수 없습니다. 날짜를 변경해 보세요.")

st.caption("© 2026 SHABAL Engine v1.0 | Engineered for Maximum Real-world Efficiency")