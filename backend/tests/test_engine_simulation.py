try:
    from tests.simulation import run_simulation
except ImportError:  # pytest가 tests 폴더만 경로에 넣은 경우
    from simulation import run_simulation


def test_simulation_270_profiles_keep_prereq_order():
    results = run_simulation()
    assert len(results) == 270
    assert sum(r.order_violations for r in results) == 0
    assert sum(r.deferred_prereq_violations for r in results) == 0
    assert all(len(r.asked) <= 10 for r in results)
