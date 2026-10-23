# Simple ledger API

Python 3.9+ / FastAPI, in-memory accounts, and a standard-library CLI client.

by Garrett Jones, Oct 2026

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m ledger
```

The default address is `http://127.0.0.1:8000`. Override it with
`python -m ledger --host 127.0.0.1 --port 9000`.

In another terminal, activate the environment and create two accounts:

```sh
source .venv/bin/activate
python -m ledger.cli create-account
python -m ledger.cli create-account
```

Replace `SOURCE_ID` and `DESTINATION_ID` below with the returned four-character hex IDs:

```sh
# Cash deposit
python -m ledger.cli transaction 100.00 --from-cash --to-account SOURCE_ID
# Transfer
python -m ledger.cli transaction 25.50 --from-account SOURCE_ID --to-account DESTINATION_ID
# Cash withdrawal
python -m ledger.cli transaction 5.00 --from-account DESTINATION_ID --to-cash
python -m ledger.cli balance SOURCE_ID
python -m ledger.cli balance DESTINATION_ID
python -m ledger.cli history SOURCE_ID
python -m ledger.cli history DESTINATION_ID --offset 0 --limit 10
python -m ledger.cli accounts
python -m ledger.cli transactions
```

Use `--url http://127.0.0.1:9000` before the subcommand to target another server.

Transactions require one source (`--from-account ID` or `--from-cash`) and one
destination (`--to-account ID` or `--to-cash`). Cash-to-cash movements are rejected.
The CLI infers the URL account ID and sends `null` for the cash side in the API
request.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/accounts` | Create a zero-balance customer account; body `{}` (201) |
| GET | `/accounts?offset=0&limit=100` | All accounts, including cash clearing, in creation order (200) |
| GET | `/transactions?offset=0&limit=100` | All ledger transactions once each, with both entries, oldest first (200) |
| GET | `/accounts/{id}` | Account ID, kind, and current balance (200) |
| GET | `/accounts/{id}/balance` | Current balance (200) |
| POST | `/accounts/{id}/transactions` | Record any money movement (201) |
| GET | `/accounts/{id}/transactions?offset=0&limit=100` | This account's entries, oldest first (200) |
| GET | `/openapi.json` | Machine-readable API schema |

All movements use one transaction request model and one endpoint. Amounts are
positive decimal **strings**, with at most 12 integer digits and two decimal
places. Responses use two decimal places. Storage uses integer cents. All
accounts use the same currency with two decimal places.

A transfer requires both customer account IDs; the path must match `from_account`:

```json
{"from_account": "SOURCE_ID", "to_account": "DESTINATION_ID", "amount": "25.50"}
```

For a cash deposit, omit `from_account` and use the recipient ID in the path:

```json
{"to_account": "DESTINATION_ID", "amount": "100.00"}
```

For a cash withdrawal, omit `to_account` and use the source ID in the path:

```json
{"from_account": "SOURCE_ID", "amount": "5.00"}
```

Explicit `null` has the same meaning as omission. At least one customer account
must be specified. These requests record completed movements; they do not initiate
external cash handling or bank payments. Accounts start at zero. Funding is recorded through transactions.

All account, transaction, and entry IDs are four lowercase hexadecimal characters
(e.g. `a3f1`, `09bc`). IDs are randomly drawn without replacement from one shared namespace;
`0000` is reserved for cash clearing. IDs are never reused while the server runs.
When all 65,535 available IDs are consumed, creation returns 409 without changing
balances or histories. Restarting resets the in-memory ledger and reshuffles the ID pool.

## Transactions and entries

Each successful request returns one transaction containing:

- `id`, `type` (`deposit`, `withdrawal`, or `transfer`), and `created_at` (UTC).
- Resolved `from_account`, `to_account`, and `amount`.
- Exactly two immutable `entries`: a source debit and a destination credit.

Each entry has a distinct `id`, the shared `transaction_id`, its `account_id`,
`direction`, positive `amount`, `balance_after`, and `created_at`. Account history
returns only entries belonging to that account. A transfer therefore appears as
a debit in the source history and a separate credit in the destination history,
linked by the transaction ID. The response's `entries` contains both sides.

This simplified ledger uses signed balance postings: debits subtract and credits
add. Every transaction has equal debit and credit amounts, so its postings sum to
zero. This is a balanced movement ledger, without asset/liability account types
or account-specific normal balance rules of a full general ledger.

Cash movements use the system cash clearing account
`0000` as their counterpart. Its balance and history
can be read through the same account endpoints. It tracks the opposite of net
customer funding and can be negative; it is not a physical cash inventory.
Clients must omit the external side rather than explicitly pass this system ID.
Customer balances cannot go negative.

Unknown accounts return 404. Insufficient funds return 409. Invalid amounts,
self-transfers, missing both accounts, explicit system IDs, and path mismatches
return 422. Rejected requests leave balances and histories unchanged. Repeated
successful requests create separate transactions (no idempotency).

History defaults to 100 entries, with a maximum of 1000; increase `offset` for
subsequent pages. All data is stored in dictionaries and lists in one process.
Account and ledger transaction listings use the same pagination defaults and bounds.
Restarting clears it. Run one worker, since workers have independent state.
There is no persistence, authentication, monitoring, transaction coordination,
or application UI.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover balanced entries, account histories, cash movements, transfers,
precision, pagination, invalid requests, overdrafts, and application isolation.
