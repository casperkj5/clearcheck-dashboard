import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="ClearCheck Approval Analysis", layout="wide")

# ---- Load data ----
@st.cache_data
def load_data():
    approvals = pd.read_excel("ClearCheck_Dashboard_Data.xlsx", sheet_name="approvals")
    daily = pd.read_excel("ClearCheck_Dashboard_Data.xlsx", sheet_name="daily")
    approvals["date"] = pd.to_datetime(approvals["date"]).dt.date
    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    return approvals, daily

approvals, daily = load_data()

st.title("ClearCheck Technologies: Approval Behavior Analysis")

# ---- Sidebar filters ----
st.sidebar.header("Filters")

technicians = sorted(approvals["technician"].unique())
selected_technicians = st.sidebar.multiselect("Technician", technicians, default=technicians)

min_date = approvals["date"].min()
max_date = approvals["date"].max()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

fast_threshold = st.sidebar.slider("Fast-approval threshold (seconds)", 1, 60, 10)

# ---- Apply filters ----
filtered = approvals[
    (approvals["technician"].isin(selected_technicians))
    & (approvals["date"] >= start_date)
    & (approvals["date"] <= end_date)
]

filtered_daily = daily[
    (daily["technician"].isin(selected_technicians))
    & (daily["date"] >= start_date)
    & (daily["date"] <= end_date)
]

total_approvals = len(filtered)

if total_approvals == 0:
    st.warning("No data matches the current filters. Try widening the date range or technician selection.")
    st.stop()

# ---- KPI row ----
col1, col2, col3, col4 = st.columns(4)

avg_duration = filtered["duration_seconds_clean"].mean()
fast_pct = (filtered["duration_seconds_clean"] < fast_threshold).mean() * 100
total_revenue = filtered["pay_amount"].sum()

col1.metric("Total Approvals", f"{total_approvals:,}")
col2.metric("Average Duration (sec)", f"{avg_duration:.1f}" if pd.notna(avg_duration) else "N/A")
col3.metric(f"Under {fast_threshold} sec", f"{fast_pct:.1f}%")
col4.metric("Total Revenue", f"${total_revenue:,.0f}")

# ---- Duration histogram ----
st.subheader("Distribution of Approval Durations")

hist_data = filtered["duration_seconds_clean"].dropna()
hist_data_zoom = hist_data[hist_data <= 60]

fig, ax = plt.subplots(figsize=(10, 4))
ax.hist(hist_data_zoom, bins=60, color="steelblue")
ax.axvline(fast_threshold, color="red", linestyle="--", label=f"{fast_threshold}-second cutoff")
ax.set_xlabel("Duration (seconds)")
ax.set_ylabel("Number of Approvals")
ax.legend()
st.pyplot(fig)

st.caption(
    f"Zoomed to 0-60 seconds, where most approvals fall. "
    f"{fast_pct:.1f}% of approvals in the current selection happened in under {fast_threshold} seconds."
)

# ---- Top approval days ----
st.subheader("Top Approval Days")

top_days = filtered_daily.sort_values("approvals", ascending=False).head(10)
labels = top_days["date"].astype(str) + " (" + top_days["technician"] + ")"

fig2, ax2 = plt.subplots(figsize=(10, 4))
ax2.bar(labels, top_days["approvals"], color="steelblue")
ax2.set_ylabel("Approvals")
plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")
st.pyplot(fig2)

# ---- Block analysis ----
st.subheader("Approval Blocks (Review Sessions)")
st.write(
    "A block is a run of approvals with no gap of 10 minutes or more between them, "
    "treated as one continuous review session. Everything below reflects your current filters."
)

block_summary_filtered = filtered.groupby(["technician", "block_id"]).agg(
    case_count=("duration_seconds_clean", "size"),
    block_start=("approval_date", "min"),
    block_end=("approval_date", "max"),
).reset_index()

block_summary_filtered["block_length_seconds"] = (
    block_summary_filtered["block_end"] - block_summary_filtered["block_start"]
).dt.total_seconds()
block_summary_filtered["avg_seconds_per_case"] = (
    block_summary_filtered["block_length_seconds"] / (block_summary_filtered["case_count"] - 1)
)

block_kpis = block_summary_filtered.groupby("technician").agg(
    num_blocks=("block_id", "count"),
    avg_cases_per_block=("case_count", "mean"),
    avg_seconds_per_case=("avg_seconds_per_case", "mean"),
)
st.dataframe(block_kpis.style.format({"avg_cases_per_block": "{:.1f}", "avg_seconds_per_case": "{:.1f}"}))

st.write("Time between approvals within each technician's single largest review session in the current selection:")

largest_blocks = block_summary_filtered.loc[block_summary_filtered.groupby("technician")["case_count"].idxmax()]

fig3, axes3 = plt.subplots(nrows=len(largest_blocks), ncols=1, figsize=(10, 4 * len(largest_blocks)), sharey=True)
if len(largest_blocks) == 1:
    axes3 = [axes3]

for ax, (_, row) in zip(axes3, largest_blocks.iterrows()):
    tech = row["technician"]
    b_id = row["block_id"]
    block_rows = filtered[(filtered["technician"] == tech) & (filtered["block_id"] == b_id)].reset_index(drop=True)
    block_rows["case_order"] = block_rows.index + 1
    block_rows = block_rows.iloc[1:]

    ax.plot(block_rows["case_order"], block_rows["duration_seconds_clean"], marker="o", markersize=3)
    ax.set_title(f"{tech} - Largest Session ({int(row['case_count'])} cases)")
    ax.set_ylabel("Seconds since previous approval")
    ax.set_ylim(0, 120)

axes3[-1].set_xlabel("Case order within the session")
plt.tight_layout()
st.pyplot(fig3)
