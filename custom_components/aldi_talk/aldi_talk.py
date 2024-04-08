import logging
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

# Constants
LOGIN_URL = "https://login.alditalk-kundenbetreuung.de/sso/UI/Login"
DASHBOARD_URL = "https://www.alditalk-kundenbetreuung.de/de/"
DATE_FORMAT = "%d.%m.%Y %H:%M"
DEFAULT_UPDATE = False


class AldiTalk:
    """Class for interacting with AldiTalk service."""

    def __init__(self, username: str, password: str):
        """
        Initialize AldiTalk instance.

        Args:
            username (str): Username for AldiTalk login.
            password (str): Password for AldiTalk login.
        """
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.logger = logging.getLogger(__name__)
        self._account_balance = None
        self._remaining_data_volume = None
        self._total_data_volume = None
        self._end_date = None

    def _login(self):
        """Perform login."""
        self.logger.debug("Attempting login...")
        response = self.session.post(
            LOGIN_URL, data={"IDToken1": self.username, "IDToken2": self.password}
        )
        if "Rufnummer und/oder Passwort falsch." in response.text:
            self.logger.error("Login failed: Invalid username or password.")
            raise ValueError("Invalid username or password.")
        self.logger.debug("Login response: %s", response.status_code)

    def _fetch_dashboard(self):
        """Fetch dashboard HTML."""
        self.logger.debug("Fetching dashboard...")
        if not self.logged_in():
            self._login()
        return self.session.get(DASHBOARD_URL)

    def _parse_dashboard(self, dashboard):
        """Parse dashboard HTML."""
        soup = BeautifulSoup(dashboard.content, "html.parser")
        self._account_balance = self._extract_account_balance(soup)
        self._remaining_data_volume = self._extract_usage_remaining(soup)
        self._total_data_volume = self._extract_usage_total(soup)
        self._end_date = self._extract_end_date(soup)

    def _extract_account_balance(self, soup):
        """Extract account balance from parsed HTML."""
        account_balance_element = soup.find(
            "div", id="ajaxReplaceQuickInfoBoxBalanceId"
        )
        if account_balance_element:
            try:
                return float(
                    account_balance_element.find("p")
                    .text.strip()
                    .replace(",", ".")
                    .replace("€", "")
                )
            except ValueError:
                self.logger.error("Failed to parse account balance.")
        else:
            self.logger.error("Failed to find account balance element.")
        return None

    def _extract_usage_remaining(self, soup):
        """Extract remaining data usage from parsed HTML."""
        try:
            usage_remaining = (
                soup.find("td", class_="pack__usage", colspan="2")
                .find("span", class_="pack__usage-remaining")
                .text
            )

            unit = (
                soup.find("td", class_="pack__usage", colspan="2")
                .find("span", class_="pack__usage-unit")
                .text
            )
        except AttributeError:
            self.logger.error("Failed to find remaining data usage element.")
            return None

        try:
            usage_remaining = float(usage_remaining.strip().replace(",", "."))
            if unit == "GB":
                usage_remaining *= 1000
            return usage_remaining
        except ValueError:
            self.logger.error("Failed to parse remaining data usage.")
        return None

    def _extract_usage_total(self, soup):
        """Extract total data usage from parsed HTML."""
        usage_total = (
            soup.find("td", class_="pack__usage", colspan="2")
            .find("span", class_="oftotal")
            .find("span", class_="pack__usage-total")
            .text
        )

        unit = (
            soup.find("td", class_="pack__usage", colspan="2")
            .find("span", class_="oftotal")
            .find("span", class_="pack__usage-unit")
            .text
        )

        try:
            usage_total = float(usage_total.strip().replace(",", "."))
            if unit == "GB":
                usage_total *= 1000
            return usage_total
        except ValueError:
            self.logger.error("Failed to parse total data usage.")
        return None

    def _extract_end_date(self, soup):
        """Extract end date from parsed HTML."""
        end_date_element = soup.find(
            "tr", class_="t-row pack__panel pack__panel--end-date"
        )
        if end_date_element:
            end_date_text = end_date_element.find("td", colspan="2").text.strip()
            end_date_text = (
                end_date_text.split(",")[1].strip().split()[0]
                + " "
                + end_date_text.split(",")[1].strip().split()[1]
            )
            try:
                return datetime.strptime(end_date_text, DATE_FORMAT).astimezone()
            except ValueError:
                self.logger.error("Failed to parse end date.")
        else:
            self.logger.error("Failed to find end date element.")
        return None

    def logged_in(self):
        """
        Check if user is logged in.

        Returns:
            bool: True if logged in, False otherwise.
        """
        self.logger.debug("Checking login status...")
        dashboard = self.session.get(DASHBOARD_URL)
        login_status = '<ul class="nav-items level-0">' in dashboard.text
        self.logger.debug("Login status: %s", login_status)
        return login_status

    def update(self):
        """Update account information."""
        dashboard = self._fetch_dashboard()
        self._parse_dashboard(dashboard)

    def get_data(self, update=True):
        """Get data."""
        if update:
            self.update()
        return {
            "account_balance": self._account_balance,
            "remaining_data_volume": self._remaining_data_volume,
            "total_data_volume": self._total_data_volume,
            "start_date": self.get_start_date(),
            "end_date": self._end_date,
        }

    def get_account_balance(self):
        """Get account balance."""
        return self._account_balance

    def get_remaining_data_volume(self):
        """Get remaining data usage."""
        return self._remaining_data_volume

    def get_total_data_volume(self):
        """Get remaining data usage."""
        return self._total_data_volume

    def get_end_date(self):
        """Get end date."""
        return self._end_date

    def get_start_date(self):
        """Get start date (28 days before end date)."""
        if self._end_date:
            return self._end_date - timedelta(days=28)
        else:
            return None
