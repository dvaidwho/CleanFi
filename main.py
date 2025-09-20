import streamlit as st
import pandas as pd  # allows to easily load csv files 
import plotly.express as px  # allows to create interactive plots and graphs 
import numpy as np  # allows to do numerical operations on dataframes
import json  # save and load json files 
import os  # allows to access the file system
import io 
import re

from clean import build_clean_views, CATEGORY_RULES  # cleans the data and prepares it for display

st.set_page_config(page_title="CleanFi Finance App", page_icon="💰", layout="wide")

def main():
    st.title("CleanFi - Simplify Your Bank Statement 💰")

    upload_file = st.file_uploader("Upload your Bank Statement (CSV)", type=["csv"])

    if not upload_file: # if no file is uploaded, show a message and return
        return

    # Load CSV (UI stays here; no cleaning logic)
    try:
        df_raw = pd.read_csv(upload_file)
    except Exception as e:
        st.error(f"Error reading CSV: {str(e)}")
        return

    # Build clean views via helper module
    df_clean, df_clean_display, mapping, missing_required = build_clean_views(df_raw)

    # Tabs for Clean and Advanced views
    clean_tab, adv_tab = st.tabs(["💎 Clean View", "🔧 Advanced View"])

    if missing_required:
        st.error(
            "Couldn't auto-detect required column(s): " + ", ".join(missing_required) +
            ". Try renaming them in your CSV to common names like 'Date', 'Description', 'Amount'."
        )
        with adv_tab:
            st.dataframe(df_raw, use_container_width=True)
        return

    #add visual here


    
    # Clean view 
    with clean_tab:
        # Use st.data_editor instead of st.dataframe for editable categories
        column_config = {
            "Date": st.column_config.DateColumn("Date", disabled=True),
            "Description": st.column_config.TextColumn("Description", disabled=True),
            "Amount": st.column_config.NumberColumn("Amount", disabled=True, format="$%.2f"),
            "Balance": st.column_config.NumberColumn("Balance", disabled=True, format="$%.2f"),
            "Type": st.column_config.TextColumn("Type", disabled=True),
            "Category": st.column_config.SelectboxColumn(
                "Category",
                options=list(CATEGORY_RULES.keys()) + ["Uncategorized"],
                required=True
            )
        }
        
        edited_df = st.data_editor(
            df_clean_display,
            column_config=column_config,
            use_container_width=True,
            key="category_editor"
        )
        
        # Update the dataframe with edited categories
        if edited_df is not None:
            df_clean_display = edited_df
        
        # Count uncategorized transactions (after any edits)
        uncategorized_count = (df_clean_display['Category'] == 'Uncategorized').sum()
        total_count = len(df_clean_display)
        categorized_count = total_count - uncategorized_count
        
        # Display progress metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📊 Total Transactions", total_count)
        with col2:
            st.metric("✅ Categorized", categorized_count)
        with col3:
            st.metric("❓ Uncategorized", uncategorized_count, delta=None)
        
        # Progress bar
        if total_count > 0:
            progress = categorized_count / total_count
            st.progress(progress, text=f"Categorization Progress: {progress:.1%}")
        
        # Pie chart of expenses by category
        st.divider()
        st.subheader("Expenses by Category")
        exclude_cats = ["Transfer", "ATM & Cash", "Uncategorized"]
        expenses_df = df_clean_display[
            (df_clean_display["Amount"] < 0) & (~df_clean_display["Category"].isin(exclude_cats))
        ]
        if not expenses_df.empty:
            pie_data = expenses_df.groupby("Category")["Amount"].sum().abs().reset_index()
            fig = px.pie(pie_data, names="Category", values="Amount", title="Expense Distribution")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No expenses to display.")

        # Metrics after pie chart
        st.subheader("Key Metrics")
        # Total income (positive amounts)
        total_income = df_clean_display[df_clean_display["Amount"] > 0]["Amount"].sum()
        # Total spent (negative amounts, absolute value)
        total_spent = abs(df_clean_display[df_clean_display["Amount"] < 0]["Amount"].sum())
        # Highest spending category
        if not expenses_df.empty:
            highest_cat_row = pie_data.loc[pie_data["Amount"].idxmax()]
            highest_cat = highest_cat_row["Category"]
            highest_cat_amt = highest_cat_row["Amount"]
        else:
            highest_cat = "-"
            highest_cat_amt = 0

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Income", f"${total_income:,.2f}")
        col2.metric("Total Spent", f"${total_spent:,.2f}")
        col3.metric("Highest Spending Category", highest_cat, f"${highest_cat_amt:,.2f}")

    # (downloadable button)
        csv_bytes = df_clean_display.to_csv(index=False).encode("utf-8")
        st.download_button("Download Clean CSV", data=csv_bytes,
                           file_name="clean_transactions.csv", mime="text/csv")
    # Advanced view always shows raw for inspection
    with adv_tab:
        st.dataframe(df_raw, use_container_width=True)

if __name__ == "__main__":
    main()
