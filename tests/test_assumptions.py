from heattwin.assumptions import Assumptions


def test_all_assumptions_have_provenance():
    a = Assumptions.load()
    assert len(list(a.items())) > 0
    for key, entry in a.items():
        assert entry.source.strip(), key
        assert entry.unit.strip(), key


def test_ll97_penalty():
    assert Assumptions.load().v("policy.ll97_penalty") == 268


def test_duplicate_sections_are_rejected(tmp_path):
    import pytest
    p = tmp_path / "a.yaml"
    p.write_text("g:\n  x: {value: 1, unit: u, source: s, confidence: high}\n"
                 "g:\n  y: {value: 2, unit: u, source: s, confidence: high}\n")
    with pytest.raises(ValueError, match="duplicate"):
        Assumptions.load(p)
