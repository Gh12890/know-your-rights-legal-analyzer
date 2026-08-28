
"""
indiankanoon_client.py

Thin wrapper around the Indian Kanoon API (api.indiankanoon.org).

ARCHITECTURE NOTE (do not violate):
This file does ONE job: authenticated HTTP calls to Indian Kanoon's
/search/ and /doc/ endpoints, returning raw structured data.

It does NOT:
- decide relevance (that's Step 2, query construction)
- decide trustworthiness (that's Step 3, the QA gate)
- talk to any LLM
- get merged into JUDGMENT_CITATION_MAP directly

Every result from this file is UNVERIFIED until it passes through the
QA gate in Step 3. Nothing here should be shown to a user directly.

Every function in this file that calls the API costs real money —
current rates: api.indiankanoon.org/pricing/ (subject to change on
IK's end; don't hardcode numbers here, they'll go stale silently).
"""

import os
import time
import logging

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("indiankanoon_client")

BASE_URL = "https://api.indiankanoon.org"
API_KEY = os.getenv("INDIANKANOON_API_KEY")

# Conservative client-side rate limiting. IK doesn't publish a strict
# RPS limit in the docs snippet we have; this is a safety margin, not
# a confirmed contractual number. [Guessing] — adjust if IK support
# confirms an actual rate limit.
MIN_SECONDS_BETWEEN_CALLS = 0.5
_last_call_time = 0.0


class IndianKanoonError(Exception):
    """Raised for any non-recoverable API failure (auth, network, bad response shape)."""
    pass


class IndianKanoonBalanceError(IndianKanoonError):
    """Raised specifically when the account balance appears to be exhausted."""
    pass


def _check_api_key() -> None:
    if not API_KEY:
        raise IndianKanoonError(
            "INDIANKANOON_API_KEY not found in environment. "
            "Check .env file exists and contains this key."
        )


def _throttle() -> None:
    """Client-side pacing so we never hammer the API faster than a
    reasonable rate, independent of whatever IK's real server-side
    limit is."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_time = time.time()


def _request(method: str, endpoint: str, **kwargs) -> dict:
    """Internal: single point of control for every API call. All auth,
    throttling, and error handling lives here so search() and
    get_document() stay simple."""
    _check_api_key()
    _throttle()

    url = f"{BASE_URL}{endpoint}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Token {API_KEY}"

    try:
        resp = requests.request(method, url, headers=headers, timeout=20, **kwargs)
    except requests.exceptions.RequestException as e:
        raise IndianKanoonError(f"Network error calling {endpoint}: {e}")

    if resp.status_code == 401 or resp.status_code == 403:
        raise IndianKanoonError(
            f"Auth failed ({resp.status_code}) on {endpoint}. "
            f"Check INDIANKANOON_API_KEY is valid and account is active. "
            f"Response: {resp.text[:300]}"
        )

    if resp.status_code != 200:
        body_lower = resp.text.lower()
        if "balance" in body_lower or "insufficient" in body_lower:
            raise IndianKanoonBalanceError(
                f"Request to {endpoint} failed, response suggests balance "
                f"exhaustion. Response: {resp.text[:300]}"
            )
        raise IndianKanoonError(
            f"Unexpected status {resp.status_code} from {endpoint}. "
            f"Response: {resp.text[:300]}"
        )

    try:
        return resp.json()
    except ValueError:
        raise IndianKanoonError(
            f"Response from {endpoint} was not valid JSON. "
            f"Raw response: {resp.text[:300]}"
        )


def search(query: str, page_num: int = 0) -> dict:
    """
    Search Indian Kanoon. Returns the raw API response dict.

    IMPORTANT: this is a RAW search call. It does not filter for
    relevance beyond whatever Indian Kanoon's own ranking does. The
    caller (Step 2, query construction) is responsible for building a
    query that's actually anchored to a specific BNS/BNSS section or
    known doctrine, not a vague free-text guess.

    Args:
        query: search string. Indian Kanoon supports operators
            (e.g. title:, doctypes:, fromdate:) — see Documentation
            page for the full operator set before assuming plain
            keywords are the best approach.
        page_num: 0-indexed page of results (confirmed: IK's pagenum
            starts at 0, not 1 — this is documented explicitly by IK,
            not a guess).

    Returns:
        dict with at least 'found' (str, e.g. "1 - 10 of 9402") and
        'docs' (list of dicts, each with at least 'tid' and 'title').

    Raises:
        IndianKanoonError, IndianKanoonBalanceError
    """
    params = {"formInput": query, "pagenum": page_num}
    result = _request("POST", "/search/", params=params)
    logger.info(
        "IK search: query=%r page=%d found=%r docs_returned=%d",
        query, page_num, result.get("found"), len(result.get("docs", []))
    )
    return result


def get_document(doc_id: str) -> dict:
    """
    Fetch a full document by its Indian Kanoon tid (document ID).

    Args:
        doc_id: the 'tid' field from a search() result's docs list.

    Returns:
        dict with the document's full content and metadata. Exact
        shape should be confirmed against a real response the first
        time this is called for real — do not assume field names
        without checking (same discipline as everything else this
        session: verify against real data, not documentation alone).

    Raises:
        IndianKanoonError, IndianKanoonBalanceError
    """
    if not doc_id:
        raise IndianKanoonError("get_document called with empty doc_id")

    result = _request("POST", f"/doc/{doc_id}/")
    logger.info("IK get_document: doc_id=%s", doc_id)
    return result


def get_document_metainfo(doc_id: str) -> dict:
    """
    Fetch only metadata for a document (cheapest call: Rs 0.02 vs
    Rs 0.20 for full document). Useful for a lightweight pre-check
    (e.g. confirming court/date) before spending on the full doc.

    Raises:
        IndianKanoonError, IndianKanoonBalanceError
    """
    if not doc_id:
        raise IndianKanoonError("get_document_metainfo called with empty doc_id")

    result = _request("POST", f"/docmeta/{doc_id}/")
    logger.info("IK get_document_metainfo: doc_id=%s", doc_id)
    return result

