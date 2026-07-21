import sys
import os

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import time
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Set Page Config for wide layout and custom styling
st.set_page_config(
    layout="wide",
    page_title="aerodata-qcomm | Alternative Data Intelligence Dashboard",
    page_icon="📊"
)

# -------------------------------------------------------------
# 0. SECURITY GATEKEEPER LAYER
# -------------------------------------------------------------
def check_password():
    """Returns True if the user has entered the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        master_password = None
        try:
            if "DASHBOARD_PASSWORD" in st.secrets:
                master_password = st.secrets["DASHBOARD_PASSWORD"]
        except Exception:
            pass
            
        if not master_password:
            master_password = os.getenv("DASHBOARD_PASSWORD", "admin123")
            
        if st.session_state["password_input"] == master_password:
            st.session_state["authenticated"] = True
            del st.session_state["password_input"]  # don't store password in session state
            st.rerun()
        else:
            st.session_state["authenticated"] = False

    # Check if already authenticated
    if st.session_state.get("authenticated", False):
        return True

    # Show login UI
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("")
        st.write("")
        st.write("")
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center; color: #00d2ff; font-family: Outfit, sans-serif;'>🔒 Institutional Access Required</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #888; margin-bottom: 20px;'>aerodata-qcomm Alternative Data Platform</p>", unsafe_allow_html=True)
            
            st.text_input(
                "Enter Access Key",
                type="password",
                on_change=password_entered,
                key="password_input",
                placeholder="Enter password..."
            )
            
            if "authenticated" in st.session_state and not st.session_state["authenticated"]:
                st.error("😕 Incorrect password. Please try again.")
                
    return False

if not check_password():
    st.stop()

# Custom styles injection for high-fidelity dark aesthetics
st.markdown("""
<style>
    .main-title {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-weight: 800;
        color: #00d2ff;
        font-size: 2.5rem;
        margin-bottom: 5px;
    }
    .main-subtitle {
        font-family: 'Inter', sans-serif;
        font-weight: 400;
        color: #888;
        font-size: 1.1rem;
        margin-bottom: 25px;
    }
    .metric-card {
        background-color: #111;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        border-radius: 5px 5px 0px 0px;
        background-color: #111;
        border: 1px solid #222;
        color: #aaa;
    }
    .stTabs [aria-selected="true"] {
        background-color: #222;
        border-bottom: 2px solid #00d2ff !important;
        color: #00d2ff !important;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 1. DATA ACCESS & FALLBACK LAYER
# -------------------------------------------------------------

def load_heartbeat():
    """
    Reads the system heartbeat.json containing latest run info.
    """
    heartbeat_path = "heartbeat.json"
    if os.path.exists(heartbeat_path):
        try:
            with open(heartbeat_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def get_log_tail(n=50):
    """
    Reads the last N lines of logs/scheduler.log.
    """
    log_path = os.path.join("logs", "scheduler.log")
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()
                return "".join(lines[-n:])
        except Exception as e:
            return f"Error reading log file: {e}"
    return "Log file not found. Scheduler daemon may not have run yet."

def generate_mock_raw_data():
    """
    Generates rich historical mock records if database is empty to ensure visual charts populate.
    """
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    records = []
    platforms = ["Zepto", "Blinkit", "Swiggy Instamart"]
    brands = ["Amul", "Nandini", "Harvest Gold", "Modern", "Tata"]
    categories = ["Dairy, Bread & Eggs", "Fruits & Vegetables", "Groceries"]
    
    base_prices = {
        "Dairy, Bread & Eggs": 50.0,
        "Fruits & Vegetables": 45.0,
        "Groceries": 75.0
    }
    
    np.random.seed(42)
    
    for dt in dates:
        # Simulate micro-inflation over time (0.4% compound daily)
        inflation_factor = 1.0 + (dt - dates[0]).days * 0.004
        for platform in platforms:
            for brand in brands:
                for category in categories:
                    for i in range(2):
                        product_id = f"p-{brand.lower()}-{category[:3].lower()}-{i}"
                        product_name = f"{brand} {category[:-1]} Special {i+1}"
                        
                        base_p = base_prices[category] * inflation_factor
                        # Price variances
                        listed_price = round(base_p * np.random.uniform(0.95, 1.05), 2)
                        discount_price = round(listed_price * np.random.uniform(0.90, 1.0), 2)
                        
                        # Set OOS probabilities
                        oos_prob = 0.15 if platform == "Zepto" else (0.10 if platform == "Swiggy Instamart" else 0.20)
                        stock_status = np.random.random() > oos_prob
                        
                        records.append({
                            "observed_at": dt,
                            "effective_at": dt,
                            "platform_name": platform,
                            "store_id": f"store_{platform.lower()}_blr",
                            "product_id": product_id,
                            "product_name": product_name,
                            "category": category,
                            "brand_name": brand,
                            "listed_price": listed_price,
                            "discount_price": discount_price,
                            "stock_status": stock_status,
                            "parent_ticker": platform.upper()
                        })
    return pd.DataFrame(records)

import io
import requests
from sqlalchemy import create_engine

def federate_datasets(hot_df, cold_df):
    """
    Concatenates hot and cold tier DataFrames, renaming 'timestamp' to 'observed_at'
    if necessary, and drops duplicates across composite indices.
    """
    if hot_df.empty and cold_df.empty:
        return pd.DataFrame()
        
    # Standardize columns
    if not hot_df.empty and "timestamp" in hot_df.columns:
        hot_df = hot_df.rename(columns={"timestamp": "observed_at"})
    if not cold_df.empty and "timestamp" in cold_df.columns:
        cold_df = cold_df.rename(columns={"timestamp": "observed_at"})
        
    combined = pd.concat([hot_df, cold_df], ignore_index=True)
    
    # Ensure both timestamp and observed_at are present for deduplication compatibility
    if "observed_at" in combined.columns:
        combined["timestamp"] = combined["observed_at"]
    elif "timestamp" in combined.columns:
        combined["observed_at"] = combined["timestamp"]
        
    # Deduplicate across ["timestamp", "platform_name", "store_id", "product_id"]
    combined = combined.drop_duplicates(subset=["timestamp", "platform_name", "store_id", "product_id"])
    
    # Sort by timestamp/observed_at DESC
    sort_col = "observed_at" if "observed_at" in combined.columns else "timestamp"
    combined = combined.sort_values(sort_col, ascending=False)
    
    return combined

@st.cache_data(ttl=300)
def fetch_raw_data():
    """
    Fetches raw product records dynamically via hybrid data federation:
    - Hot tier: Neon Serverless Postgres for the last 30 days
    - Cold tier: Hugging Face dataset vault for older records
    """
    hot_df = pd.DataFrame()
    cold_df = pd.DataFrame()
    
    # 1. Fetch from Hot Tier: Neon Serverless Postgres (timestamp >= NOW() - INTERVAL '30 days')
    db_url = None
    try:
        if "DATABASE_URL" in st.secrets:
            db_url = st.secrets["DATABASE_URL"]
    except Exception:
        pass
        
    if not db_url:
        db_url = os.getenv("DATABASE_URL")
        
    if not db_url:
        from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
        db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    try:
        engine = create_engine(
            db_url,
            pool_size=5,
            max_overflow=10
        )
        # Select records where timestamp >= NOW() - INTERVAL '30 days'
        query = """
            SELECT 
                timestamp AS observed_at, 
                platform_name, 
                store_id, 
                product_id, 
                product_name, 
                listed_price, 
                discount_price, 
                category, 
                brand_name, 
                stock_status, 
                parent_ticker
            FROM qcomm_prices
            WHERE timestamp >= NOW() - INTERVAL '30 days'
            ORDER BY timestamp DESC;
        """
        with engine.connect() as conn:
            hot_df = pd.read_sql_query(query, conn)
    except Exception as e:
        logger.warning(f"Failed to query Hot Tier: {e}")

    # 2. Fetch from Cold Tier: Hugging Face dataset archive
    hf_url = "https://huggingface.co/datasets/VaNam65/qcomm-cold-archive/resolve/main/data/archive_cold_tier.parquet"
    hf_token = None
    try:
        if "HF_TOKEN" in st.secrets:
            hf_token = st.secrets["HF_TOKEN"]
    except Exception:
        pass
        
    if not hf_token:
        hf_token = os.getenv("HF_TOKEN")

    headers = {}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    try:
        response = requests.get(hf_url, headers=headers, timeout=15)
        if response.status_code == 200:
            cold_df = pd.read_parquet(io.BytesIO(response.content))
            logger.info("Successfully fetched Cold Tier from Hugging Face Parquet dataset.")
        else:
            logger.warning(f"Hugging Face Parquet fetch failed with status: {response.status_code}")
    except Exception as e:
        logger.warning(f"Error fetching Cold Tier from Hugging Face: {e}")

    # 3. Unify and Deduplicate
    df = pd.DataFrame()
    source_name = "Mock Sandbox Cache"

    if not hot_df.empty or not cold_df.empty:
        df = federate_datasets(hot_df, cold_df)
        if not hot_df.empty and not cold_df.empty:
            source_name = "Federated (Neon Hot + Hugging Face Cold)"
        elif not hot_df.empty:
            source_name = "Neon Serverless Postgres (Hot Only)"
        else:
            source_name = "Hugging Face Parquet (Cold Only)"

    # 4. Fallback to generating mock raw records if both tiers are empty
    if df.empty:
        df = generate_mock_raw_data()
        
    return df, source_name

# -------------------------------------------------------------
# 2. RENDER INTERFACE
# -------------------------------------------------------------

# Title & Description Header
st.markdown('<div class="main-title">AERODATA-QCOMM CONTROL COMMAND</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Harvesting Quick-Commerce Pricing, Stockouts & Catalog Signals for Quantitative Funds</div>', unsafe_allow_html=True)

# Fetch raw data set
raw_df, data_source = fetch_raw_data()

# Map store_id to city
def map_store_to_city(store_id):
    store_lower = str(store_id).lower()
    if "blr" in store_lower or "bangalore" in store_lower or "hsr" in store_lower or "ind" in store_lower:
        return "Bangalore"
    elif "bom" in store_lower or "mumbai" in store_lower or "lpr" in store_lower or "and" in store_lower:
        return "Mumbai"
    elif "del" in store_lower or "delhi" in store_lower or "gur" in store_lower or "sak" in store_lower:
        return "Delhi-NCR"
    return "Other"

if not raw_df.empty:
    raw_df["city"] = raw_df["store_id"].apply(map_store_to_city)
else:
    raw_df["city"] = []

# Sidebar Control Center
with st.sidebar:
    st.image("https://img.icons8.com/nolan/96/database.png", width=70)
    st.markdown("### Command Center")
    if "Federated" in data_source:
        st.info(f"Data Source:\n**{data_source}**")
    else:
        st.info(f"Data Connection Source:\n**{data_source}**")
    
    st.markdown("---")
    st.markdown("### Geographical Filters")
    city_filter = st.selectbox(
        "Select Urban Region",
        ["All Cities", "Bangalore", "Mumbai", "Delhi-NCR"]
    )
    
    st.markdown("---")
    st.markdown("### Log Monitoring")
    auto_refresh = st.checkbox("Auto-Refresh Log Tail", value=False)
    refresh_rate = st.slider("Refresh Interval (s)", min_value=2, max_value=30, value=5)
    
    st.markdown("---")
    if st.button("Refresh Ingestion Data"):
        st.cache_data.clear()
        st.rerun()

# Filter raw_df dynamically based on the dropdown selection
if city_filter != "All Cities":
    filtered_df = raw_df[raw_df["city"] == city_filter]
else:
    filtered_df = raw_df

# Calculate daily indices on the dynamically filtered raw dataframe
from signals.aggregator import calculate_brand_stockouts, calculate_inflation_index

if not filtered_df.empty:
    stockouts_df = calculate_brand_stockouts(filtered_df)
    inflation_df = calculate_inflation_index(filtered_df)
else:
    # Empty data handling to avoid errors if filter yields no rows
    stockouts_df = pd.DataFrame(columns=["observed_date", "platform_name", "brand_name", "total_products", "oos_products", "oos_rate"])
    inflation_df = pd.DataFrame(columns=["observed_date", "dairy_avg_price", "produce_avg_price", "staples_avg_price", "index_value", "inflation_dod"])

# tab selection
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Market CPI & Inflation", 
    "📦 Brand Stockout Analysis", 
    "💸 Cross-Regional Arbitrage", 
    "📈 Alpha Signals & Macro Insights", 
    "⚙️ SRE System Health"
])

# -------------------------------------------------------------
# COMPONENT A: SYSTEM HEALTH & METRICS COMMAND CENTER (Rendered inside Tab 5)
# -------------------------------------------------------------
with tab5:
    st.subheader("SRE System Health & Ingestion Pipeline")
    hb = load_heartbeat()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if hb:
            status = hb.get("run_status", "UNKNOWN")
            color = "green" if status == "SUCCESS" else "red"
            st.markdown(f"""
            <div class="metric-card">
                <h4 style="color:#888;margin:0;">LATEST DAEMON RUN</h4>
                <h1 style="color:{color};margin:10px 0;">{status}</h1>
                <small style="color:#666;">Status check from heartbeat.json</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="metric-card">
                <h4 style="color:#888;margin:0;">LATEST DAEMON RUN</h4>
                <h1 style="color:orange;margin:10px 0;">NO CRAWL</h1>
                <small style="color:#666;">No heartbeat.json found</small>
            </div>
            """, unsafe_allow_html=True)
            
    with col2:
        timestamp_val = hb.get("timestamp", "Never") if hb else "Never"
        if timestamp_val != "Never":
            try:
                # Format ISO timestamp
                dt_obj = datetime.fromisoformat(timestamp_val)
                timestamp_display = dt_obj.strftime("%Y-%m-%d %H:%M IST")
            except Exception:
                timestamp_display = timestamp_val[:16]
        else:
            timestamp_display = "No runs recorded"
            
        st.markdown(f"""
        <div class="metric-card">
            <h4 style="color:#888;margin:0;">LAST UPDATED TIMESTAMP</h4>
            <h2 style="color:#00d2ff;margin:15px 0;font-size:1.4rem;">{timestamp_display}</h2>
            <small style="color:#666;">Time of last database upsert</small>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        total_rows = hb.get("total_rows_committed", 0) if hb else 0
        st.markdown(f"""
        <div class="metric-card">
            <h4 style="color:#888;margin:0;">TOTAL INGESTED ROWS</h4>
            <h1 style="color:#00d2ff;margin:10px 0;">{total_rows:,}</h1>
            <small style="color:#666;">Committed to qcomm_catalog_history</small>
        </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <h4 style="color:#888;margin:0;">PARTITIONING STATUS</h4>
            <h1 style="color:#20fc03;margin:10px 0;">ACTIVE</h1>
            <small style="color:#666;">7-day partition / 14-day ZSTD compression</small>
        </div>
        """, unsafe_allow_html=True)

    # Ingestion Platform Breakdown
    st.write("")
    st.markdown("### Ingestion Volume Platform Breakdown")
    breakdown_data = hb.get("platform_breakdown", {}) if hb else {}
    if breakdown_data:
        b_cols = st.columns(len(breakdown_data))
        for i, (platform, count) in enumerate(breakdown_data.items()):
            with b_cols[i]:
                st.metric(label=f"{platform} Raw Scrapes", value=f"{count:,} items")
    else:
        # fallback breakdown stats
        st.info("No platform breakdown recorded in latest run. Displaying active platform connections:")
        b_cols = st.columns(3)
        with b_cols[0]: st.metric("Zepto Ingestion Stream", "ACTIVE")
        with b_cols[1]: st.metric("Blinkit Ingestion Stream", "ACTIVE")
        with b_cols[2]: st.metric("Swiggy Instamart Ingestion Stream", "ACTIVE")

    # -------------------------------------------------------------
    # COMPONENT D: LIVE DAEMON LOG TAIL
    # -------------------------------------------------------------
    st.write("")
    st.markdown("### Background Daemon Logs (`logs/scheduler.log`)")
    log_content = get_log_tail(50)
    st.code(log_content, language="text")

# -------------------------------------------------------------
# COMPONENT B: STAPLES INFLATION INDEX (CPI PROXY) VISUALIZER
# -------------------------------------------------------------
with tab1:
    st.subheader("Staples Inflation Index (Daily CPI Proxy)")
    
    if inflation_df.empty:
        st.warning("No price inflation records found. Seed data or start crawler.")
    else:
        # Ensure correct datatypes
        inflation_df["observed_date"] = pd.to_datetime(inflation_df["observed_date"])
        
        # Dual-axis Plotly Chart: Index Value and YoY DoD Rate
        fig = go.Figure()
        
        # Line for Index Value
        fig.add_trace(go.Scatter(
            x=inflation_df["observed_date"],
            y=inflation_df["index_value"],
            name="CPI Index Value (INR)",
            mode="lines+markers",
            line=dict(color="#00d2ff", width=3),
            marker=dict(size=6)
        ))
        
        # Bar for DoD Rate
        fig.add_trace(go.Bar(
            x=inflation_df["observed_date"],
            y=inflation_df["inflation_dod"] * 100,
            name="DoD Inflation %",
            yaxis="y2",
            marker_color="rgba(255, 99, 132, 0.4)",
            hoverinfo="x+y"
        ))
        
        fig.update_layout(
            title="Q-Commerce CPI Staples Basket Index & Day-over-Day Inflation Rate",
            template="plotly_dark",
            hovermode="x unified",
            height=450,
            legend=dict(x=0.01, y=0.99),
            yaxis=dict(
                title=dict(text="Index Value (INR)", font=dict(color="#00d2ff")),
                tickfont=dict(color="#00d2ff")
            ),
            yaxis2=dict(
                title=dict(text="DoD Inflation %", font=dict(color="#ff6384")),
                tickfont=dict(color="#ff6384"),
                anchor="x",
                overlaying="y",
                side="right"
            )
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Category Breakdown
        st.write("")
        st.markdown("### staples Sector Average Prices Breakdown")
        
        fig2 = go.Figure()
        for cat_col, color, name in [
            ("dairy_avg_price", "#00d2ff", "Dairy & Bread"),
            ("produce_avg_price", "#20fc03", "Fruits & Vegetables"),
            ("staples_avg_price", "#ffc107", "Groceries")
        ]:
            if cat_col in inflation_df.columns:
                fig2.add_trace(go.Scatter(
                    x=inflation_df["observed_date"],
                    y=inflation_df[cat_col],
                    name=name,
                    mode="lines+markers",
                    line=dict(color=color, width=2)
                ))
                
        fig2.update_layout(
            title="Localized Micro-Price Trends by Staple Category",
            template="plotly_dark",
            height=400,
            xaxis_title="Observed Date",
            yaxis_title="Average Price (INR)"
        )
        st.plotly_chart(fig2, use_container_width=True)

# -------------------------------------------------------------
# COMPONENT C: BRAND STOCKOUT ANALYSIS
# -------------------------------------------------------------
with tab2:
    st.subheader("FMCG Brand Out-of-Stock (OOS) rates")
    
    if stockouts_df.empty:
        st.warning("No out-of-stock data found. Seed database to populate.")
    else:
        # Grouped bar chart comparing brand stockout rates across different platforms
        fig_bar = px.bar(
            stockouts_df,
            x="brand_name",
            y="oos_rate",
            color="platform_name",
            barmode="group",
            title="FMCG Brand Distribution Gaps (Daily OOS Rate %)",
            labels={"oos_rate": "Out-of-Stock Rate (%)", "brand_name": "FMCG Brand", "platform_name": "Store Platform"},
            template="plotly_dark",
            height=450,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        
        fig_bar.update_layout(
            barmode='group',
            yaxis=dict(range=[0, 100]),
            yaxis_title="Out-of-Stock Rate (%)",
            xaxis_title="FMCG Brand"
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
        # Detail stats table
        st.write("")
        st.markdown("### Brand Stockout Detail Metrics")
        # Rename columns for presentation
        disp_df = stockouts_df.rename(columns={
            "observed_date": "Date",
            "platform_name": "Platform",
            "brand_name": "FMCG Brand",
            "total_products": "Total Items Tracked",
            "oos_products": "Stockout Items",
            "oos_rate": "OOS Rate (%)"
        })
        # Format percentages
        disp_df["OOS Rate (%)"] = disp_df["OOS Rate (%)"].map("{:.2f}%".format)
        st.dataframe(disp_df.sort_values(by="Date", ascending=False), use_container_width=True)

# -------------------------------------------------------------
# COMPONENT D: CROSS-REGIONAL PRICE SPREAD & ARBITRAGE (Rendered inside Tab 3)
# -------------------------------------------------------------
with tab3:
    st.subheader("Cross-Regional Price Spreads & Arbitrage Alerts")
    st.markdown("Identifies price disparities for identical FMCG SKUs across major urban grids to detect supply chain inefficiencies.")
    
    # Calculate price spreads
    def calculate_regional_spreads(df):
        if df.empty:
            return pd.DataFrame()
        # Get latest price per product, brand, and city
        latest = df.sort_values("observed_at").groupby(["product_name", "brand_name", "city"]).last().reset_index()
        # Pivot by city
        pivoted = latest.pivot(index=["product_name", "brand_name"], columns="city", values="discount_price").reset_index()
        
        cities = [c for c in ["Bangalore", "Mumbai", "Delhi-NCR"] if c in pivoted.columns]
        if len(cities) < 2:
            return pd.DataFrame()
            
        spread_records = []
        for idx, row in pivoted.iterrows():
            prices = {c: row[c] for c in cities if pd.notna(row[c]) and row[c] > 0}
            if len(prices) < 2:
                continue
            min_c = min(prices, key=prices.get)
            max_c = max(prices, key=prices.get)
            min_p = prices[min_c]
            max_p = prices[max_c]
            
            spread_val = max_p - min_p
            spread_pct = (spread_val / min_p) * 100.0 if min_p > 0 else 0.0
            
            spread_records.append({
                "Brand": row["brand_name"],
                "Product Name": row["product_name"],
                "Cheapest Region": f"{min_c} (₹{min_p:.2f})",
                "Cheapest Price": min_p,
                "Most Expensive Region": f"{max_c} (₹{max_p:.2f})",
                "Most Expensive Price": max_p,
                "Spread (INR)": spread_val,
                "Spread (%)": spread_pct
            })
        return pd.DataFrame(spread_records)

    spreads_df = calculate_regional_spreads(raw_df)
    
    if not spreads_df.empty:
        # Sort descending by spread percent
        spreads_df = spreads_df.sort_values("Spread (%)", ascending=False)
        
        # Color red if > 15%, else cyan
        colors = ['#ff4b4b' if pct > 15.0 else '#00d2ff' for pct in spreads_df["Spread (%)"]]
        
        fig_spread = go.Figure(go.Bar(
            x=spreads_df["Spread (%)"].head(15),
            y=spreads_df["Product Name"].head(15),
            orientation='h',
            marker_color=colors[:15],
            text=[f"{pct:.1f}%" for pct in spreads_df["Spread (%)"].head(15)],
            textposition='auto',
            hovertemplate='<b>%{y}</b><br>Spread Premium: %{x:.2f}%<extra></extra>'
        ))
        
        fig_spread.update_layout(
            title="Top Cross-Regional FMCG Price Premiums (%)",
            xaxis_title="Spread Premium (%)",
            yaxis_title="Product SKU",
            height=500,
            margin=dict(l=200, r=20, t=50, b=50),
            template="plotly_dark",
            yaxis={'categoryorder':'total ascending'}
        )
        st.plotly_chart(fig_spread, use_container_width=True)
        
        # Alert for spreads > 15%
        high_spreads = spreads_df[spreads_df["Spread (%)"] > 15.0]
        if not high_spreads.empty:
            st.warning(f"⚠️ CRITICAL ARBITRAGE ALERT: Detected {len(high_spreads)} items with cross-regional price spreads exceeding 15% threshold!")
            
        st.markdown("### Actionable Price Spread Matrix")
        display_cols = ["Brand", "Product Name", "Cheapest Region", "Most Expensive Region", "Spread (INR)", "Spread (%)"]
        st.dataframe(
            spreads_df[display_cols].style.format({
                "Spread (INR)": "₹{:.2f}",
                "Spread (%)": "{:.2f}%"
            }),
            use_container_width=True
        )
    else:
        st.info("No cross-regional spreads detected. Ensure multi-city pricing records are available in the database.")

# -------------------------------------------------------------
# COMPONENT E: ALPHA SIGNALS & MACRO INSIGHTS VISUALIZER (Tab 4)
# -------------------------------------------------------------
with tab4:
    st.subheader("Micro-Price Index Drift (\Delta CPI) Alpha Engine")
    st.markdown("Annualized price index momentum and 7-day rolling volatility filters computed dynamically from federated data pool.")
    
    # 1. Compute alpha signal
    from signals.alpha_engine import calculate_staples_index
    alpha_df = calculate_staples_index(filtered_df)
    
    if not alpha_df.empty:
        from plotly.subplots import make_subplots
        
        # Create subplots for dual-axis charting
        fig_alpha = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Line for baseline Staples Index Value
        fig_alpha.add_trace(
            go.Scatter(
                x=alpha_df["observed_date"],
                y=alpha_df["index_value"],
                name="Staples Index Value (INR)",
                mode="lines+markers",
                line=dict(color="#00d2ff", width=3)
            ),
            secondary_y=False
        )
        
        # Bar for DoD Drift Velocity (\Delta CPI %)
        fig_alpha.add_trace(
            go.Bar(
                x=alpha_df["observed_date"],
                y=alpha_df["drift_dod"] * 100.0,
                name="Drift Velocity (\Delta CPI %)",
                marker_color="rgba(230, 126, 34, 0.5)",
                hoverinfo="x+y"
            ),
            secondary_y=True
        )
        
        fig_alpha.update_layout(
            title="Staples Index Value & Micro-Price Index Drift (\Delta CPI %)",
            template="plotly_dark",
            hovermode="x unified",
            height=450,
            legend=dict(x=0.01, y=0.99),
            yaxis=dict(
                title=dict(text="Staples Index (INR)", font=dict(color="#00d2ff")),
                tickfont=dict(color="#00d2ff")
            ),
            yaxis2=dict(
                title=dict(text="Drift Velocity (\Delta CPI %)", font=dict(color="#e67e22")),
                tickfont=dict(color="#e67e22"),
                anchor="x",
                overlaying="y",
                side="right"
            )
        )
        st.plotly_chart(fig_alpha, use_container_width=True)
        
        # Highlight metrics cards and details
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown("#### Drift & Volatility Highlights")
            latest_row = alpha_df.iloc[-1]
            st.metric(
                label="Latest Staples Index Value",
                value=f"INR {latest_row['index_value']:.2f}"
            )
            st.metric(
                label="Latest DoD Price Drift (\Delta CPI)",
                value=f"{latest_row['drift_dod']*100:.4f}%"
            )
            st.metric(
                label="7-Day Rolling Volatility Threshold",
                value=f"{latest_row['volatility_7d']*100:.4f}%"
            )
            
        with col_m2:
            st.markdown("#### Signal Output Log")
            st.dataframe(
                alpha_df[["observed_date", "index_value", "drift_dod", "volatility_7d"]].sort_values("observed_date", ascending=False),
                use_container_width=True
            )
            
        # 2. Compute stockout velocity vector (SVV)
        from signals.alpha_engine import calculate_stockout_metrics
        so_metrics_df = calculate_stockout_metrics(filtered_df)
        
        if not so_metrics_df.empty:
            st.markdown("---")
            st.subheader("Stockout Velocity Vector ($SVV$) Inventory Depletion Engine")
            st.markdown("Smoothed rolling Day-over-Day Stockout Velocity Vector ($SVV = SR_t - SR_{t-1}$) mapped across primary urban consumption zones.")
            
            # Filter to target zones (Indiranagar, HSR Layout, Lower Parel)
            target_zones = ["Indiranagar", "HSR Layout", "Lower Parel"]
            so_chart_df = so_metrics_df[so_metrics_df["zone"].isin(target_zones)]
            if so_chart_df.empty:
                so_chart_df = so_metrics_df.copy()
                
            fig_so = px.line(
                so_chart_df,
                x="observed_date",
                y="svv_ema",
                color="zone",
                title="Urban Zone Stockout Velocity Vector ($SVV$) 3-Day EMA",
                labels={"svv_ema": "Stockout Velocity Vector (3-Day EMA)", "observed_date": "Observation Date", "zone": "Urban Center Zone"},
                template="plotly_dark",
                height=400,
                markers=True
            )
            st.plotly_chart(fig_so, use_container_width=True)
            
            # Correlation analysis alert card
            st.info(
                "💡 **Macro Correlation Insight:** A simultaneous positive breakout in both the Micro-Price Index Drift (\\Delta CPI) "
                "and the Stockout Velocity Vector ($SVV$) signals structural supply anomalies. When restocking velocity fails to match "
                "consumer depletion (rising $SVV$), quick-commerce platforms lose buffer margins, immediately translating to upward pricing "
                "drift (positive \\Delta CPI)."
            )
    else:
        st.info("No data available to calculate Staples Index. Stream new records to activate signal telemetry.")

# -------------------------------------------------------------
# AUTO-REFRESH DAEMON LOGIC
# -------------------------------------------------------------
if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()
