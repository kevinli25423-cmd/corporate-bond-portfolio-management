from __future__ import annotations

import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN_URL = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token?grant_type=client_credentials"
API_BASE = "https://api.finra.org"


def _credentials() -> tuple[str, str]:
    client_id = os.getenv("FINRA_CLIENT_ID") or input("FINRA Client ID: ").strip()
    client_secret = os.getenv("FINRA_CLIENT_SECRET") or getpass.getpass("FINRA Client Secret (hidden): ")
    if not client_id or not client_secret:
        raise SystemExit("Client ID and Client Secret are required.")
    return client_id, client_secret


def _request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, dict(resp.headers.items()), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, raw


def get_access_token(client_id: str, client_secret: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    status, _, raw = _request(
        TOKEN_URL,
        method="POST",
        headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
    )
    if status != 200:
        raise SystemExit(f"OAuth token request failed with HTTP {status}: {raw[:500]}")
    payload = json.loads(raw)
    token = payload.get("access_token")
    if not token:
        raise SystemExit("OAuth response did not contain access_token.")
    print(f"OAuth: OK (token received; expires_in={payload.get('expires_in', 'n/a')})")
    return token


def check_metadata(token: str, group: str, dataset: str) -> tuple[int, str]:
    url = f"{API_BASE}/metadata/group/{group}/name/{dataset}"
    status, _, raw = _request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    print(f"Metadata {group}/{dataset}: HTTP {status}")
    if status != 200:
        print("  Response:", raw[:300].replace("\n", " "))
    return status, raw


def query_one_trade_activity_row(token: str, dataset: str) -> None:
    url = f"{API_BASE}/data/group/FixedIncomeMarket/name/{dataset}"
    body = {
        "limit": 1,
        "fields": [
            "issueSymbolIdentifier",
            "issuerName",
            "tradeExecutionDate",
            "reportedTradeVolume",
            "lastSalePrice",
            "lastSaleYield",
            "tradeExecutionTime",
            "cusip",
        ],
        "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "cusip", "fieldValue": "46647PEU6"}
        ],
        "sortFields": ["-tradeExecutionDate"],
    }
    status, headers, raw = _request(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        body=body,
    )
    print(f"Sample query {dataset}: HTTP {status}")
    if status == 200:
        print("  Record-Total:", headers.get("Record-Total", "n/a"))
        try:
            parsed = json.loads(raw)
            print("  Sample row:", json.dumps(parsed[0] if isinstance(parsed, list) and parsed else parsed, indent=2)[:1200])
        except json.JSONDecodeError:
            print("  Response preview:", raw[:1200])
    else:
        print("  Response:", raw[:500].replace("\n", " "))


def main() -> None:
    print("FINRA official API access check")
    print("Credentials are read from environment variables or entered locally; the secret is not printed.\n")
    client_id, client_secret = _credentials()
    token = get_access_token(client_id, client_secret)

    # Control check: this is an officially documented public Fixed Income Query API dataset.
    control_status, _ = check_metadata(token, "fixedIncomeMarket", "treasuryDailyAggregates")
    if control_status != 200:
        print("\nYour credential authenticated, but the documented public Fixed Income metadata check failed.")
        print("Check that the credential type is Public and active before continuing.")
        return

    print("\nChecking whether the single-bond Corporate & Agency Trade Activity grid is exposed through the official Query API...")
    candidates = ["CorporateAndAgencyTradeActivity", "corporateAndAgencyTradeActivity"]
    for dataset in candidates:
        status, _ = check_metadata(token, "FixedIncomeMarket", dataset)
        if status == 200:
            print(f"\nDataset is available through the official Query API as: {dataset}")
            query_one_trade_activity_row(token, dataset)
            return

    print("\nResult: the credential works, but this specific single-bond Trade Activity dataset was not found in the official Query API metadata catalog under the tested names.")
    print("Do not automate the public website's internal services-dynarep endpoint. The next project step should use a FINRA-supported data access route or a separately licensed/downloaded TRACE dataset.")


if __name__ == "__main__":
    main()
