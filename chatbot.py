import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import base64
import requests
from io import StringIO


# ============================================================
# CONFIGURATION
# ============================================================

COLUMNS = [
    "DATE",
    "CUSTOMER NAME",
    "AMOUNT OWED",
    "BALANCE PAID",
    "BALANCE AS OF TODAY",
    "STATUS"
]


# ============================================================
# GITHUB CONFIGURATION
# ============================================================

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


# ============================================================
# GITHUB FUNCTIONS
# ============================================================

def github_load_csv():

    """
    Load customers.csv from GitHub.
    """

    response = requests.get(
        API_URL,
        headers=HEADERS
    )

    if response.status_code == 200:

        content = base64.b64decode(
            response.json()["content"]
        ).decode("utf-8")

        df = pd.read_csv(
            StringIO(content)
        )

        return df

    else:

        return pd.DataFrame(
            columns=COLUMNS
        )



def github_save_csv(df):

    """
    Save updated CSV back to GitHub.
    """

    df = df.reindex(
        columns=COLUMNS
    )

    csv_content = df.to_csv(
        index=False
    )

    encoded = base64.b64encode(
        csv_content.encode()
    ).decode()


    # Get existing file SHA

    check = requests.get(
        API_URL,
        headers=HEADERS
    )


    sha = None

    if check.status_code == 200:
        sha = check.json()["sha"]


    payload = {
        "message":
        "Updated customer database",
        "content":
        encoded
    }


    if sha:
        payload["sha"] = sha



    response = requests.put(
        API_URL,
        headers=HEADERS,
        json=payload
    )


    if response.status_code not in [
        200,
        201
    ]:

        st.error(
            f"GitHub Error: {response.text}"
        )

    else:

        st.success(
            "Data saved successfully ✅"
        )



# ============================================================
# DATA PROCESSING
# ============================================================


def compute_status(balance):

    if float(balance) <= 0:
        return "Cleared ✅"

    return "Pending ⏳"



def load_data():

    df = github_load_csv()


    if df.empty:

        return pd.DataFrame(
            columns=COLUMNS
        )


    for col in [
        "AMOUNT OWED",
        "BALANCE PAID",
        "BALANCE AS OF TODAY"
    ]:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0)


    # Always calculate balance automatically

    df["BALANCE AS OF TODAY"] = (
        df["AMOUNT OWED"]
        -
        df["BALANCE PAID"]
    ).clip(lower=0)


    df["STATUS"] = (
        df["BALANCE AS OF TODAY"]
        .apply(compute_status)
    )


    return df



# ============================================================
# CUSTOMER FUNCTIONS
# ============================================================


def add_customer(
        name,
        debt,
        payment
):

    df = load_data()


    customer = (
        name
        .strip()
        .title()
    )


    if not customer:

        st.warning(
            "Enter customer name"
        )

        return



    if customer in df["CUSTOMER NAME"].values:

        st.warning(
            "Customer already exists. Use Update Customer."
        )

        return



    balance = max(
        float(debt)
        -
        float(payment),
        0
    )


    new_customer = {

        "DATE":
        datetime.now()
        .strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "CUSTOMER NAME":
        customer,

        "AMOUNT OWED":
        float(debt),

        "BALANCE PAID":
        float(payment),

        "BALANCE AS OF TODAY":
        balance,

        "STATUS":
        compute_status(balance)
    }



    df = pd.concat(
        [
            df,
            pd.DataFrame(
                [new_customer]
            )
        ],
        ignore_index=True
    )


    github_save_csv(df)


    st.success(
        f"{customer} added successfully"
    )



def update_customer(
        name,
        payment,
        additional_debt
):

    df = load_data()


    customer = (
        name
        .strip()
        .title()
    )


    if customer not in df["CUSTOMER NAME"].values:

        st.error(
            "Customer not found"
        )

        return


    index = df.index[
        df["CUSTOMER NAME"]
        ==
        customer
    ][0]


    # Add new borrowing

    df.at[index,"AMOUNT OWED"] += float(
        additional_debt
    )


    # Add payment

    df.at[index,"BALANCE PAID"] += float(
        payment
    )


    # Recalculate balance

    df.at[index,"BALANCE AS OF TODAY"] = max(
        df.at[index,"AMOUNT OWED"]
        -
        df.at[index,"BALANCE PAID"],
        0
    )


    df.at[index,"DATE"] = (
        datetime.now()
        .strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )


    df.at[index,"STATUS"] = compute_status(
        df.at[index,"BALANCE AS OF TODAY"]
    )


    github_save_csv(df)


    st.success(
        "Customer updated successfully"
    )

# ============================================================
# STREAMLIT APPLICATION UI
# ============================================================

st.set_page_config(
    page_title="Customer Balance Tracker",
    page_icon="💰",
    layout="wide"
)


st.title(
    "💰 Customer Debt & Payment Tracker"
)

st.caption(
    "GitHub Synced Database - Data remains after restart"
)


# ============================================================
# SIDEBAR MENU
# ============================================================

menu = st.sidebar.selectbox(
    "Menu",
    [
        "Add New Customer",
        "Update Customer",
        "Customer Report",
        "View / Edit Table",
        "Debug Info"
    ]
)



# ============================================================
# PAGE 1 - ADD CUSTOMER
# ============================================================

if menu == "Add New Customer":

    st.header(
        "➕ Add New Customer"
    )


    with st.form(
        "add_customer"
    ):

        name = st.text_input(
            "Customer Name"
        )


        debt = st.number_input(
            "Amount Owed (UGX)",
            min_value=0.0,
            step=1000.0
        )


        payment = st.number_input(
            "Payment Made Today (UGX)",
            min_value=0.0,
            step=1000.0
        )


        submit = st.form_submit_button(
            "Save Customer"
        )


        if submit:

            add_customer(
                name,
                debt,
                payment
            )




# ============================================================
# PAGE 2 - UPDATE CUSTOMER
# ============================================================

elif menu == "Update Customer":

    st.header(
        "💳 Update Customer Payment / Debt"
    )


    df = load_data()


    if df.empty:

        st.info(
            "No customers available"
        )


    else:


        customer = st.selectbox(
            "Select Customer",
            df["CUSTOMER NAME"]
        )


        index = df.index[
            df["CUSTOMER NAME"]
            ==
            customer
        ][0]


        st.write(
            f"Current Debt: UGX {df.at[index,'AMOUNT OWED']:,.2f}"
        )


        st.write(
            f"Paid So Far: UGX {df.at[index,'BALANCE PAID']:,.2f}"
        )


        st.write(
            f"Balance Remaining: UGX {df.at[index,'BALANCE AS OF TODAY']:,.2f}"
        )


        st.divider()


        with st.form(
            "update_customer"
        ):


            payment = st.number_input(
                "Payment Today (UGX)",
                min_value=0.0,
                step=1000.0
            )


            additional_debt = st.number_input(
                "Additional Debt / New Loan (UGX)",
                min_value=0.0,
                step=1000.0
            )


            submit = st.form_submit_button(
                "Update Customer"
            )


            if submit:

                update_customer(
                    customer,
                    payment,
                    additional_debt
                )





# ============================================================
# PAGE 3 - CUSTOMER REPORT
# ============================================================

elif menu == "Customer Report":


    st.header(
        "📊 Customer Balance Report"
    )


    df = load_data()


    if df.empty:

        st.info(
            "No records available"
        )


    else:


        search = st.text_input(
            "Search Customer"
        )


        report = df.copy()


        if search:

            report = report[
                report["CUSTOMER NAME"]
                .str.contains(
                    search,
                    case=False
                )
            ]


        col1,col2,col3 = st.columns(3)


        col1.metric(
            "Total Customers",
            len(report)
        )


        col2.metric(
            "Total Debt",
            f"UGX {report['AMOUNT OWED'].sum():,.2f}"
        )


        col3.metric(
            "Outstanding",
            f"UGX {report['BALANCE AS OF TODAY'].sum():,.2f}"
        )


        st.dataframe(
            report,
            use_container_width=True
        )


        csv = report.to_csv(
            index=False
        ).encode()


        st.download_button(
            "Download Report CSV",
            csv,
            "customer_report.csv",
            "text/csv"
        )





# ============================================================
# PAGE 4 - EDIT TABLE
# ============================================================

elif menu == "View / Edit Table":


    st.header(
        "✏️ Edit Customer Records"
    )


    df = load_data()


    if df.empty:

        st.info(
            "No data"
        )


    else:


        edited = st.data_editor(
            df,
            use_container_width=True,
            disabled=[
                "DATE",
                "CUSTOMER NAME",
                "AMOUNT OWED",
                "BALANCE PAID",
                "STATUS"
            ]
        )


        if st.button(
            "Save Table Changes"
        ):

            edited["BALANCE AS OF TODAY"] = (
                edited["BALANCE AS OF TODAY"]
                .clip(lower=0)
            )


            edited["STATUS"] = (
                edited["BALANCE AS OF TODAY"]
                .apply(compute_status)
            )


            github_save_csv(
                edited
            )





# ============================================================
# PAGE 5 - DEBUG
# ============================================================

elif menu == "Debug Info":


    st.header(
        "System Information"
    )


    st.write(
        "Python Version:"
    )

    st.code(
        sys.version
    )


    st.write(
        "Repository:"
    )

    st.write(
        REPO_NAME
    )


    st.write(
        "CSV Location:"
    )

    st.write(
        FILE_PATH
    )


    df = load_data()


    st.dataframe(
        df.head(20)
    )
