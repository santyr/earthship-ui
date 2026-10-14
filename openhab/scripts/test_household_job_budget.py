"""RAM admission reserves future growth of concurrent jobs."""
import pytest

MiB=1024**2
GiB=1024**3


def admission(**changes):
    from household_job_budget import admit_memory
    values=dict(available_bytes=8*GiB,pool_limit_bytes=6*GiB,pool_used_bytes=0,
        jobs={},minimum_bytes=256*MiB,preferred_bytes=2*GiB,reserve_bytes=3*GiB)
    values.update(changes)
    return admit_memory(**values)


def test_idle_job_receives_preferred_budget_when_host_and_pool_have_room():
    assert admission()==2*GiB


def test_outstanding_sibling_growth_is_reserved_before_new_job():
    # Four GiB available includes the sibling's present one GiB usage.
    # Another one GiB is already promised to it, leaving nothing above reserve.
    from household_job_budget import AdmissionDeferred
    with pytest.raises(AdmissionDeferred):
        admission(available_bytes=4*GiB,pool_used_bytes=GiB,
            jobs={'training':{'used_bytes':GiB,'limit_bytes':2*GiB}})


def test_preferred_budget_reduces_to_available_capacity_above_minimum():
    assert admission(available_bytes=3*GiB+700*MiB+123)==700*MiB


def test_pool_cap_counts_parent_charges_and_child_reservations():
    # Child currently consumes1GiB, can grow to3GiB. Another2GiB is
    # charged directly to the pool. Six GiB ceiling leaves only1GiB.
    assert admission(pool_used_bytes=3*GiB,
        jobs={'training':{'used_bytes':GiB,'limit_bytes':3*GiB}})==GiB


def test_new_job_cannot_overcommit_sum_of_sibling_maximums():
    assert admission(jobs={'a':{'used_bytes':0,'limit_bytes':3*GiB},
        'b':{'used_bytes':0,'limit_bytes':2*GiB}},available_bytes=16*GiB)==GiB


def test_minimum_is_not_silently_reduced_to_make_a_job_start():
    from household_job_budget import AdmissionDeferred
    with pytest.raises(AdmissionDeferred):admission(available_bytes=3*GiB+255*MiB)


@pytest.mark.parametrize('changes',[
    {'available_bytes':-1},{'available_bytes':True},{'pool_limit_bytes':'max'},
    {'pool_used_bytes':float('nan')},{'reserve_bytes':-1},
    {'minimum_bytes':0},{'minimum_bytes':3*GiB},
    {'jobs':{'a':{'used_bytes':0,'limit_bytes':'max'}}},
    {'jobs':{'a':{'used_bytes':2*GiB,'limit_bytes':GiB}}},
])
def test_unknown_or_contradictory_resource_metadata_refuses(changes):
    with pytest.raises(ValueError):admission(**changes)
