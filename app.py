import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.signal import savgol_filter
from datetime import timedelta
import os
import zipfile
import io

st.set_page_config(layout="wide")

# SAFE KALEIDO CHECK
try:
    import kaleido
    KALEIDO_AVAILABLE = True
except:
    KALEIDO_AVAILABLE = False

# LOGO
logo_path = os.path.join(os.path.dirname(__file__), "Envision.png")
col1, col2, col3 = st.columns([1,2,1])
with col2:
    if os.path.exists(logo_path):
        st.image(logo_path, width=300)

# TITLE
st.title("Power Curve Analytics Report")

# SITE CAPACITY
SITE_CAPACITY = {site:3.3 for site in [
"CIP Hatalageri","JSW Tuljapur","Blupine Sagapara","Kalavad GJ","Kalavad_PH2",
"AMP_Energy","Wanki","CleanMax Motadevaliya","Ayana Amerli","Mahadev PH1",
"Blupine-I, Ambada-GJ","ACME Shapar","FP_Kudligi","Sprng TN",
"Otha Pithalpur-GJ","AMGEPL,Kurnool AP","ReNew1_Gadag","partner Ottapidaum",
"Cleanmax SANATHALI","Cleanmax Babra","RenfraEnergy Trichy","RENEW-03 Sholapur",
"Renew2 Chandwad","ReNew-4 Patoda","Clean max Jagalur","Sembcorp Tuticorin",
"Renew-4 Kudligi","Renew Otha","Cleanmax Honavad","Blueleaf Agar",
"JSW_Sandur","India_Hero_Doni"
]}

REF_FILE = "India site Standard & Theoretical PC data 1234.xlsx"
BIN_SIZE = 0.5

# SIDEBAR
st.sidebar.subheader("Upload SCADA File")
uploaded_file = st.sidebar.file_uploader("Upload SCADA CSV", type=["csv"])

if uploaded_file is None:
    st.warning("Please upload SCADA file")
    st.stop()

site = st.sidebar.selectbox("Select Site", list(SITE_CAPACITY.keys()))

mode = st.sidebar.radio(
    "Select View",
    ["Single Turbine", "Compare Turbines", "Show All Turbines"]
)

# LOAD SCADA
@st.cache_data
def load_scada(file):
    df = pd.read_csv(file, low_memory=False)
    df.columns = df.columns.str.strip()

    wind_col = [c for c in df.columns if "wind" in c.lower()][0]
    power_col = [c for c in df.columns if "power" in c.lower() or "active" in c.lower()][0]
    time_col = [c for c in df.columns if "time" in c.lower()][0]

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df[wind_col] = pd.to_numeric(df[wind_col], errors="coerce")
    df[power_col] = pd.to_numeric(df[power_col], errors="coerce")

    df = df.dropna(subset=[wind_col,power_col,time_col])
    df["Name"] = df["Name"].astype(str).str.strip()

    return df, wind_col, power_col, time_col

df, wind_col, power_col, time_col = load_scada(uploaded_file)

# DATE FILTER
st.sidebar.markdown("## 📅 Select Date & Time Range")

min_date = df[time_col].min()
max_date = df[time_col].max()

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=[max_date - timedelta(days=15), max_date],
    min_value=min_date,
    max_value=max_date
)

if isinstance(date_range, list) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = date_range
    end_date = date_range

start_datetime = pd.to_datetime(start_date)
end_datetime = pd.to_datetime(end_date) + timedelta(days=1) - timedelta(seconds=1)

df = df[(df[time_col] >= start_datetime) & (df[time_col] <= end_datetime)]

st.info(f"Total Data Points After Filter: {len(df)}")

# HEADER
num_turbines = df["Name"].nunique()
capacity_per_turbine = SITE_CAPACITY.get(site, 3.3)
total_capacity = num_turbines * capacity_per_turbine

st.subheader(f"{site} | {num_turbines} Turbines | {capacity_per_turbine} MW Each | Total: {round(total_capacity,2)} MW")

# LOAD REFERENCE
@st.cache_data
def load_reference(site):
    ref_raw = pd.read_excel(REF_FILE, header=None)

    for r in range(ref_raw.shape[0]):
        for c in range(ref_raw.shape[1]):
            if site.lower() in str(ref_raw.iloc[r,c]).lower():
                ref = ref_raw.iloc[r+2:r+60,[c-1,c+3]].copy()
                ref.columns=["WindSpeed","RefPower"]
                ref = ref.dropna()

                ref["WindSpeed"]=pd.to_numeric(ref["WindSpeed"], errors="coerce")
                ref["RefPower"]=pd.to_numeric(ref["RefPower"], errors="coerce")

                wind_bins = np.arange(4,10,BIN_SIZE)
                ref_interp = np.interp(wind_bins, ref["WindSpeed"], ref["RefPower"])

                return pd.DataFrame({"WindBin":wind_bins,"RefPower":ref_interp})

    st.error("Site not found")
    st.stop()

ref_curve = load_reference(site)

# PROCESS
def process_turbine(t):
    df_all = df[df["Name"]==t].copy()

    df_scatter = df_all.copy()

    df_curve = df_all[(df_all[wind_col]>=3)&(df_all[wind_col]<=25)&(df_all[power_col]>0)]

    if len(df_curve)<30:
        return None

    df_curve["WindBin"] = (df_curve[wind_col]/BIN_SIZE).round()*BIN_SIZE
    actual = df_curve.groupby("WindBin").agg(AvgPower=(power_col,"mean")).reset_index()

    merged = ref_curve.merge(actual,on="WindBin",how="left")

    valid = merged["AvgPower"].notna()
    if valid.sum()>7:
        merged.loc[valid,"AvgPower"] = savgol_filter(merged.loc[valid,"AvgPower"],7,2)

    merged["Deviation_%"] = ((merged["AvgPower"]-merged["RefPower"])/merged["RefPower"])*100
    avg_dev = merged["Deviation_%"].mean(skipna=True)

    availability = (len(df_curve)/len(df_all))*100 if len(df_all)>0 else 0

    return df_scatter, merged, avg_dev, availability

# GRAPH (🔥 FIXED SCATTER VISIBILITY)
def plot_graph(df_scatter, merged, title, dev, availability):

    n = len(df_scatter)

    if n < 200:
        size, op = 7, 0.9
    elif n < 1000:
        size, op = 5, 0.6
    else:
        size, op = 3, 0.3

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_scatter[wind_col],
        y=df_scatter[power_col],
        mode='markers',
        marker=dict(size=size, opacity=op),
        name=f"Scatter ({n})"
    ))

    fig.add_trace(go.Scatter(
        x=merged["WindBin"],
        y=merged["AvgPower"],
        mode='lines+markers',
        name="Actual Curve"
    ))

    fig.add_trace(go.Scatter(
        x=merged["WindBin"],
        y=merged["RefPower"],
        mode='lines',
        line=dict(dash='dash'),
        name="Reference Curve"
    ))

    return fig

# MODE
turbines = df["Name"].unique()

if mode == "Single Turbine":
    turbines_to_show = [st.sidebar.selectbox("Select Turbine", turbines)]
elif mode == "Compare Turbines":
    turbines_to_show = st.sidebar.multiselect("Select Turbines", turbines)
else:
    turbines_to_show = turbines

# DISPLAY
results = []

for t in turbines_to_show:
    res = process_turbine(t)
    if not res:
        continue

    df_scatter, merged, dev, availability = res

    fig = plot_graph(df_scatter, merged, t, dev, availability)
    st.plotly_chart(fig, use_container_width=True)

    results.append({
        "Turbine": t,
        "Deviation_%": round(dev, 2),
        "Availability_%": round(availability,1)
    })

# TABLE WITH COLORS
st.subheader("Turbine Ranking")

results_df = pd.DataFrame(results).sort_values(by="Deviation_%")

def color_dev(val):
    if val < -10:
        return "background-color:red;color:white"
    elif val < -2:
        return "background-color:orange"
    elif val > 8:
        return "background-color:green;color:white"
    elif val > 2:
        return "background-color:lightgreen"
    else:
        return "background-color:white"

styled_df = results_df.style.applymap(color_dev, subset=["Deviation_%"])

st.dataframe(styled_df, use_container_width=True)
