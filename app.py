import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.signal import savgol_filter
from datetime import timedelta
import os
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(layout="wide")

# ---------------- LOGO ----------------
logo_path = os.path.join(os.path.dirname(__file__), "Envision.png")

col1, col2, col3 = st.columns([1,2,1])
with col2:
    if os.path.exists(logo_path):
        st.image(logo_path, width=250)

st.title("Power Curve Analytics Report")

# ---------------- CONSTANTS ----------------
BIN_SIZE = 0.5
REF_FILE = "India site Standard & Theoretical PC data 1234.xlsx"

# ---------------- SIDEBAR ----------------
uploaded_file = st.sidebar.file_uploader("Upload SCADA CSV", type=["csv"])

if uploaded_file is None:
    st.warning("Upload SCADA file")
    st.stop()

# ---------------- LOAD ----------------
@st.cache_data
def load_scada(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()

    wind_col = [c for c in df.columns if "wind" in c.lower()][0]
    power_col = [c for c in df.columns if "power" in c.lower() or "active" in c.lower()][0]
    time_col = [c for c in df.columns if "time" in c.lower()][0]

    df[time_col] = pd.to_datetime(df[time_col])
    df[wind_col] = pd.to_numeric(df[wind_col], errors="coerce")
    df[power_col] = pd.to_numeric(df[power_col], errors="coerce")

    df = df.dropna()
    df["Name"] = df["Name"].astype(str)

    return df, wind_col, power_col, time_col

df, wind_col, power_col, time_col = load_scada(uploaded_file)

# ---------------- DATE FILTER ----------------
min_date = df[time_col].min()
max_date = df[time_col].max()

date_range = st.sidebar.date_input(
    "Select Date Range",
    [max_date - timedelta(days=15), max_date]
)

start = pd.to_datetime(date_range[0])
end = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1)

df = df[(df[time_col] >= start) & (df[time_col] < end)]

st.info(f"Data Points: {len(df)}")
st.markdown(f"**Date Range:** {start} → {end}")

# ---------------- REFERENCE ----------------
@st.cache_data
def load_reference():
    ref = pd.read_excel(REF_FILE)
    ref.columns = ["WindBin", "RefPower"]
    return ref

ref_curve = load_reference()

# ---------------- PROCESS ----------------
def process_turbine(t):
    d = df[df["Name"] == t]

    df_scatter = d.copy()
    df_curve = d[(d[wind_col] >= 3) & (d[power_col] > 0)]

    if len(df_curve) < 20:
        return None

    df_curve["WindBin"] = (df_curve[wind_col] / BIN_SIZE).round() * BIN_SIZE
    actual = df_curve.groupby("WindBin")[power_col].mean().reset_index()
    actual.columns = ["WindBin", "AvgPower"]

    merged = ref_curve.merge(actual, on="WindBin", how="left")

    valid = merged["AvgPower"].notna()
    if valid.sum() > 5:
        merged.loc[valid, "AvgPower"] = savgol_filter(merged.loc[valid, "AvgPower"], 5, 2)

    merged["Deviation_%"] = ((merged["AvgPower"] - merged["RefPower"]) / merged["RefPower"]) * 100
    dev = merged["Deviation_%"].mean()

    availability = (len(df_curve) / len(d)) * 100

    return df_scatter, merged, dev, availability

# ---------------- COMMENT ----------------
def comment(dev):
    if dev < -10:
        return "Severe underperformance"
    elif dev < -2:
        return "Underperformance"
    elif dev > 8:
        return "High overperformance"
    elif dev > 2:
        return "Slight overperformance"
    else:
        return "Normal"

# ---------------- GRAPH ----------------
def plot_graph(df_scatter, merged, t):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_scatter[wind_col],
        y=df_scatter[power_col],
        mode='markers',
        marker=dict(size=3, opacity=0.3),
        name="Scatter"
    ))

    fig.add_trace(go.Scatter(
        x=merged["WindBin"],
        y=merged["AvgPower"],
        mode='lines+markers',
        name="Actual"
    ))

    fig.add_trace(go.Scatter(
        x=merged["WindBin"],
        y=merged["RefPower"],
        mode='lines',
        name="Reference"
    ))

    return fig

# ---------------- DISPLAY ----------------
results = []
images = []

for t in df["Name"].unique():
    res = process_turbine(t)
    if not res:
        continue

    df_scatter, merged, dev, avail = res

    fig = plot_graph(df_scatter, merged, t)
    st.plotly_chart(fig, use_container_width=True)

    st.write(f"Comment: {comment(dev)}")

    img_bytes = fig.to_image(format="png")
    images.append((t, img_bytes, dev, avail, comment(dev)))

    results.append([t, round(dev,2), round(avail,1)])

# ---------------- TABLE ----------------
st.subheader("Turbine Ranking")
df_res = pd.DataFrame(results, columns=["Turbine","Deviation","Availability"])
st.dataframe(df_res)

# ---------------- PDF GENERATION ----------------
def get_color(dev):
    if dev < -10:
        return colors.red
    elif dev < -2:
        return colors.orange
    elif dev > 8:
        return colors.green
    elif dev > 2:
        return colors.lightgreen
    else:
        return colors.whitesmoke

def create_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    elements = []

    # -------- HEADER --------
    if os.path.exists(logo_path):
        elements.append(Image(logo_path, width=120, height=50))

    elements.append(Paragraph("Power Curve Analytics Report", styles["Title"]))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Date Range: {start} to {end}", styles["Normal"]))
    elements.append(Paragraph(f"Total Turbines: {len(results)}", styles["Normal"]))
    elements.append(Paragraph(f"Total Data Points: {len(df)}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    # -------- TURBINE PAGES --------
    for t, img, dev, avail, comm in images:
        elements.append(Paragraph(f"Turbine: {t}", styles["Heading2"]))
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(f"Deviation: {round(dev,2)}%", styles["Normal"]))
        elements.append(Paragraph(f"Availability: {round(avail,1)}%", styles["Normal"]))
        elements.append(Paragraph(f"Comment: {comm}", styles["Normal"]))
        elements.append(Spacer(1, 10))

        img_file = io.BytesIO(img)
        elements.append(Image(img_file, width=480, height=260))

        elements.append(PageBreak())  # 👈 one turbine per page

    # -------- RANKING TABLE --------
    table_data = [["Turbine","Deviation","Availability"]] + results
    table = Table(table_data)

    style = TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID',(0,0),(-1,-1),1,colors.black)
    ])

    for i, row in enumerate(results, start=1):
        style.add('BACKGROUND', (1,i), (1,i), get_color(row[1]))

    table.setStyle(style)

    elements.append(Paragraph("Turbine Ranking", styles["Heading2"]))
    elements.append(Spacer(1,10))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# ---------------- DOWNLOAD ----------------
pdf = create_pdf()

st.download_button(
    "Download Full Professional Report (PDF)",
    data=pdf,
    file_name="WindFarm_Professional_Report.pdf",
    mime="application/pdf"
)
