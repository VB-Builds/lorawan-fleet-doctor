from fleetdoctor.diagnose.common import Config
from fleetdoctor.diagnose.fcnt import analyze, check
from conftest import make_uplink


def test_clean_sequence():
    s = analyze(list(range(100, 200)))
    assert (s.received, s.missed, s.resets, s.rollovers) == (100, 0, 0, 0)


def test_gaps_counted():
    s = analyze([1, 2, 5, 6, 10])  # missing 3,4 and 7,8,9
    assert (s.received, s.missed, s.expected) == (5, 5, 10)
    assert s.loss == 0.5


def test_duplicates_ignored():
    assert analyze([1, 2, 2, 3]).missed == 0


def test_16_bit_rollover_is_not_a_reset():
    s = analyze([65533, 65534, 65535, 0, 1])
    assert (s.resets, s.rollovers, s.missed) == (0, 1, 0)
    s = analyze([65530, 3])  # lost 65531..65535 and 0..2
    assert (s.resets, s.rollovers, s.missed) == (0, 1, 8)


def test_32_bit_rollover_is_not_a_reset():
    top = (1 << 32) - 1
    s = analyze([top - 1, top, 0, 1])
    assert (s.resets, s.rollovers, s.missed) == (0, 1, 0)


def test_reset_detected_and_no_loss_counted_across_it():
    s = analyze([500, 501, 502, 0, 1, 2, 3])
    assert (s.resets, s.rollovers, s.missed) == (1, 0, 0)
    s = analyze([70_000, 70_001, 4])  # 32-bit counter far from any limit going backwards
    assert s.resets == 1


def test_huge_forward_jump_is_not_loss():
    assert analyze([10, 900_000]).missed == 0


def test_check_findings_and_severity():
    cfg = Config()
    gappy = [make_uplink(dev="aa", t_s=i * 3600, fcnt=i * 2) for i in range(60)]  # 50 % loss
    resets = [make_uplink(dev="bb", t_s=i * 3600, fcnt=i % 20) for i in range(60)]  # 2 resets
    fine = [make_uplink(dev="cc", t_s=i * 3600, fcnt=i) for i in range(60)]
    found = {(f.subject, f.check, f.severity) for f in check(gappy + resets + fine, cfg)}
    assert found == {("aa", "fcnt_gaps", "critical"), ("bb", "fcnt_reset", "warning")}


def test_evidence_is_human_readable():
    ups = [make_uplink(t_s=i * 1800, fcnt=i + i // 9) for i in range(300)]  # ~10 % missing
    (f,) = check(ups, Config(loss_warn=0.05))
    assert f.evidence.startswith("FCnt gaps: ") and "expected uplinks missing" in f.evidence
