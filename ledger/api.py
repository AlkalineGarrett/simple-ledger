from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from ledger.models import Account, CreateAccountRequest, Balance, Entry, Identifier, Transaction, CreateTransactionRequest
from ledger.service import (
    AccountNotFound, IdSpaceExhausted, InsufficientFunds, InvalidTransaction,
    Ledger, LedgerError,
)


app = FastAPI(title="Simple Ledger", version="3.0.0", docs_url=None, redoc_url=None)
ledger = Ledger()


@app.exception_handler(LedgerError)
async def handle_ledger_error(request: Request, error: LedgerError) -> JSONResponse:
    status_codes = {
        AccountNotFound: 404,
        InvalidTransaction: 422,
        InsufficientFunds: 409,
        IdSpaceExhausted: 409,
    }
    return JSONResponse(status_code=status_codes[type(error)], content={"detail": str(error)})


@app.post("/accounts", response_model=Account, status_code=201)
async def create_account(account: CreateAccountRequest) -> Account:
    return ledger.create_account()


@app.get("/accounts/{account_id}", response_model=Account)
async def get_account(account_id: Identifier) -> Account:
    return ledger.get_account(account_id)


@app.get("/accounts", response_model=list[Account])
async def get_accounts(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Account]:
    """List accounts in creation order, including cash clearing."""
    return ledger.get_accounts(offset, limit)


@app.get("/transactions", response_model=list[Transaction])
async def get_transactions(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Transaction]:
    """List ledger transactions once each, oldest first, with both entries."""
    return ledger.get_transactions(offset, limit)


@app.get("/accounts/{account_id}/balance", response_model=Balance)
async def get_balance(account_id: Identifier) -> Balance:
    return ledger.get_balance(account_id)


@app.post(
    "/accounts/{account_id}/transactions", response_model=Transaction, status_code=201,
    responses={404: {"description": "Account not found"},
               409: {"description": "Insufficient funds"}},
)
async def record_transaction(account_id: Identifier, movement: CreateTransactionRequest) -> Transaction:
    return ledger.record_transaction(account_id, movement)


@app.get("/accounts/{account_id}/transactions", response_model=list[Entry])
async def get_history(
    account_id: Identifier,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Entry]:
    """Return this account's transaction entries, oldest first."""
    return ledger.get_history(account_id, offset, limit)
