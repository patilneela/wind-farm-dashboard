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

# KALEIDO CHECK
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

st.title("Power Curve Analytics Report")

# SITE
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
uploaded_file = st.sidebar.file_uploader("Upload SCADA CSV", type=["csv"])
if uploaded_file is None:
    st.stop()

site = st.sidebar.selectbox("Select Site", list(SITE_CAPACITY.keys()))

# LOAD
@st.cache_data
def load_scada(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()

    wind_col = [c for c in df.columns if "wind" in c.lower()][0]
    power_col = [c for c in df.columns if "power" in c.lower() or "active" in c.lower()][0]
    time_col = [c for c in df.columns if "time" in c.lower()][0]

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df[wind_col] = pd.to_numeric(df[wind_col], errors="coerce")
    df[power_col] = pd.to_numeric(df[power_col], errors="coerce")

    df = df.dropna(subset=[wind_col,power_col,time_col])
    df["Name"] = df["Name"].astype(str)

    return df, wind_col, power_col, time_col

df, wind_col, power_col, time_col = load_scada(uploaded_file)

# DATE FILTER (FIXED)
min_date = df[time_col].min()
max_date = df[time_col].max()

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=[max_date - timedelta(days=15), max_date]
)

start_date, end_date = date_range
start_datetime = pd.to_datetime(start_date)
end_datetime = pd.to_datetime(end_date) + pd.Timedelta(days=1)

df = df[(df[time_col] >= start_datetime) & (df[time_col] < end_datetime)]

st.info(f"Total Data Points: {len(df)}")

# REFERENCE
@st.cache_data
def load_reference(site):
    ref_raw = pd.read_excel(REF_FILE, header=None)

    for r in range(ref_raw.shape[0]):
        for c in range(ref_raw.shape[1]):
            if site.lower() in str(ref_raw.iloc[r,c]).lower():
                ref = ref_raw.iloc[r+2:r+60,[c-1,c+3]].copy()
                ref.columns=["WindSpeed","RefPower"]
                ref = ref.dropna()

                ref["WindSpeed"]=pd.to_numeric(ref["WindSpeed"])
                ref["RefPower"]=pd.to_numeric(ref["RefPower"])

                bins = np.arange(4,10,BIN_SIZE)
                interp = np.interp(bins, ref["WindSpeed"], ref["RefPower"])

                return pd.DataFrame({"WindBin":bins,"RefPower":interp})

ref_curve = load_reference(site)

# COMMENT
def generate_comment(dev):
    if dev < -10: return "Severe underperformance"
    elif dev < -2: return "Underperformance"
    elif dev > 8: return "High overperformance"
    elif dev > 2: return "Slight overperformance"
    else: return "Normal"

# PROCESS
def process_turbine(t):
    df_all = df[df["Name"]==t]

    df_scatter = df_all.copy()
    df_curve = df_all[(df_all[wind_col]>=3)&(df_all[power_col]>0)]

    if len(df_curve)<30:
        return None

    df_curve["WindBin"] = (df_curve[wind_col]/BIN_SIZE).round()*BIN_SIZE
    actual = df_curve.groupby("WindBin").mean().reset_index()

    merged = ref_curve.merge(actual,on="WindBin",how="left")

    merged["Deviation_%"] = ((merged[power_col]-merged["RefPower"])/merged["RefPower"])*100
    dev = merged["Deviation_%"].mean()

    return df_scatter, merged, dev

# GRAPH
def plot_graph(df_scatter, merged, t, dev):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_scatter[wind_col],y=df_scatter[power_col],mode='markers'))
    fig.add_trace(go.Scatter(x=merged["WindBin"],y=merged[power_col],mode='lines'))
    fig.add_trace(go.Scatter(x=merged["WindBin"],y=merged["RefPower"],mode='lines',line=dict(dash='dash')))
    fig.update_layout(title=f"{t} Dev:{round(dev,2)}%")
    return fig

# MAIN LOOP + REPORT
results = []
html_report = "<h1>Power Curve Report</h1>"

zip_buffer = io.BytesIO()
zip_file = zipfile.ZipFile(zip_buffer, "w")

for t in df["Name"].unique():
    res = process_turbine(t)
    if not res:
        continue

    df_scatter, merged, dev = res

    fig = plot_graph(df_scatter, merged, t, dev)
    st.plotly_chart(fig)

    comment = generate_comment(dev)

    # SAVE IMAGE
    if KALEIDO_AVAILABLE:
        img = fig.to_image(format="png")
        zip_file.writestr(f"{t}.png", img)

    # ADD TO HTML
    html_report += f"<h2>{t}</h2>"
    html_report += f"<p>Deviation: {round(dev,2)}%</p>"
    html_report += f"<p>{comment}</p>"
    html_report += f'<img src="{t}.png"><br><br>'

    results.append({"Turbine":t,"Deviation_%":round(dev,2)})

# TABLE
results_df = pd.DataFrame(results)
st.dataframe(results_df)

# ADD FILES TO ZIP
zip_file.writestr("report.csv", results_df.to_csv(index=False))
zip_file.writestr("report.html", html_report)

zip_file.close()

# DOWNLOAD
st.download_button(
    "Download Full Report (ZIP)",
    data=zip_buffer.getvalue(),
    file_name="WindFarm_Report.zip"
)
