"""Read actual finite cgroup commitments before launching concurrent work."""
from pathlib import Path
import pytest
from household_job_budget import GiB


def pool(tmp_path):
    root=tmp_path/'earthship-work.slice';root.mkdir()
    for name,value in {'memory.max':6*GiB,'memory.high':5*GiB,'memory.current':GiB,
            'memory.swap.max':0,'pids.max':256,'cpu.max':'800000 100000'}.items():
        (root/name).write_text(str(value))
    child=root/'earthship-job-a.scope';child.mkdir()
    (child/'memory.current').write_text(str(GiB))
    (child/'memory.max').write_text(str(2*GiB))
    return root,child


def test_pool_snapshot_retains_finite_child_commitments(tmp_path):
    from household_job_pool import read_pool
    root,_=pool(tmp_path)
    snapshot=read_pool(root)
    assert snapshot=={'pool_limit_bytes':6*GiB,'pool_used_bytes':GiB,
        'jobs':{'earthship-job-a.scope':{'used_bytes':GiB,'limit_bytes':2*GiB}}}


@pytest.mark.parametrize('file,value',[
    ('memory.max','max'),('memory.swap.max','1'),('pids.max','max'),
    ('cpu.max','max 100000'),('cpu.max','900000 100000'),('memory.high','max')])
def test_unverified_aggregate_envelope_refuses(tmp_path,file,value):
    from household_job_pool import read_pool
    root,_=pool(tmp_path);(root/file).write_text(value)
    with pytest.raises(ValueError):read_pool(root)


def test_uncapped_sibling_cannot_be_treated_as_zero_usage(tmp_path):
    from household_job_pool import read_pool
    root,child=pool(tmp_path);(child/'memory.max').write_text('max')
    with pytest.raises(ValueError):read_pool(root)


def test_disappearing_counter_refuses_this_snapshot(tmp_path):
    from household_job_pool import read_pool
    root,child=pool(tmp_path);(child/'memory.current').unlink()
    with pytest.raises(ValueError):read_pool(root)


def test_symlink_child_cannot_escape_managed_pool(tmp_path):
    from household_job_pool import read_pool
    root,child=pool(tmp_path);outside=tmp_path/'outside';child.rename(outside)
    child.symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):read_pool(root)


def test_host_available_requires_exact_kernel_quantity(tmp_path):
    from household_job_pool import available_memory
    p=tmp_path/'meminfo';p.write_text('MemTotal: 16000000 kB\nMemAvailable: 4000000 kB\n')
    assert available_memory(p)==4096000000
    p.write_text('MemAvailable: 4000000 MB\n')
    with pytest.raises(ValueError):available_memory(p)


@pytest.mark.parametrize('some,full,available',[(5.01,0,4*GiB),(0,1.01,4*GiB),(0,0,1536*1024**2-1)])
def test_sustained_pressure_or_emergency_ram_reserve_defers_work(tmp_path,some,full,available):
    from household_job_budget import AdmissionDeferred
    from household_job_pool import check_host_pressure
    path=tmp_path/'pressure';path.write_text(f'some avg10={some} avg60=0.00 avg300=0.00 total=0\nfull avg10={full} avg60=0.00 avg300=0.00 total=0\n')
    with pytest.raises(AdmissionDeferred):check_host_pressure(path,available=lambda:available)


def test_transient_pressure_counter_without_sustained_stalls_is_allowed(tmp_path):
    from household_job_pool import check_host_pressure
    path=tmp_path/'pressure';path.write_text('some avg10=0.00 avg60=0.00 avg300=0.00 total=1000000\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=1000000\n')
    check_host_pressure(path,available=lambda:4*GiB)
