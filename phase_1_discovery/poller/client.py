"""
OddsPapi REST client.

Responsibilities:
- Fetch odds for a specific fixture across multiple bookmakers
- Track request usage so we don't blow the 250/month free tier

NBA IDs are confirmed constants — no discovery calls needed:
  NBA_SPORT_ID      = 11   (Basketball)
  NBA_TOURNAMENT_ID = 132  (NBA, slug "nba", USA)

For the live discovery run, use fetch_fixture_odds(fixture_id) directly.
fetch_nba_odds() is retained for general polling across all fixtures.
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.oddspapi.io/v4"

NBA_SPORT_ID = 11
NBA_TOURNAMENT_ID = 132

DEFAULT_BOOKMAKERS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "caesars",
    "pinnacle",
]


class QuotaWarning(Exception):
    pass


class OddsAPIClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ODDSPAPI_KEY")
        if not self.api_key:
            raise ValueError("ODDSPAPI_KEY not set. Add it to your .env file.")

        self._request_count = 0
        self._last_response: list | None = None
        self._last_fetched_at: float | None = None

    @property
    def request_count(self) -> int:
        return self._request_count

    def _get(self, path: str, params: dict) -> dict | list:
        if self._request_count >= 240:
            raise QuotaWarning(
                f"Approaching monthly limit ({self._request_count} requests used). "
                "Halting to protect free tier quota."
            )
        params["apiKey"] = self.api_key
        response = requests.get(f"{BASE_URL}{path}", params=params, timeout=10)
        response.raise_for_status()
        self._request_count += 1
        return response.json()

    def fetch_fixture_odds(
        self,
        fixture_id: str,
        bookmakers: list[str] = DEFAULT_BOOKMAKERS,
        odds_format: str = "american",
    ) -> dict:
        """
        Fetch current odds for a single fixture across all requested bookmakers.

        This is the primary method for the live discovery run — one call
        per snapshot, targeting a specific game by its fixture ID.

        Cost: 1 request per call.
        """
        return self._get("/odds", {
            "fixtureId": fixture_id,
            "bookmakers": ",".join(bookmakers),
            "oddsFormat": odds_format,
            "language": "en",
            "verbosity": 3,
        })

    def get_nba_fixtures(self) -> list[dict]:
        """Fetch upcoming NBA fixtures that have odds available. One request."""
        raw = self._get("/fixtures", {
            "tournamentId": NBA_TOURNAMENT_ID,
            "statusId": 0,
            "hasOdds": "true",
        })
        return raw if isinstance(raw, list) else raw.get("data", [])

    def fetch_nba_odds(
        self,
        bookmakers: list[str] = DEFAULT_BOOKMAKERS,
        odds_format: str = "american",
    ) -> list:
        """
        Fetch current odds across all upcoming NBA fixtures.

        One call per fixture. Cost: 1 (fixtures) + 1 per fixture.
        """
        fixtures = self.get_nba_fixtures()
        results = []

        for fixture in fixtures:
            fixture_id = fixture.get("fixtureId") or fixture.get("id")
            data = self.fetch_fixture_odds(fixture_id, bookmakers, odds_format)
            results.append(data)
            time.sleep(0.5)  # respect 500ms cooldown

        self._last_response = results
        self._last_fetched_at = time.time()
        return self._last_response

    @property
    def cached_response(self) -> list | None:
        return self._last_response

    @property
    def seconds_since_last_fetch(self) -> float | None:
        if self._last_fetched_at is None:
            return None
        return time.time() - self._last_fetched_at
