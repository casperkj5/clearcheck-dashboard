import streamlit as st
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

st.set_page_config(page_title="ClearCheck Approval Analysis", layout="wide")

# ---- Load data ----
@st.cache_data
def load_data():
    approvals = pd.read_excel("ClearCheck_Dashboard_Data.xlsx", sheet_name="approvals")
    daily = pd.read_excel("ClearCheck_Dashboard_Data.xlsx", sheet_name="daily")
    approvals["date"] = pd.to_datetime(approvals["date"]).dt.date
    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    if "pay_period" not in daily.columns:
        cutoff = pd.Timestamp("2020-06-01").date()
        daily["pay_period"] = daily["date"].apply(lambda d: "After" if d >= cutoff else "Before")
    return approvals, daily

approvals, daily = load_data()

st.title("ClearCheck Technologies: Approval Behavior Analysis")
st.markdown("### Key Findings")
st.info(
    "- Across all three technicians, most approvals happen far faster than any professional review "
    "standard, often in single-digit seconds.\n"
    "- This isn't just gaps between shifts. Even inside continuous review sessions, Gary Arnold and "
    "Matt Shawn's pace stays extremely fast and steady, a pattern that looks mechanical rather than "
    "case-by-case judgment. Juan Mendez shows more natural, variable review times.\n"
    "- The \"we pre-review, then batch approve\" defense doesn't hold up: even in the largest single "
    "review sessions, the average time spent per case is still only seconds.\n"
    "- The payout cut from \$50 to \$17 per approval (June 2020) did not slow Gary Arnold down. His "
    "per-case speed didn't significantly change, and he approved significantly more cases per day "
    "afterward, yet his average daily earnings still fell by more than half.\n"
    "- Limitation: this data only records approvals. There is no record of rejected cases, so fast "
    "timing is strong evidence of a problem, not final proof of negligence."
)
st.divider()
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
    
fast_threshold = 10

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

# ---- Fast-approval thresholds ----
st.subheader("Fast-Approval Thresholds")

threshold_list = [2, 5, 10, 30, 60]

def threshold_table(data, group_col, value_col):
    rows = []
    for tech in selected_technicians:
        tech_data = data.loc[data[group_col] == tech, value_col].dropna()
        row = {"technician": tech, "n": len(tech_data)}
        for t in threshold_list:
            row[f"% under {t}s"] = (tech_data < t).mean() * 100 if len(tech_data) > 0 else float("nan")
        rows.append(row)
    return pd.DataFrame(rows).set_index("technician")

st.write("All approvals in the current selection:")
overall_thresholds = threshold_table(filtered, "technician", "duration_seconds_clean")
st.dataframe(overall_thresholds.style.format({c: "{:.1f}%" for c in overall_thresholds.columns if c != "n"}))

st.write("Restricted to approvals inside an active review session (excludes the gap that started each session):")
within_session = filtered[filtered["new_block"] == False]
within_thresholds = threshold_table(within_session, "technician", "duration_seconds_clean")
st.dataframe(within_thresholds.style.format({c: "{:.1f}%" for c in within_thresholds.columns if c != "n"}))

# ---- Industry standard t-tests ----
st.subheader("Does Average Review Time Meet Industry Standards?")
st.caption("One-sample t-test comparing each technician's average duration against four minimum-review-time standards.")

standard_minutes = [10, 5, 2, 1]
ttest_rows = []
for tech in selected_technicians:
    tech_data = filtered.loc[filtered["technician"] == tech, "duration_seconds_clean"].dropna()
    if len(tech_data) < 2:
        continue
    row = {"technician": tech, "mean_sec": tech_data.mean(), "median_sec": tech_data.median(), "n": len(tech_data)}
    for m in standard_minutes:
        t_stat, p_val = stats.ttest_1samp(tech_data, popmean=m * 60)
        row[f"p vs {m}-min"] = p_val
    ttest_rows.append(row)

if ttest_rows:
    ttest_table = pd.DataFrame(ttest_rows).set_index("technician")
    fmt = {"mean_sec": "{:.1f}", "median_sec": "{:.1f}", "n": "{:.0f}"}
    for m in standard_minutes:
        fmt[f"p vs {m}-min"] = "{:.5f}"
    st.dataframe(ttest_table.style.format(fmt))
    st.caption("A p-value below 0.05 means the average duration is statistically different from that standard. Compare the mean to the standard to see which direction.")

# ---- Monthly coverage chart ----
st.subheader("Approvals per Month (Full History)")
st.caption("Always shows the complete history for the selected technicians, regardless of the date filter above, so the coverage pattern stays visible.")

monthly = approvals[approvals["technician"].isin(selected_technicians)].copy()
monthly["month"] = pd.to_datetime(monthly["date"].astype(str)).dt.to_period("M").astype(str)
monthly_counts = monthly.groupby(["month", "technician"]).size().unstack(fill_value=0)

fig4, ax4 = plt.subplots(figsize=(12, 4))
monthly_counts.plot(kind="bar", ax=ax4)
ax4.set_ylabel("Approvals")
ax4.set_xlabel("Month")
plt.setp(ax4.get_xticklabels(), rotation=45, ha="right")
st.pyplot(fig4)

# ---- Top approval days ----
st.subheader("Top Approval Days")
st.caption("Each technician's own busiest days, shown separately so the comparison stays fair.")

top_days_per_tech = (
    filtered_daily.sort_values(["technician", "approvals"], ascending=[True, False])
    .groupby("technician")
    .head(3)
)

labels = top_days_per_tech["date"].astype(str) + " (" + top_days_per_tech["technician"] + ")"

colors = {"Gary Arnold": "steelblue", "Juan Mendez": "darkorange", "Matt Shawn": "seagreen"}
bar_colors = top_days_per_tech["technician"].map(colors).fillna("gray")

fig2, ax2 = plt.subplots(figsize=(10, 4))
ax2.bar(labels, top_days_per_tech["approvals"], color=bar_colors)
ax2.set_ylabel("Approvals")
plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")
st.pyplot(fig2)

# ---- Block analysis ----
st.subheader("Approval Blocks (Review Sessions)")
st.write(
    "A block is a run of approvals with no gap of 10 minutes or more between them, "
    "treated as one continuous review session."
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
    median_seconds_per_case=("avg_seconds_per_case", "median"),
)
st.dataframe(block_kpis.style.format({
    "avg_cases_per_block": "{:.1f}", "avg_seconds_per_case": "{:.1f}", "median_seconds_per_case": "{:.1f}"
}))

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

# ---- Incentive magnitude ----
st.subheader("How Attractive Was It to Move Fast?")

perspective_rows = []
for tech in selected_technicians:
    tech_rows = filtered[filtered["technician"] == tech]
    tech_daily = filtered_daily[filtered_daily["technician"] == tech]

    median_duration = tech_rows["duration_seconds_clean"].median()
    top_day_revenue = tech_daily["revenue"].max() if len(tech_daily) > 0 else float("nan")
    avg_daily_revenue = tech_daily["revenue"].mean() if len(tech_daily) > 0 else float("nan")

    common_pay = tech_rows["pay_amount"].mode()
    pay_per_case = common_pay.iloc[0] if len(common_pay) > 0 else float("nan")
    implied_hourly = (pay_per_case / median_duration) * 3600 if median_duration and median_duration > 0 else float("nan")

    perspective_rows.append({
        "technician": tech,
        "median_seconds_per_case": median_duration,
        "top_single_day_revenue": top_day_revenue,
        "avg_daily_revenue": avg_daily_revenue,
        "implied_hourly_rate_if_sustained": implied_hourly,
    })

perspective_table = pd.DataFrame(perspective_rows).set_index("technician")
st.dataframe(perspective_table.style.format({
    "median_seconds_per_case": "{:.1f}",
    "top_single_day_revenue": "${:,.0f}",
    "avg_daily_revenue": "${:,.0f}",
    "implied_hourly_rate_if_sustained": "${:,.0f}",
}))

st.caption(
    "The implied hourly rate is illustrative, not a real wage: it's what a technician's typical "
    "per-case pace would translate to if sustained non-stop for a full hour. Nobody works at that "
    "pace all day, but it shows how strong the financial pull toward speed was."
)

# ---- Did the payout change work? ----
st.subheader("Did the Payout Change Affect Behavior?")
st.caption("Only technicians with approvals on both sides of the June 2020 payout change (\$50 to \$17) can be compared this way.")

for tech in selected_technicians:
    tech_rows = filtered[filtered["technician"] == tech]
    before = tech_rows.loc[tech_rows["pay_period"] == "Before", "duration_seconds_clean"].dropna()
    after = tech_rows.loc[tech_rows["pay_period"] == "After", "duration_seconds_clean"].dropna()

    if len(before) < 2 or len(after) < 2:
        st.write(f"**{tech}**: no data on both sides of the payout change in the current selection.")
        continue

    t_stat, p_val = stats.ttest_ind(before, after, equal_var=False)

    tech_daily = filtered_daily[filtered_daily["technician"] == tech]
    before_appr = tech_daily.loc[tech_daily["pay_period"] == "Before", "approvals"]
    after_appr = tech_daily.loc[tech_daily["pay_period"] == "After", "approvals"]
    before_rev = tech_daily.loc[tech_daily["pay_period"] == "Before", "revenue"]
    after_rev = tech_daily.loc[tech_daily["pay_period"] == "After", "revenue"]

    vol_t, vol_p = stats.ttest_ind(before_appr, after_appr, equal_var=False)

    st.markdown(f"**{tech}**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Median duration, Before -> After", f"{before.median():.0f}s -> {after.median():.0f}s")
    c2.metric("Avg approvals/day, Before -> After", f"{before_appr.mean():.0f} -> {after_appr.mean():.0f}")
    c3.metric("Avg revenue/day, Before -> After", f"\${before_rev.mean():,.0f} -> \${after_rev.mean():,.0f}")
    st.write(
        f"Duration t-test p-value: {p_val:.4f} "
        f"({'no significant change in per-case speed' if p_val >= 0.05 else 'significant change in per-case speed'}). "
        f"Daily volume t-test p-value: {vol_p:.4f} "
        f"({'no significant change in daily volume' if vol_p >= 0.05 else 'significant change in daily volume'})."
    )
