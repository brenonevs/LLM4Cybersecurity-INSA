"""Unit tests for the first, non-blocking Axis B trust state."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.agent import Agent
from terrain.corpus import generer
from terrain.outils import Etat, Fragment, SourceReference
from terrain.protections import ScoreConfiance


def test_new_author_category_starts_with_beta_prior_and_neutral_trust():
    protection = ScoreConfiance()

    state = protection.etat("prestataire-externe", "ticket")

    assert state.alpha == 1.0
    assert state.beta == 1.0
    assert state.confiance == 0.5
    assert protection.confiance("prestataire-externe", "ticket") == 0.5


def test_each_author_and_record_category_has_an_independent_state():
    protection = ScoreConfiance()

    contractor_ticket = protection.etat("prestataire-externe", "ticket")
    contractor_fiche = protection.etat("prestataire-externe", "fiche")
    technician_ticket = protection.etat("tech1", "ticket")

    assert contractor_ticket is protection.etat("prestataire-externe", "ticket")
    assert contractor_ticket is not contractor_fiche
    assert contractor_ticket is not technician_ticket
    assert contractor_fiche.confiance == technician_ticket.confiance == 0.5


@pytest.mark.parametrize("author_id, record_kind", [
    ("", "ticket"),
    ("prestataire-externe", ""),
    ("   ", "journal"),
])
def test_empty_author_or_record_category_is_rejected(author_id, record_kind):
    with pytest.raises(ValueError, match="non-empty"):
        ScoreConfiance().confiance(author_id, record_kind)


def test_first_trust_state_does_not_block_tools():
    protection = ScoreConfiance()

    assert protection.verifier("send_email", {}, "utilisateur") is None


def test_observer_records_each_author_category_seen_in_the_task_once():
    protection = ScoreConfiance()
    fragment = Fragment("data", sources=[
        SourceReference("ticket:TCK-046:description", "ticket", "TCK-046",
                        "description", "externe", "prestataire-externe"),
        SourceReference("ticket:TCK-047:description", "ticket", "TCK-047",
                        "description", "externe", "prestataire-externe"),
        SourceReference("journal:14:mesure", "journal", "14", "mesure",
                        "interne", "sensor:POMPE-01"),
    ])

    protection.observer(fragment)
    protection.observer(fragment)

    assert protection.sources_tache() == {
        ("prestataire-externe", "ticket"): (
            "ticket:TCK-046:description", "ticket:TCK-047:description"),
        ("sensor:POMPE-01", "journal"): ("journal:14:mesure",),
    }
    assert protection.confiance("prestataire-externe", "ticket") == 0.5


def test_new_task_clears_seen_sources_but_keeps_reputation_states():
    protection = ScoreConfiance()
    protection.observer(Fragment("data", sources=[
        SourceReference("ticket:TCK-046:description", "ticket", "TCK-046",
                        "description", "externe", "prestataire-externe"),
    ]))

    protection.reinitialiser()

    assert protection.sources_tache() == {}
    assert protection.etat("prestataire-externe", "ticket").confiance == 0.5


def test_agent_reading_a_real_record_populates_task_sources():
    class Modele:
        def __init__(self):
            self.actions = iter([
                {"outil": "read_log", "args": {"equipement": "SENS-39"}},
                {"fin": "done"},
            ])

        def prochaine_action(self, *_):
            return next(self.actions)

    protection = ScoreConfiance()
    Agent(Etat(generer()), Modele(), protection).executer("Read SENS-39.")

    seen = protection.sources_tache()
    assert ("prestataire-externe", "ticket") in seen
    assert any(key[1] == "journal" for key in seen)
