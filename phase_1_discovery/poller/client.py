"""
OddsPapi REST client.

Responsibilities:
- Discover NBA sport ID and tournament IDs via the OddsPapi API
- Fetch live NBA odds across a list of bookmakers (one call per bookmaker)
- Track request usage so we don't blow the 250/month free tier
- Cache sport/tournament IDs so discovery doesn't burn quota on every cycle

OddsPapi flow:
  1. GET /v4/sports               → find NBA sport ID
  2. GET /v4/tournaments          → find NBA tournament IDs
  3. GET /v4/odds-by-tournaments  → fetch odds per bookmaker
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
            name = sport.get("name", "").lower()
            if "basketball" in name or "nba" in name:
                self._nba_sport_id = sport["id"]
                return self._nba_sport_id

        raise ValueError("NBA/basketball sport not found in OddsPapi sports list.")

    def get_nba_tournament_ids(self) -> list[int]:
        """Fetch NBA tournaments and return their IDs. Cached after first call."""
        if self._nba_tournament_ids is not None:
            return self._nba_tournament_ids

        sport_id = self.get_nba_sport_id()
        tournaments = self._get("/tournaments", {"sportId": sport_id})
        self._nba_tournament_ids = [t["id"] for t in tournaments]
        return self._nba_tournament_ids

    def fetch_nba_odds(
        self,
        bookmakers: list[str] = DEFAULT_BOOKMAKERS,
        odds_format: str = "american",
    ) -> list:
        """
        Fetch current NBA odds across multiple bookmakers.

        Makes one API call per bookmaker. Results are merged into a single
        list keyed by fixture so downstream normalization works the same way.

        Each call costs 1 request against the 250/month free tier.
        """
        tournament_ids = self.get_nba_tournament_ids()
        tournament_ids_str = ",".join(str(t) for t in tournament_ids)

        merged: dict[str, dict] = {}

        for bookmaker in bookmakers:
            data = self._get("/odds-by-tournaments", {
                "tournamentIds": tournament_ids_str,
                "bookmaker": bookmaker,
                "oddsFormat": odds_format,
            })

            for fixture in data if isinstance(data, list) else data.get("data", []):
                fid = fixture.get("id")
                if fid not in merged:
                    merged[fid] = {
                        "id": fid,
                        "home_team": fixture.get("home_team"),
                        "away_team": fixture.get("away_team"),
                        "commence_time": fixture.get("commence_time"),
                        "bookmakers": [],
                    }
                merged[fid]["bookmakers"].extend(fixture.get("bookmakers", []))

        self._last_response = list(merged.values())
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
