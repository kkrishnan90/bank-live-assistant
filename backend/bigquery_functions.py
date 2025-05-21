import os
from google.cloud import bigquery
import datetime
import uuid
import logging
import sys # Added to redirect logger to stdout
import json # For structured logging of parameters and results
from dotenv import load_dotenv
from google.oauth2 import service_account




# Load environment variables from .env file
load_dotenv()

# Configure logging
# Ensure a logger instance is used for more control if needed, but basicConfig is fine for now.
# For file-based logging, a FileHandler could be added here.
# For now, stdout logging as configured is acceptable per instructions.
logging.basicConfig(
    stream=sys.stdout, # Direct logs to stdout
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__) # Use a specific logger for this module

# Global store for logs
GLOBAL_LOG_STORE = []
 
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

# Initialize BigQuery Client
# Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set.
# For local development, you might set it like this:
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "path/to/your/service-account-file.json"
# In a deployed environment (e.g., Google Cloud Run/Functions), this is often handled automatically.
try:
    # client = bigquery.Client(project=GOOGLE_CLOUD_PROJECT, credentials=service_account.Credentials.from_service_account_file(CREDENTIALS_PATH))
    client = bigquery.Client(project="account-pocs")
    # Attempt a simple query to verify connection and credentials
    # This also helps in resolving the project ID if not explicitly set
    if client.project:
         logger.info(f"\033[92mBigQuery client initialized successfully for project: {client.project}.\033[0m")
    else: # Should not happen if client init is successful without error
         logger.warning("BigQuery client initialized, but project ID could not be determined automatically.")
    # client.query("SELECT 1").result() # Optional: verify with a query
except Exception as e:
    logger.error(f"Failed to initialize BigQuery client: {e}", exc_info=True) # Added exc_info=True
    # Fallback or raise an error if the client is essential for the module to load
    client = None

# Placeholder for User ID - replace with actual authentication mechanism later
USER_ID = "user_krishnan_001"

# Determine Project ID and Dataset ID
# Use GOOGLE_CLOUD_PROJECT env var if set, otherwise try to get from initialized client
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
if not PROJECT_ID and client:
    PROJECT_ID = client.project
if not PROJECT_ID:
    logger.warning("GOOGLE_CLOUD_PROJECT environment variable not set and client.project is unavailable. Using placeholder 'your-gcp-project-id'. Table references might be incorrect.")
    PROJECT_ID = "your-gcp-project-id" # Fallback placeholder

DATASET_ID = "bank_voice_assistant_dataset" # Assuming the dataset name from bigquery_setup.sql

# --- Structured Logging Helper ---
def log_bq_interaction(func_name: str, params: dict, query: str = None, status: str = "N/A", result_summary: str = None, error_message: str = None):
    """Helper function for structured logging of BigQuery interactions."""
    log_entry = {
        "operation": func_name,
        "parameters": params,
        "query": query if query else "N/A",
        "status": status,
    }
    if result_summary is not None: # Could be a success message or data summary
        log_entry["result_summary"] = result_summary
    if error_message:
        log_entry["error_message"] = error_message
    
    # Using logger.info for all structured logs for simplicity,
    # the 'status' field within the JSON will indicate success/failure.
    # Alternatively, use logger.error for failed statuses.
    
    # Store the log entry in the global list
    GLOBAL_LOG_STORE.append(log_entry)

    if "ERROR" in status.upper() or "FAIL" in status.upper():
        logger.error(json.dumps(log_entry)) # Error logs remain default color
    else:
        logger.info(f"\033[92m{json.dumps(log_entry)}\033[0m") # Successful BQ interactions in green

# Helper to construct full table IDs
def _table_ref(table_name: str) -> str:
    if PROJECT_ID == "your-gcp-project-id": # Check if using placeholder
        # This is a less safe fallback if project ID couldn't be determined
        logger.warning(f"Using fallback table reference for {table_name} as PROJECT_ID is a placeholder.")
        return f"`{DATASET_ID}.{table_name}`"
    return f"`{PROJECT_ID}.{DATASET_ID}.{table_name}`"

def test_bigquery_connection():
    """
    Tests the BigQuery connection by executing a simple query.
    Logs success or failure.
    """
    func_name = "test_bigquery_connection"
    params = {}
    # Using a very simple query that doesn't rely on specific tables initially
    query_str = "SELECT 1 AS test_column"
    logger.info(f"[{func_name}] Attempting to test BigQuery connection.")

    if not client:
        log_message = "BigQuery client is not initialized. Cannot perform connection test."
        logger.error(f"[{func_name}] {log_message}")
        # Manual log for consistency if needed
        GLOBAL_LOG_STORE.append({
            "operation": func_name, "parameters": params, "query": query_str,
            "status": "ERROR_CLIENT_NOT_INITIALIZED", "error_message": log_message
        })
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": log_message}

    try:
        logger.info(f"\033[92m[{func_name}] Executing test query: {query_str}\033[0m")
        query_job = client.query(query_str)
        results = query_job.result()  # Waits for the job to complete.
        
        data_val = None
        for row in results:
            data_val = row.test_column # Access the aliased column
            break

        result_summary = f"Test query successful. Result: {data_val}"
        logger.info(f"\033[92m[{func_name}] {result_summary}\033[0m")
        log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=result_summary)
        return {"status": "SUCCESS", "message": result_summary, "data": data_val}
    except Exception as e:
        error_message = f"BigQuery connection test failed: {str(e)}"
        # Log with full traceback here
        logger.error(f"[{func_name}] {error_message}", exc_info=True)
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=error_message)
        return {"status": "ERROR_QUERY_FAILED", "message": error_message}

def _get_account_details(account_type: str, user_id: str) -> dict:
    """
    Helper function to retrieve account_id, balance, and currency for a given account_type and user_id.
    """
    func_name = "_get_account_details"
    params = {"account_type": account_type, "user_id": user_id}
    query_str = None
    
    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}

    accounts_table = _table_ref("Accounts")
    query_str = f"""
        SELECT account_id, balance, currency
        FROM {accounts_table}
        WHERE user_id = @user_id AND account_type = @account_type
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("account_type", "STRING", account_type),
        ]
    )
    try:
        query_job = client.query(query_str, job_config=job_config)
        results = query_job.result()
        row_data = None
        for row in results: # Should be at most one row due to LIMIT 1
            row_data = {
                "account_id": row.account_id,
                "balance": float(row.balance),
                "currency": row.currency,
                "account_type": account_type
            }
            break # Found the account
        
        if row_data:
            log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=f"Account found: {row_data['account_id']}")
            return {"status": "SUCCESS", **row_data}
        else:
            log_bq_interaction(func_name, params, query_str, status="ERROR_ACCOUNT_NOT_FOUND", error_message=f"Account type '{account_type}' not found for user '{user_id}'.")
            return {"status": "ERROR_ACCOUNT_NOT_FOUND", "message": f"Account type '{account_type}' not found for user '{user_id}'."}
    except Exception as e:
        logger.error(f"Exception details in {func_name}: {str(e)}", exc_info=True) # Added exc_info=True
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=str(e))
        # The original logging.error is now covered by log_bq_interaction if status is error
        return {"status": "ERROR_QUERY_FAILED", "message": str(e)}


def get_account_balance(account_type: str) -> dict:
    """
    Queries the Accounts table for the balance of a specific account type for the USER_ID.
    Returns:
        dict: {"account_type": "checking", "balance": 1250.75, "currency": "USD", "account_id": "acc_chk_krishnan_001"}
              or an error message.
    """
    details = _get_account_details(account_type, USER_ID)
    if details["status"] == "SUCCESS":
        return {
            "account_type": account_type, # Already in details, but spec asks for it explicitly
            "balance": details["balance"],
            "currency": details["currency"],
            "account_id": details["account_id"]
        }
    return details # Return the error message from helper


def get_transaction_history(account_type: str, limit: int = 5) -> list:
    """
    Fetches transaction history for a given account_type for the default USER_ID.
    """
    func_name = "get_transaction_history"
    params = {"account_type": account_type, "limit": limit, "user_id": USER_ID}
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return [{"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}]

    # _get_account_details already logs its interaction
    account_details = _get_account_details(account_type, USER_ID)
    if account_details["status"] != "SUCCESS":
        # Log this specific failure context for get_transaction_history
        log_bq_interaction(func_name, params, status=account_details["status"], error_message=f"Failed to get account details for {account_type}: {account_details.get('message')}")
        return [account_details]

    account_id = account_details["account_id"]
    transactions_table = _table_ref("Transactions")

    query_str = f"""
        SELECT transaction_id, date, description, amount, currency, type
        FROM {transactions_table}
        WHERE account_id = @account_id
        ORDER BY date DESC
        LIMIT @limit
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("account_id", "STRING", account_id),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )
    try:
        query_job = client.query(query_str, job_config=job_config)
        results = query_job.result()
        transactions_data = []
        for row in results:
            transactions_data.append({
                "transaction_id": row.transaction_id,
                "date": row.date.isoformat() if isinstance(row.date, (datetime.datetime, datetime.date)) else str(row.date),
                "description": row.description,
                "amount": float(row.amount),
                "currency": row.currency,
                "type": row.type
            })
        
        if not transactions_data:
            log_bq_interaction(func_name, params, query_str, status="NO_TRANSACTIONS_FOUND", result_summary=f"No transactions found for account {account_id}.")
            return [{"status": "NO_TRANSACTIONS_FOUND", "message": f"No transactions found for account {account_id} (type: {account_type})."}]
        
        log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=f"Retrieved {len(transactions_data)} transaction(s).")
        return transactions_data
    except Exception as e:
        logger.error(f"Exception details in {func_name}: {str(e)}", exc_info=True) # Added exc_info=True
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=str(e))
        return [{"status": "ERROR_QUERY_FAILED", "message": str(e)}]


def initiate_fund_transfer_check(from_account_type: str, to_account_type: str, amount: float) -> dict:
    """
    Checks if a fund transfer is possible between two account types for the USER_ID.
    """
    func_name = "initiate_fund_transfer_check"
    params = {"from_account_type": from_account_type, "to_account_type": to_account_type, "amount": amount, "user_id": USER_ID}

    if not isinstance(amount, (int, float)) or amount <= 0:
        log_bq_interaction(func_name, params, status="ERROR_INVALID_AMOUNT", error_message="Transfer amount must be a positive number.")
        return {"status": "ERROR_INVALID_AMOUNT", "message": "Transfer amount must be a positive number."}

    # _get_account_details logs its own interactions
    from_account_details = _get_account_details(from_account_type, USER_ID)
    if from_account_details["status"] != "SUCCESS":
        err_msg = f"From account ('{from_account_type}'): {from_account_details.get('message', 'Error fetching details.')}"
        log_bq_interaction(func_name, params, status=from_account_details["status"], error_message=err_msg)
        return {"status": from_account_details["status"], "message": err_msg}

    to_account_details = _get_account_details(to_account_type, USER_ID)
    if to_account_details["status"] != "SUCCESS":
        err_msg = f"To account ('{to_account_type}'): {to_account_details.get('message', 'Error fetching details.')}"
        log_bq_interaction(func_name, params, status=to_account_details["status"], error_message=err_msg)
        return {"status": to_account_details["status"], "message": err_msg}

    from_account_id = from_account_details["account_id"]
    from_balance = from_account_details["balance"]
    to_account_id = to_account_details["account_id"]

    if from_account_id == to_account_id:
        log_bq_interaction(func_name, params, status="ERROR_SAME_ACCOUNT", error_message="Cannot transfer funds to the same account ID.")
        return {"status": "ERROR_SAME_ACCOUNT", "message": "Cannot transfer funds to the same account type, resulting in the same account ID."}
    
    result_data = {}
    if from_balance >= amount:
        status = "SUFFICIENT_FUNDS"
        result_data = {
            "from_account_id": from_account_id, "to_account_id": to_account_id,
            "from_account_balance": from_balance, "transfer_amount": amount,
            "currency": from_account_details["currency"]
        }
        log_bq_interaction(func_name, params, status=status, result_summary=f"Sufficient funds. From: {from_account_id}, To: {to_account_id}, Amount: {amount}")
    else:
        status = "INSUFFICIENT_FUNDS"
        result_data = {
            "current_balance": from_balance, "from_account_id": from_account_id,
            "to_account_id": to_account_id, "requested_amount": amount,
            "currency": from_account_details["currency"]
        }
        log_bq_interaction(func_name, params, status=status, error_message=f"Insufficient funds. Has: {from_balance}, Needs: {amount}")
    
    return {"status": status, **result_data}


def execute_fund_transfer(from_account_id: str, to_account_id: str, amount: float, currency: str, memo: str) -> dict:
    """
    Executes a fund transfer by updating account balances and recording transactions in BigQuery.
    Operations are performed within a multi-statement transaction for atomicity.
    """
    func_name = "execute_fund_transfer"
    params = {"from_account_id": from_account_id, "to_account_id": to_account_id, "amount": amount, "currency": currency, "memo": memo, "user_id": USER_ID}
    query_str = None # Will hold the multi-statement query

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}

    if not isinstance(amount, (int, float)) or amount <= 0:
        log_bq_interaction(func_name, params, status="ERROR_INVALID_AMOUNT", error_message="Transfer amount must be a positive number.")
        return {"status": "ERROR_INVALID_AMOUNT", "message": "Transfer amount must be a positive number."}

    if from_account_id == to_account_id:
        log_bq_interaction(func_name, params, status="ERROR_SAME_ACCOUNT", error_message="Cannot execute transfer to the same account ID.")
        return {"status": "ERROR_SAME_ACCOUNT", "message": "Cannot transfer funds to the same account."}

    # Fetch account details for validation
    from_account_details = _get_account_balance_by_id(from_account_id, USER_ID)
    if from_account_details["status"] != "SUCCESS":
        err_msg = f"Sender account '{from_account_id}' not found or error: {from_account_details.get('message')}"
        log_bq_interaction(func_name, params, status="ERROR_FROM_ACCOUNT_INVALID", error_message=err_msg)
        return {"status": "ERROR_FROM_ACCOUNT_INVALID", "message": err_msg}

    to_account_details = _get_account_balance_by_id(to_account_id, USER_ID)
    if to_account_details["status"] != "SUCCESS":
        err_msg = f"Recipient account '{to_account_id}' not found or error: {to_account_details.get('message')}"
        log_bq_interaction(func_name, params, status="ERROR_TO_ACCOUNT_INVALID", error_message=err_msg)
        return {"status": "ERROR_TO_ACCOUNT_INVALID", "message": err_msg}

    if from_account_details["currency"] != currency or to_account_details["currency"] != currency:
        err_msg = (f"Currency mismatch. Transfer currency: {currency}, "
                   f"Sender account ({from_account_id}) currency: {from_account_details['currency']}, "
                   f"Recipient account ({to_account_id}) currency: {to_account_details['currency']}.")
        log_bq_interaction(func_name, params, status="ERROR_CURRENCY_MISMATCH", error_message=err_msg)
        return {"status": "ERROR_CURRENCY_MISMATCH", "message": err_msg}

    if from_account_details["balance"] < amount:
        err_msg = f"Insufficient funds in sender account '{from_account_id}'. Has: {from_account_details['balance']} {currency}, Needs: {amount} {currency}"
        log_bq_interaction(func_name, params, status="ERROR_INSUFFICIENT_FUNDS", error_message=err_msg)
        return {
            "status": "ERROR_INSUFFICIENT_FUNDS", "current_balance": from_account_details['balance'],
            "requested_amount": amount, "currency": currency,
            "from_account_id": from_account_id, "to_account_id": to_account_id, "message": err_msg
        }

    transaction_base_id = f"txn_{uuid.uuid4().hex}"
    debit_transaction_id = f"{transaction_base_id}_D"
    credit_transaction_id = f"{transaction_base_id}_C"
    current_timestamp_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    accounts_table = _table_ref("Accounts")
    transactions_table = _table_ref("Transactions")

    # Multi-statement transaction
    # Note: Parameterization within a single multi-statement string sent to client.query()
    # can be tricky. For complex cases, consider stored procedures or multiple client.query calls
    # managed by application logic if BEGIN/COMMIT isn't directly parameterizable as one string.
    # However, for this structure, we'll build the DML string.
    # Ensure values are properly escaped or use query parameters if supported by the client library for multi-statement.
    # For direct DML string construction, ensure numeric types are not quoted, strings are.
    # BigQuery's standard SQL client.query() with @params should handle this.

    query_str = f"""
    BEGIN TRANSACTION;

    -- Decrement sender's balance
    UPDATE {accounts_table}
    SET balance = balance - @amount
    WHERE account_id = @from_account_id AND user_id = @user_id;

    -- Increment recipient's balance
    UPDATE {accounts_table}
    SET balance = balance + @amount
    WHERE account_id = @to_account_id AND user_id = @user_id;

    -- Insert debit transaction for sender
    INSERT INTO {transactions_table} (transaction_id, account_id, user_id, date, description, amount, currency, type, memo)
    VALUES (@debit_transaction_id, @from_account_id, @user_id, @timestamp, @debit_description, -@amount, @currency, 'transfer_debit', @memo);

    -- Insert credit transaction for recipient
    INSERT INTO {transactions_table} (transaction_id, account_id, user_id, date, description, amount, currency, type, memo)
    VALUES (@credit_transaction_id, @to_account_id, @user_id, @timestamp, @credit_description, @amount, @currency, 'transfer_credit', @memo);

    COMMIT TRANSACTION;
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("amount", "FLOAT64", amount),
            bigquery.ScalarQueryParameter("from_account_id", "STRING", from_account_id),
            bigquery.ScalarQueryParameter("to_account_id", "STRING", to_account_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", USER_ID),
            bigquery.ScalarQueryParameter("debit_transaction_id", "STRING", debit_transaction_id),
            bigquery.ScalarQueryParameter("credit_transaction_id", "STRING", credit_transaction_id),
            bigquery.ScalarQueryParameter("timestamp", "TIMESTAMP", current_timestamp_str),
            bigquery.ScalarQueryParameter("debit_description", "STRING", f"Transfer to account {to_account_id}"),
            bigquery.ScalarQueryParameter("credit_description", "STRING", f"Transfer from account {from_account_id}"),
            bigquery.ScalarQueryParameter("currency", "STRING", currency),
            bigquery.ScalarQueryParameter("memo", "STRING", memo),
        ]
    )

    try:
        logger.info(f"[{func_name}] Executing fund transfer transaction for user {USER_ID} from {from_account_id} to {to_account_id} for {amount} {currency}.")
        query_job = client.query(query_str, job_config=job_config)
        query_job.result()  # Wait for the transaction to complete

        if query_job.errors:
            # This block might not be reached if errors cause an exception handled by the except block.
            # However, it's good practice to check job.errors if result() doesn't raise.
            error_detail = f"BigQuery transaction failed: {query_job.errors}"
            log_bq_interaction(func_name, params, query_str, status="ERROR_TRANSACTION_FAILED", error_message=error_detail)
            return {"status": "ERROR_TRANSACTION_FAILED", "message": "Fund transfer failed during BigQuery execution.", "details": query_job.errors}

        success_msg = f"Fund transfer of {amount} {currency} from {from_account_id} to {to_account_id} completed successfully. Transaction ID: {transaction_base_id}"
        log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=success_msg)
        return {
            "status": "SUCCESS",
            "transaction_id": transaction_base_id,
            "message": success_msg
        }
    except Exception as e:
        error_message = f"Exception during fund transfer: {str(e)}"
        logger.error(f"[{func_name}] {error_message}", exc_info=True)
        # Attempt to rollback if possible, though BigQuery auto-rolls back on error in a transaction
        try:
            client.query("ROLLBACK TRANSACTION;").result() # May error if no transaction active
            logger.info(f"[{func_name}] Attempted ROLLBACK TRANSACTION due to error.")
        except Exception as rb_e:
            logger.warning(f"[{func_name}] Error during explicit ROLLBACK attempt: {rb_e}")

        log_bq_interaction(func_name, params, query_str, status="ERROR_EXCEPTION", error_message=error_message)
        return {"status": "ERROR_EXCEPTION", "message": "An internal error occurred during fund transfer.", "details": str(e)}


def get_bill_details(bill_type: str, payee_nickname: str = None) -> dict:
    """
    Queries the RegisteredBillers table for bill details for the USER_ID.
    """
    func_name = "get_bill_details"
    params = {"bill_type": bill_type, "payee_nickname": payee_nickname, "user_id": USER_ID}
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}

    billers_table = _table_ref("RegisteredBillers")
    query_params_list = [
        bigquery.ScalarQueryParameter("user_id", "STRING", USER_ID),
        bigquery.ScalarQueryParameter("bill_type", "STRING", bill_type),
    ]
    
    where_conditions = ["user_id = @user_id", "bill_type = @bill_type"]
    
    if payee_nickname:
        where_conditions.append("payee_nickname = @payee_nickname")
        query_params_list.append(bigquery.ScalarQueryParameter("payee_nickname", "STRING", payee_nickname))
        
    query_str = f"""
        SELECT biller_id, biller_name, last_due_amount as due_amount, last_due_date as due_date, default_payment_account_id
        FROM {billers_table}
        WHERE {" AND ".join(where_conditions)}
    """
    job_config = bigquery.QueryJobConfig(query_parameters=query_params_list)
    
    try:
        query_job = client.query(query_str, job_config=job_config)
        results = list(query_job.result())
        
        if not results:
            msg = f"Biller for type '{bill_type}'" + (f" with nickname '{payee_nickname}'" if payee_nickname else "") + f" not found for user '{USER_ID}'."
            log_bq_interaction(func_name, params, query_str, status="ERROR_BILLER_NOT_FOUND", error_message=msg)
            return {"status": "ERROR_BILLER_NOT_FOUND", "message": msg}
            
        if len(results) > 1:
            biller_names = [row.biller_name for row in results]
            billers_summary = [{"biller_id": r.biller_id, "biller_name": r.biller_name} for r in results]
            msg = f"Multiple billers found for type '{bill_type}'" + (f" with nickname '{payee_nickname}'" if payee_nickname else "") + f". Please specify. Found: {', '.join(biller_names)} for user '{USER_ID}'."
            log_bq_interaction(func_name, params, query_str, status="AMBIGUOUS_BILLER_FOUND", result_summary=f"Found {len(results)} billers.", error_message=msg) # error_message used for detailed user-facing message
            return {
                "status": "AMBIGUOUS_BILLER_FOUND", "message": msg,
                "billers": [{
                    "biller_id": row.biller_id, "biller_name": row.biller_name,
                    "due_amount": float(row.due_amount) if row.due_amount is not None else None,
                    "due_date": row.due_date.isoformat() if isinstance(row.due_date, (datetime.datetime, datetime.date)) else str(row.due_date),
                    "default_payment_account_id": row.default_payment_account_id
                } for row in results]
            }

        row = results[0]
        result_data = {
            "biller_id": row.biller_id, "biller_name": row.biller_name,
            "due_amount": float(row.due_amount) if row.due_amount is not None else None,
            "due_date": row.due_date.isoformat() if isinstance(row.due_date, (datetime.datetime, datetime.date)) else str(row.due_date),
            "default_payment_account_id": row.default_payment_account_id
        }
        log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=f"Biller found: {row.biller_id} - {row.biller_name}")
        return {"status": "SUCCESS", **result_data}
    except Exception as e:
        logger.error(f"Exception details in {func_name}: {str(e)}", exc_info=True) # Added exc_info=True
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=str(e))
        return {"status": "ERROR_QUERY_FAILED", "message": str(e)}


def _get_payee_name(payee_id: str, user_id: str) -> str | None:
    """Helper to fetch payee name from RegisteredBillers for a specific user."""
    func_name = "_get_payee_name"
    params = {"payee_id": payee_id, "user_id": user_id}
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available for _get_payee_name.")
        return None # Function expects str or None
    
    billers_table = _table_ref("RegisteredBillers")
    query_str = f"""
        SELECT biller_name
        FROM {billers_table}
        WHERE biller_id = @payee_id AND user_id = @user_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("payee_id", "STRING", payee_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
        ]
    )
    try:
        query_job = client.query(query_str, job_config=job_config)
        payee_name_found = None
        for row in query_job.result():
            payee_name_found = row.biller_name
            break
        
        if payee_name_found:
            log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=f"Biller name found: {payee_name_found}")
            return payee_name_found
        else:
            log_bq_interaction(func_name, params, query_str, status="WARNING_BILLER_NAME_NOT_FOUND", result_summary=f"Biller name not found for biller_id (param payee_id): {payee_id}, user_id: {user_id}")
            # Original code logged warning, returning None is the expected behavior.
            return None
    except Exception as e:
        logger.error(f"Exception details in {func_name}: {str(e)}", exc_info=True) # Added exc_info=True
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=str(e))
        return None


def _get_account_balance_by_id(account_id: str, user_id: str) -> dict:
    """Helper to get balance and currency for a specific account_id and user_id."""
    func_name = "_get_account_balance_by_id"
    params = {"account_id": account_id, "user_id": user_id}
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}

    accounts_table = _table_ref("Accounts")
    query_str = f"""
        SELECT balance, currency
        FROM {accounts_table}
        WHERE account_id = @account_id AND user_id = @user_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("account_id", "STRING", account_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
        ]
    )
    try:
        query_job = client.query(query_str, job_config=job_config)
        row_data = None
        for row in query_job.result():
            row_data = {"balance": float(row.balance), "currency": row.currency}
            break
        
        if row_data:
            log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=f"Balance found for account {account_id}.")
            return {"status": "SUCCESS", **row_data}
        else:
            msg = f"Account ID '{account_id}' not found for user '{user_id}'."
            log_bq_interaction(func_name, params, query_str, status="ERROR_ACCOUNT_NOT_FOUND", error_message=msg)
            return {"status": "ERROR_ACCOUNT_NOT_FOUND", "message": msg}
    except Exception as e:
        logger.error(f"Exception details in {func_name}: {str(e)}", exc_info=True) # Added exc_info=True
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=str(e))
        return {"status": "ERROR_QUERY_FAILED", "message": str(e)}


def pay_bill(payee_id: str, amount: float, from_account_id: str, user_id: str = None) -> dict:
    """
    Pays a bill for the specified user by deducting from the specified account,
    recording the transaction, and updating the bill's due amount.
    
    Args:
        payee_id: The ID of the payee (biller) to pay.
        amount: The amount to pay.
        from_account_id: The account ID from which to deduct the payment.
        user_id: The ID of the user making the payment. Defaults to the global USER_ID.
    """
    func_name = "pay_bill"
    user_id = user_id or USER_ID
    params = {"payee_id": payee_id, "amount": amount, "from_account_id": from_account_id, "user_id": user_id}
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}

    if not isinstance(amount, (int, float)) or amount <= 0:
        log_bq_interaction(func_name, params, status="ERROR_INVALID_AMOUNT", error_message="Payment amount must be a positive number.")
        return {"status": "ERROR_INVALID_AMOUNT", "message": "Payment amount must be a positive number."}

    # Validate source account and check balance
    balance_details = _get_account_balance_by_id(from_account_id, user_id)
    if balance_details["status"] != "SUCCESS":
        err_msg = f"Error with payment account '{from_account_id}': {balance_details.get('message')}"
        log_bq_interaction(func_name, params, status=balance_details["status"], error_message=err_msg)
        return {"status": balance_details["status"], "message": err_msg}

    current_balance = balance_details["balance"]
    currency = balance_details["currency"]

    if current_balance < amount:
        err_msg = f"Insufficient funds in account {from_account_id}. Has: {current_balance} {currency}, Needs: {amount} {currency}"
        log_bq_interaction(func_name, params, status="INSUFFICIENT_FUNDS", error_message=err_msg)
        return {
            "status": "INSUFFICIENT_FUNDS", "current_balance": current_balance,
            "requested_amount": amount, "currency": currency,
            "from_account_id": from_account_id, "payee_id": payee_id, "message": err_msg
        }

    # Validate payee
    payee_name = _get_payee_name(payee_id, user_id) # This helper fetches from RegisteredBillers
    if not payee_name: # payee_name here is actually biller_name
        err_msg = f"Biller with ID '{payee_id}' not found for user '{user_id}'." # payee_id parameter is used as biller_id
        log_bq_interaction(func_name, params, status="ERROR_BILLER_NOT_FOUND", error_message=err_msg)
        return {"status": "ERROR_BILLER_NOT_FOUND", "message": err_msg}

    confirmation_number = f"BP{uuid.uuid4().hex[:10].upper()}"
    current_timestamp = datetime.datetime.now(datetime.timezone.utc)
    current_timestamp_iso = current_timestamp.isoformat()
    bill_txn_id = f"txn_bill_{uuid.uuid4().hex}"

    accounts_table = _table_ref("Accounts")
    transactions_table = _table_ref("Transactions")
    registered_billers_table = _table_ref("RegisteredBillers")

    query_str = f"""
    BEGIN TRANSACTION;

    -- Deduct amount from source account
    UPDATE {accounts_table}
    SET balance = balance - @amount
    WHERE account_id = @from_account_id AND user_id = @user_id;

    -- Record the bill payment transaction
    INSERT INTO {transactions_table}
        (transaction_id, account_id, user_id, date, description, amount, currency, type, memo)
    VALUES
        (@bill_txn_id, @from_account_id, @user_id, @timestamp, @description, -@amount, @currency, 'bill_payment', @memo);

    -- Update the bill's last_due_amount to 0 and set last_due_date to today's date
    UPDATE {registered_billers_table}
    SET last_due_amount = 0,
        last_due_date = DATE(@timestamp)
    WHERE biller_id = @payee_id AND user_id = @user_id;

    COMMIT TRANSACTION;
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("amount", "FLOAT64", amount),
            bigquery.ScalarQueryParameter("from_account_id", "STRING", from_account_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("bill_txn_id", "STRING", bill_txn_id),
            bigquery.ScalarQueryParameter("timestamp", "TIMESTAMP", current_timestamp_iso),
            bigquery.ScalarQueryParameter("description", "STRING", f"Bill Payment to {payee_name} (Biller ID: {payee_id})"),
            bigquery.ScalarQueryParameter("currency", "STRING", currency),
            bigquery.ScalarQueryParameter("memo", "STRING", f"Payment for bill {payee_id}"),
            bigquery.ScalarQueryParameter("confirmation_number", "STRING", confirmation_number),
            bigquery.ScalarQueryParameter("payee_id", "STRING", payee_id), # This @payee_id maps to biller_id in the WHERE clause
        ]
    )

    try:
        logger.info(f"[{func_name}] Executing bill payment transaction for user {user_id}, payee {payee_id}, amount {amount} {currency} from account {from_account_id}.")
        query_job = client.query(query_str, job_config=job_config)
        query_job.result()  # Wait for the transaction to complete

        if query_job.errors:
            error_detail = f"BigQuery transaction for bill payment failed: {query_job.errors}"
            log_bq_interaction(func_name, params, query_str, status="ERROR_TRANSACTION_FAILED", error_message=error_detail)
            return {"status": "ERROR_TRANSACTION_FAILED", "message": "Bill payment failed during BigQuery execution.", "details": query_job.errors}

        success_msg = f"Bill payment of {amount} {currency} to {payee_name} (Biller ID: {payee_id}) from account {from_account_id} was successful. Confirmation: {confirmation_number}."
        log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=success_msg)
        return {
            "status": "SUCCESS",
            "confirmation_number": confirmation_number,
            "transaction_id": bill_txn_id,
            "biller_name": payee_name, # payee_name variable holds the biller_name
            "amount_paid": float(amount),
            "currency": currency,
            "from_account_id": from_account_id,
            "message": success_msg
        }
    except Exception as e:
        error_message = f"Exception during bill payment transaction: {str(e)}"
        logger.error(f"[{func_name}] {error_message}", exc_info=True)
        # BigQuery automatically rolls back transactions on error for multi-statement queries
        log_bq_interaction(func_name, params, query_str, status="ERROR_EXCEPTION", error_message=error_message)
        return {"status": "ERROR_EXCEPTION", "message": "An internal error occurred during bill payment.", "details": str(e)}

def register_biller(user_id: str, biller_name: str, biller_type: str, account_number: str, payee_nickname: str = None, default_payment_account_id: str = None, due_amount: float = None, due_date: str = None) -> dict:
    """
    Registers a new biller for a given user in the RegisteredBillers table.
    Checks for duplicates based on user_id, biller_type, and account_number.
    """
    func_name = "register_biller"
    params = {
        "user_id": user_id, "biller_name": biller_name, "biller_type": biller_type,
        "account_number": account_number, "payee_nickname": payee_nickname,
        "default_payment_account_id": default_payment_account_id,
        "due_amount": due_amount, "due_date": due_date
    }
    query_str_check = None
    query_str_insert = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}

    if not all([user_id, biller_name, biller_type, account_number]):
        log_bq_interaction(func_name, params, status="ERROR_MISSING_PARAMETERS", error_message="User ID, Biller Name, Biller Type, and Account Number are required.")
        return {"status": "ERROR_MISSING_PARAMETERS", "message": "User ID, Biller Name, Biller Type, and Account Number are required."}

    billers_table = _table_ref("RegisteredBillers")
    
    # Check for existing active biller
    query_str_check = f"""
        SELECT biller_id FROM {billers_table}
        WHERE user_id = @user_id
          AND biller_type = @biller_type
          AND account_number = @account_number
          AND status = 'ACTIVE'
        LIMIT 1
    """
    job_config_check = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("biller_type", "STRING", biller_type),
            bigquery.ScalarQueryParameter("account_number", "STRING", account_number),
        ]
    )
    try:
        query_job_check = client.query(query_str_check, job_config=job_config_check)
        results_check = list(query_job_check.result())
        if results_check:
            existing_biller_id = results_check[0].biller_id
            error_message = f"An active biller with the same type and account number already exists for this user (Biller ID: {existing_biller_id})."
            log_bq_interaction(func_name, params, query_str_check, status="ERROR_DUPLICATE_BILLER", error_message=error_message)
            return {"status": "ERROR_DUPLICATE_BILLER", "message": error_message, "biller_id": existing_biller_id}
    except Exception as e_check:
        logger.error(f"Exception during biller check in {func_name}: {str(e_check)}", exc_info=True)
        log_bq_interaction(func_name, params, query_str_check, status="ERROR_QUERY_FAILED", error_message=f"Biller check failed: {str(e_check)}")
        return {"status": "ERROR_QUERY_FAILED", "message": f"Failed to check for existing biller: {str(e_check)}"}

    biller_id_generated = f"biller_reg_{uuid.uuid4().hex}"
    current_ts = datetime.datetime.now(datetime.timezone.utc)

    # Parse due_date string to date object if provided
    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            log_bq_interaction(func_name, params, status="ERROR_INVALID_DATE_FORMAT", error_message="Invalid due_date format. Please use YYYY-MM-DD.")
            return {"status": "ERROR_INVALID_DATE_FORMAT", "message": "Invalid due_date format. Please use YYYY-MM-DD."}

    query_str_insert = f"""
        INSERT INTO {billers_table} (
            biller_id, user_id, biller_name, biller_type, account_number,
            payee_nickname, default_payment_account_id, status,
            due_amount, due_date, registration_ts, last_updated_ts
        ) VALUES (
            @biller_id, @user_id, @biller_name, @biller_type, @account_number,
            @payee_nickname, @default_payment_account_id, 'ACTIVE',
            @due_amount, @due_date, @current_ts, @current_ts
        )
    """
    job_config_insert = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("biller_id", "STRING", biller_id_generated),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("biller_name", "STRING", biller_name),
            bigquery.ScalarQueryParameter("biller_type", "STRING", biller_type),
            bigquery.ScalarQueryParameter("account_number", "STRING", account_number),
            bigquery.ScalarQueryParameter("payee_nickname", "STRING", payee_nickname),
            bigquery.ScalarQueryParameter("default_payment_account_id", "STRING", default_payment_account_id),
            bigquery.ScalarQueryParameter("due_amount", "FLOAT64", due_amount),
            bigquery.ScalarQueryParameter("due_date", "DATE", parsed_due_date),
            bigquery.ScalarQueryParameter("current_ts", "TIMESTAMP", current_ts),
        ]
    )
    try:
        query_job_insert = client.query(query_str_insert, job_config=job_config_insert)
        query_job_insert.result()  # Wait for completion

        if query_job_insert.errors:
            error_detail = f"BigQuery insert failed: {query_job_insert.errors}"
            log_bq_interaction(func_name, params, query_str_insert, status="ERROR_INSERT_FAILED", error_message=error_detail)
            return {"status": "ERROR_INSERT_FAILED", "message": "Biller registration failed during BigQuery execution.", "details": query_job_insert.errors}

        success_msg = f"Biller '{biller_name}' registered successfully with ID {biller_id_generated}."
        log_bq_interaction(func_name, params, query_str_insert, status="SUCCESS", result_summary=success_msg)
        return {"status": "SUCCESS", "message": success_msg, "biller_id": biller_id_generated}
    except Exception as e_insert:
        logger.error(f"Exception during biller insert in {func_name}: {str(e_insert)}", exc_info=True)
        log_bq_interaction(func_name, params, query_str_insert, status="ERROR_EXCEPTION", error_message=str(e_insert))
        return {"status": "ERROR_EXCEPTION", "message": f"An internal error occurred during biller registration: {str(e_insert)}"}

def update_biller_details(user_id: str, payee_id: str, updates: dict) -> dict:
    """
    Updates details for an existing registered biller for a given user.
    'updates' dict can contain: biller_name, biller_type, account_number,
                                payee_nickname, default_payment_account_id, status,
                                due_amount, due_date.
    """
    func_name = "update_biller_details"
    params = {"user_id": user_id, "payee_id": payee_id, "updates": updates}
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}

    if not updates:
        log_bq_interaction(func_name, params, status="ERROR_NO_UPDATES_PROVIDED", error_message="No updates provided.")
        return {"status": "ERROR_NO_UPDATES_PROVIDED", "message": "No updates provided to apply."}

    billers_table = _table_ref("RegisteredBillers")
    set_clauses = []
    query_params_list = []
    
    allowed_fields = {
        "biller_name": "STRING", "biller_type": "STRING", "account_number": "STRING",
        "payee_nickname": "STRING", "default_payment_account_id": "STRING", 
        "status": "STRING", "due_amount": "FLOAT64", "due_date": "DATE"
    }

    for field, value in updates.items():
        if field in allowed_fields:
            set_clauses.append(f"{field} = @{field}")
            param_type = allowed_fields[field]
            # Handle date parsing for due_date
            if field == "due_date" and value is not None:
                try:
                    value = datetime.datetime.strptime(value, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    log_bq_interaction(func_name, params, status="ERROR_INVALID_DATE_FORMAT", error_message=f"Invalid due_date format for field '{field}'. Use YYYY-MM-DD.")
                    return {"status": "ERROR_INVALID_DATE_FORMAT", "message": f"Invalid due_date format for field '{field}'. Use YYYY-MM-DD."}
            
            query_params_list.append(bigquery.ScalarQueryParameter(field, param_type, value))
        else:
            logger.warning(f"[{func_name}] Unknown field '{field}' in updates, skipping.")

    if not set_clauses:
        log_bq_interaction(func_name, params, status="ERROR_NO_VALID_UPDATES", error_message="No valid fields to update.")
        return {"status": "ERROR_NO_VALID_UPDATES", "message": "No valid fields provided for update."}

    set_clauses.append("last_updated_ts = @current_ts")
    query_params_list.append(bigquery.ScalarQueryParameter("current_ts", "TIMESTAMP", datetime.datetime.now(datetime.timezone.utc)))
    query_params_list.append(bigquery.ScalarQueryParameter("user_id", "STRING", user_id))
    query_params_list.append(bigquery.ScalarQueryParameter("payee_id", "STRING", payee_id))

    query_str = f"""
        UPDATE {billers_table}
        SET {', '.join(set_clauses)}
        WHERE user_id = @user_id AND biller_id = @payee_id
    """
    job_config = bigquery.QueryJobConfig(query_parameters=query_params_list)

    try:
        logger.info(f"[{func_name}] Attempting to update biller {payee_id} for user {user_id} with query: {query_str} and params: {updates}")
        query_job = client.query(query_str, job_config=job_config)
        query_job.result()  # Wait for completion

        if query_job.errors:
            error_detail = f"BigQuery update failed: {query_job.errors}"
            log_bq_interaction(func_name, params, query_str, status="ERROR_UPDATE_FAILED", error_message=error_detail)
            return {"status": "ERROR_UPDATE_FAILED", "message": "Biller update failed during BigQuery execution.", "details": query_job.errors}
        
        # Check if any rows were actually updated
        if query_job.num_dml_affected_rows is not None and query_job.num_dml_affected_rows > 0:
            success_msg = f"Biller '{payee_id}' updated successfully for user '{user_id}'."
            log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=success_msg)
            return {"status": "SUCCESS", "message": success_msg, "payee_id": payee_id, "updated_rows": query_job.num_dml_affected_rows}
        else:
            # This could mean the biller_id/user_id combination was not found, or values were the same
            not_found_msg = f"Biller '{payee_id}' not found for user '{user_id}', or no changes applied."
            log_bq_interaction(func_name, params, query_str, status="WARNING_NO_ROWS_UPDATED", result_summary=not_found_msg)
            return {"status": "WARNING_NO_ROWS_UPDATED", "message": not_found_msg, "payee_id": payee_id}

    except Exception as e:
        logger.error(f"Exception during biller update in {func_name}: {str(e)}", exc_info=True)
        log_bq_interaction(func_name, params, query_str, status="ERROR_EXCEPTION", error_message=str(e))
        return {"status": "ERROR_EXCEPTION", "message": f"An internal error occurred during biller update: {str(e)}"}

def remove_biller(user_id: str, payee_id: str) -> dict:
    """
    Removes a biller for a user by marking its status as 'INACTIVE'.
    """
    func_name = "remove_biller"
    params = {"user_id": user_id, "payee_id": payee_id}
    
    updates = {"status": "INACTIVE"}
    # Use update_biller_details to perform the status change
    result = update_biller_details(user_id=user_id, payee_id=payee_id, updates=updates)

    if result.get("status") == "SUCCESS":
        # Modify log entry for clarity
        log_bq_interaction(func_name, params, query_str=f"UPDATE RegisteredBillers SET status = 'INACTIVE' WHERE user_id='{user_id}' AND biller_id='{payee_id}'", status="SUCCESS", result_summary=f"Biller {payee_id} marked as INACTIVE.")
        return {"status": "SUCCESS", "message": f"Biller '{payee_id}' marked as inactive successfully.", "payee_id": payee_id}
    elif result.get("status") == "WARNING_NO_ROWS_UPDATED":
        log_bq_interaction(func_name, params, query_str=f"UPDATE RegisteredBillers SET status = 'INACTIVE' WHERE user_id='{user_id}' AND biller_id='{payee_id}'", status="ERROR_BILLER_NOT_FOUND_OR_NO_CHANGE", error_message=f"Biller {payee_id} not found for user {user_id} or already inactive.")
        return {"status": "ERROR_BILLER_NOT_FOUND_OR_NO_CHANGE", "message": f"Biller '{payee_id}' not found for user '{user_id}' or already inactive."}
    else: # Propagate other errors
        log_bq_interaction(func_name, params, query_str=f"UPDATE RegisteredBillers SET status = 'INACTIVE' WHERE user_id='{user_id}' AND biller_id='{payee_id}'", status=result.get("status", "ERROR_REMOVING_BILLER"), error_message=result.get("message", "Failed to remove biller."))
        return result

def list_registered_billers(user_id: str) -> dict:
    """
    Lists registered billers for a given user_id.
    """
    func_name = "list_registered_billers"
    params = {"user_id": user_id} # Removed status_filter
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return {"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available.", "billers": []}

    billers_table = _table_ref("RegisteredBillers")
    # Only user_id is needed for filtering
    query_params_list = [bigquery.ScalarQueryParameter("user_id", "STRING", user_id)]
    
    # WHERE clause now only filters by user_id
    where_clauses = ["rb.user_id = @user_id"]

    query_str = f"""
        SELECT rb.biller_id,
               rb.biller_name,
               rb.bill_type AS biller_type,
               rb.account_number_at_biller AS account_number,
               rb.biller_nickname AS payee_nickname,
               rb.default_payment_account_id,
               rb.last_due_amount AS due_amount,
               rb.last_due_date AS due_date
        FROM {billers_table} AS rb
        WHERE {" AND ".join(where_clauses)}
        ORDER BY rb.biller_name, rb.biller_nickname
    """
    job_config = bigquery.QueryJobConfig(query_parameters=query_params_list)
    
    try:
        query_job = client.query(query_str, job_config=job_config)
        results = list(query_job.result())
        
        billers_data = []
        for row in results:
            billers_data.append({
                "biller_id": row.biller_id,
                "biller_name": row.biller_name,
                "biller_type": row.biller_type, # Aliased from bill_type
                "account_number": row.account_number, # Aliased from account_number_at_biller
                "payee_nickname": row.payee_nickname, # Aliased from biller_nickname
                "default_payment_account_id": row.default_payment_account_id,
                "due_amount": float(row.due_amount) if row.due_amount is not None else None, # Aliased from last_due_amount
                "due_date": row.due_date.isoformat() if isinstance(row.due_date, (datetime.date, datetime.datetime)) else str(row.due_date), # Aliased from last_due_date
                # Removed status, registration_ts, last_updated_ts
            })
        
        if not billers_data:
            msg = f"No billers found for user '{user_id}'." # Updated message
            log_bq_interaction(func_name, params, query_str, status="NO_BILLERS_FOUND", result_summary=msg)
            return {"status": "NO_BILLERS_FOUND", "message": msg, "billers": []}
        
        log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=f"Retrieved {len(billers_data)} biller(s).")
        return {"status": "SUCCESS", "billers": billers_data}
    except Exception as e:
        logger.error(f"Exception in {func_name}: {str(e)}", exc_info=True)
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=str(e))
        return {"status": "ERROR_QUERY_FAILED", "message": str(e), "billers": []}


def get_accounts_for_user(user_id: str) -> list:
    """
    Retrieves all accounts for a given user_id.
    Returns a list of account dictionaries on success, or a list containing an error dictionary.
    """
    func_name = "get_accounts_for_user"
    params = {"user_id": user_id}
    query_str = None

    if not client:
        log_bq_interaction(func_name, params, status="ERROR_CLIENT_NOT_INITIALIZED", error_message="BigQuery client not available.")
        return [{"status": "ERROR_CLIENT_NOT_INITIALIZED", "message": "BigQuery client not available."}]

    accounts_table = _table_ref("Accounts")
    query_str = f"""
        SELECT account_id, account_type, balance, currency, account_nickname
        FROM {accounts_table}
        WHERE user_id = @user_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
        ]
    )
    try:
        query_job = client.query(query_str, job_config=job_config)
        results = query_job.result()
        accounts_data = []
        for row in results:
            accounts_data.append({
                "account_id": row.account_id,
                "account_name": row.account_type, # Use account_type as the source for 'account_name' field
                "account_type": row.account_type,
                "balance": float(row.balance) if row.balance is not None else 0.0,
                "currency": row.currency,
                "account_nickname": row.account_nickname
            })
        
        if not accounts_data:
            log_bq_interaction(func_name, params, query_str, status="NO_ACCOUNTS_FOUND", result_summary=f"No accounts found for user {user_id}.")
            # Return as a list with a status dict, consistent with error returns
            return [{"status": "NO_ACCOUNTS_FOUND", "message": f"No accounts found for user {user_id}."}]
        
        log_bq_interaction(func_name, params, query_str, status="SUCCESS", result_summary=f"Retrieved {len(accounts_data)} account(s) for user {user_id}.")
        return accounts_data # Success: return list of account dicts
    except Exception as e:
        logger.error(f"Exception details in {func_name}: {str(e)}", exc_info=True)
        log_bq_interaction(func_name, params, query_str, status="ERROR_QUERY_FAILED", error_message=str(e))
        return [{"status": "ERROR_QUERY_FAILED", "message": str(e)}]


def find_account_by_natural_language(user_id: str, natural_language_string: str) -> dict:
    """
    Attempts to find a unique account_id for a user based on a natural language string.
    Matches against account_name and account_type.
    """
    func_name = "find_account_by_natural_language"
    params = {"user_id": user_id, "natural_language_string": natural_language_string}
    
    user_accounts_result = get_accounts_for_user(user_id)

    if not isinstance(user_accounts_result, list) or not user_accounts_result:
        log_bq_interaction(func_name, params, status="ERROR_UNEXPECTED_ACCOUNTS_RESPONSE", error_message="Unexpected response from get_accounts_for_user.")
        return {"status": "ERROR_UNEXPECTED_ACCOUNTS_RESPONSE", "message": "Failed to retrieve user accounts."}

    first_item = user_accounts_result[0]
    if isinstance(first_item, dict) and "status" in first_item and first_item["status"] != "SUCCESS":
        # This means get_accounts_for_user returned an error status (e.g., ERROR_CLIENT_NOT_INITIALIZED, NO_ACCOUNTS_FOUND, ERROR_QUERY_FAILED)
        # NO_ACCOUNTS_FOUND is a valid case where we can't find a match.
        if first_item["status"] == "NO_ACCOUNTS_FOUND":
             log_bq_interaction(func_name, params, status="ERROR_ACCOUNT_NOT_FOUND", error_message=f"No accounts exist for user '{user_id}' to match against '{natural_language_string}'.")
             return {"status": "ERROR_ACCOUNT_NOT_FOUND", "message": f"No accounts exist for user '{user_id}' to perform a match."}
        
        log_bq_interaction(func_name, params, status=first_item["status"], error_message=f"Could not retrieve accounts for matching: {first_item.get('message')}")
        return first_item

    user_accounts = user_accounts_result

    nl_lower = natural_language_string.lower()
    nl_words = set(nl_lower.split())

    potential_matches = []

    for acc in user_accounts:
        acc_name_lower = acc.get("account_name", "").lower()
        acc_type_lower = acc.get("account_type", "").lower()
        acc_nickname_lower = acc.get("account_nickname", "").lower() # Get account nickname
        score = 0
        match_reasons = []

        # Highest priority: Exact match on nickname
        if acc_nickname_lower and acc_nickname_lower == nl_lower:
            score += 200 # Very high score for exact nickname match
            match_reasons.append("exact_nickname_match")
        # High priority: All NL words in nickname (if nickname exists)
        elif acc_nickname_lower and nl_words.issubset(set(acc_nickname_lower.split())):
            score += 150 * len(nl_words)
            match_reasons.append("all_nl_words_in_nickname")

        if acc_name_lower == nl_lower:
            score += 100
            match_reasons.append("exact_name_match")

        if nl_words.issubset(set(acc_name_lower.split())):
            score += 50 * len(nl_words)
            match_reasons.append("all_nl_words_in_name")
        
        # More granular: check individual word matches in name
        name_words_present = nl_words.intersection(set(acc_name_lower.split()))
        if name_words_present:
            score += 15 * len(name_words_present) # Boost for each common word
            match_reasons.append(f"name_words_match:{','.join(name_words_present)}")


        if acc_type_lower in nl_words: # e.g. nl_words = {"my", "savings"}, acc_type_lower = "savings"
            score += 40 # Higher score for direct type keyword match
            match_reasons.append("type_keyword_match")
        elif acc_type_lower in nl_lower: # e.g. nl_lower = "my savings account", acc_type_lower = "savings"
            score += 30
            match_reasons.append("type_substring_match")
        
        if "primary" in nl_words and ("primary" in acc_name_lower or ("primary" in acc_nickname_lower if acc_nickname_lower else False)):
            score += 25 # Specific boost for "primary"
            match_reasons.append("primary_keyword_name_or_nickname_match")
        
        if score > 0:
            potential_matches.append({"account_id": acc["account_id"], "account_name": acc["account_name"], "account_type": acc["account_type"], "account_nickname": acc.get("account_nickname", ""), "score": score, "reasons": match_reasons})

    if not potential_matches:
        log_bq_interaction(func_name, params, status="ERROR_ACCOUNT_NOT_FOUND", error_message=f"No matching account found for '{natural_language_string}'.")
        return {"status": "ERROR_ACCOUNT_NOT_FOUND", "message": f"Could not find an account matching '{natural_language_string}'."}

    potential_matches.sort(key=lambda x: x["score"], reverse=True)
    best_match = potential_matches[0]

    # If only one match, or top score is significantly higher
    if len(potential_matches) == 1 or best_match["score"] >= 100 and (len(potential_matches) == 1 or best_match["score"] > potential_matches[1]["score"] + 20) :
        log_bq_interaction(func_name, params, status="SUCCESS", result_summary=f"Found account: {best_match['account_id']} (Name: {best_match['account_name']}, Nickname: {best_match.get('account_nickname', 'N/A')}, Type: {best_match['account_type']}, Score: {best_match['score']})")
        return {
            "status": "SUCCESS",
            "account_id": best_match["account_id"],
            "account_name": best_match["account_name"],
            "account_nickname": best_match.get("account_nickname", "N/A"), # Include nickname in response
            "account_type": best_match["account_type"],
            "message": f"Successfully identified account '{best_match['account_name']}' (Nickname: {best_match.get('account_nickname', 'N/A')})."
        }
    else:
        ambiguous_options = [{"account_id": m["account_id"], "name": m["account_name"], "nickname": m.get("account_nickname", "N/A"), "type": m["account_type"], "score": m["score"]} for m in potential_matches if m["score"] > 10][:3] # Show top 3 with reasonable score
        if not ambiguous_options: # If all scores are too low
             log_bq_interaction(func_name, params, status="ERROR_ACCOUNT_NOT_FOUND", error_message=f"No sufficiently matching account found for '{natural_language_string}'. Top score: {best_match['score']}")
             return {"status": "ERROR_ACCOUNT_NOT_FOUND", "message": f"Could not find a sufficiently clear match for account '{natural_language_string}'."}

        log_bq_interaction(func_name, params, status="ERROR_AMBIGUOUS_ACCOUNT", error_message=f"Multiple accounts match '{natural_language_string}'. Options: {ambiguous_options}")
        return {
            "status": "ERROR_AMBIGUOUS_ACCOUNT",
            "message": f"Your description '{natural_language_string}' is ambiguous and matches multiple accounts. Please be more specific.",
            "options": ambiguous_options
        }

# Example usage (for testing purposes, can be removed or commented out)
if __name__ == "__main__":
    if not client:
        logger.error("BigQuery client not initialized. Cannot run examples.") # Use logger
    else:
        # Use logger for example outputs
        logger.info(f"Using Project ID: {PROJECT_ID}, Dataset ID: {DATASET_ID}")
        logger.info(f"Using User ID: {USER_ID}\n")

        logger.info("--- Test BigQuery Connection ---")
        test_result = test_bigquery_connection()
        logger.info(f"Test Connection Result: {test_result}\n")

        logger.info("--- Get Account Balance (checking) ---")
        balance_checking = get_account_balance("checking")
        logger.info(balance_checking) # The function itself will log details
        logger.info("\n--- Get Account Balance (savings) ---")
        balance_savings = get_account_balance("savings")
        logger.info(balance_savings)
        logger.info("\n--- Get Account Balance (non_existent_account) ---")
        balance_non_existent = get_account_balance("non_existent_account")
        logger.info(balance_non_existent)

        logger.info("\n--- Get Transaction History (checking, limit 2) ---")
        history_checking = get_transaction_history("checking", limit=2)
        logger.info(history_checking)
        
        logger.info("\n--- Get Transaction History (savings, limit 3) ---")
        history_savings = get_transaction_history("savings", limit=3)
        logger.info(history_savings)

        logger.info("\n--- Initiate Fund Transfer Check (checking to savings, 50.0) ---")
        transfer_check_sufficient = initiate_fund_transfer_check("checking", "savings", 50.0)
        logger.info(transfer_check_sufficient)

        logger.info("\n--- Initiate Fund Transfer Check (checking to savings, 50000.0 - insufficient) ---")
        transfer_check_insufficient = initiate_fund_transfer_check("checking", "savings", 50000.0)
        logger.info(transfer_check_insufficient)
        
        logger.info("\n--- Initiate Fund Transfer Check (checking to non_existent, 50.0) ---")
        transfer_check_no_to_acc = initiate_fund_transfer_check("checking", "non_existent", 50.0)
        logger.info(transfer_check_no_to_acc)

        logger.info("\n--- Initiate Fund Transfer Check (non_existent to savings, 50.0) ---")
        transfer_check_no_from_acc = initiate_fund_transfer_check("non_existent", "savings", 50.0)
        logger.info(transfer_check_no_from_acc)
        
        logger.info("\n--- Initiate Fund Transfer Check (checking to checking, 50.0 - same account) ---")
        transfer_check_same_acc = initiate_fund_transfer_check("checking", "checking", 50.0)
        logger.info(transfer_check_same_acc)

        logger.info("\n--- Initiate Fund Transfer Check (checking to savings, -50.0 - invalid amount) ---")
        transfer_check_invalid_amount = initiate_fund_transfer_check("checking", "savings", -50.0)
        logger.info(transfer_check_invalid_amount)


        if transfer_check_sufficient.get("status") == "SUFFICIENT_FUNDS":
            logger.info("\n--- Execute Fund Transfer (simulated) ---")
            exec_transfer = execute_fund_transfer(
                from_account_id=transfer_check_sufficient["from_account_id"],
                to_account_id=transfer_check_sufficient["to_account_id"],
                amount=transfer_check_sufficient["transfer_amount"],
                currency=transfer_check_sufficient["currency"],
                memo="Monthly allowance"
            )
            logger.info(exec_transfer)

        logger.info("\n--- Get Bill Details (electricity, no nickname) ---")
        bill_details_elec = get_bill_details("electricity")
        logger.info(bill_details_elec)

        logger.info("\n--- Get Bill Details (internet, nickname 'MyHomeNet') ---")
        bill_details_internet = get_bill_details("internet", payee_nickname="MyHomeNet")
        logger.info(bill_details_internet)
        
        logger.info("\n--- Get Bill Details (non_existent_bill_type) ---")
        bill_details_non_existent = get_bill_details("non_existent_bill_type")
        logger.info(bill_details_non_existent)

        payee_to_pay = None
        if bill_details_elec.get("status") == "SUCCESS":
            payee_to_pay = bill_details_elec
        elif bill_details_elec.get("status") == "AMBIGUOUS_BILLER_FOUND" and bill_details_elec.get("billers"):
            payee_to_pay = bill_details_elec["billers"][0]
            logger.info(f"\nPaying first ambiguous biller: {payee_to_pay.get('payee_name')}")
            
        if payee_to_pay and payee_to_pay.get("default_payment_account_id") and payee_to_pay.get("due_amount") is not None:
            logger.info(f"\n--- Pay Bill (simulated for {payee_to_pay.get('payee_name')}) ---")
            payment_result = pay_bill(
                payee_id=payee_to_pay["payee_id"],
                amount=payee_to_pay["due_amount"],
                from_account_id=payee_to_pay["default_payment_account_id"]
            )
            logger.info(payment_result)
        elif payee_to_pay:
             logger.info(f"\n--- Cannot simulate Pay Bill for {payee_to_pay.get('payee_name')} due to missing default_payment_account_id or due_amount ---")


        logger.info("\n--- Pay Bill (simulated, insufficient funds example) ---")
        test_payee_id_for_insufficient = "biller_elec_krishnan_001"
        if bill_details_elec.get("status") == "SUCCESS":
            test_payee_id_for_insufficient = bill_details_elec["payee_id"]
        elif bill_details_elec.get("status") == "AMBIGUOUS_BILLER_FOUND" and bill_details_elec.get("billers"):
             if bill_details_elec["billers"]:
                test_payee_id_for_insufficient = bill_details_elec["billers"][0]["payee_id"]

        payment_insufficient = pay_bill(
            payee_id=test_payee_id_for_insufficient,
            amount=100000.0,
            from_account_id="acc_chk_krishnan_001"
        )
        logger.info(payment_insufficient)

        logger.info("\n--- Pay Bill (simulated, invalid from_account_id) ---")
        payment_invalid_acc = pay_bill(
            payee_id=test_payee_id_for_insufficient,
            amount=50.0,
            from_account_id="acc_non_existent_000"
        )
        logger.info(payment_invalid_acc)

        logger.info("\n--- Pay Bill (simulated, invalid payee_id) ---")
        payment_invalid_payee = pay_bill(
            payee_id="biller_non_existent_000",
            amount=50.0,
            from_account_id="acc_chk_krishnan_001"
        )
        logger.info(payment_invalid_payee)

        logger.info("\n--- Pay Bill (simulated, invalid amount) ---")
        payment_invalid_amount = pay_bill(
            payee_id=test_payee_id_for_insufficient,
            amount=-50.0,
            from_account_id="acc_chk_krishnan_001"
        )
        logger.info(payment_invalid_amount)