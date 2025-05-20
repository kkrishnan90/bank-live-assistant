from google.genai import types
import asyncio # For potential future use with to_thread
import bigquery_functions # Use absolute import
from bigquery_functions import USER_ID # Import USER_ID
import json
from datetime import datetime, timezone
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Helper function for structured logging
def _log_tool_event(event_type: str, tool_name: str, parameters: dict, response: dict = None):
    """Helper function to create and print a structured log entry for tool events."""
    log_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_type": "TOOL_EVENT",
        "event_subtype": event_type,
        "tool_function_name": tool_name,
        "parameters_sent": parameters
    }
    if response is not None:
        log_payload["response_received"] = response
    print(json.dumps(log_payload))

# Function Declaration for getBalance
getBalance_declaration = types.FunctionDeclaration(
    name="getBalance",
    description="Fetches the current balance for a specified bank account type (e.g., checking, savings).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "account_type": types.Schema(type=types.Type.STRING, description="The type of account to fetch the balance for (e.g., 'checking', 'savings').")
        },
        required=["account_type"]
    )
)

# Function Declaration for getTransactionHistory
getTransactionHistory_declaration = types.FunctionDeclaration(
    name="getTransactionHistory",
    description="Fetches the last N transactions for a specified bank account type.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "account_type": types.Schema(type=types.Type.STRING, description="The type of account (e.g., 'checking', 'savings')."),
            "limit": types.Schema(type=types.Type.INTEGER, description="The number of transactions to retrieve (defaults to 5).")
        },
        required=["account_type"] # 'limit' is optional as it's not in required and has a default
    )
)

# Function Declaration for initiateFundTransfer
initiateFundTransfer_declaration = types.FunctionDeclaration(
    name="initiateFundTransfer",
    description="Initiates a fund transfer between two accounts. May require further clarification from the user.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "amount": types.Schema(type=types.Type.NUMBER, description="The amount to transfer."),
            "currency": types.Schema(type=types.Type.STRING, description="The currency of the amount (e.g., 'USD')."),
            "from_account_type": types.Schema(type=types.Type.STRING, description="The account type to transfer from (e.g., 'checking')."),
            "to_account_type": types.Schema(type=types.Type.STRING, description="The account type to transfer to (e.g., 'savings').")
        },
        required=["amount", "currency", "from_account_type", "to_account_type"]
    )
)

# Function Declaration for executeFundTransfer
executeFundTransfer_declaration = types.FunctionDeclaration(
    name="executeFundTransfer",
    description="Executes a previously confirmed fund transfer. This is called after user confirmation.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "amount": types.Schema(type=types.Type.NUMBER, description="The amount to transfer."),
            "currency": types.Schema(type=types.Type.STRING, description="The currency of the amount."),
            "from_account_id": types.Schema(type=types.Type.STRING, description="The ID of the account to transfer from."),
            "to_account_id": types.Schema(type=types.Type.STRING, description="The ID of the account to transfer to."),
            "memo": types.Schema(type=types.Type.STRING, description="A memo or note for the transfer.")
        },
        required=["amount", "currency", "from_account_id", "to_account_id", "memo"]
    )
)

# Function Declaration for getBillDetails
getBillDetails_declaration = types.FunctionDeclaration(
    name="getBillDetails",
    description="Fetches details for a bill, such as due amount and payee name. Provide bill_type or payee_nickname (corresponds to biller_nickname in DB). At least one is recommended.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "bill_type": types.Schema(type=types.Type.STRING, description="Optional. The type of bill (e.g., 'electricity', 'water'). Corresponds to 'bill_type' in the database."),
            "payee_nickname": types.Schema(type=types.Type.STRING, description="Optional. The nickname of the payee (e.g., 'My Electric Co.'). Corresponds to 'biller_nickname' in the database.")
        },
        # Implementation should check that at least one is provided.
        required=[]
    )
)

# Function Declaration for payBill
payBill_declaration = types.FunctionDeclaration(
    name="payBill",
    description="Pays a bill from a specified account after user confirmation.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "payee_id": types.Schema(type=types.Type.STRING, description="The internal ID of the payee."),
            "amount": types.Schema(type=types.Type.NUMBER, description="The amount to pay."),
            "from_account_id": types.Schema(type=types.Type.STRING, description="The ID of the account to pay from, or a natural language description like 'my savings' or 'Krishnan's checking'.")
        },
        required=["payee_id", "amount", "from_account_id"]
    )
)

# Function Declaration for registerBiller
registerBiller_declaration = types.FunctionDeclaration(
    name="registerBiller",
    description="Registers a new biller for the user. Requires biller name and account number. Other fields are optional.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "biller_name": types.Schema(type=types.Type.STRING, description="The official name of the biller company. Corresponds to 'biller_name' (REQUIRED) in the database."),
            "biller_type": types.Schema(type=types.Type.STRING, description="Optional. The category of the bill (e.g., 'electricity', 'internet', 'credit card'). Corresponds to 'bill_type' (OPTIONAL) in the database."),
            "account_number": types.Schema(type=types.Type.STRING, description="The user's account number with the biller. Corresponds to 'account_number_at_biller' (REQUIRED) in the database."),
            "payee_nickname": types.Schema(type=types.Type.STRING, description="Optional. A nickname for this biller (e.g., 'My Power Bill'). Corresponds to 'biller_nickname' (OPTIONAL) in the database."),
            "default_payment_account_id": types.Schema(type=types.Type.STRING, description="Optional. The ID of the user's bank account for default payments. Corresponds to 'default_payment_account_id' (OPTIONAL) in the database."),
            "due_amount": types.Schema(type=types.Type.NUMBER, description="Optional. The current due amount. Corresponds to 'last_due_amount' (FLOAT, OPTIONAL) in the database."),
            "due_date": types.Schema(type=types.Type.STRING, description="Optional. The current due date in YYYY-MM-DD format. Corresponds to 'last_due_date' (DATE, OPTIONAL) in the database.")
        },
        required=["biller_name", "account_number"]
    )
)

# Function Declaration for updateBillerDetails
updateBillerDetails_declaration = types.FunctionDeclaration(
    name="updateBillerDetails",
    description="Updates details for an existing registered biller.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "payee_id": types.Schema(type=types.Type.STRING, description="The unique ID of the biller to update. Corresponds to 'biller_id' (REQUIRED) in the database."),
            "updates": types.Schema(
                type=types.Type.OBJECT,
                description="A dictionary of fields to update. Maps to BQ columns: biller_name (REQUIRED), biller_type (maps to 'bill_type', OPTIONAL), account_number (maps to 'account_number_at_biller', REQUIRED), payee_nickname (maps to 'biller_nickname', OPTIONAL), default_payment_account_id (OPTIONAL), status ('ACTIVE'/'INACTIVE', app-level), due_amount (maps to 'last_due_amount', OPTIONAL), due_date (maps to 'last_due_date', OPTIONAL, YYYY-MM-DD).",
                properties={
                    "biller_name": types.Schema(type=types.Type.STRING, description="New official name of the biller company."),
                    "biller_type": types.Schema(type=types.Type.STRING, description="New category of the bill. Maps to 'bill_type' in DB."),
                    "account_number": types.Schema(type=types.Type.STRING, description="New user's account number with the biller. Maps to 'account_number_at_biller' in DB."),
                    "payee_nickname": types.Schema(type=types.Type.STRING, description="New nickname for this biller. Maps to 'biller_nickname' in DB."),
                    "default_payment_account_id": types.Schema(type=types.Type.STRING, description="New default payment account ID."),
                    "status": types.Schema(type=types.Type.STRING, enum=["ACTIVE", "INACTIVE"], description="Application-level status for the biller."),
                    "due_amount": types.Schema(type=types.Type.NUMBER, description="New current due amount. Maps to 'last_due_amount' in DB."),
                    "due_date": types.Schema(type=types.Type.STRING, description="New due date (YYYY-MM-DD). Maps to 'last_due_date' in DB.")
                }
            )
        },
        required=["payee_id", "updates"]
    )
)

# Function Declaration for removeBiller
removeBiller_declaration = types.FunctionDeclaration(
    name="removeBiller",
    description="Removes (marks as inactive) a registered biller for the user.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "payee_id": types.Schema(type=types.Type.STRING, description="The unique ID of the biller to remove.")
        },
        required=["payee_id"]
    )
)

# Function Declaration for listRegisteredBillers
listRegisteredBillers_declaration = types.FunctionDeclaration(
    name="listRegisteredBillers",
    description="Lists all registered billers for the user, optionally filtered by status.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
        }
        # 'status' parameter removed as it's not used in the BQ function
    )
)

# Actual Python function implementations
async def getBalance(account_type: str):
    tool_name = "getBalance"
    params_sent = {"account_type": account_type}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.get_account_balance with account_type: {account_type}")
    api_response = {}
    try:
        bq_result = bigquery_functions.get_account_balance(account_type)
        logger.info(f"[{tool_name}] Received from bigquery_functions.get_account_balance: {bq_result}")
    
        # Ensure the result aligns with the expected schema for Gemini (status, account_type, balance, currency)
        # bigquery_functions.get_account_balance returns:
        # {"account_type": "checking", "balance": 1250.75, "currency": "USD", "account_id": "acc_chk_krishnan_001"}
        # or an error like: {"status": "ERROR_ACCOUNT_NOT_FOUND", "message": "..."}
        if bq_result.get("status") == "ERROR_ACCOUNT_NOT_FOUND": # Specific error from BQ
             api_response = {"status": "error", "message": bq_result.get("message", f"Account type '{account_type}' not recognized or error fetching details.")}
        elif bq_result.get("status") and "ERROR" in bq_result.get("status"): # Generic BQ error
             api_response = {"status": "error", "message": bq_result.get("message", "An error occurred while fetching account balance.")}
        elif "balance" in bq_result and "currency" in bq_result:
            api_response = {
                "status": "success",
                "account_type": bq_result.get("account_type", account_type),
                "balance": bq_result["balance"],
                "currency": bq_result["currency"],
                # "account_id": bq_result.get("account_id") # Optional, not in original Gemini schema
            }
        else: # Fallback for unexpected BQ result format
            api_response = {"status": "error", "message": "Failed to retrieve account balance in expected format."}
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result for getBalance: {e}", exc_info=True)
        api_response = {"status": "error", "message": f"An internal error occurred while fetching account balance for {account_type}."}

    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response


async def getTransactionHistory(account_type: str, limit: int = 5):
    tool_name = "getTransactionHistory"
    params_sent = {"account_type": account_type, "limit": limit}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.get_transaction_history with account_type: {account_type}, limit: {limit}")
    api_response = {}
    try:
        bq_transactions = bigquery_functions.get_transaction_history(account_type, limit)
        logger.info(f"[{tool_name}] Received from bigquery_functions.get_transaction_history: {bq_transactions}")
        # bq_transactions returns a list of transactions or a list containing an error dict.
        # Example success: [{"transaction_id": ..., "date": ..., "description": ..., "amount": ..., ...}]
        # Example error: [{"status": "ERROR_ACCOUNT_NOT_FOUND", "message": "..."}]
        # Example no_transactions: [{"status": "NO_TRANSACTIONS_FOUND", "message": "..."}]

        if bq_transactions and isinstance(bq_transactions, list) and len(bq_transactions) > 0:
            first_item = bq_transactions[0]
            if isinstance(first_item, dict) and first_item.get("status") and "ERROR" in first_item.get("status"):
                api_response = {"status": "error", "message": first_item.get("message", "Error fetching transaction history.")}
            elif isinstance(first_item, dict) and first_item.get("status") == "NO_TRANSACTIONS_FOUND":
                 api_response = {"status": "success", "account_type": account_type, "transactions": []} # Return empty list for no transactions
            else:
                # Assuming success if no error status, map to expected format if needed
                # The BQ function already returns transactions in a good list format.
                # The original static response had "id" instead of "transaction_id". Let's align.
                formatted_transactions = []
                for t in bq_transactions:
                    formatted_transactions.append({
                        "id": t.get("transaction_id"),
                        "date": t.get("date"),
                        "description": t.get("description"),
                        "amount": t.get("amount"),
                        "currency": t.get("currency")
                        # Add other fields if the Gemini schema expects them (e.g., type, status from BQ)
                    })
                api_response = {"status": "success", "account_type": account_type, "transactions": formatted_transactions}
        elif isinstance(bq_transactions, list) and not bq_transactions: # Empty list means success with no transactions
            api_response = {"status": "success", "account_type": account_type, "transactions": []}
        else:
            api_response = {"status": "error", "message": "Failed to retrieve transaction history in expected format."}
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result for getTransactionHistory: {e}", exc_info=True)
        api_response = {"status": "error", "message": f"An internal error occurred while fetching transaction history for {account_type}."}
    
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response


async def initiateFundTransfer(amount: float, currency: str, from_account_type: str, to_account_type: str):
    tool_name = "initiateFundTransfer"
    params_sent = {"amount": amount, "currency": currency, "from_account_type": from_account_type, "to_account_type": to_account_type}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.initiate_fund_transfer_check with from_account_type: {from_account_type}, to_account_type: {to_account_type}, amount: {amount}")
    api_response = {}
    try:
        # This function in gemini_tools is for initiating, the BQ one is for checking
        check_result = bigquery_functions.initiate_fund_transfer_check(from_account_type, to_account_type, amount)
        logger.info(f"[{tool_name}] Received from bigquery_functions.initiate_fund_transfer_check: {check_result}")
    
        # Expected by Gemini: "status": "requires_confirmation", "message": ..., "transfer_details": {...}
        # BQ check_result:
        # Success: {"status": "SUFFICIENT_FUNDS", "from_account_id": ..., "to_account_id": ..., ...}
        # Error: {"status": "INSUFFICIENT_FUNDS", ...} or {"status": "ERROR_ACCOUNT_NOT_FOUND", ...}

        if check_result.get("status") == "SUFFICIENT_FUNDS":
            api_response = {
                "status": "requires_confirmation",
                "message": f"Please confirm transfer of {amount} {currency} from {from_account_type} (ID: {check_result.get('from_account_id')}) to {to_account_type} (ID: {check_result.get('to_account_id')}).",
                "transfer_details": {
                    "amount": amount,
                    "currency": currency, # Assuming currency matches, BQ check uses from_account's currency
                    "from_account_type": from_account_type,
                    "from_account_id": check_result.get("from_account_id"), # Add ID for execute step
                    "to_account_type": to_account_type,
                    "to_account_id": check_result.get("to_account_id"),     # Add ID for execute step
                    "confirmation_id": f"confirm_{check_result.get('from_account_id')}_{check_result.get('to_account_id')}_{amount}" # More dynamic ID
                }
            }
        else: # INSUFFICIENT_FUNDS, ERROR_ACCOUNT_NOT_FOUND, ERROR_INVALID_AMOUNT etc.
            api_response = {
                "status": "error", # Or a more specific status if Gemini can handle it
                "message": check_result.get("message", "Fund transfer initiation failed.")
                # Potentially add more details from check_result if useful for user feedback
            }
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result for initiateFundTransfer: {e}", exc_info=True)
        api_response = {"status": "error", "message": "An internal error occurred while initiating fund transfer."}
    
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response

async def executeFundTransfer(amount: float, currency: str, from_account_id: str, to_account_id: str, memo: str):
    tool_name = "executeFundTransfer"
    params_sent = {"amount": amount, "currency": currency, "from_account_id": from_account_id, "to_account_id": to_account_id, "memo": memo}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.execute_fund_transfer with from_account_id: {from_account_id}, to_account_id: {to_account_id}, amount: {amount}, currency: {currency}, memo: {memo}")
    api_response = {}
    try:
        # The BQ function `execute_fund_transfer` simulates the transfer and logs.
        bq_result = bigquery_functions.execute_fund_transfer(from_account_id, to_account_id, amount, currency, memo)
        logger.info(f"[{tool_name}] Received from bigquery_functions.execute_fund_transfer: {bq_result}")
        # BQ result: {"status": "SUCCESS", "transaction_id": ..., "message": ...}
        # or error: {"status": "ERROR_CLIENT_NOT_INITIALIZED", ...}
    
        if bq_result.get("status") == "SUCCESS":
            api_response = {
                "status": "success",
                "message": bq_result.get("message", f"Transfer of {amount} {currency} from {from_account_id} to {to_account_id} processed."),
                "transaction_id": bq_result.get("transaction_id", "N/A")
            }
        else:
            api_response = {
                "status": "error",
                "message": bq_result.get("message", "Fund transfer execution failed.")
            }
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result for executeFundTransfer: {e}", exc_info=True)
        api_response = {"status": "error", "message": "An internal error occurred while executing fund transfer."}
    
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response

async def getBillDetails(bill_type: str, payee_nickname: str = None):
    tool_name = "getBillDetails"
    params_sent = {"bill_type": bill_type, "payee_nickname": payee_nickname}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.get_bill_details with bill_type: {bill_type}, payee_nickname: {payee_nickname}")
    api_response = {}
    try:
        bq_result = bigquery_functions.get_bill_details(bill_type, payee_nickname)
        logger.info(f"[{tool_name}] Received from bigquery_functions.get_bill_details: {bq_result}")
        # BQ Success: {"status": "SUCCESS", "payee_id": ..., "payee_name": ..., "due_amount": ..., ...}
        # BQ Error: {"status": "ERROR_BILLER_NOT_FOUND", ...} or {"status": "AMBIGUOUS_BILLER_FOUND", ...}

        if bq_result.get("status") == "SUCCESS":
            api_response = {
                "status": "success",
                "bill_type": bill_type, # Add back as it was in original static response
                "payee_name": bq_result.get("biller_name"), # Changed from payee_name
                "due_amount": bq_result.get("due_amount"),
                "due_date": bq_result.get("due_date"),
                "payee_id": bq_result.get("biller_id") # Changed from payee_id
            }
        elif bq_result.get("status") == "AMBIGUOUS_BILLER_FOUND":
            api_response = { # Pass ambiguity back to Gemini
                "status": "clarification_needed", # Or a custom status Gemini might understand
                "message": bq_result.get("message"),
                "options": bq_result.get("billers") # Provide options if Gemini can use them
            }
        else: # ERROR_BILLER_NOT_FOUND or other errors
            api_response = {
                "status": "error",
                "message": bq_result.get("message", f"Could not retrieve details for bill type '{bill_type}'.")
            }
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result for getBillDetails: {e}", exc_info=True)
        api_response = {"status": "error", "message": f"An internal error occurred while fetching bill details for {bill_type}."}
    
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response

async def resolve_account_by_name(user_id: str, natural_language_name: str) -> dict:
    """Helper function to resolve natural language account name to an account ID."""
    tool_name = "resolve_account_by_name"
    params_sent = {"user_id": user_id, "natural_language_name": natural_language_name}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.find_account_by_natural_language for user {user_id} with name '{natural_language_name}'")
    
    try:
        resolution_result = bigquery_functions.find_account_by_natural_language(user_id, natural_language_name)
        logger.info(f"[{tool_name}] Received from bigquery_functions.find_account_by_natural_language: {resolution_result}")
        
        # Directly return the result from BQ function as it already has status, message, account_id etc.
        _log_tool_event("INVOCATION_END", tool_name, params_sent, resolution_result)
        return resolution_result
        
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result: {e}", exc_info=True)
        error_response = {"status": "error", "message": f"An internal error occurred while resolving account name: {str(e)}"}
        _log_tool_event("INVOCATION_END", tool_name, params_sent, error_response)
        return error_response

async def resolve_biller_by_name(user_id: str, biller_name: str) -> dict:
    """Helper function to resolve biller name to a biller ID."""
    tool_name = "resolve_biller_by_name"
    params_sent = {"user_id": user_id, "biller_name": biller_name}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to find biller by name for user {user_id} with name '{biller_name}'")
    
    try:
        # Get list of all billers for the user
        all_billers_result = bigquery_functions.list_registered_billers(user_id)
        logger.info(f"[{tool_name}] Retrieved billers: {all_billers_result}")
        
        if all_billers_result.get("status") != "SUCCESS" or not all_billers_result.get("billers"):
            error_response = {
                "status": "ERROR_NO_BILLERS_FOUND", 
                "message": f"No billers found for user {user_id}"
            }
            _log_tool_event("INVOCATION_END", tool_name, params_sent, error_response)
            return error_response
        
        # Lowercase the input for case-insensitive comparison
        biller_name_lower = biller_name.lower()
        
        # First try exact match on biller_name or biller_nickname
        exact_matches = []
        partial_matches = []
        
        for biller in all_billers_result["billers"]:
            # Check for exact matches
            if (biller.get("biller_name", "").lower() == biller_name_lower or 
                    biller.get("payee_nickname", "").lower() == biller_name_lower):
                exact_matches.append(biller)
            
            # Check for partial matches
            elif (biller_name_lower in biller.get("biller_name", "").lower() or
                  (biller.get("payee_nickname") and biller_name_lower in biller.get("payee_nickname", "").lower())):
                partial_matches.append(biller)
        
        # Return the first exact match if found
        if exact_matches:
            if len(exact_matches) == 1:
                biller = exact_matches[0]
                result = {
                    "status": "SUCCESS",
                    "biller_id": biller["biller_id"],
                    "biller_name": biller["biller_name"]
                }
                _log_tool_event("INVOCATION_END", tool_name, params_sent, result)
                return result
            else:
                # Multiple exact matches, return ambiguity error
                ambiguous_options = [{"biller_id": b["biller_id"], "biller_name": b["biller_name"]} for b in exact_matches]
                error_response = {
                    "status": "ERROR_AMBIGUOUS_BILLER",
                    "message": f"Multiple billers match '{biller_name}'. Please specify which one.",
                    "options": ambiguous_options
                }
                _log_tool_event("INVOCATION_END", tool_name, params_sent, error_response)
                return error_response
        
        # If no exact match, try partial matches
        if partial_matches:
            if len(partial_matches) == 1:
                biller = partial_matches[0]
                result = {
                    "status": "SUCCESS",
                    "biller_id": biller["biller_id"],
                    "biller_name": biller["biller_name"]
                }
                _log_tool_event("INVOCATION_END", tool_name, params_sent, result)
                return result
            else:
                # Multiple partial matches, return ambiguity error
                ambiguous_options = [{"biller_id": b["biller_id"], "biller_name": b["biller_name"]} for b in partial_matches]
                error_response = {
                    "status": "ERROR_AMBIGUOUS_BILLER",
                    "message": f"Multiple billers contain '{biller_name}'. Please specify which one.",
                    "options": ambiguous_options
                }
                _log_tool_event("INVOCATION_END", tool_name, params_sent, error_response)
                return error_response
        
        # No matches found
        error_response = {
            "status": "ERROR_BILLER_NOT_FOUND",
            "message": f"No biller matching '{biller_name}' found for user {user_id}"
        }
        _log_tool_event("INVOCATION_END", tool_name, params_sent, error_response)
        return error_response
        
    except Exception as e:
        logger.error(f"[{tool_name}] Error while resolving biller name: {e}", exc_info=True)
        error_response = {"status": "error", "message": f"An internal error occurred while resolving biller name: {str(e)}"}
        _log_tool_event("INVOCATION_END", tool_name, params_sent, error_response)
        return error_response

async def payBill(payee_id: str, amount: float, from_account_id: str):
    tool_name = "payBill"
    original_from_account_id_param = from_account_id # Keep original for logging
    original_payee_id_param = payee_id # Keep original payee_id for logging
    params_sent = {"payee_id": original_payee_id_param, "amount": amount, "from_account_id": original_from_account_id_param}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    
    resolved_from_account_id = from_account_id
    resolved_payee_id = payee_id
    
    # Attempt to resolve if from_account_id doesn't look like a direct ID
    if not from_account_id.startswith("acc_"):
        logger.info(f"[{tool_name}] '{from_account_id}' doesn't look like a direct account ID. Attempting natural language resolution for user {USER_ID}.")
        resolution_result = await resolve_account_by_name(USER_ID, from_account_id)
        
        if resolution_result.get("status") == "SUCCESS":
            resolved_from_account_id = resolution_result["account_id"]
            logger.info(f"[{tool_name}] Natural language resolved '{from_account_id}' to account ID '{resolved_from_account_id}'.")
        else:
            # If resolution fails (not found, ambiguous, error), return the error message from resolution
            logger.error(f"[{tool_name}] Failed to resolve natural language account '{from_account_id}': {resolution_result.get('message')}")
            _log_tool_event("INVOCATION_END", tool_name, params_sent, resolution_result) # Log with original params
            return resolution_result # Return the error from resolver
    
    # Attempt to resolve if payee_id doesn't look like a direct biller ID
    if not payee_id.startswith("biller_"):
        logger.info(f"[{tool_name}] '{payee_id}' doesn't look like a direct biller ID. Attempting biller name resolution for user {USER_ID}.")
        biller_resolution_result = await resolve_biller_by_name(USER_ID, payee_id)
        
        if biller_resolution_result.get("status") == "SUCCESS":
            resolved_payee_id = biller_resolution_result["biller_id"]
            logger.info(f"[{tool_name}] Resolved biller name '{payee_id}' to biller ID '{resolved_payee_id}'.")
        else:
            # If resolution fails, return the error message from resolution
            logger.error(f"[{tool_name}] Failed to resolve biller name '{payee_id}': {biller_resolution_result.get('message')}")
            _log_tool_event("INVOCATION_END", tool_name, params_sent, biller_resolution_result) # Log with original params
            return biller_resolution_result # Return the error from resolver

    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.pay_bill with payee_id: {resolved_payee_id}, amount: {amount}, resolved_from_account_id: {resolved_from_account_id}")
    api_response = {}
    try:
        bq_result = bigquery_functions.pay_bill(resolved_payee_id, amount, resolved_from_account_id)
        logger.info(f"[{tool_name}] Received from bigquery_functions.pay_bill: {bq_result}")
        # BQ Success: {"status": "SUCCESS", "confirmation_number": ..., "message": ...}
        # BQ Error: {"status": "INSUFFICIENT_FUNDS", ...} or {"status": "ERROR_PAYEE_NOT_FOUND", ...}

        if bq_result.get("status") == "SUCCESS":
            api_response = {
                "status": "success",
                "message": bq_result.get("message", f"Bill payment to {payee_id} processed."),
                "payment_confirmation_id": bq_result.get("confirmation_number", "N/A")
            }
        else:
            api_response = { # Pass through BQ error
                "status": "error", # Ensure it's marked as error
                "message": bq_result.get("message", "Bill payment failed.")
            }
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result for payBill: {e}", exc_info=True)
        api_response = {"status": "error", "message": "An internal error occurred while processing bill payment."}

    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response) # Log with original params
    return api_response

async def registerBiller(biller_name: str, biller_type: str, account_number: str, payee_nickname: str = None, default_payment_account_id: str = None, due_amount: float = None, due_date: str = None):
    tool_name = "registerBiller"
    params_sent = {
        "biller_name": biller_name, "biller_type": biller_type, "account_number": account_number,
        "payee_nickname": payee_nickname, "default_payment_account_id": default_payment_account_id,
        "due_amount": due_amount, "due_date": due_date
    }
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.register_biller for user {USER_ID}")
    api_response = {}
    try:
        bq_result = bigquery_functions.register_biller(
            user_id=USER_ID, # Using the imported USER_ID
            biller_name=biller_name,
            biller_type=biller_type,
            account_number=account_number,
            payee_nickname=payee_nickname,
            default_payment_account_id=default_payment_account_id,
            due_amount=due_amount,
            due_date=due_date
        )
        logger.info(f"[{tool_name}] Received from bigquery_functions.register_biller: {bq_result}")
        # bq_result: {"status": "SUCCESS", "message": ..., "payee_id": ...} or error
        api_response = bq_result # Pass through BQ result directly
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result: {e}", exc_info=True)
        api_response = {"status": "error", "message": f"An internal error occurred: {str(e)}"}
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response

async def updateBillerDetails(payee_id: str, updates: dict):
    tool_name = "updateBillerDetails"
    params_sent = {"payee_id": payee_id, "updates": updates}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.update_biller_details for user {USER_ID}, payee_id {payee_id}")
    api_response = {}
    try:
        bq_result = bigquery_functions.update_biller_details(
            user_id=USER_ID, # Using the imported USER_ID
            payee_id=payee_id,
            updates=updates
        )
        logger.info(f"[{tool_name}] Received from bigquery_functions.update_biller_details: {bq_result}")
        api_response = bq_result
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result: {e}", exc_info=True)
        api_response = {"status": "error", "message": f"An internal error occurred: {str(e)}"}
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response

async def removeBiller(payee_id: str):
    tool_name = "removeBiller"
    params_sent = {"payee_id": payee_id}
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.remove_biller for user {USER_ID}, payee_id {payee_id}")
    api_response = {}
    try:
        bq_result = bigquery_functions.remove_biller(
            user_id=USER_ID, # Using the imported USER_ID
            payee_id=payee_id
        )
        logger.info(f"[{tool_name}] Received from bigquery_functions.remove_biller: {bq_result}")
        api_response = bq_result
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result: {e}", exc_info=True)
        api_response = {"status": "error", "message": f"An internal error occurred: {str(e)}"}
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response

async def listRegisteredBillers():
    tool_name = "listRegisteredBillers"
    params_sent = {} # Status removed
    _log_tool_event("INVOCATION_START", tool_name, params_sent)
    logger.info(f"[{tool_name}] Attempting to call bigquery_functions.list_registered_billers for user {USER_ID}") # Status removed from log
    api_response = {}
    try:
        bq_result = bigquery_functions.list_registered_billers(
            user_id=USER_ID # Using the imported USER_ID
            # status parameter removed from BQ call
        )
        logger.info(f"[{tool_name}] Received from bigquery_functions.list_registered_billers: {bq_result}")
        # Expected: {"status": "SUCCESS", "billers": [...]} or error
        if bq_result.get("status") == "SUCCESS":
            api_response = {
                "status": "success",
                "billers": bq_result.get("billers", [])
            }
        elif bq_result.get("status") == "NO_BILLERS_FOUND":
             api_response = {
                "status": "success", # Still a success, just no data
                "message": bq_result.get("message", "No billers found matching criteria."),
                "billers": []
            }
        else: # Error cases
            api_response = {
                "status": "error",
                "message": bq_result.get("message", "Failed to list billers."),
                "billers": []
            }
    except Exception as e:
        logger.error(f"[{tool_name}] Error calling BQ or processing result: {e}", exc_info=True)
        api_response = {"status": "error", "message": f"An internal error occurred: {str(e)}", "billers": []}
    _log_tool_event("INVOCATION_END", tool_name, params_sent, api_response)
    return api_response

# Tool instance containing all function declarations
banking_tool = types.Tool(
    function_declarations=[
        getBalance_declaration,
        getTransactionHistory_declaration,
        initiateFundTransfer_declaration,
        executeFundTransfer_declaration,
        getBillDetails_declaration,
        payBill_declaration,
        registerBiller_declaration,
        updateBillerDetails_declaration,
        removeBiller_declaration,
        listRegisteredBillers_declaration,
    ]
)

# Example of how you might want to export or use this tool
# (This part is for demonstration and might need adjustment based on your project structure)
#
# available_tools = {
# "banking_tool": banking_tool
# }
#
# if __name__ == "__main__":
# # You can print the tool to see its structure
#     import json
#     print(json.dumps(banking_tool.to_dict(), indent=2))