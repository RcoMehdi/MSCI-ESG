"""Interpretation des reponses courantes, p. 15 et 39 du document MSCI."""
from __future__ import annotations


def describe_response(response: dict, requested_factors: list[str]) -> dict:
    result = response["result"]
    metadata = result.get("response_metadata", {})
    resolved = metadata.get("resolved_factors", [])
    if not isinstance(resolved, list):
        raise ValueError("resolved_factors doit etre une liste pour issuers/funds.")
    series = metadata.get("resolved_series_factors", [])
    return {
        "trace_id": response.get("trace_id"),
        "timestamp": response.get("timestamp"),
        "messages": response.get("messages", []),
        "metadata": metadata,
        "requested_factors": requested_factors,
        "resolved_factors": resolved,
        # Ce constat n'est PAS une preuve d'absence de licence.
        "requested_but_not_resolved": sorted(set(requested_factors) - set(resolved) - set(series)),
        "rows_returned": len(result.get("data", [])),
    }


def row_state(isin_valid: bool, unresolved: bool, ambiguous: bool,
              returned: bool, esg_count: int, missing: list[str]) -> str:
    if not isin_valid:
        return "invalid_isin"
    if ambiguous:
        return "ambiguous_identifier"
    if unresolved:
        return "unresolved_identifier"
    if not returned:
        return "no_data_returned"
    if esg_count == 0:
        return "reference_only"
    return "partial" if missing else "complete"
