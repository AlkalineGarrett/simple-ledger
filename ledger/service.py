"""In-memory ledger state and operations, independent of HTTP."""

from datetime import datetime, timezone
from random import shuffle

from ledger.models import (
    CASH_ACCOUNT_ID, Account, Balance, Entry, Transaction, CreateTransactionRequest,
    format_money, to_cents,
)


class LedgerError(Exception):
    pass


class AccountNotFound(LedgerError):
    pass


class InvalidTransaction(LedgerError):
    pass


class InsufficientFunds(LedgerError):
    pass


class IdSpaceExhausted(LedgerError):
    pass


class Ledger:
    def __init__(self) -> None:
        self._balances: dict[str, int] = {CASH_ACCOUNT_ID: 0}
        self._histories: dict[str, list[Entry]] = {CASH_ACCOUNT_ID: []}
        self._transactions: list[Transaction] = []
        self._available_ids = list(range(1, 0x10000))
        shuffle(self._available_ids)

    def _allocate_ids(self, count: int) -> list[str]:
        if count > len(self._available_ids):
            raise IdSpaceExhausted("ID space exhausted; restart the toy ledger")
        return [f"{self._available_ids.pop():04x}" for _ in range(count)]

    def _require_account(self, account_id: str) -> None:
        if account_id not in self._balances:
            raise AccountNotFound("Account not found")

    def create_account(self) -> Account:
        account_id, = self._allocate_ids(1)
        self._balances[account_id] = 0
        self._histories[account_id] = []
        return Account(id=account_id, kind="customer", balance="0.00")

    def get_account(self, account_id: str) -> Account:
        self._require_account(account_id)
        return Account(id=account_id,
                       kind="cash_clearing" if account_id == CASH_ACCOUNT_ID else "customer",
                       balance=format_money(self._balances[account_id]))

    def get_balance(self, account_id: str) -> Balance:
        self._require_account(account_id)
        return Balance(balance=format_money(self._balances[account_id]))

    def get_accounts(self, offset: int = 0, limit: int = 100) -> list[Account]:
        account_ids = list(self._balances)[offset:offset + limit]
        return [self.get_account(account_id) for account_id in account_ids]

    def get_transactions(self, offset: int = 0, limit: int = 100) -> list[Transaction]:
        return self._transactions[offset:offset + limit]

    def record_transaction(self, account_id: str, movement: CreateTransactionRequest) -> Transaction:
        self._require_account(account_id)
        source = movement.from_account or CASH_ACCOUNT_ID
        destination = movement.to_account or CASH_ACCOUNT_ID
        self._require_account(source)
        self._require_account(destination)

        expected_path = destination if movement.from_account is None else source
        if account_id != expected_path:
            raise InvalidTransaction("Path must match source, or recipient for cash deposits")

        cents = to_cents(movement.amount)
        if source != CASH_ACCOUNT_ID and cents > self._balances[source]:
            raise InsufficientFunds("Insufficient funds")

        transaction_id, debit_id, credit_id = self._allocate_ids(3)
        now = datetime.now(timezone.utc)
        debit = Entry(id=debit_id, transaction_id=transaction_id, account_id=source,
                      direction="debit", amount=format_money(cents),
                      balance_after=format_money(self._balances[source] - cents), created_at=now)
        credit = Entry(id=credit_id, transaction_id=transaction_id, account_id=destination,
                       direction="credit", amount=format_money(cents),
                       balance_after=format_money(self._balances[destination] + cents), created_at=now)

        transaction = Transaction(
            id=transaction_id,
            type="deposit" if movement.from_account is None else
                 "withdrawal" if movement.to_account is None else "transfer",
            from_account=source, to_account=destination,
            amount=format_money(cents), created_at=now, entries=(debit, credit),
        )

        self._balances[source] -= cents
        self._balances[destination] += cents
        self._histories[source].append(debit)
        self._histories[destination].append(credit)
        self._transactions.append(transaction)
        
        return transaction

    def get_history(self, account_id: str, offset: int = 0, limit: int = 100) -> list[Entry]:
        self._require_account(account_id)
        return self._histories[account_id][offset:offset + limit]
