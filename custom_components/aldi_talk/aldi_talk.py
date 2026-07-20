import base64
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests

PORTAL_BASE = "https://www.alditalk-kundenportal.de"
AUTH_BASE = "https://login.alditalk-kundenbetreuung.de"
AUTH_API = f"{AUTH_BASE}/signin/json/authenticate"
REALM = "/alditalk"
SERVICE = "Login"
PORTAL_OVERVIEW_URL = f"{PORTAL_BASE}/portal/auth/uebersicht/"

BFF207 = "/scs/bff/scs-207-customer-master-data-bff/customer-master-data"
BFF209 = "/scs/bff/scs-209-selfcare-dashboard-bff/selfcare-dashboard"


class AldiTalk:
    """Class for interacting with the Aldi Talk portal."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._reset_session()
        self.logger = logging.getLogger(__name__)
        self._account_balance = None
        self._remaining_data_volume = None
        self._total_data_volume = None
        self._remaining_data_percentage = None
        self._eu_roaming_remaining_data_volume = None
        self._eu_roaming_total_data_volume = None
        self._eu_roaming_remaining_data_percentage = None
        self._start_date = None
        self._end_date = None
        self._contract_id = None
        self._first_name = None
        self._offer_name = None

    def _reset_session(self):
        # A fresh session (empty cookie jar) is required before every login.
        # The ForgeRock/OIDC login chain fails if stale, expired portal cookies
        # from a previous session are still present, so reusing the same session
        # to re-login makes valid credentials look rejected. Starting clean
        # mirrors what the config-flow reauth does with a new AldiTalk instance.
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def _portal_json_headers(self):
        return {
            "Accept": "application/json, text/plain, */*",
            "Referer": PORTAL_OVERVIEW_URL,
        }

    def _auth_headers(self):
        return {
            "Accept-API-Version": "protocol=1.0,resource=2.1",
            "Content-Type": "application/json",
            "X-Username": "anonymous",
            "X-Password": "anonymous",
            "X-NoSession": "true",
            "Origin": AUTH_BASE,
            "Referer": f"{AUTH_BASE}/signin/XUI/",
        }

    def _start_portal_flow(self):
        self.logger.debug("Starting portal-auth flow")
        self.session.get(PORTAL_OVERVIEW_URL, allow_redirects=True, timeout=15)

    def _fetch_auth_callbacks(self):
        self.logger.debug("Fetching ForgeRock callback tree")
        response = self.session.post(
            AUTH_API,
            params={
                "realm": REALM,
                "authIndexType": "service",
                "authIndexValue": SERVICE,
            },
            json={},
            headers=self._auth_headers(),
            timeout=15,
        )
        response.raise_for_status()

        payload = response.json()
        auth_id = payload.get("authId")
        callbacks = payload.get("callbacks")
        if not auth_id or callbacks is None:
            raise RuntimeError("Unexpected authentication response from Aldi Talk.")
        return auth_id, callbacks

    def _extract_pow_info(self, callbacks):
        for callback in callbacks:
            if callback.get("type") != "TextOutputCallback":
                continue

            message = next(
                (
                    output.get("value", "")
                    for output in callback.get("output", [])
                    if output.get("name") == "message"
                ),
                "",
            )
            work_match = re.search(r'var work\s*=\s*"([^"]+)"', message)
            difficulty_match = re.search(r"var difficulty\s*=\s*(\d+)", message)
            if work_match:
                difficulty = int(difficulty_match.group(1)) if difficulty_match else 3
                return work_match.group(1), difficulty

        return None, 3

    def _solve_pow(self, work, difficulty):
        prefix = "0" * difficulty
        nonce = 0
        while True:
            digest = hashlib.sha1(f"{work}{nonce}".encode()).hexdigest()
            if digest.startswith(prefix):
                return str(nonce)
            nonce += 1

    def _fill_callbacks(self, callbacks, pow_solution):
        for callback in callbacks:
            callback_type = callback.get("type", "")
            inputs = callback.get("input", [])
            outputs = callback.get("output", [])

            if callback_type == "HiddenValueCallback":
                is_pow_callback = any(
                    output.get("name") == "id"
                    and output.get("value") == "proofOfWorkNonce"
                    for output in outputs
                )
                if is_pow_callback:
                    for item in inputs:
                        item["value"] = pow_solution
                    continue

                fallback_value = next(
                    (
                        output.get("value")
                        for output in outputs
                        if output.get("name") == "value"
                    ),
                    None,
                )
                if fallback_value is not None:
                    for item in inputs:
                        item["value"] = fallback_value
                continue

            if callback_type == "NameCallback":
                for item in inputs:
                    item["value"] = self.username
                continue

            if callback_type == "PasswordCallback":
                for item in inputs:
                    item["value"] = self.password
                continue

            if callback_type == "ConfirmationCallback":
                for item in inputs:
                    item["value"] = 2

        return callbacks

    def _submit_credentials(self, auth_id, callbacks):
        self.logger.debug("Submitting credentials")
        response = self.session.post(
            AUTH_API,
            params={
                "realm": REALM,
                "authIndexType": "service",
                "authIndexValue": SERVICE,
            },
            json={"authId": auth_id, "callbacks": callbacks},
            headers=self._auth_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def _follow_success_url(self, success_url):
        if not success_url:
            raise RuntimeError("Authentication did not return a success URL.")

        resolved_url = (
            success_url
            if success_url.startswith("http")
            else urljoin(AUTH_BASE, success_url)
        )
        self.session.headers.update({"Accept": "text/html,application/xhtml+xml,*/*"})
        self.session.get(resolved_url, allow_redirects=True, timeout=15)

    def _verify_logged_in(self):
        # The portal finishes login via an OIDC authorization-code redirect
        # chain (overview -> /signin/oauth2/authorize -> /logged-in-home-page/
        # ?code=... -> overview). That final callback is what sets the portal
        # session cookies. Following the redirects (allow_redirects=True)
        # completes the exchange and lands on the overview with HTTP 200;
        # stopping at the first 302 to the auth host aborts before the callback
        # and misreports a successful login as failed.
        response = self.session.get(
            PORTAL_OVERVIEW_URL, allow_redirects=True, timeout=15
        )
        final_url = response.url or ""
        if (
            response.status_code != 200
            or AUTH_BASE in final_url
            or "/signin" in final_url
        ):
            # RuntimeError (not ValueError): the coordinator maps ValueError to
            # ConfigEntryAuthFailed (reauth prompt) and everything else to a
            # transient UpdateFailed. Not reaching the overview here is usually a
            # transient hiccup in the multi-step redirect chain, not bad
            # credentials, so it should retry silently rather than nag for a
            # reauth. Genuine credential rejection is raised as ValueError above.
            raise RuntimeError(
                "Login failed: portal did not reach the authenticated overview."
            )

    def _login(self):
        self.logger.debug("Attempting Aldi Talk OAuth login")
        self._reset_session()
        self._start_portal_flow()
        auth_id, callbacks = self._fetch_auth_callbacks()
        pow_work, pow_difficulty = self._extract_pow_info(callbacks)
        pow_solution = self._solve_pow(pow_work, pow_difficulty) if pow_work else "0"
        callbacks = self._fill_callbacks(callbacks, pow_solution)
        result = self._submit_credentials(auth_id, callbacks)

        success_url = result.get("successUrl")
        if not success_url:
            reason = result.get("message") or result.get("detail") or json.dumps(result)
            if (
                "passwort" in reason.lower()
                or "password" in reason.lower()
                or "login" in reason.lower()
            ):
                raise ValueError(f"Login rejected: {reason}")
            raise RuntimeError(f"Login failed: {reason}")

        self._follow_success_url(success_url)
        self._verify_logged_in()

    def _parse_datetime(self, value):
        if not value:
            return None

        text = str(value).strip()
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                return datetime.fromisoformat(candidate).astimezone()
            except ValueError:
                pass

        for date_format in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%d.%m.%Y %H:%M",
        ):
            try:
                return datetime.strptime(text, date_format).astimezone()
            except ValueError:
                continue

        self.logger.debug("Could not parse date value: %s", value)
        return None

    def _decode_msisdn(self):
        lgrs_id = self.session.cookies.get("lgrs_id", "")
        if not lgrs_id:
            return ""

        padded = lgrs_id + ("=" * (-len(lgrs_id) % 4))
        try:
            return base64.b64decode(padded).decode()
        except (ValueError, UnicodeDecodeError):
            self.logger.debug("Unable to decode lgrs_id cookie")
            return ""

    def _request_portal_json(self, path, params=None):
        response = self.session.get(
            PORTAL_BASE + path,
            params=params or {},
            allow_redirects=True,
            timeout=15,
            headers=self._portal_json_headers(),
        )
        response.raise_for_status()
        return response.json()

    def _get_contract_id(self):
        params = {}
        msisdn = self._decode_msisdn()
        if msisdn:
            params["msisdn"] = msisdn

        payload = self._request_portal_json(
            f"{BFF207}/v1/navigation-list", params=params
        )
        subscriptions = payload.get("userDetails", {}).get("subscriptions", [])
        if not subscriptions:
            raise RuntimeError(
                "No Aldi Talk subscription found in navigation-list response."
            )

        contract_id = subscriptions[0].get("contractId")
        if not contract_id:
            raise RuntimeError("navigation-list response did not contain a contractId.")
        return contract_id

    def _get_account_identity(self):
        params = {}
        msisdn = self._decode_msisdn()
        if msisdn:
            params["msisdn"] = msisdn

        payload = self._request_portal_json(
            f"{BFF207}/v1/navigation-list", params=params
        )
        user_details = payload.get("userDetails", {})
        subscriptions = user_details.get("subscriptions", [])
        if not subscriptions:
            raise RuntimeError(
                "No Aldi Talk subscription found in navigation-list response."
            )

        contract_id = subscriptions[0].get("contractId")
        if not contract_id:
            raise RuntimeError("navigation-list response did not contain a contractId.")

        first_name = user_details.get("firstName") or ""
        return contract_id, first_name

    def get_contract_id(self):
        """Public accessor for contract id."""
        return self._get_contract_id()

    def _get_data_entries(self, contract_id):
        payload = self._request_portal_json(
            f"{BFF209}/v1/offers",
            params={"contractId": contract_id, "productType": ""},
        )

        entries = []
        total_balance = payload.get("totalBalance")
        if total_balance is None:
            raise RuntimeError("offers response did not contain totalBalance.")

        subscribed_offers = payload.get("subscribedOffers", [])
        offer_name = next(
            (
                offer.get("offerName")
                for offer in subscribed_offers
                if offer.get("offerName")
            ),
            "",
        )
        for offer in payload.get("subscribedOffers", []):
            for pack in offer.get("pack", []):
                if pack.get("type") != "data":
                    continue

                try:
                    allocated_kb = int(pack["allocated"])
                    used_kb = int(pack["used"])
                except (KeyError, TypeError, ValueError):
                    continue

                entries.append(
                    {
                        "allocated_kb": allocated_kb,
                        "used_kb": used_kb,
                        "next_expiration": pack.get("nextExpirationDate", ""),
                        "balance_attribute_reference": pack.get(
                            "balanceAttributeReference", ""
                        ),
                    }
                )

        return entries, total_balance, offer_name

    def _calculate_data_metrics(self, entry):
        allocated_kb = entry["allocated_kb"]
        used_kb = entry["used_kb"]
        total_data_volume = round(allocated_kb / (1024 * 1024), 2)
        remaining_data_volume = round((allocated_kb - used_kb) / (1024 * 1024), 2)

        if total_data_volume:
            remaining_data_percentage = round(
                (remaining_data_volume / total_data_volume) * 100,
                1,
            )
        else:
            remaining_data_percentage = 0.0

        return {
            "total_data_volume": total_data_volume,
            "remaining_data_volume": remaining_data_volume,
            "remaining_data_percentage": remaining_data_percentage,
        }

    def _update_from_api(self):
        contract_id, first_name = self._get_account_identity()
        # Get entries and total balance from the offers endpoint to minimize requests
        entries, total_balance, offer_name = self._get_data_entries(contract_id)
        # store account balance (expects numeric)
        try:
            self._account_balance = float(total_balance)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "totalBalance from offers is not a valid number"
            ) from exc

        standard_entry = entries[0] if entries else None
        eu_roaming_entry = next(
            (
                item
                for item in entries
                if item.get("balance_attribute_reference") == "dataGrantAmountFUP"
            ),
            None,
        )

        if standard_entry:
            standard_metrics = self._calculate_data_metrics(standard_entry)
            self._total_data_volume = standard_metrics["total_data_volume"]
            self._remaining_data_volume = standard_metrics["remaining_data_volume"]
            self._remaining_data_percentage = standard_metrics[
                "remaining_data_percentage"
            ]

            self._end_date = self._parse_datetime(standard_entry.get("next_expiration"))
            self._start_date = (
                self._end_date - timedelta(days=28) if self._end_date else None
            )
        else:
            self._total_data_volume = None
            self._remaining_data_volume = None
            self._remaining_data_percentage = None
            self._start_date = None
            self._end_date = None

        if eu_roaming_entry:
            eu_roaming_metrics = self._calculate_data_metrics(eu_roaming_entry)
            self._eu_roaming_total_data_volume = eu_roaming_metrics["total_data_volume"]
            self._eu_roaming_remaining_data_volume = eu_roaming_metrics[
                "remaining_data_volume"
            ]
            self._eu_roaming_remaining_data_percentage = eu_roaming_metrics[
                "remaining_data_percentage"
            ]
        else:
            self._eu_roaming_total_data_volume = None
            self._eu_roaming_remaining_data_volume = None
            self._eu_roaming_remaining_data_percentage = None

        self._contract_id = contract_id
        self._first_name = first_name
        self._offer_name = offer_name

    def logged_in(self):
        """Check whether the portal still accepts the current session."""
        self.logger.debug("Checking login status")
        try:
            # Follow the OIDC redirect chain (see _verify_logged_in): a live
            # session lands on the overview with HTTP 200, while an expired one
            # ends on the auth server's sign-in page.
            response = self.session.get(
                PORTAL_OVERVIEW_URL, allow_redirects=True, timeout=15
            )
        except requests.RequestException:
            return False

        final_url = response.url or ""
        if AUTH_BASE in final_url or "/signin" in final_url:
            return False

        return response.status_code == 200

    def update(self):
        """Update account information."""
        if not self.logged_in():
            self._login()

        try:
            self._update_from_api()
        except (requests.RequestException, RuntimeError, ValueError):
            if self.logged_in():
                raise
            self._login()
            self._update_from_api()

    def get_data(self, update=True):
        """Get data."""
        if update:
            self.update()
        return {
            "account_balance": self._account_balance,
            "remaining_data_volume": self._remaining_data_volume,
            "total_data_volume": self._total_data_volume,
            "remaining_data_percentage": self._remaining_data_percentage,
            "eu_roaming_remaining_data_volume": self._eu_roaming_remaining_data_volume,
            "eu_roaming_total_data_volume": self._eu_roaming_total_data_volume,
            "eu_roaming_remaining_data_percentage": self._eu_roaming_remaining_data_percentage,
            "start_date": self.get_start_date(),
            "end_date": self._end_date,
            "contract_id": getattr(self, "_contract_id", None),
            "first_name": getattr(self, "_first_name", None),
            "offer_name": getattr(self, "_offer_name", None),
            "supports_data_sensors": self._remaining_data_volume is not None,
            "supports_eu_roaming_data_sensors": self._eu_roaming_remaining_data_volume
            is not None,
        }

    def get_account_balance(self):
        """Get account balance."""
        return self._account_balance

    def get_remaining_data_volume(self):
        """Get remaining data usage."""
        return self._remaining_data_volume

    def get_total_data_volume(self):
        """Get total data usage."""
        return self._total_data_volume

    def get_end_date(self):
        """Get end date."""
        return self._end_date

    def get_start_date(self):
        """Get start date (28 days before end date)."""
        if self._start_date:
            return self._start_date
        if self._end_date:
            return self._end_date - timedelta(days=28)
        return None
