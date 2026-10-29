"""Client MSCI V4. Documentation juillet 2026, p. 4, 7-20, 31-59.

Les metadonnees decrivent un catalogue; elles ne prouvent pas l'acces aux valeurs.
Aucun token, secret ou en-tete Authorization n'est ecrit dans les diagnostics.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests


class MSCIError(RuntimeError):
    """Erreur transport/API; le texte ne contient pas les secrets de la requete."""


class MSCIClient:
    BASE_URL = "https://api.msci.com/esg/data/v4.0"
    TOKEN_URL = "https://accounts.msci.com/oauth/token"
    ENDPOINTS = {"/issuers", "/funds", "/coverage", "/metadata/factors", "/metadata/products"}

    def __init__(self, client_id: str, client_secret: str, *, timeout: int = 60,
                 retries: int = 3, session: requests.Session | None = None):
        if not client_id or not client_secret:
            raise ValueError("Renseigner MSCI_CLIENT_ID et MSCI_CLIENT_SECRET dans .env.")
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout doit etre positif; retries doit etre positif ou nul.")
        self._id, self._secret = client_id, client_secret
        self._token, self._expires = "", 0.0
        self.timeout, self.retries = timeout, retries
        self.session = session or requests.Session()
        # Audit limite aux requetes de donnees: jamais d'en-tetes ni de reponse OAuth.
        self.audit: list[dict] = []

    def close(self) -> None:
        self.session.close()
        self._token = ""

    @staticmethod
    def _delay(response: requests.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0, float(value))
            except ValueError:
                try:
                    date = parsedate_to_datetime(value)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    return max(0, (date - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
        return min(2 ** attempt, 30)

    def _send(self, method: str, url: str, *, token_request: bool = False, **kwargs: Any):
        """Reprises bornees; TLS reste actif. Pas de redirection d'un secret/token."""
        for attempt in range(self.retries + 1):
            try:
                if token_request:
                    response = self.session.post(url, timeout=self.timeout,
                                                 allow_redirects=False, **kwargs)
                else:
                    response = self.session.request(method, url, timeout=self.timeout,
                                                    allow_redirects=False, **kwargs)
            except requests.exceptions.SSLError:
                raise MSCIError("Erreur certificat TLS: contacter l'IT; ne pas desactiver TLS.") from None
            except (requests.Timeout, requests.ConnectionError):
                if attempt == self.retries:
                    raise MSCIError("Echec reseau apres les tentatives configurees.") from None
                time.sleep(min(2 ** attempt, 30))
                continue
            except requests.RequestException:
                raise MSCIError("Erreur HTTP/reseau; verifier la configuration avec l'IT.") from None
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                # Coverage: p. 43 recommande 5 minutes pendant le chargement quotidien.
                delay = self._delay(response, attempt)
                if url.endswith('/coverage') and response.status_code == 503:
                    delay = max(delay, 300)
                time.sleep(delay)
                continue
            return response
        raise MSCIError("Tentatives epuisees.")

    @staticmethod
    def _json(response) -> dict:
        try:
            body = response.json()
        except ValueError:
            raise MSCIError("La reponse n'est pas un JSON valide.") from None
        if not isinstance(body, dict):
            raise MSCIError("Structure JSON inattendue: objet attendu.")
        return body

    def _authenticate(self) -> None:
        # OAuth client_credentials, audience exacte: p. 7-9.
        response = self._send("POST", self.TOKEN_URL, token_request=True, json={
            "client_id": self._id, "client_secret": self._secret,
            "grant_type": "client_credentials", "audience": "https://esg/data",
        })
        if response.status_code != 200:
            raise MSCIError(f"Authentification MSCI: HTTP {response.status_code}.")
        body = self._json(response)
        if not isinstance(body.get("access_token"), str) or not body["access_token"]:
            raise MSCIError("Reponse OAuth sans access_token valide.")
        try:
            lifetime = int(body["expires_in"])
        except (KeyError, ValueError, TypeError):
            raise MSCIError("Reponse OAuth sans expires_in valide.") from None
        if lifetime <= 0:
            raise MSCIError("Le token retourne est deja expire.")
        self._token = body["access_token"]
        self._expires = time.monotonic() + lifetime - min(60, lifetime / 10)

    def request(self, method: str, endpoint: str, **kwargs: Any) -> dict:
        if endpoint not in self.ENDPOINTS:
            raise ValueError(f"Endpoint non implemente: {endpoint}")
        for refresh in range(2):
            if time.monotonic() >= self._expires:
                self._authenticate()
            response = self._send(method, self.BASE_URL + endpoint, headers={
                "Authorization": f"Bearer {self._token}", "Accept": "application/json",
            }, **kwargs)
            if response.status_code == 401 and refresh == 0:
                self._expires = 0
                continue
            if response.status_code not in (200, 206):
                self.audit.append({"endpoint": endpoint, "http_status": response.status_code})
                raise MSCIError(f"{endpoint}: HTTP {response.status_code}. "
                                "Verifier la requete, les droits et le service MSCI.")
            body = self._json(response)
            if not isinstance(body.get("result"), dict):
                raise MSCIError(f"{endpoint}: result absent ou de type inattendu.")
            self.audit.append({
                "endpoint": endpoint, "http_status": response.status_code,
                "trace_id": body.get("trace_id"), "timestamp": body.get("timestamp"),
                "messages": body.get("messages", []),
                "response_metadata": body.get("result", {}).get("response_metadata", {}),
            })
            if body.get("code", response.status_code) not in (200, 206):
                raise MSCIError(f"{endpoint}: code applicatif non reussi; voir diagnostics.")
            if not isinstance(body.get("result"), dict):
                raise MSCIError(f"{endpoint}: result absent ou de type inattendu.")
            return body
        raise MSCIError("Authentification refusee apres renouvellement du token.")

    def batches(self, endpoint: str, payload: dict) -> list[dict]:
        """p. 12, 32, 43: premier lot puis data_request_id/batch_id, sans cache."""
        first = self.request("POST", endpoint, json=payload)
        metadata = first["result"].get("response_metadata", {})
        count = int(metadata.get("total_number_of_batches", 1))
        if count < 1 or int(metadata.get("current_batch", 1)) != 1:
            raise MSCIError("Premier lot ou nombre de lots incoherent.")
        responses = [first]
        for batch_id in range(2, count + 1):
            if not metadata.get("data_request_id"):
                raise MSCIError("data_request_id absent pour les lots suivants.")
            next_payload = {"data_request_id": metadata["data_request_id"], "batch_id": batch_id}
            if endpoint == "/coverage":
                next_payload["entity_type"] = payload["entity_type"]
            response = self.request("POST", endpoint, json=next_payload)
            current = response["result"].get("response_metadata", {})
            if int(current.get("current_batch", batch_id)) != batch_id:
                raise MSCIError("Le lot retourne ne correspond pas au lot demande.")
            responses.append(response)
        return responses

    def factors(self, entity: str) -> dict[str, dict]:
        body = self.request("GET", "/metadata/factors", params={"factor_type": entity})
        return {f["factor_header"]: f for f in body["result"]["factors"]
                if f.get("factor_type") == entity}

    def products(self, entity: str) -> list[dict]:
        return self.request("GET", "/metadata/products", params={"factor_type": entity})[
            "result"]["products"]
