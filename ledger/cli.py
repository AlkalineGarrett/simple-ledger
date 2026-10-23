"""Standard-library HTTP client for a running ledger server."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="Call the ledger API")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Server base URL")

    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-account", help="Create a zero-balance account")

    balance = commands.add_parser("balance", help="Show current balance")
    balance.add_argument("account_id")

    history = commands.add_parser("history", help="Show transaction history, oldest first")
    history.add_argument("account_id")
    history.add_argument("--offset", type=int, default=0)
    history.add_argument("--limit", type=int, default=100)

    for name in ("accounts", "transactions"):
        listing = commands.add_parser(name, help=f"List all {name}")
        listing.add_argument("--offset", type=int, default=0)
        listing.add_argument("--limit", type=int, default=100)

    transaction = commands.add_parser("transaction", help="Record a transfer or cash movement")
    transaction.add_argument("amount", help="Positive decimal amount, e.g. 10.50")
    
    source = transaction.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-account", help="Source account ID")
    source.add_argument("--from-cash", action="store_true", help="Source is external cash")

    destination = transaction.add_mutually_exclusive_group(required=True)
    destination.add_argument("--to-account", help="Destination account ID")
    destination.add_argument("--to-cash", action="store_true", help="Destination is external cash")

    args = parser.parse_args()
    if args.command == "transaction" and args.from_cash and args.to_cash:
        parser.error("Cash-to-cash transactions are not supported; specify an account")

    body = None
    if args.command == "create-account":
        path = "/accounts"
        body = b"{}"
    elif args.command == "balance":
        path = f"/accounts/{args.account_id}/balance"
    elif args.command == "history":
        path = f"/accounts/{args.account_id}/transactions?" + urlencode(
            {"offset": args.offset, "limit": args.limit})
    elif args.command in ("accounts", "transactions"):
        endpoint = "/accounts" if args.command == "accounts" else "/transactions"
        path = endpoint + "?" + urlencode({"offset": args.offset, "limit": args.limit})
    else:
        account_id = args.from_account or args.to_account
        path = f"/accounts/{account_id}/transactions"
        body = json.dumps({"from_account": args.from_account,
                           "to_account": args.to_account, "amount": args.amount}).encode()
                           
    request = Request(args.url.rstrip("/") + path, data=body,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            print(json.dumps(json.load(response), indent=2))
    except HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode()}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, ValueError, OSError) as error:
        print(f"Request failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
