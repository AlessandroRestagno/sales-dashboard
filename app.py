import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Sales Dashboard", layout="wide")

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

creds = Credentials.from_service_account_info(
    st.secrets,
    scopes=SCOPE
)

client = gspread.authorize(creds)

# Open the spreadsheet by name
SPREADSHEET_ID = "1qoCyybRlqu_yTOniUkFR8WfA4J9vlhQmsihx5xJ-l1M"
WORKSHEET_NAME = "Sheet1"

sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
rows = sheet.get_all_records()

# --- DataFrame ---
df = pd.DataFrame(rows)

# Clean columns
df.columns = [c.strip().lower() for c in df.columns]

# Map Italian columns to canonical names
df = df.rename(columns={
    "data": "date",
    "cliente": "customer",
    "id": "id",
    "id animale": "product",
    "peso": "quantity",
    "prezzo al kg": "unit_price",
    "totale": "total",
    "agente": "agent",
    "percentuale": "commission_rate",
    "commissione": "commission",
})

# Convert types
df["date"] = pd.to_datetime(df.get("date"), errors="coerce", dayfirst=True)
df["quantity"] = pd.to_numeric(df.get("quantity"), errors="coerce")
df["unit_price"] = pd.to_numeric(clean_currency(df.get("unit_price")), errors="coerce")
df["total"] = pd.to_numeric(clean_currency(df.get("total")), errors="coerce")

if df["total"].isna().any():
    df["total"] = df["total"].fillna(df["quantity"] * df["unit_price"])

# Commission numeric: allow percentage in 0-100 or 0.XX
if "commission_rate" in df.columns:
    df["commission_rate"] = pd.to_numeric(df["commission_rate"], errors="coerce")
    df.loc[df["commission_rate"] > 1, "commission_rate"] = (
        df.loc[df["commission_rate"] > 1, "commission_rate"] / 100
    )

if "commission" in df.columns:
    df["commission"] = pd.to_numeric(df["commission"], errors="coerce")
    missing_commission = (
        df["commission"].isna()
        & df["commission_rate"].notna()
        & df["total"].notna()
    )
    df.loc[missing_commission, "commission"] = (
        df.loc[missing_commission, "total"]
        * df.loc[missing_commission, "commission_rate"]
    )

st.title("Sales Dashboard")

# --- Sidebar filters ---
st.sidebar.header("Filters")

min_date = df["date"].min()
max_date = df["date"].max()

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date.date(), max_date.date())
)

customers = sorted(df.get("customer", pd.Series(dtype="str")).dropna().unique())
selected_customers = st.sidebar.multiselect(
    "Cliente",
    customers,
    default=[]
)

agents = sorted(df.get("agent", pd.Series(dtype="str")).dropna().unique())
selected_agents = st.sidebar.multiselect(
    "Agente",
    agents,
    default=[]
)

filtered = df.copy()

if len(date_range) == 2:
    start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    filtered = filtered[
        (filtered["date"] >= start_date)
        & (filtered["date"] <= end_date)
    ]

if selected_customers:
    filtered = filtered[filtered["customer"].isin(selected_customers)]

if selected_agents:
    filtered = filtered[filtered["agent"].isin(selected_agents)]

# --- KPIs ---
col1, col2, col3, col4 = st.columns(4)

col1.metric("Ricavi", f"€ {filtered['total'].sum():,.2f}")
col2.metric("Peso totale", f"{filtered['quantity'].sum():,.0f} kg")
col3.metric("Clienti", f"{filtered['customer'].nunique():,}")
col4.metric("Animali", f"{filtered['product'].nunique():,}")

# --- Monthly Sales ---
st.subheader("Monthly Sales")

monthly = (
    filtered
    .dropna(subset=["date"])
    .assign(month=lambda x: x["date"].dt.to_period("M").astype(str))
    .groupby("month", as_index=False)["total"]
    .sum()
)

st.line_chart(monthly.set_index("month"))

# --- Top Customers ---
st.subheader("Top Customers")

top_customers = (
    filtered.groupby("customer", as_index=False)
    .agg(revenue=("total", "sum"), quantity=("quantity", "sum"))
    .sort_values("revenue", ascending=False)
)

st.dataframe(top_customers, use_container_width=True)

# --- Customers > 10 items ---
st.subheader("Customers with more than 10 items")

more_than_10 = (
    filtered.groupby("customer", as_index=False)["quantity"]
    .sum()
)

more_than_10 = more_than_10[more_than_10["quantity"] > 10]

st.dataframe(more_than_10, use_container_width=True)

# --- Raw Data ---
st.subheader("Raw Data")
st.dataframe(filtered, use_container_width=True)
