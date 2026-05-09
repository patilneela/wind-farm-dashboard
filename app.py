import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.signal import savgol_filter
from datetime import timedelta
import os
import io

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak
)

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus.paragraph import Paragraph
from reportlab.lib.styles import ParagraphStyle

st.set_page_config(layout="wide")

# ---------------- LOGO ----------------
logo_path = os.path.join(os.path.dirname(__file__), "Envision.png")

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    if os.path.exists(logo_path):
        st.image(logo_path, width=260)

st.title("Power Curve Analytics Report")

# ---------------- CONSTANTS ----------------
BIN_SIZE = 0.5
REF_FILE = "India site Standard & Theoretical PC data 1234.xlsx"

# ---------------- SIDEBAR ----------------
uploaded_file = st.sidebar.file_uploader(
    "Upload SCADA CSV",
    type=["csv"]
)

if uploaded_file is None:
    st.warning("Upload SCADA file")
    st.stop()

# ---------------- LOAD DATA ----------------
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

df = df[
    (df[time_col] >= start) &
    (df[time_col] < end)
]

st.info(f"Total Data Points: {len(df)}")

st.markdown(
    f"""
    <div style="
        background-color:#f2f2f2;
        padding:10px;
        border-radius:10px;
        font-size:18px;
        font-weight:bold;">
        Date Range: {start} → {end}
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------- LOAD REFERENCE ----------------
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

    # FILTERED DATA FOR ACTUAL CURVE
    df_curve = d[
        (d[wind_col] >= 3) &
        (d[power_col] > 0)
    ]

    if len(df_curve) < 20:
        return None

    df_curve["WindBin"] = (
        (df_curve[wind_col] / BIN_SIZE).round() * BIN_SIZE
    )

    actual = df_curve.groupby("WindBin")[power_col].mean().reset_index()

    actual.columns = ["WindBin", "AvgPower"]

    merged = ref_curve.merge(
        actual,
        on="WindBin",
        how="left"
    )

    valid = merged["AvgPower"].notna()

    # FILTERED / SMOOTHED CURVE
    if valid.sum() > 5:
        merged.loc[valid, "AvgPower"] = savgol_filter(
            merged.loc[valid, "AvgPower"],
            5,
            2
        )

    merged["Deviation_%"] = (
        (
            merged["AvgPower"] - merged["RefPower"]
        ) / merged["RefPower"]
    ) * 100

    dev = merged["Deviation_%"].mean()

    availability = (
        len(df_curve) / len(d)
    ) * 100

    return df_scatter, merged, dev, availability

# ---------------- COMMENT ----------------
def comment(dev):

    if dev < -10:
        return "Severe underperformance", "#ff0000"

    elif dev < -2:
        return "Underperformance", "#ff9900"

    elif dev > 8:
        return "High overperformance", "#009900"

    elif dev > 2:
        return "Slight overperformance", "#66cc66"

    else:
        return "Normal", "#0066cc"

# ---------------- GRAPH ----------------
def plot_graph(df_scatter, merged, t):

    n = len(df_scatter)

    if n < 200:
        size, op = 7, 0.9

    elif n < 1000:
        size, op = 5, 0.6

    else:
        size, op = 3, 0.3

    fig = go.Figure()

    # SCADA DATA
    fig.add_trace(go.Scatter(
        x=df_scatter[wind_col],
        y=df_scatter[power_col],
        mode='markers',
        marker=dict(
            size=size,
            opacity=op,
            color='lightblue'
        ),
        name="SCADA Data"
    ))

    # ACTUAL CURVE
    fig.add_trace(go.Scatter(
        x=merged["WindBin"],
        y=merged["AvgPower"],
        mode='lines+markers',
        line=dict(
            width=3,
            color='green'
        ),
        marker=dict(size=7),
        name="Actual Curve"
    ))

    # REFERENCE CURVE
    fig.add_trace(go.Scatter(
        x=merged["WindBin"],
        y=merged["RefPower"],
        mode='lines',
        line=dict(
            dash='dash',
            width=3,
            color='red'
        ),
        name="Reference Curve"
    ))

    fig.update_layout(

        title=f"Power Curve Analysis - {t}",

        xaxis_title="Wind Speed (m/s)",

        yaxis_title="Power Output (kW)",

        height=600,

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),

        template="plotly_white"
    )

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

    comm, color = comment(dev)

    st.markdown(
        f"""
        <div style="
            background-color:{color};
            padding:12px;
            border-radius:10px;
            color:white;
            font-size:18px;
            font-weight:bold;
            margin-bottom:25px;">
            Comment: {comm}
            <br>
            Deviation: {round(dev,2)}%
            <br>
            Availability: {round(avail,1)}%
        </div>
        """,
        unsafe_allow_html=True
    )

    # SAVE IMAGE FOR PDF
    img_bytes = fig.to_image(
        format="png",
        width=1400,
        height=700,
        scale=2
    )

    images.append(
        (
            t,
            img_bytes,
            dev,
            avail,
            comm,
            color
        )
    )

    results.append([
        t,
        round(dev, 2),
        round(avail, 1),
        comm
    ])

# ---------------- TABLE ----------------
st.subheader("Turbine Ranking")

df_res = pd.DataFrame(
    results,
    columns=[
        "Turbine",
        "Deviation (%)",
        "Availability (%)",
        "Comment"
    ]
)

# TABLE COLOR FUNCTION
def color_comment(val):

    if "Severe" in val:
        return 'background-color: #ff0000; color:white'

    elif "Underperformance" in val:
        return 'background-color: #ff9900; color:white'

    elif "High" in val:
        return 'background-color: #009900; color:white'

    elif "Slight" in val:
        return 'background-color: #66cc66; color:black'

    else:
        return 'background-color: #0066cc; color:white'

styled_df = df_res.style.applymap(
    color_comment,
    subset=["Comment"]
)

st.dataframe(
    styled_df,
    use_container_width=True
)

# ---------------- PDF GENERATION ----------------
def create_pdf():

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()

    center_style = ParagraphStyle(
        name='Center',
        parent=styles['Heading1'],
        alignment=TA_CENTER
    )

    elements = []

    # LOGO
    if os.path.exists(logo_path):

        elements.append(
            Image(
                logo_path,
                width=180,
                height=60
            )
        )

        elements.append(Spacer(1, 20))

    # TITLE
    elements.append(
        Paragraph(
            "Power Curve Analytics Report",
            center_style
        )
    )

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            f"<b>Date Range:</b> {start} to {end}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"<b>Total Data Points:</b> {len(df)}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 20))

    # TURBINE REPORTS
    for t, img, dev, avail, comm, color in images:

        elements.append(
            Paragraph(
                f"<b>Turbine:</b> {t}",
                styles["Heading2"]
            )
        )

        elements.append(Spacer(1, 5))

        elements.append(
            Paragraph(
                f"<b>Deviation:</b> {round(dev,2)}%",
                styles["Normal"]
            )
        )

        elements.append(
            Paragraph(
                f"<b>Availability:</b> {round(avail,1)}%",
                styles["Normal"]
            )
        )

        comment_para = Paragraph(
            f"""
            <para align=center>
            <font color="white">
            <b>{comm}</b>
            </font>
            </para>
            """,
            ParagraphStyle(
                'comment',
                backColor=color,
                borderPadding=8,
                leading=20
            )
        )

        elements.append(comment_para)

        elements.append(Spacer(1, 15))

        img_file = io.BytesIO(img)

        elements.append(
            Image(
                img_file,
                width=520,
                height=300
            )
        )

        elements.append(Spacer(1, 25))

        elements.append(PageBreak())

    # ---------------- SUMMARY TABLE ----------------
    elements.append(
        Paragraph(
            "Turbine Ranking Summary",
            styles["Heading2"]
        )
    )

    elements.append(Spacer(1, 15))

    table_data = [[
        "Turbine",
        "Deviation (%)",
        "Availability (%)",
        "Comment"
    ]]

    for row in results:
        table_data.append(row)

    table = Table(table_data)

    table.setStyle(TableStyle([

        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),

        ('GRID', (0, 0), (-1, -1), 1, colors.black),

        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),

        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),

        ('ALIGN', (0, 0), (-1, -1), 'CENTER')
    ]))

    elements.append(table)

    # BUILD PDF
    doc.build(elements)

    buffer.seek(0)

    return buffer.getvalue()

# ---------------- DOWNLOAD ----------------
pdf_bytes = create_pdf()

st.download_button(
    label="Download Full Dashboard Report (PDF)",
    data=pdf_bytes,
    file_name="WindFarm_Full_Report.pdf",
    mime="application/pdf"
)
