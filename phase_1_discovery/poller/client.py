"""
OddsPapi REST client.

Responsibilities:
- Fetch live NBA odds from OddsPapi
- Track request usage so we don't blow the 250/month free tier
- Cache the last response so upstream callers can retry without burning quota
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.oddspapi.io/v4"
SPORT_KEY = "basketball_nba"


class QuotaWarning(Exception):
    pass


class OddsAPIClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ODDSPAPI_KEY")
        if not self.api_key:
            raise ValueError("ODDSPAPI_KEY not set. Add it to your .env file.")

        self._request_count = 0
        self._last_response: dict | None = None
        self._last_fetched_at: float | None = None

    @property
    def request_count(self) -> int:
        return self._request_count

    def fetch_nba_odds(self, regions: str = "us", markets: str = "h2h") -> dict:
        """
        Fetch current NBA odds.

        Each call costs 1 request against the 250/month free tier.
        Caller is responsible for not calling this more than needed — use
        the cached response when possible.
        """
        if self._request_count >= 240:
            raise QuotaWarning(
                f"Approaching monthly limit ({self._request_count} requests used). "
                "Halting to protect free tier quota."
            )

        url = f"{BASE_URL}/sports/{SPORT_KEY}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "american",
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        self._request_count += 1
        self._last_response = response.json()
        self._last_fetched_at = time.time()

        return self._last_response

    @property
    def cached_response(self) -> dict | None:
        return self._last_response

    @property
    def seconds_since_last_fetch(self) -> float | None:
        if self._last_fetched_at is None:
            return None
        return time.time() - self._last_fetched_at
