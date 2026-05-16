"""
OddsPapi REST client.

Responsibilities:
- Discover NBA sport ID and tournament IDs via the OddsPapi API
- Fetch upcoming NBA fixtures, then odds per fixture across all bookmakers
- Track request usage so we don't blow the 250/month free tier
- Cache sport/tournament IDs so discovery doesn't burn quota on every cycle

OddsPapi flow:
  1. GET /v4/sports                    → find NBA sport ID (cached)
  2. GET /v4/tournaments               → find NBA tournament IDs (cached)
  3. GET /v4/fixtures                  → list upcoming NBA fixtures
  4. GET /v4/odds?fixtureId=X          → all bookmakers for one fixture, one call
     (500ms cooldown between calls enforced by the API)
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.oddspapi.io/v4"

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

        # Cached discovery results — only fetched once per session
        self._nba_sport_id: int | None = None
        self._nba_tournament_ids: list[int] | None = None

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

    def get_nba_sport_id(self) -> int:
        """Fetch sport list and return the NBA sport ID. Cached after first call."""
        if self._nba_sport_id is not None:
            return self._nba_sport_id

        sports = self._get("/sports", {})
        for sport in sports:
            name = sport.get("sportName", "").lower()
            if "basketball" in name or "nba" in name:
                self._nba_sport_id = sport["sportId"]
                return self._nba_sport_id

        raise ValueError("NBA/basketball sport not found in OddsPapi sports list.")

    def get_nba_tournament_ids(self) -> list[int]:
        """Fetch basketball tournaments and return the NBA tournament ID. Cached after first call."""
        if self._nba_tournament_ids is not None:
            return self._nba_tournament_ids

        sport_id = self.get_nba_sport_id()
        tournaments = self._get("/tournaments", {"sportId": sport_id})
        tournament_list = tournaments if isinstance(tournaments, list) else tournaments.get("data", [])

        # Target the main NBA tournament only (slug "nba") to avoid passing
        # hundreds of global basketball league IDs to the fixtures endpoint.
        nba = [t for t in tournament_list if t.get("tournamentSlug") == "nba"]
        if not nba:
            raise ValueError("NBA tournament (slug 'nba') not found in tournaments list.")

        self._nba_tournament_ids = [t["tournamentId"] for t in nba]
        return self._nba_tournament_ids

    def get_nba_fixtures(self) -> list[dict]:
        """Fetch upcoming NBA fixtures that have odds available. One request."""
        tournament_id = self.get_nba_tournament_ids()[0]  # NBA is a single tournament
        raw = self._get("/fixtures", {
            "tournamentId": tournament_id,
            "statusId": 0,       # not started
            "hasOdds": "true",
        })
        return raw if isinstance(raw, list) else raw.get("data", [])

    def fetch_nba_odds(
        self,
        bookmakers: list[str] = DEFAULT_BOOKMAKERS,
        odds_format: str = "american",
    ) -> list:
        """
        Fetch current NBA odds across all requested bookmakers.

        One call per fixture (all bookmakers returned in that single call).
        The API enforces a 500ms cooldown between calls, respected here.

        Cost: 1 request for fixtures + 1 per fixture with live odds.
        """
        fixtures = self.get_nba_fixtures()
        bookmakers_str = ",".join(bookmakers)
        results = []

        for fixture in fixtures:
            fixture_id = fixture.get("id") or fixture.get("fixtureId")
            data = self._get("/odds", {
                "fixtureId": fixture_id,
                "bookmakers": bookmakers_str,
                "oddsFormat": odds_format,
                "language": "en",
                "verbosity": 3,
            })
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
