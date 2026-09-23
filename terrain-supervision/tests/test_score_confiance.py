"""Unit tests for the first, non-blocking Axis B trust state."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
