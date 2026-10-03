from heattwin.assumptions import Assumptions


def test_all_assumptions_have_provenance():
    a = Assumptions.load()
    assert len(list(a.items())) > 0
    for key, entry in a.items():
        assert entry.source.strip(), key
        assert entry.unit.strip(), key


def test_ll97_penalty():
    assert Assumptions.load().v("policy.ll97_penalty") == 268
