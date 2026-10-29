"""Commandes du projet. Les chemins de configuration sont relatifs a la racine."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .client import MSCIClient
from .excel import headers, read_input
from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="MSCI Enrichment V2: references et donnees ESG")
    parser.add_argument("command", choices=["run", "validate", "products", "metadata", "probe"])
    parser.add_argument("--config", default="config/settings.json")
    parser.add_argument("--entity", choices=["issuer", "fund"], default="issuer")
    parser.add_argument("--identifier", help="ISIN emetteur ou MDSUID fonds pour probe")
    parser.add_argument("--factor", action="append", help="Facteur a tester; option repetable")
    args = parser.parse_args()
    client = None
    try:
        config = Path(args.config).resolve()
        root = config.parent.parent
        settings = json.loads(config.read_text(encoding="utf-8"))
        if args.command == "validate":
            columns = headers(root / settings["template"])
            mapping = json.loads((root / settings["mapping"]).read_text(encoding="utf-8"))
            for entity, names in columns.items():
                if list(mapping[entity]) != names:
                    raise ValueError(f"Mapping/en-tetes incompatibles pour {entity}.")
            rows = read_input(root / settings["input"], settings["input_sheets"], settings["isin_column"])
            print("Configuration locale coherente; aucun appel API effectue.")
            for entity, values in rows.items():
                print(f"{entity}: {len(values)} lignes d'entree; {len(columns[entity])} colonnes cible.")
            return
        load_dotenv(root / ".env", override=False)
        client = MSCIClient(os.getenv("MSCI_CLIENT_ID", ""), os.getenv("MSCI_CLIENT_SECRET", ""),
                            timeout=settings["timeout_seconds"], retries=settings["max_retries"])
        if args.command == "products":
            print(json.dumps(client.products(args.entity), ensure_ascii=False, indent=2))
        elif args.command == "metadata":
            if args.factor:
                response = client.request("GET", "/metadata/factors", params={
                    "factor_type": args.entity, "factor_name_list": args.factor})
                print(json.dumps(response, ensure_ascii=False, indent=2))
            else:
                print(json.dumps(client.factors(args.entity), ensure_ascii=False, indent=2))
        elif args.command == "probe":
            if not args.identifier:
                raise ValueError("probe requiert --identifier.")
            factors = args.factor or (["ISSUER_NAME", "ISSUER_TICKER", "IVA_COMPANY_RATING"]
                                      if args.entity == "issuer" else ["FUND_NAME", "FUND_ISIN"])
            payload = {f"{args.entity}_identifier_list": [args.identifier],
                       "factor_name_list": factors, "format": "json"}
            endpoint = "/issuers" if args.entity == "issuer" else "/funds"
            response = client.request("POST", endpoint, json=payload)
            print(json.dumps({"endpoint": endpoint, "request": payload, "response": response},
                             ensure_ascii=False, indent=2))
        else:
            report = run(client, settings, root)
            summary = report["summary"]
            print(f"Export ecrit: {settings['output']}")
            print(f"Lignes d'entree: {summary['input_rows']}; "
                  f"lignes avec au moins une valeur ESG: {summary['rows_with_esg_values']}.")
            print("Etats: " + json.dumps(summary["states"], ensure_ascii=False))
            if report["warnings"]:
                print("ATTENTION: export partiel ou avertissements. "
                      "Un fichier cree ne signifie pas que les donnees ESG sont accessibles.")
            print(f"Diagnostic: {settings['diagnostics']}")
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"Erreur: {exc}\nSi un ancien Excel existe, il ne constitue pas un nouvel export.\n")
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
