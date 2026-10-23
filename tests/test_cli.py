import io
import json
import sys

import pytest

from ledger import cli


@pytest.mark.parametrize("flags, source, destination, path_account", [
    (["--from-cash", "--to-account", "recipient"], None, "recipient", "recipient"),
    (["--from-account", "sender", "--to-cash"], "sender", None, "sender"),
    (["--from-account", "sender", "--to-account", "recipient"], "sender", "recipient", "sender"),
])
def test_transaction_routes_and_payload(monkeypatch, flags, source, destination, path_account):
    monkeypatch.setattr(sys, "argv", ["ledger.cli", "transaction", "10.50", *flags])
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(cli, "urlopen", urlopen)
    assert cli.main() == 0
    assert len(requests) == 1
    assert requests[0].full_url == f"http://127.0.0.1:8000/accounts/{path_account}/transactions"
    assert json.loads(requests[0].data) == {
        "from_account": source, "to_account": destination, "amount": "10.50",
    }


@pytest.mark.parametrize("flags", [
    [],
    ["--to-account", "recipient"],
    ["--from-account", "sender"],
    ["--from-cash", "--to-cash"],
    ["--from-account", "sender", "--from-cash", "--to-account", "recipient"],
    ["--from-account", "sender", "--to-account", "recipient", "--to-cash"],
])
def test_invalid_sides_fail_before_http(monkeypatch, flags):
    monkeypatch.setattr(sys, "argv", ["ledger.cli", "transaction", "10.50", *flags])

    def unexpected_request(*args, **kwargs):
        pytest.fail("Invalid CLI input must not send a request")

    monkeypatch.setattr(cli, "urlopen", unexpected_request)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


@pytest.mark.parametrize("command, endpoint", [("accounts", "/accounts"), ("transactions", "/transactions")])
def test_listing_commands(monkeypatch, command, endpoint):
    monkeypatch.setattr(sys, "argv", ["ledger.cli", command, "--offset", "2", "--limit", "10"])
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        return io.BytesIO(b'[]')

    monkeypatch.setattr(cli, "urlopen", urlopen)
    assert cli.main() == 0
    assert requests[0].full_url == f"http://127.0.0.1:8000{endpoint}?offset=2&limit=10"
    assert requests[0].get_method() == "GET"
