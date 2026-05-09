import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import base64
import requests
from io import StringIO

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
COLUMNS = [
    "DATE",
    "CUSTOMER NAME",
    "AMOUNT OWED",
    "BALANCE PAID",
    "BALANCE AS OF TODAY",
    "STATUS"
]

# -----------------------------------------------------------------------------
# GITHUB CONFIG
# -----------------------------------------------------------------------------
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_PATH = st.secrets["FILE_PATH"]

API_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}"
}

# -----------------------------------------------------------------------------
# PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Customer Balance Tracker",
    page_icon="💰",
    layout="centered"
)

# -----------------------------------------------------------------------------
# GITHUB FUNCTIONS
# -----------------------------------------------------------------------------
def github_load_csv():
    """
    Load CSV from GitHub repository.
    """

    res = requests.get(API_URL, headers=HEADERS)

    if res.status_code == 200:
        content = base64.b64decode(
            res.json()["content"]
        ).decode()

        df = pd.read_csv(StringIO(content))

        return df

    return pd.DataFrame(columns=COLUMNS)


def github_save_csv(df):
    """
    Save CSV to GitHub repository.
    """

    df = df.reindex(columns=COLUMNS)

    csv_content = df.to_csv(index=False)

    encoded = base64.b64encode(
        csv_content.encode()
    ).decode()

    # Check existing SHA
    get_res = requests.get(API_URL, headers=HEADERS)

    sha = None

    if get_res.status_code == 200:
        sha = get_res.json()["sha"]

    payload = {
        "message": "Update customers.csv from Streamlit app",
        "content": encoded,
        "sha": sha
    }

    put_res = requests.put(
        API_URL,
        headers=HEADERS,
        json=payload
    )

    if put_res.status_code not in [200, 201]:
        st.error(
            f"❌ GitHub save failed: "
            f"{put_res.status_code}"
        )

    else:
        st.success("✅ Data saved successfully.")


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def compute_status(balance):
    """
    Determine payment status.
    """

    if float(balance) <= 0:
        return "Cleared ✅"

    return "Pending ⏳"


def load_data():
    """
    Load and clean data.
    """

    df = github_load_csv()

    # Ensure numeric columns
    for col in [
        "AMOUNT OWED",
        "BALANCE PAID",
        "BALANCE AS OF TODAY"
    ]:
        df[col] = pd.to_numeric(
            df.get(col, 0.0),
            errors="coerce"
        ).fillna(0.0)

    # Recalculate balances
    df["BALANCE AS OF TODAY"] = (
        df["AMOUNT OWED"] -
        df["BALANCE PAID"]
    ).clip(lower=0.0)

    # Update statuses
    df["STATUS"] = df[
        "BALANCE AS OF TODAY"
    ].apply(compute_status)

    return df


# -----------------------------------------------------------------------------
# ADD / UPDATE CUSTOMER
# -----------------------------------------------------------------------------
def add_or_update_customer(
    name,
    amount_owed,
    payment_now
):
    """
    Add new customer or update existing one.
    """

    df = load_data()

    key = name.strip().title()

    if not key:
        st.warning("Please enter customer name.")
        return

    amount_owed = float(amount_owed)
    payment_now = float(payment_now)

    # -------------------------------------------------------------------------
    # EXISTING CUSTOMER
    # -------------------------------------------------------------------------
    if key in df["CUSTOMER NAME"].values:

        idx = df.index[
            df["CUSTOMER NAME"] == key
        ][0]

        previous_owed = float(
            df.at[idx, "AMOUNT OWED"]
        )

        previous_paid = float(
            df.at[idx, "BALANCE PAID"]
        )

        # Update values
        new_total_owed = previous_owed + amount_owed

        new_total_paid = previous_paid + payment_now

        new_balance = max(
            new_total_owed - new_total_paid,
            0.0
        )

        # Save updates
        df.at[idx, "AMOUNT OWED"] = new_total_owed

        df.at[idx, "BALANCE PAID"] = new_total_paid

        df.at[idx, "BALANCE AS OF TODAY"] = new_balance

        df.at[idx, "STATUS"] = compute_status(
            new_balance
        )

        df.at[idx, "DATE"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        github_save_csv(df)

        st.success(
            f"✅ Existing customer updated.\n\n"
            f"Customer: {key}\n"
            f"Total Owed: {new_total_owed:,.0f} UGX\n"
            f"Balance: {new_balance:,.0f} UGX"
        )

    # -------------------------------------------------------------------------
    # NEW CUSTOMER
    # -------------------------------------------------------------------------
    else:

        balance_paid = payment_now

        balance_as_of_today = max(
            amount_owed - balance_paid,
            0.0
        )

        new_row = {
            "DATE": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "CUSTOMER NAME": key,
            "AMOUNT OWED": amount_owed,
            "BALANCE PAID": balance_paid,
            "BALANCE AS OF TODAY": balance_as_of_today,
            "STATUS": compute_status(
                balance_as_of_today
            )
        }

        df = pd.concat(
            [df, pd.DataFrame([new_row])],
            ignore_index=True
        )

        github_save_csv(df)

        st.success(
            f"✅ New customer added.\n\n"
            f"Customer: {key}\n"
            f"Balance: {balance_as_of_today:,.0f} UGX"
        )


# -----------------------------------------------------------------------------
# UPDATE PAYMENT ONLY
# -----------------------------------------------------------------------------
def update_customer_payment(
    name,
    payment_now,
    manual_balance=None
):
    """
    Record customer payment.
    """

    df = load_data()

    key = name.strip().title()

    if key not in df["CUSTOMER NAME"].values:
        st.error("Customer not found.")
        return

    idx = df.index[
        df["CUSTOMER NAME"] == key
    ][0]

    previous_paid = float(
        df.at[idx, "BALANCE PAID"]
    )

    new_paid = previous_paid + float(payment_now)

    df.at[idx, "BALANCE PAID"] = new_paid

    computed_balance = max(
        float(df.at[idx, "AMOUNT OWED"]) -
        new_paid,
        0.0
    )

    if manual_balance is None:
        df.at[idx, "BALANCE AS OF TODAY"] = computed_balance

    else:
        df.at[idx, "BALANCE AS OF TODAY"] = max(
            float(manual_balance),
            0.0
        )

    df.at[idx, "STATUS"] = compute_status(
        df.at[idx, "BALANCE AS OF TODAY"]
    )

    df.at[idx, "DATE"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    github_save_csv(df)

    st.success(
        f"✅ Payment updated for {key}"
    )


# -----------------------------------------------------------------------------
# APP UI
# -----------------------------------------------------------------------------
st.title("💰 Customer Balance Tracker")

menu = st.sidebar.selectbox(
    "Menu",
    [
        "Add / Update Customer",
        "Update Payment",
        "View / Edit Table",
        "Debug Info"
    ]
)

# -----------------------------------------------------------------------------
# ADD / UPDATE CUSTOMER
# -----------------------------------------------------------------------------
if menu == "Add / Update Customer":

    st.header("Add or Update Customer")

    with st.form("add_customer_form"):

        name = st.text_input(
            "Customer Name"
        )

        amount_owed = st.number_input(
            "Amount Owed (UGX)",
            min_value=0.0,
            step=100.0,
            format="%.2f"
        )

        payment_now = st.number_input(
            "Payment Now (UGX)",
            min_value=0.0,
            step=100.0,
            format="%.2f"
        )

        submit = st.form_submit_button(
            "Save Customer"
        )

        if submit:

            add_or_update_customer(
                name,
                amount_owed,
                payment_now
            )

# -----------------------------------------------------------------------------
# UPDATE PAYMENT
# -----------------------------------------------------------------------------
elif menu == "Update Payment":

    st.header("Update Payment")

    df = load_data()

    if df.empty:
        st.info("No customers found.")

    else:

        names = df["CUSTOMER NAME"].tolist()

        selected = st.selectbox(
            "Select Customer",
            [""] + names
        )

        if selected:

            idx = df.index[
                df["CUSTOMER NAME"] == selected
            ][0]

            st.write(
                f"### Customer Summary"
            )

            st.write(
                f"**Amount Owed:** "
                f"{df.at[idx,'AMOUNT OWED']:,.0f} UGX"
            )

            st.write(
                f"**Paid So Far:** "
                f"{df.at[idx,'BALANCE PAID']:,.0f} UGX"
            )

            st.write(
                f"**Current Balance:** "
                f"{df.at[idx,'BALANCE AS OF TODAY']:,.0f} UGX"
            )

            st.write(
                f"**Status:** "
                f"{df.at[idx,'STATUS']}"
            )

            st.markdown("---")

            with st.form("update_payment_form"):

                payment_now = st.number_input(
                    "Payment Now (UGX)",
                    min_value=0.0,
                    step=100.0,
                    format="%.2f"
                )

                manual_balance = st.number_input(
                    "Manual Balance Override (Optional)",
                    min_value=-1.0,
                    step=100.0,
                    format="%.2f",
                    value=-1.0
                )

                submit_update = st.form_submit_button(
                    "Apply Payment"
                )

                if submit_update:

                    override = (
                        manual_balance
                        if manual_balance >= 0
                        else None
                    )

                    update_customer_payment(
                        selected,
                        payment_now,
                        override
                    )

# -----------------------------------------------------------------------------
# VIEW / EDIT TABLE
# -----------------------------------------------------------------------------
elif menu == "View / Edit Table":

    st.header("Customer Records")

    df = load_data()

    if df.empty:

        st.info("No records found.")

    else:

        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            disabled=[
                "DATE",
                "CUSTOMER NAME",
                "STATUS"
            ]
        )

        if st.button("Save Table Changes"):

            edited["BALANCE AS OF TODAY"] = (
                edited["AMOUNT OWED"] -
                edited["BALANCE PAID"]
            ).clip(lower=0.0)

            edited["STATUS"] = edited[
                "BALANCE AS OF TODAY"
            ].apply(compute_status)

            github_save_csv(edited)

# -----------------------------------------------------------------------------
# DEBUG
# -----------------------------------------------------------------------------
elif menu == "Debug Info":

    st.header("Debug Information")

    st.write(f"Python Version: {sys.version}")

    st.write(f"Repository: {REPO_NAME}")

    st.write(f"CSV File: {FILE_PATH}")

    df = load_data()

    st.dataframe(df)
