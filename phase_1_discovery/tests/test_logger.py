"""
Tests for the logger module.

Covers:
- CSV is created with headers on first write
- Opportunity data is written correctly
- Multiple calls append (not overwrite)
- Handles empty opportunity list gracefully
"""

import csv
import pytest
from pathlib import Path
from phase_1_discovery.normalizer.normalizer import Outcome
from phase_1_discovery.detector.detector import ArbOpportunity
from phase_1_discovery.logger.logger import log_opportunities, FIELDNAMES


def make_opportunity(event_id="e1", margin=2.5) -> ArbOpportunity:
    return ArbOpportunity(
        event_id=event_id,
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time="2026-05-20T01:00:00Z",
        best_outcomes={
            "Los Angeles Lakers": Outcome("Los Angeles Lakers", "draftkings", 0.476),
            "Boston Celtics": Outcome("Boston Celtics", "fanduel", 0.500),
        },
        implied_prob_sum=0.976,
        margin_pct=margin,
    )


class TestLogOpportunities:
    def test_creates_csv_with_headers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_opportunities([make_opportunity()])

        csv_file = tmp_path / "data" / "opportunities.csv"
        assert csv_file.exists()

        with open(csv_file) as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == FIELDNAMES

    def test_writes_one_row_per_opportunity(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_opportunities([make_opportunity("e1"), make_opportunity("e2")])

        with open(tmp_path / "data" / "opportunities.csv") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2

    def test_appends_on_subsequent_calls(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_opportunities([make_opportunity("e1")])
        log_opportunities([make_opportunity("e2")])

        with open(tmp_path / "data" / "opportunities.csv") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2

    def test_row_fields_are_correct(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_opportunities([make_opportunity("e_test", margin=3.14)])

        with open(tmp_path / "data" / "opportunities.csv") as f:
            row = list(csv.DictReader(f))[0]

        assert row["event_id"] == "e_test"
        assert row["home_team"] == "Los Angeles Lakers"
        assert float(row["margin_pct"]) == 3.14

    def test_empty_list_does_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_opportunities([])  # Should not raise
