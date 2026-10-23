"""Unit tests for src.mtgtop8.hadouken (Hadouken league tournament page parser)."""

from pathlib import Path

import pytest

from src.mtgtop8.hadouken import (
    HadoukenPairing,
    is_hadouken_url,
    pairing_results,
    parse_hadouken_event,
    parse_spanish_date,
)

FIXTURE = Path(__file__).parent / "fixtures" / "hadouken_event.html"
URL = "https://hadoleague.vercel.app/torneos/fecha-6-t2-duel-commander-1791661849109"


@pytest.fixture(scope="module")
def event():
    return parse_hadouken_event(FIXTURE.read_text(encoding="utf-8"), url=URL)


class TestParseHadoukenEvent:
    def test_event_metadata(self, event):
        assert event.url == URL
        assert event.name == "Fecha 6 / T2 - Duel Commander"
        assert event.date == "09/10/26"
        assert event.format_id == "EDH"
        assert event.store == "Hadouken"
        assert event.player_count == 26

    def test_standings(self, event):
        assert len(event.standings) == 26
        first = event.standings[0]
        assert (first.rank, first.player, first.points) == (1, "Leonardo Basualdo", 15)
        assert (first.wins, first.losses, first.draws) == (5, 0, 0)
        assert event.standings[-1].rank == 26
        assert event.standings[-1].player == "Gloria Alan"

    def test_names_are_title_cased_with_accents_kept(self, event):
        names = {s.player for s in event.standings}
        assert "Santiago Monsú" in names
        assert "Masino Julian" in names

    def test_pairings(self, event):
        assert {p.round for p in event.pairings} == {1, 2, 3, 4, 5}
        assert len(event.pairings) == 5 * 13
        assert event.pairings[0] == HadoukenPairing(
            round=1, player1="Lautaro Rojas", player2="Masino Julian", games1=0, games2=2
        )

    def test_pairings_agree_with_standings(self, event):
        """W/L/D derived from the pairings must equal the standings table (validates score interpretation)."""
        derived: dict[str, list[int]] = {s.player: [0, 0, 0] for s in event.standings}
        for p in event.pairings:
            r1, r2 = pairing_results(p)
            for player, result in ((p.player1, r1), (p.player2, r2)):
                idx = {"win": 0, "loss": 1}.get(result, 2)
                derived[player][idx] += 1
        for s in event.standings:
            assert derived[s.player] == [s.wins, s.losses, s.draws], s.player

    def test_rejects_page_without_event(self):
        with pytest.raises(ValueError):
            parse_hadouken_event("<html><body><main><p>nada</p></main></body></html>")


class TestPairingResults:
    def test_win_loss(self):
        assert pairing_results(HadoukenPairing(1, "A", "B", 2, 1)) == ("win", "loss")
        assert pairing_results(HadoukenPairing(1, "A", "B", 0, 2)) == ("loss", "win")

    def test_draw(self):
        assert pairing_results(HadoukenPairing(1, "A", "B", 1, 1)) == ("draw", "draw")

    def test_zero_zero_is_intentional_draw(self):
        assert pairing_results(HadoukenPairing(1, "A", "B", 0, 0)) == ("intentional_draw", "intentional_draw")


class TestParseSpanishDate:
    def test_full_date(self):
        assert parse_spanish_date("viernes, 9 de octubre de 2026, 10:00 p. m.") == "09/10/26"

    def test_accented_month_and_case(self):
        assert parse_spanish_date("Sábado, 21 de Septiembre de 2026") == "21/09/26"
        assert parse_spanish_date("1 de setiembre de 2026") == "01/09/26"

    def test_unparseable(self):
        assert parse_spanish_date("mañana") == ""


class TestIsHadoukenUrl:
    def test_accepts_tournament_url(self):
        assert is_hadouken_url(URL)

    def test_rejects_other_hosts_and_paths(self):
        assert not is_hadouken_url("https://evil.example.com/torneos/x")
        assert not is_hadouken_url("https://hadoleague.vercel.app.evil.com/torneos/x")
        assert not is_hadouken_url("https://hadoleague.vercel.app/jugadores/x")
        assert not is_hadouken_url("http://localhost:8000/torneos/x")
