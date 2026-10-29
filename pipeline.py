"""Pipeline d'enrichissement, sans substitution silencieuse ni imputation.

Les decisions de mapping sont dans config/mapping.json, pas dans le client HTTP.
Les references sont demandees explicitement, meme si elles figurent en metadonnees.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .diagnostics import describe_response, row_state
from .excel import export, headers, read_input, valid_isin

REFERENCE_FACTORS = {"issuer": {"ISSUER_NAME", "ISSUER_TICKER"},
                     "fund": {"FUND_NAME", "FUND_ISIN"}}
REFERENCE_FIELDS = {
    "ISSUER_NAME", "ISSUER_TICKER", "ISSUERID", "ISSUER_ISIN", "ISSUER_CUSIP",
    "ISSUER_SEDOL", "ISSUER_CNTRY_DOMICILE", "FUND_NAME", "FUND_ISIN", "FUND_CUSIP",
    "FUND_SEDOL", "FUND_SHARE_CLASS_ID", "Client_ID", "Security_Status",
}


def flatten(item: dict) -> dict:
    """Format courant p. 19-20/40-41. Pas de reduction arbitraire d'une serie."""
    result = {}
    metadata = item.get("issuer_metadata", [])
    if not isinstance(metadata, list) or len(metadata) > 1:
        raise ValueError("Metadonnees emetteur ambigues ou de format inattendu.")
    if metadata:
        result.update(metadata[0])
    for factor in item.get("factors", []):
        if "value" in factor:
            value = factor["value"]
            if isinstance(value, (dict, list)):
                raise ValueError("Facteur non scalaire: regle metier necessaire avant export.")
            name = factor["name"]
            if name in result and result[name] is not None and value is not None:
                if result[name] != value:
                    raise ValueError(f"Valeurs contradictoires pour {name}.")
            if value is not None or name not in result:
                result[name] = value
        elif "data_values" in factor:
            raise ValueError("Format historique/serie non pris en charge dans le pipeline courant.")
    if item.get("series"):
        raise ValueError("Serie retournee: selection d'une observation non implementee.")
    return result


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp.json')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run(client, settings: dict, root: Path) -> dict:
    """Conserve les diagnostics meme si une erreur API interrompt l'export."""
    paths = {key: (root / settings[key]).resolve() for key in
             ("input", "template", "output", "diagnostics", "mapping")}
    if len(set(paths.values())) != len(paths):
        raise ValueError("Les chemins entree, template, mapping, sortie et diagnostics doivent differer.")
    report = {"version": "0.2.0", "extracted_at": datetime.now(timezone.utc).isoformat(),
              "status": "started", "mapping": [], "rows": [], "api": [], "warnings": []}
    try:
        _enrich(client, settings, paths, report)
        report["status"] = "completed_with_warnings" if report["warnings"] else "completed"
    except Exception as exc:
        report["status"] = "failed"
        # Erreurs client sanitisees; pas de contenu OAuth dans le rapport.
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        report["http_audit"] = getattr(client, "audit", [])
        _write_report(paths["diagnostics"], report)
    return report


def _enrich(client, settings: dict, paths: dict, report: dict) -> None:
    columns = headers(paths["template"])
    mapping = json.loads(paths["mapping"].read_text(encoding="utf-8"))
    inputs = read_input(paths["input"], settings["input_sheets"], settings["isin_column"])
    outputs = {entity: [] for entity in columns}
    size = int(settings["batch_size"])
    if not 1 <= size <= 50:
        raise ValueError("batch_size doit etre compris entre 1 et 50 (choix conservateur du projet).")
    for entity in columns:
        if list(mapping.get(entity, {})) != columns[entity]:
            raise ValueError(f"Le mapping doit reprendre exactement les en-tetes et l'ordre {entity}.")
    for entity, input_rows in inputs.items():
        if not input_rows:
            continue
        rules = mapping[entity]
        metadata = client.factors(entity)
        factors = set(REFERENCE_FACTORS[entity])
        for target, rule in rules.items():
            kind, source = rule["kind"], rule.get("source")
            if kind not in {"factor", "metadata", "input", "input_isin", "coverage", "blocked"}:
                raise ValueError(f"Type de regle inconnu: {kind}.")
            if kind == "factor":
                if source in metadata:
                    factors.add(source)
                    state = "present_in_catalog_not_proof_of_value_access"
                else:
                    state = "absent_from_returned_catalog"
            else:
                state = kind
                if kind == "metadata" and source in metadata:
                    factors.add(source)
            report["mapping"].append({"entity": entity, "target": target, "source": source,
                                      "state": state, "note": rule.get("note", "")})

        isins = list(dict.fromkeys(r["_isin"] for r in input_rows if valid_isin(r["_isin"])))
        lookup = {isin: isin for isin in isins}
        coverage_data, ambiguous = {}, set()
        if entity == "fund" and isins:
            products = settings.get("fund_products", [])
            if not products:
                raise ValueError("Pour Fonds, renseigner fund_products avec un nom exact retourne "
                                 "par la commande products --entity fund.")
            matches = {isin: {} for isin in isins}
            for product in products:
                for response in client.batches("/coverage", {
                    "entity_type": "fund", "product": product, "format": "json",
                }):
                    report["api"].append({"endpoint": "/coverage", "product": product,
                                          "trace_id": response.get("trace_id"),
                                          "messages": response.get("messages", []),
                                          "metadata": response["result"].get("response_metadata", {})})
                    for item in response["result"].get("data", []):
                        isin = item.get("ISIN")
                        if isin in matches and item.get("MDSUID"):
                            matches[isin][item["MDSUID"]] = item
            lookup = {}
            for isin, candidates in matches.items():
                if len(candidates) == 1:
                    uid, item = next(iter(candidates.items()))
                    lookup[isin], coverage_data[isin] = uid, item
                elif len(candidates) > 1:
                    ambiguous.add(isin)

        collected, unresolved, rejected = {}, set(), set()
        identifiers = list(dict.fromkeys(lookup.values()))
        for offset in range(0, len(identifiers), size):
            requested = identifiers[offset:offset + size]
            payload = {f"{entity}_identifier_list": requested,
                       "factor_name_list": sorted(factors), "format": "json"}
            endpoint = "/issuers" if entity == "issuer" else "/funds"
            for response in client.batches(endpoint, payload):
                info = describe_response(response, sorted(factors))
                report["api"].append({"endpoint": endpoint, "request": payload, **info})
                rejected.update(info["requested_but_not_resolved"])
                for item in info["metadata"].get("unresolved_identifiers", []):
                    if isinstance(item, str):
                        unresolved.add(item)
                    elif isinstance(item, dict):
                        key = item.get("requested_id") or item.get("identifier")
                        if key:
                            unresolved.add(key)
                for item in response["result"].get("data", []):
                    key = item.get("requested_id")
                    if key not in requested:
                        raise ValueError("requested_id inattendu: rapprochement interrompu.")
                    if key in collected:
                        raise ValueError("requested_id duplique: rapprochement ambigu.")
                    collected[key] = flatten(item)
        if rejected:
            report["warnings"].append({"entity": entity, "type": "factors_not_resolved",
                                       "factors": sorted(rejected),
                                       "note": "Consulter messages; ne pas conclure automatiquement a une licence absente."})

        for row in input_rows:
            isin = row["_isin"]
            resolved = lookup.get(isin)
            data = collected.get(resolved, {})
            result, missing = {}, []
            for target in columns[entity]:
                rule = rules[target]
                kind, source = rule["kind"], rule.get("source")
                value = None
                if kind in ("factor", "metadata"):
                    value = data.get(source)
                elif kind == "input":
                    value = row.get(source)
                elif kind == "input_isin":
                    value = isin
                elif kind == "coverage":
                    value = data.get(target, coverage_data.get(isin, {}).get(source))
                result[target] = value
                if value is None:
                    missing.append(target)
            esg_count = sum(value is not None and target not in REFERENCE_FIELDS
                            and rules[target]["kind"] == "factor"
                            for target, value in result.items())
            state = row_state(valid_isin(isin), resolved in unresolved, isin in ambiguous,
                              resolved in collected, esg_count, missing)
            report["rows"].append({"entity": entity, "input_row": row["_row"], "isin": isin,
                                   "resolved_id": resolved, "issuer_id": data.get("ISSUERID"),
                                   "state": state, "esg_values_count": esg_count,
                                   "missing_columns": missing})
            outputs[entity].append(result)
    counts = {}
    for row in report["rows"]:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    report["summary"] = {"input_rows": len(report["rows"]), "states": counts,
                         "rows_with_esg_values": sum(r["esg_values_count"] > 0 for r in report["rows"])}
    if report["summary"]["rows_with_esg_values"] == 0:
        report["warnings"].append({"type": "no_esg_values", "note":
                                   "Aucune valeur ESG recuperee; references seules ou aucune donnee."})
    if any(r["state"] != "complete" for r in report["rows"]):
        report["warnings"].append({"type": "incomplete_output", "note":
                                   "Export incomplet; voir le diagnostic de chaque ligne."})
    export(paths["template"], paths["output"], outputs)
