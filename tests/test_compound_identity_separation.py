"""Test that the governed family roster preserves distinct compound identities."""

# SPDX-License-Identifier: MIT

from cardozo_ketamine_hr.family_analysis import family_roster


def test_compound_identities_are_distinct():
    roster = family_roster()
    assert roster["compound_id"].is_unique
    assert roster["compound_label"].is_unique
    assert "Ketamine, pooled parent" in set(roster["compound_label"])
    assert "Ketamine, confirmed racemate" in set(roster["compound_label"])
    assert "S-ketamine" in set(roster["compound_label"])
    assert "R-ketamine" in set(roster["compound_label"])
