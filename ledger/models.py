from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


Money = Annotated[str, Field(
    pattern=r"^[0-9]{1,12}(\.[0-9]{1,2})?$",
    description="Positive decimal string, up to 12 integer digits and 2 decimal places.",
    examples=["25.50"],
)]
Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{4}$")]
CASH_ACCOUNT_ID = "0000"


def to_cents(value: str) -> int:
    whole, _, fraction = value.partition(".")
    return int(whole) * 100 + int(fraction.ljust(2, "0"))


def positive_amount(value: str) -> str:
    if to_cents(value) == 0:
        raise ValueError("Amount must be greater than zero")
    return value


PositiveMoney = Annotated[Money, AfterValidator(positive_amount)]


def format_money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


class CreateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Account(BaseModel):
    id: Identifier
    kind: Literal["customer", "cash_clearing"]
    balance: str


class CreateTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_account: Optional[Identifier] = None
    to_account: Optional[Identifier] = None
    amount: PositiveMoney

    @model_validator(mode="after")
    def validate_accounts(self):
        if self.from_account is None and self.to_account is None:
            raise ValueError("At least one customer account is required")
        if self.from_account == self.to_account:
            raise ValueError("Accounts must be different")
        if CASH_ACCOUNT_ID in (self.from_account, self.to_account):
            raise ValueError("Omit the external side for cash movements")
        return self


class Entry(BaseModel):
    """Signed balance postings: debits decrease, credits increase account balances."""
    model_config = ConfigDict(frozen=True)

    id: Identifier
    transaction_id: Identifier
    account_id: Identifier
    direction: Literal["debit", "credit"]
    amount: str
    balance_after: str
    created_at: datetime


class Transaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: Identifier
    type: Literal["deposit", "withdrawal", "transfer"]
    from_account: Identifier
    to_account: Identifier
    amount: str
    created_at: datetime
    entries: tuple[Entry, Entry]


class Balance(BaseModel):
    balance: str

