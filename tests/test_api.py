import pytest
from fastapi.testclient import TestClient

from ledger import api
from ledger.service import Ledger
from ledger.models import CASH_ACCOUNT_ID


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "ledger", Ledger())
    with TestClient(api.app) as client:
        yield client


def account(client, opening="0.00"):
    response = client.post("/accounts", json={})
    assert response.status_code == 201
    account_id = response.json()["id"]
    if opening != "0.00":
        assert client.post(f"/accounts/{account_id}/transactions", json={
            "to_account": account_id, "amount": opening,
        }).status_code == 201
    return account_id


def balance(client, account_id):
    return client.get(f"/accounts/{account_id}/balance").json()["balance"]


def history(client, account_id):
    return client.get(f"/accounts/{account_id}/transactions").json()


def missing_account(client):
    for value in range(1, 0x10000):
        candidate = f"{value:04x}"
        if client.get(f"/accounts/{candidate}").status_code == 404:
            return candidate
    pytest.fail("Expected an unused account ID")


def transfer(client, source, destination, amount="1.00", path_account=None):
    return client.post(f"/accounts/{path_account or source}/transactions", json={
        "from_account": source, "to_account": destination, "amount": amount,
    })


def test_account_creation(client):
    response = client.post("/accounts", json={})
    assert response.status_code == 201
    data = response.json()
    assert data["balance"] == "0.00"
    assert client.get(f"/accounts/{data['id']}").json() == data
    assert history(client, data["id"]) == []
    other = account(client, "10")
    assert other != data["id"]
    assert balance(client, other) == "10.00"


def test_transfers_and_account_history(client):
    source, destination, unrelated = account(client, "10.10"), account(client), account(client)
    first = transfer(client, source, destination, "0.20")
    assert first.status_code == 201
    transaction = first.json()
    assert transaction["entries"][0]["balance_after"] == "9.90"
    assert transaction["entries"][1]["balance_after"] == "0.20"
    assert transaction["from_account"] == source
    assert transaction["to_account"] == destination
    assert transaction["created_at"].endswith("Z")
    assert balance(client, source) == "9.90"
    assert balance(client, destination) == "0.20"
    second = transfer(client, source, destination, "9.90")
    assert second.status_code == 201
    assert balance(client, source) == "0.00"
    assert balance(client, destination) == "10.10"
    debit, credit = transaction["entries"]
    assert debit["id"] != credit["id"]
    assert debit["transaction_id"] == credit["transaction_id"] == transaction["id"]
    assert debit["direction"] == "debit"
    assert credit["direction"] == "credit"
    assert debit["amount"] == credit["amount"] == "0.20"
    assert debit["account_id"] == source
    assert credit["account_id"] == destination
    assert history(client, source)[1:] == [debit, second.json()["entries"][0]]
    assert history(client, destination) == [credit, second.json()["entries"][1]]
    assert history(client, unrelated) == []
    assert client.get(f"/accounts/{destination}/transactions?offset=1&limit=1").json() == [second.json()["entries"][1]]
    assert transfer(client, destination, source, "10.10").status_code == 201
    assert balance(client, source) == "10.10"


def test_failed_transfers_leave_all_state_unchanged(client):
    source, destination = account(client, "5"), account(client)
    before = history(client, source)
    assert transfer(client, source, destination, "5.01").status_code == 409
    assert transfer(client, source, source).status_code == 422
    assert transfer(client, source, destination, path_account=destination).status_code == 422
    unknown = missing_account(client)
    assert transfer(client, source, unknown).status_code == 404
    assert transfer(client, unknown, destination).status_code == 404
    assert balance(client, source) == "5.00"
    assert balance(client, destination) == "0.00"
    assert history(client, source) == before
    assert history(client, destination) == []


@pytest.mark.parametrize("amount", ["0", "0.00", "-1", "1.001", "NaN", "Infinity",
                                   "1e2", "", "1000000000000", 1.2, True, None])
def test_invalid_transfer_amounts(client, amount):
    source, destination = account(client, "5"), account(client)
    assert transfer(client, source, destination, amount).status_code == 422
    assert balance(client, source) == "5.00"
    assert balance(client, destination) == "0.00"
    assert len(history(client, source)) == 1
    assert history(client, destination) == []


@pytest.mark.parametrize("amount", ["-1", "1.001", "NaN", "Infinity", 1.2, True, None])
def test_opening_balance_is_not_supported(client, amount):
    assert client.post("/accounts", json={"opening_balance": amount}).status_code == 422


@pytest.mark.parametrize("payload", [{}, {"amount": "1"},
                                      {"type": "deposit", "amount": "1"},
                                      {"from_account": "bad", "to_account": "bad", "amount": "1"}])
def test_invalid_bodies(client, payload):
    source = account(client)
    assert client.post(f"/accounts/{source}/transactions", json=payload).status_code == 422


@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=1001", "limit=abc"])
def test_invalid_pagination(client, query):
    source = account(client)
    assert client.get(f"/accounts/{source}/transactions?{query}").status_code == 422


@pytest.mark.parametrize("suffix", ["", "/balance", "/transactions"])
def test_unknown_accounts(client, suffix):
    assert client.get(f"/accounts/{missing_account(client)}{suffix}").status_code == 404
    assert client.get(f"/accounts/not-an-id{suffix}").status_code == 422


def test_new_ledger_has_fresh_state(client, monkeypatch):
    source = account(client, "1")
    monkeypatch.setattr(api, "ledger", Ledger())
    with TestClient(api.app) as fresh:
        assert fresh.get(f"/accounts/{source}/balance").status_code == 404


def test_global_balance_and_transaction_creation_are_not_available(client):
    assert client.get("/balance").status_code == 404
    assert client.get("/transactions").json() == []
    assert client.post("/transactions", json={"type": "deposit", "amount": "1"}).status_code == 405


def test_cash_movements_have_balanced_entries(client):
    customer = account(client)
    cash = str(CASH_ACCOUNT_ID)
    deposit = client.post(f"/accounts/{customer}/transactions", json={
        "to_account": customer, "amount": "100.00",
    })
    assert deposit.status_code == 201
    assert deposit.json()["type"] == "deposit"
    assert deposit.json()["from_account"] == cash
    assert balance(client, cash) == "-100.00"
    withdrawal = client.post(f"/accounts/{customer}/transactions", json={
        "from_account": customer, "amount": "25.50",
    })
    assert withdrawal.status_code == 201
    assert withdrawal.json()["type"] == "withdrawal"
    assert balance(client, customer) == "74.50"
    assert balance(client, cash) == "-74.50"
    assert history(client, customer) == [deposit.json()["entries"][1], withdrawal.json()["entries"][0]]
    assert history(client, cash) == [deposit.json()["entries"][0], withdrawal.json()["entries"][1]]
    for response in (deposit, withdrawal):
        debit, credit = response.json()["entries"]
        assert debit["direction"] == "debit"
        assert credit["direction"] == "credit"
        assert debit["amount"] == credit["amount"]
        assert debit["transaction_id"] == credit["transaction_id"] == response.json()["id"]
    before = history(client, customer), history(client, cash)
    assert client.post(f"/accounts/{customer}/transactions", json={
        "from_account": customer, "amount": "100",
    }).status_code == 409
    assert (history(client, customer), history(client, cash)) == before
    assert balance(client, customer) == "74.50"


def test_reserved_cash_account_cannot_be_used_explicitly(client):
    customer = account(client)
    assert transfer(client, str(CASH_ACCOUNT_ID), customer).status_code == 422
    assert transfer(client, customer, str(CASH_ACCOUNT_ID)).status_code == 422


def test_deposit_path_must_match_recipient(client):
    first, second = account(client), account(client)
    assert client.post(f"/accounts/{first}/transactions", json={
        "to_account": second, "amount": "10",
    }).status_code == 422
    assert balance(client, first) == balance(client, second) == "0.00"


def test_short_ids_are_unique_across_accounts_transactions_and_entries(client):
    import re

    first, second = account(client), account(client)
    identifiers = {CASH_ACCOUNT_ID, first, second}
    for _ in range(20):
        response = client.post(f"/accounts/{first}/transactions", json={
            "to_account": first, "amount": "1.00",
        })
        assert response.status_code == 201
        transaction = response.json()
        new_ids = [transaction["id"], *(entry["id"] for entry in transaction["entries"])]
        assert len(set(new_ids)) == 3
        assert not identifiers.intersection(new_ids)
        identifiers.update(new_ids)
    assert all(re.fullmatch(r"[0-9a-f]{4}", value) for value in identifiers)
    assert balance(client, first) == "20.00"


@pytest.mark.parametrize("invalid_id", ["abc", "abcde", "gggg", "ABCD", "12345678-1234-1234-1234-123456789abc"])
def test_invalid_id_format(client, invalid_id):
    assert client.get(f"/accounts/{invalid_id}/balance").status_code == 422
    customer = account(client)
    assert transfer(client, customer, invalid_id).status_code == 422


def test_list_accounts_includes_current_balances_and_cash(client):
    assert client.get("/accounts").json() == [
        {"id": CASH_ACCOUNT_ID, "kind": "cash_clearing", "balance": "0.00"},
    ]
    first, second = account(client, "10"), account(client)
    transfer(client, first, second, "2.50")
    accounts = client.get("/accounts").json()
    assert [item["id"] for item in accounts] == [CASH_ACCOUNT_ID, first, second]
    assert [item["balance"] for item in accounts] == ["-10.00", "7.50", "2.50"]
    assert client.get("/accounts?offset=1&limit=1").json() == [accounts[1]]
    assert client.get("/accounts?offset=3").json() == []


def test_list_transactions_returns_each_movement_once(client):
    assert client.get("/transactions").json() == []
    first, second = account(client), account(client)
    deposit = client.post(f"/accounts/{first}/transactions", json={
        "to_account": first, "amount": "10",
    }).json()
    movement = transfer(client, first, second, "2.50").json()
    withdrawal = client.post(f"/accounts/{second}/transactions", json={
        "from_account": second, "amount": "1",
    }).json()
    assert transfer(client, first, second, "100").status_code == 409
    transactions = client.get("/transactions").json()
    assert transactions == [deposit, movement, withdrawal]
    assert len({item["id"] for item in transactions}) == 3
    assert all(len(item["entries"]) == 2 for item in transactions)
    assert client.get("/transactions?offset=1&limit=1").json() == [movement]
    assert client.get("/transactions?offset=3").json() == []


@pytest.mark.parametrize("endpoint", ["/accounts", "/transactions"])
@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=1001", "limit=abc"])
def test_listing_pagination_validation(client, endpoint, query):
    assert client.get(f"{endpoint}?{query}").status_code == 422
