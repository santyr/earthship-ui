"""Production admission uses available RAM and kernel worker isolation."""
import pytest
from test_household_cycle_resources import fixture as resources
from household_cycle_resources import publication_resource_preflight
from native_inference_pressure import NativeInferenceHeadroom


def monitor(tmp_path):
    args,_=resources(tmp_path)
    vm=tmp_path/'vmstat';vm.write_text('pswpin 1\npswpout 1\noom_kill 3\n')
    events=args['leaf']/'memory.events';events.write_text('max 0\noom 0\noom_kill 0\n')
    guard=NativeInferenceHeadroom(vmstat=vm,memory_events=events,resource_check=lambda:publication_resource_preflight(**args))
    return guard,args,vm,events


def test_host_swap_occupancy_and_unrelated_paging_do_not_block_worker(tmp_path):
    guard,args,vm,_=monitor(tmp_path)
    args['meminfo'].write_text('MemAvailable: 8072708 kB\nSwapTotal: 4194304 kB\nSwapFree: 592132 kB\n')
    guard.check();vm.write_text('pswpin 1000000\npswpout 1000000\noom_kill 3\n');guard.check()


@pytest.mark.parametrize('damage',['low_ram','worker_swap','memory_event','host_oom','sustained_pressure'])
def test_real_host_and_worker_limits_still_refuse_and_latch(tmp_path,damage):
    guard,args,vm,events=monitor(tmp_path);guard.check()
    if damage=='low_ram':args['meminfo'].write_text('MemAvailable: 1572863 kB\n')
    elif damage=='worker_swap':(args['leaf']/'memory.swap.max').write_text('1')
    elif damage=='memory_event':events.write_text('max 1\noom 0\noom_kill 0\n')
    elif damage=='host_oom':vm.write_text('oom_kill 4\n')
    else:args['pressure'].write_text('some avg10=10.00 avg60=0.00 avg300=0.00 total=1\nfull avg10=5.00 avg60=0.00 avg300=0.00 total=1\n')
    with pytest.raises(ValueError):guard.check()
    with pytest.raises(ValueError,match='previously refused'):guard.check()
