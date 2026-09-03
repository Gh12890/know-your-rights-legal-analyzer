
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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("indiankanoon_client")

BASE_URL = "https://api.indiankanoon.org"
API_KEY = os.getenv("INDIANKANOON_API_KEY")

# Client-side rate limiting. IK doesn't publish a strict RPS limit; this
# is a safety margin, not a contractual number. It is now a GLOBAL gap
# between call STARTS (lock-guarded), so it holds whether calls come one
# at a time or from the parallel helpers below -- a ~7/sec ceiling.
MIN_SECONDS_BETWEEN_CALLS = 0.15
_last_call_time = 0.0
_throttle_lock = threading.Lock()

# Concurrency cap for search_many / get_documents. Kept low: polite to
# IK, and the global throttle above is the real limiter anyway.
MAX_PARALLEL_CALLS = 4

# Retries on a 429 (rate limited) before giving up.
_MAX_429_RETRIES = 2


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
    """Global pacing: hold at least MIN_SECONDS_BETWEEN_CALLS between the
    START of any two calls, whether serial or from the parallel helpers.
    Lock-guarded so N threads still queue up behind one ~7/sec gate."""
    global _last_call_time
    with _throttle_lock:
        wait = MIN_SECONDS_BETWEEN_CALLS - (time.time() - _last_call_time)
        if wait > 0:
            time.sleep(wait)
        _last_call_time = time.time()


def _request(method: str, endpoint: str, _attempt: int = 0, **kwargs) -> dict:
    """Internal: single point of control for every API call. All auth,
    throttling, and error handling lives here so search() and
    get_document() stay simple. Retries a 429 (rate limited) with a
    short backoff, up to _MAX_429_RETRIES."""
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

    if resp.status_code == 429:
        if _attempt < _MAX_429_RETRIES:
            delay = min(int(resp.headers.get("retry-after", "2") or "2"), 5)
            logger.warning("IK 429 on %s; retry %d after %ss", endpoint, _attempt + 1, delay)
            time.sleep(delay)
            return _request(method, endpoint, _attempt=_attempt + 1, **kwargs)
        raise IndianKanoonError(f"Rate limited (429) on {endpoint} after {_MAX_429_RETRIES} retries.")

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


# ---------------------------------------------------------------------------
# Parallel helpers. Each still costs the same per-call money -- they only
# remove the wall-clock cost of doing N independent HTTP round-trips one
# after another. The global _throttle() keeps the aggregate rate polite.
# Neither ever raises: a failed item maps to None (logged) so one bad
# query / tid does not sink a whole batch.
# ---------------------------------------------------------------------------

def _run_parallel(fn, items, label, max_workers):
    items = list(dict.fromkeys(items))  # dedupe, keep order
    if not items:
        return {}
    workers = max(1, min(max_workers or MAX_PARALLEL_CALLS, MAX_PARALLEL_CALLS, len(items)))
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for fut in as_completed(futs):
            it = futs[fut]
            try:
                out[it] = fut.result()
            except Exception as e:  # noqa: BLE001 -- one item failing must not sink the batch
                logger.warning("%s: %r failed: %s", label, it, e)
                out[it] = None
    return out


def search_many(queries, max_workers: int = MAX_PARALLEL_CALLS) -> dict:
    """Run search() for each query concurrently.

    Returns {query: result_dict_or_None}. Order-preserving dedupe on the
    input. A query that errors maps to None (logged), never raised."""
    return _run_parallel(lambda q: search(q, 0), queries, "search_many", max_workers)


def get_documents(doc_ids, max_workers: int = MAX_PARALLEL_CALLS) -> dict:
    """Run get_document() for each id concurrently.

    Returns {doc_id_str: result_dict_or_None}. A fetch that errors maps
    to None (logged), never raised."""
    ids = [str(d) for d in doc_ids if d]
    return _run_parallel(get_document, ids, "get_documents", max_workers)

