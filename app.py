# DISPLAY MODE
mode = st.radio(
    "Display Mode",
    ["Show Single Turbine","Compare Two Turbines","Show All Turbines"]
)

# =========================
# SINGLE TURBINE
# =========================
if mode=="Show Single Turbine":

    selected = st.selectbox("Select Turbine",results_df["Turbine"])

    df_filtered,merged,avg_dev = process_turbine(selected)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_filtered[wind_col],
        y=df_filtered[power_col],
        mode='markers',
        name="SCADA Data"
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
        name="Reference Curve"
    ))

    st.plotly_chart(fig,use_container_width=True)


# =========================
# COMPARE TWO TURBINES
# =========================
elif mode=="Compare Two Turbines":

    t1 = st.selectbox("Turbine 1",results_df["Turbine"])
    t2 = st.selectbox("Turbine 2",results_df["Turbine"],index=1)

    df1,merged1,dev1 = process_turbine(t1)
    df2,merged2,dev2 = process_turbine(t2)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=merged1["WindBin"],
        y=merged1["AvgPower"],
        mode='lines+markers',
        name=t1
    ))

    fig.add_trace(go.Scatter(
        x=merged2["WindBin"],
        y=merged2["AvgPower"],
        mode='lines+markers',
        name=t2
    ))

    fig.add_trace(go.Scatter(
        x=merged1["WindBin"],
        y=merged1["RefPower"],
        mode='lines',
        name="Reference",
        line=dict(dash='dash')
    ))

    st.plotly_chart(fig,use_container_width=True)

    # ✅ COMMENT ADDED
    if dev1 < dev2:
        better = t2
        worse = t1
    else:
        better = t1
        worse = t2

    st.info(f"👉 {better} is performing better than {worse} based on deviation.")


# =========================
# ALL TURBINES
# =========================
else:

    cols = st.columns(2)
    i=0

    for turbine in results_df["Turbine"]:

        df_filtered,merged,avg_dev = process_turbine(turbine)

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df_filtered[wind_col],
            y=df_filtered[power_col],
            mode='markers',
            name="SCADA Data",
            marker=dict(size=3,opacity=0.4)
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
            name="Reference",
            line=dict(dash='dash')
        ))

        # ✅ STACKING COMMENT
        comment = ""
        if abs(avg_dev) >= 20:
            comment = "⚠️ Stacking Effect Suspected"

        fig.update_layout(
            title=f"{turbine} | Dev {round(avg_dev,1)} % {comment}",
            height=350
        )

        cols[i%2].plotly_chart(fig,use_container_width=True)

        i+=1
