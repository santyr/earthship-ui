"""Hermetic regression of Stage A's failed real-lock retention design."""
import os
import pytest
from services.lorawan.tests import qualification_lifetime_probe as probe
from services.lorawan.tests.qualification_guard import Refused


def test_both_locks_are_stored_real_first_and_released_real_last():
    events=[];counts=iter([1,2,1,0])
    store=probe.ProbeStore(notify=lambda text,fd=None:events.append((text,fd)),
        barrier=lambda:events.append(('barrier',None)),count=lambda:next(counts))
    store.pin(real=17,disposable=18)
    store.release()
    assert events==[('FDSTORE=1\nFDNAME=admission\nFDPOLL=0',17),('barrier',None),
        ('FDSTORE=1\nFDNAME=probe\nFDPOLL=0',18),('barrier',None),
        ('FDSTOREREMOVE=1\nFDNAME=probe',None),('barrier',None),
        ('FDSTOREREMOVE=1\nFDNAME=admission',None),('barrier',None)]


def test_partial_store_failure_never_removes_the_real_reservation():
    events=[];counts=iter([1,1])
    store=probe.ProbeStore(notify=lambda text,fd=None:events.append((text,fd)),barrier=lambda:None,count=lambda:next(counts))
    with pytest.raises(Refused):store.pin(real=17,disposable=18)
    assert events==[('FDSTORE=1\nFDNAME=admission\nFDPOLL=0',17),('FDSTORE=1\nFDNAME=probe\nFDPOLL=0',18)]


def test_restart_uses_named_real_descriptor_even_when_stdin_was_closed():
    assert probe.probe_descriptors({}) is None
    assert probe.probe_descriptors({'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'2','LISTEN_FDNAMES':'probe:admission'})=={'probe':3,'admission':4}
    assert probe.probe_descriptors({'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'2','LISTEN_FDNAMES':'admission:probe'})=={'admission':3,'probe':4}


@pytest.mark.parametrize('values',[('1','admission'),('2','probe:probe'),('2','other:probe'),('3','admission:probe:other')])
def test_ambiguous_or_partial_inheritance_refuses(values):
    with pytest.raises(Refused):probe.probe_descriptors({'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':values[0],'LISTEN_FDNAMES':values[1]})
