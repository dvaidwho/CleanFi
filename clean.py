import pandas as pd
import re

# Canonical fields you want
REQUIRED = ["Date", "Description", "Amount"]
OPTIONAL = ["Balance", "Type", "Category"]

# Common header aliases (lowercased, stripped)
ALIASES = {
    "Date": ["date", "posting date", "post date", "transaction date", "posted date"],
    "Description": ["description", "details", "memo", "payee", "narration", "transaction", "name"],
    "Amount": ["amount", "transaction amount", "amt", "debit/credit", "value"],
    "Balance": ["balance", "running balance", "available balance", "running bal", "Running Bal."],
    "Type": ["type", "transaction type", "credit/debit", "dr/cr", "category", "method"]
}

# Clean headers: strip whitespace, collapse internal spaces
def clean_headers(cols):
    return [re.sub(r"\s+", " ", str(c)).strip() for c in cols]

# Auto-map canonical -> raw column names
def auto_map(df):
    """Return a dict mapping canonical -> raw column name (or None)."""
    mapping = {k: None for k in REQUIRED + OPTIONAL}
    raw_lookup = {c.lower().strip(): c for c in df.columns}
    for canon, candidates in ALIASES.items():
        for cand in candidates:
            if cand.lower().strip() in raw_lookup and mapping[canon] is None:
                mapping[canon] = raw_lookup[cand.lower().strip()]
                break
    return mapping

# Normalization helpers
def _normalize_amount(series):
    """Handle $, commas, quotes, parentheses negatives, trailing CR/DR."""
    s = series.astype(str).str.replace(r"[\$,\"]", "", regex=True).str.strip()
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)   # (123.45) -> -123.45
    s = s.str.replace(r"[A-Za-z]+$", "", regex=True).str.strip()  # strip trailing CR/DR
    return pd.to_numeric(s, errors="coerce")

# Normalize Type values
def _normalize_type(series):
    """
    Normalize to one of: 'Debit', 'Credit', 'Deposit', 'Withdrawal'.
    Keeps Deposit/Withdrawal distinct (no collapsing into Credit/Debit).
    """
    mapping = {
        # debit family
        "debit": "Debit",
        "debit card": "Debit",
        "purchase": "Debit",
        "dr": "Debit",

        # credit family
        "credit": "Credit",
        "cr": "Credit",
        "refund": "Credit",

        # deposit / withdrawal
        "deposit": "Deposit",
        "dep": "Deposit",
        "atm deposit": "Deposit",

        "withdrawal": "Withdrawal",
        "withd": "Withdrawal",
        "atm withdrawal": "Withdrawal",
        "cash withdrawal": "Withdrawal",
        "atm": "Withdrawal",
    }

    s = series.astype(str).str.strip().str.lower()
    s = s.replace(mapping)
    # Fallback regex sweep for phrases
    s = s.replace({
        r".*\bdebit\b.*": "Debit",
        r".*\bcredit\b.*": "Credit",
        r".*\bdeposit\b.*": "Deposit",
        r".*\bwithdraw(al)?\b.*": "Withdrawal"
    }, regex=True)
    return s.str.title()

# Infer Type from Amount if missing
def _infer_type(amount_series):
    """If Type missing: positive -> Deposit, negative -> Debit."""
    return amount_series.apply(
        lambda x: "Deposit" if pd.notna(x) and x > 0
        else ("Debit" if pd.notna(x) and x < 0 else None)
    )

# Auto-categorization system
CATEGORY_RULES = {
    "Food & Dining": [
        "restaurant", "cafe", "coffee", "starbucks", "mcdonald", "burger", "pizza", "subway",
        "dining", "food", "grocery", "supermarket", "walmart", "target", "costco", "safeway",
        "kroger", "whole foods", "trader joe", "albertsons", "food lion", "publix", "chicken",
        "tea", "boba", "tst", "cava", "chili's", "kfc", "snowdaes", "dunkin", "domino's"
    ],
    "Transportation": [
        "gas", "gasoline", "fuel", "shell", "exxon", "mobil", "bp", "chevron", "speedway",
        "uber", "lyft", "taxi", "parking", "toll", "metro", "bus", "train", "airline",
        "delta", "united", "american", "southwest", "jetblue", "car rental", "hertz", "avis"
    ],
    "Shopping": [
        "amazon", "ebay", "walmart", "target", "best buy", "home depot", "lowes", "macy",
        "nordstrom", "gap", "old navy", "h&m", "zara", "online", "purchase", "order", "uniqlo",
        "7-eleven", "family dollar", "lowe's", "staples"
    ],
    "Entertainment": [
        "netflix", "spotify", "hulu", "disney", "youtube", "movie", "cinema", "theater",
        "concert", "ticket", "entertainment", "game", "steam", "playstation", "xbox", "steam"
    ],
    "Healthcare": [
        "hospital", "doctor", "medical", "pharmacy", "cvs", "walgreens", "health", "dental",
        "vision", "insurance", "clinic", "urgent care", "prescription", "medication"
    ],
    "Utilities/Bills": [
        "bill", "electric", "gas", "water", "internet", "phone", "cable", "utility", "at&t", "verizon",
        "tmobile", "sprint", "comcast", "spectrum", "cox", "directv", "dish", "openai"
    ],
    "Income": [
        "payroll", "salary", "wage", "bonus", "commission", "income", "deposit", "refund",
        "interest", "dividend", "investment", "return", "direct dep", "dep"
    ],
    "ATM & Cash": [
        "atm", "cash", "withdrawal", "deposit", "bank", "branch"
    ],
    "Insurance": [
        "insurance", "premium", "coverage", "policy", "auto insurance", "home insurance",
        "life insurance", "health insurance"
    ],
    "Education": [
        "school", "university", "college", "tuition", "education", "student", "book",
        "textbook", "course", "class"
    ],
    "Travel": [
        "hotel", "airbnb", "booking", "expedia", "priceline", "travel", "vacation",
        "flight", "cruise", "resort"
    ],
    "Subscriptions": [
        "subscription", "monthly", "annual", "recurring", "membership", "premium"
    ],
    "Transfer": [
        "transfer", "xfer from", "xfer to" 
    ]
}

def _auto_categorize(description_series):
    """Auto-categorize transactions based on description keywords."""
    def categorize_single(desc):
        if pd.isna(desc) or desc == "":
            return "Uncategorized"
        
        desc_lower = str(desc).lower()
        
        # Check each category's keywords
        for category, keywords in CATEGORY_RULES.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    return category
        
        return "Uncategorized"
    
    return description_series.apply(categorize_single)

# Format date as M/D/Y (no time), cross-platform
def _format_mdy(date_series):
    """Display dates as M/D/Y (no time) cross-platform."""
    try:
        return date_series.dt.strftime("%-m/%-d/%Y")  # POSIX
    except Exception:
        return date_series.dt.strftime("%#m/%#d/%Y")  # Windows

# Main normalization function
def normalize_df(df, mapping):
    out = pd.DataFrame()

    # Date
    if mapping["Date"]:
        out["Date"] = pd.to_datetime(df[mapping["Date"]], errors="coerce")
    else:
        out["Date"] = pd.NaT

    # Description
    if mapping["Description"]:
        out["Description"] = df[mapping["Description"]].astype(str).str.strip()
    else:
        out["Description"] = pd.NA

    # Amount
    if mapping["Amount"]:
        out["Amount"] = _normalize_amount(df[mapping["Amount"]])
    else:
        out["Amount"] = pd.NA

    # Balance (optional)
    if mapping["Balance"]:
        out["Balance"] = _normalize_amount(df[mapping["Balance"]])
    else:
        out["Balance"] = pd.NA

    # Type (optional -> normalize; else infer)
    if mapping["Type"]:
        out["Type"] = _normalize_type(df[mapping["Type"]])
    else:
        out["Type"] = _infer_type(out["Amount"])

    # Category (optional -> use existing; else auto-categorize)
    if mapping["Category"]:
        out["Category"] = df[mapping["Category"]].astype(str).str.strip()
    else:
        out["Category"] = _auto_categorize(out["Description"])

    # Final column order
    out = out[["Date", "Description", "Amount", "Balance", "Type", "Category"]]
    return out

# Public helper to build clean views
def build_clean_views(df_raw):
    """
    Public helper for the app:
    - cleans headers
    - auto-maps columns
    - validates required
    - returns (df_clean, df_clean_display, mapping, missing_required)
    """
    df = df_raw.copy()
    df.columns = clean_headers(df.columns)

    mapping = auto_map(df)
    missing_required = [c for c in REQUIRED if not mapping[c]]
    if missing_required:
        # Return early so UI can display advanced/raw view + error
        return None, None, mapping, missing_required

    df_clean = normalize_df(df, mapping)

    # Display-friendly copy with formatted date
    df_clean_display = df_clean.copy()
    if df_clean_display["Date"].notna().any():
        df_clean_display["Date"] = _format_mdy(df_clean_display["Date"])

    return df_clean, df_clean_display, mapping, []
