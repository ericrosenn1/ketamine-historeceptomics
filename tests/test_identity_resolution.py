"""Test conservative resolution of ketamine-family compound identities."""

# SPDX-License-Identifier: MIT

from cardozo_ketamine_hr.identity import resolve_compound_identity


def test_unspecified_ketamine_is_not_promoted_to_racemate():
    resolved = resolve_compound_identity("ketamine")
    assert resolved.status == "RESOLVED"
    assert resolved.canonical_id == "ketamine_unspecified"
    assert resolved.canonical_id != "ketamine_racemic"


def test_confirmed_racemate_and_enantiomers_remain_distinct():
    racemate = resolve_compound_identity("racemic ketamine")
    s_ketamine = resolve_compound_identity("esketamine")
    r_ketamine = resolve_compound_identity("arketamine")
    assert racemate.canonical_id == "ketamine_racemic"
    assert s_ketamine.canonical_id == "esketamine"
    assert r_ketamine.canonical_id == "arketamine"
    assert len({racemate.canonical_id, s_ketamine.canonical_id, r_ketamine.canonical_id}) == 3


def test_bare_hydroxyketamine_stays_ambiguous_without_lane():
    ambiguous = resolve_compound_identity("hydroxyketamine")
    assert ambiguous.status == "AMBIGUOUS"
    assert set(ambiguous.candidates) == {
        "hydroxyketamine_unspecified_isomer_aggregate",
        "HYDROXYKETAMINE_GENERIC",
    }
    family = resolve_compound_identity(
        "hydroxyketamine", source_lane="FROZEN_KETAMINE_FAMILY_U1_HPF"
    )
    e7 = resolve_compound_identity("hydroxyketamine", source_lane="E7")
    assert family.canonical_id == "hydroxyketamine_unspecified_isomer_aggregate"
    assert e7.canonical_id == "HYDROXYKETAMINE_GENERIC"


def test_hydroxynorketamine_stereoisomers_are_not_merged():
    rr = resolve_compound_identity("(2R,6R)-HNK")
    ss = resolve_compound_identity("(2S,6S)-HNK")
    generic = resolve_compound_identity("HNK")
    assert [rr.canonical_id, ss.canonical_id, generic.canonical_id] == [
        "HNK_2R_6R",
        "HNK_2S_6S",
        "HNK_GENERIC",
    ]


def test_unknown_identity_is_explicitly_unresolved():
    assert resolve_compound_identity("invented ketamine identity").status == "UNRESOLVED"
