"""Shared helpers: Matterport Model API access and .env loading."""
import os
import sys

import requests

API_URL = "https://api.matterport.com/api/models/graph"

try:  # optional: read keys from a .env file next to where you run the script
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _auth():
    key = os.environ.get("MATTERPORT_API_KEY")
    token = os.environ.get("MATTERPORT_API_TOKEN")
    if not key or not token:
        sys.exit(
            "Missing MATTERPORT_API_KEY / MATTERPORT_API_TOKEN. "
            "Get them with /costar-keys in Discord and put them in .env or your environment."
        )
    return key, token


def graph(query, variables=None, timeout=90):
    """POST a GraphQL query. Returns (data, errors). Exits on auth failure."""
    resp = requests.post(
        API_URL,
        json={"query": query, "variables": variables or {}},
        auth=_auth(),
        timeout=timeout,
    )
    if resp.status_code in (401, 403):
        sys.exit(f"HTTP {resp.status_code}: key/token rejected. Keys only work on api.matterport.com.")
    resp.raise_for_status()
    body = resp.json()
    return body.get("data"), body.get("errors")


def unwrap_type(t):
    """Follow NON_NULL / LIST wrappers to the named type. Returns (name, kind)."""
    while t and t.get("ofType") and t.get("kind") in ("NON_NULL", "LIST"):
        t = t["ofType"]
    return (t or {}).get("name"), (t or {}).get("kind")


TYPE_REF = "type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }"
