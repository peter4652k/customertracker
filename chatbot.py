import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import base64
from io import StringIO
import sys

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="Customer Balance Tracker",
    page_icon="💰",
    layout="centered"
)

# =============================================================================
# CONFIG
# =============================================================================
COLUMNS = [
    "DATE",
    "CUSTOMER NAME",
    "AMOUNT OWED",
    "BALANCE PAID",
    "BALANCE AS OF TODAY",
    "STATUS"
]

# =============================================================================
# GITHUB CONFIG
# =============================================================================
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_PATH = st.secrets["FILE_PATH"]

API_URL = (
    f"https://api.github.com/repos/"
    f"{REPO_NAME}/contents/{FILE_PATH}"
)

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# =============================================================================
# HELPERS
# =============================================================================
def compute_status(balance):

    if float(balance) <= 0:
        return "Cleared ✅"

    return "Pending ⏳"


# =============================================================================
# GITHUB LOAD
# =============================================================================
def github_load_csv():

    try:

        response = requests.get(
            API_URL,
            headers=HEADERS,
            timeout=15
        )

        # FILE EXISTS
        if response.status_code == 200:

            content = base64.b64decode(
                response.json()["content"]
            ).decode("utf-8")

            df = pd.read_csv(
                StringIO(content)
            )

            return df

        # FILE DOES NOT EXIST YET
        elif response.status_code == 404:

            return pd.DataFrame(
                columns=COLUMNS
            )

        else:

            st.error(
                f"""
GitHub Load Failed

Status Code:
{response.status_code}

Response:
{response.text}
"""
            )

            return pd.DataFrame(
                columns=COLUMNS
            )

    except Exception as e:

        st.error(
            f"GitHub Connection Error:\n{e}"
        )

        return pd.DataFrame(
            columns=COLUMNS
        )


# =============================================================================
# GITHUB SAVE
# =============================================================================
def github_save_csv(df):

    try:

        df = df.reindex(
            columns=COLUMNS
        )

        csv_content = df.to_csv(
            index=False
        )

        encoded_content = base64.b64encode(
            csv_content.encode("utf-8")
        ).decode("utf-8")

        # ---------------------------------------------------------
        # GET EXISTING FILE SHA
        # ---------------------------------------------------------
        sha = None

        get_response = requests.get(
            API_URL,
            headers=HEADERS,
            timeout=15
        )

        if get_response.status_code == 200:

            sha = get_response.json()["sha"]

        # ---------------------------------------------------------
        # CREATE PAYLOAD
        # ---------------------------------------------------------
        payload = {
            "message": "Update customer records",
            "content": encoded_content
        }

        if sha:
            payload["sha"] = sha

        # ---------------------------------------------------------
        # SAVE FILE
        # ---------------------------------------------------------
        put_response = requests.put(
            API_URL,
            headers=HEADERS,
            json=payload,
            timeout=15
        )

        if put_response.status_code in [200, 201]:

            st.success(
                "✅ Data saved successfully."
            )

            # CLEAR CACHE
            load_data.clear()

        else:

            st.error(
                f"""
GitHub Save Failed

Status Code:
{put_response.status_code}

Response:
{put_response.text}
"""
            )

    except Exception as e:

        st.error(
            f"Save Error:\n{e}"
        )


# =============================================================================
# LOAD DATA WITH CACHE
# =============================================================================
@st.cache_data(ttl=60)
def load_data():

    df = github_load_csv()

    # ENSURE COLUMNS EXIST
    for col in COLUMNS:

        if col not in df.columns:
            df[col] = ""

    # NUMERIC CLEANUP
    numeric_cols = [
        "AMOUNT OWED",
        "BALANCE PAID",
        "BALANCE AS OF TODAY"
    ]

    for col in numeric_cols:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0.0)

    # RECALCULATE BALANCES
    df["BALANCE AS OF TODAY"] = (
        df["AMOUNT OWED"] -
        df["BALANCE PAID"]
    ).clip(lower=0.0)

    # UPDATE STATUS
    df["STATUS"] = df[
        "BALANCE AS OF TODAY"
    ].apply(compute_status)

    return df


# =============================================================================
# ADD OR UPDATE CUSTOMER
# =============================================================================
def add_or_update_customer(
    name,
    amount_owed,
    payment_now
):

    df = load_data()

    customer_name = name.strip().title()

    if not customer_name:

        st.warning(
            "Please enter customer name."
        )

        return

    amount_owed = float(amount_owed)
    payment_now = float(payment_now)

    # ============================================================
    # EXISTING CUSTOMER
    # ============================================================
    if customer_name in df["CUSTOMER NAME"].values:

        idx = df.index[
            df["CUSTOMER NAME"] == customer_name
        ][0]

        previous_owed = float(
            df.at[idx, "AMOUNT OWED"]
        )

        previous_paid = float(
            df.at[idx, "BALANCE PAID"]
        )

        # UPDATE VALUES
        new_total_owed = (
            previous_owed + amount_owed
        )

        new_total_paid = (
            previous_paid + payment_now
        )

        new_balance = max(
            new_total_owed - new_total_paid,
            0.0
        )

        # SAVE CHANGES
        df.at[idx, "AMOUNT OWED"] = (
            new_total_owed
        )

        df.at[idx, "BALANCE PAID"] = (
            new_total_paid
        )

        df.at[idx, "BALANCE AS OF TODAY"] = (
            new_balance
        )

        df.at[idx, "STATUS"] = (
            compute_status(new_balance)
        )

        df.at[idx, "DATE"] = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        github_save_csv(df)

        st.success(
            f"""
✅ Existing customer updated

Customer:
{customer_name}

Total Owed:
UGX {new_total_owed:,.0f}

Balance:
UGX {new_balance:,.0f}
"""
        )

    # ============================================================
    # NEW CUSTOMER
    # ============================================================
    else:

        balance = max(
            amount_owed - payment_now,
            0.0
        )

        new_row = {
            "DATE": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "CUSTOMER NAME": customer_name,
            "AMOUNT OWED": amount_owed,
            "BALANCE PAID": payment_now,
            "BALANCE AS OF TODAY": balance,
            "STATUS": compute_status(balance)
        }

        df = pd.concat(
            [
                df,
                pd.DataFrame([new_row])
            ],
            ignore_index=True
        )

        github_save_csv(df)

        st.success(
            f"""
✅ New customer added

Customer:
{customer_name}

Balance:
UGX {balance:,.0f}
"""
        )


# =============================================================================
# UPDATE PAYMENT
# =============================================================================
def update_payment(
    customer_name,
    payment_now,
    manual_balance=None
):

    df = load_data()

    if customer_name not in df[
        "CUSTOMER NAME"
    ].values:

        st.error(
            "Customer not found."
        )

        return

    idx = df.index[
        df["CUSTOMER NAME"] == customer_name
    ][0]

    previous_paid = float(
        df.at[idx, "BALANCE PAID"]
    )

    new_paid = (
        previous_paid + float(payment_now)
    )

    df.at[idx, "BALANCE PAID"] = (
        new_paid
    )

    calculated_balance = max(
        float(df.at[idx, "AMOUNT OWED"]) -
        new_paid,
        0.0
    )

    # MANUAL OVERRIDE
    if manual_balance is not None:

        final_balance = max(
            float(manual_balance),
            0.0
        )

    else:

        final_balance = calculated_balance

    df.at[idx, "BALANCE AS OF TODAY"] = (
        final_balance
    )

    df.at[idx, "STATUS"] = (
        compute_status(final_balance)
    )

    df.at[idx, "DATE"] = (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    github_save_csv(df)

    st.success(
        f"""
✅ Payment updated

Customer:
{customer_name}

Current Balance:
UGX {final_balance:,.0f}
"""
    )


# =============================================================================
# UI
# =============================================================================
st.title(
    "💰 Customer Balance Tracker"
)

menu = st.sidebar.selectbox(
    "Menu",
    [
        "Add / Update Customer",
        "Update Payment",
        "View Records",
        "Debug Info"
    ]
)

# =============================================================================
# ADD / UPDATE CUSTOMER
# =============================================================================
if menu == "Add / Update Customer":

    st.header(
        "Add or Update Customer"
    )

    with st.form(
        "add_customer_form",
        clear_on_submit=True
    ):

        customer_name = st.text_input(
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
                customer_name,
                amount_owed,
                payment_now
            )

# =============================================================================
# UPDATE PAYMENT
# =============================================================================
elif menu == "Update Payment":

    st.header(
        "Update Customer Payment"
    )

    df = load_data()

    if df.empty:

        st.info(
            "No customer records found."
        )

    else:

        customers = df[
            "CUSTOMER NAME"
        ].tolist()

        selected_customer = st.selectbox(
            "Select Customer",
            [""] + customers
        )

        if selected_customer:

            idx = df.index[
                df["CUSTOMER NAME"] ==
                selected_customer
            ][0]

            st.markdown("---")

            st.write(
                f"""
Amount Owed:
UGX {df.at[idx,'AMOUNT OWED']:,.0f}
"""
            )

            st.write(
                f"""
Paid So Far:
UGX {df.at[idx,'BALANCE PAID']:,.0f}
"""
            )

            st.write(
                f"""
Current Balance:
UGX {df.at[idx,'BALANCE AS OF TODAY']:,.0f}
"""
            )

            st.write(
                f"""
Status:
{df.at[idx,'STATUS']}
"""
            )

            st.markdown("---")

            with st.form(
                "update_payment_form"
            ):

                payment_now = st.number_input(
                    "Payment Amount",
                    min_value=0.0,
                    step=100.0,
                    format="%.2f"
                )

                manual_balance = st.number_input(
                    "Manual Balance Override",
                    value=-1.0,
                    step=100.0,
                    format="%.2f"
                )

                update_btn = (
                    st.form_submit_button(
                        "Update Payment"
                    )
                )

                if update_btn:

                    override = (
                        manual_balance
                        if manual_balance >= 0
                        else None
                    )

                    update_payment(
                        selected_customer,
                        payment_now,
                        override
                    )

# =============================================================================
# VIEW RECORDS
# =============================================================================
elif menu == "View Records":

    st.header(
        "Customer Records"
    )

    df = load_data()

    if df.empty:

        st.info(
            "No records available."
        )

    else:

        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic"
        )

        if st.button(
            "Save Table Changes"
        ):

            edited_df[
                "BALANCE AS OF TODAY"
            ] = (
                edited_df["AMOUNT OWED"] -
                edited_df["BALANCE PAID"]
            ).clip(lower=0.0)

            edited_df["STATUS"] = (
                edited_df[
                    "BALANCE AS OF TODAY"
                ].apply(compute_status)
            )

            github_save_csv(
                edited_df
            )

# =============================================================================
# DEBUG
# =============================================================================
elif menu == "Debug Info":

    st.header("Debug Information")

    st.write(
        f"Python Version: {sys.version}"
    )

    st.write(
        f"Repository: {REPO_NAME}"
    )

    st.write(
        f"File Path: {FILE_PATH}"
    )

    st.write(
        f"API URL: {API_URL}"
    )

    st.markdown("---")

    st.subheader(
        "Preview Data"
    )

    preview_df = load_data()

    st.dataframe(preview_df)
