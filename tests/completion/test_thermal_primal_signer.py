"""Optional exact stdin-signer qualification; disposable keys and loopback only."""
import importlib.util
import json
from pathlib import Path
import threading
import time

import pytest

from test_thermal_nip04 import codec, C, O, NOW
from test_thermal_nip04_delivery import local_server
import thermal_confirmation as t
import thermal_messaging as m
import thermal_nip04 as n
import thermal_primal as cli

VERSION='nak version v0.20.7-earthship-nip04-stdin.1'
SPEC=importlib.util.spec_from_file_location('primal_nak_qualification',
    Path(__file__).resolve().parents[2]/'scripts/qualify-thermal-nak.py')
qualifier=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(qualifier)


def test_exact_versioned_candidate_passes_all_nip17_authentication_checks(codec):
    result=qualifier.qualify(codec.keyer.executable,codec.keyer.digest,expected_version=VERSION)
    assert result['nak_version']==VERSION and result['status']=='passed'
    assert len(result['checks'])==8
    assert result['household_keys_used'] is False and result['journal_writes']==0


def test_candidate_cannot_be_mislabeled_as_stock_version(codec):
    with pytest.raises(qualifier.QualificationFailed,match='version'):
        qualifier.qualify(codec.keyer.executable,codec.keyer.digest)


def test_primal_command_self_challenge_passes_actual_stdin_and_both_protocols(codec):
    result=cli.check_primal_identity(codec.keyer,C)
    assert result['status']=='passed' and result['stdin_encoding_verified'] is True
    assert result['signer_identity_verified'] is True and result['message_published'] is False
    assert result['operator_read_verified'] is False


@pytest.mark.parametrize('authorized',[False,True])
def test_primal_relay_authentication_requires_explicit_permission_and_actual_signature(
        codec,monkeypatch,authorized):
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    event=codec.encode('Synthetic local relay authentication',author=C,recipient=O,
                       created_at=int(NOW.timestamp()))
    messages=[]
    def handler(ws):
        first=json.loads(ws.recv(timeout=3)); messages.append(first)
        ws.send(t.canonical(['AUTH','synthetic-loopback-challenge']).decode())
        if not authorized: return
        answer=json.loads(ws.recv(timeout=3)); messages.append(answer)
        auth=answer[1]; codec.keyer.verify(auth,22242)
        assert answer[0]=='AUTH' and auth['pubkey']==C and auth['content']==''
        assert auth['tags']==[['relay',url],['challenge','synthetic-loopback-challenge']]
        ws.send(t.canonical(['OK',auth['id'],True,'accepted']).decode())
        resent=json.loads(ws.recv(timeout=3)); messages.append(resent)
        ws.send(t.canonical(['OK',event['id'],True,'accepted']).decode())
    with local_server(handler) as server:
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        url=f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        relay=n.PrimalRelay(codec.keyer,C,frozenset({O}),auth=authorized,local_test=True)
        if authorized:
            relay.publish(url,event)
            assert len(messages)==3 and messages[0]==messages[2]==['EVENT',event]
        else:
            with pytest.raises(t.Refused): relay.publish(url,event)
            assert messages==[['EVENT',event]]
        server.shutdown(); worker.join(timeout=3)


@pytest.mark.parametrize('reason', ['auth-required: restricted', 'ERROR: auth-required: restricted'])
@pytest.mark.parametrize('closure_first', [False, True])
def test_primal_inbox_finishes_auth_after_initial_subscription_closure(
        codec, monkeypatch, reason, closure_first):
    monkeypatch.setattr(n, 'PRIMAL_RELEASE_READY', True)
    frames = []
    def handler(ws):
        request = json.loads(ws.recv(timeout=3)); frames.append(request)
        challenge = ['AUTH', 'synthetic-inbox-challenge']
        closed = ['CLOSED', request[1], reason]
        for frame in ((closed, challenge) if closure_first else (challenge, closed)):
            ws.send(t.canonical(frame).decode())
        response = json.loads(ws.recv(timeout=3)); frames.append(response)
        assert response[0] == 'AUTH'
        signed = response[1]; codec.keyer.verify(signed, 22242)
        assert signed['pubkey'] == C and signed['content'] == ''
        assert signed['tags'] == [['relay', url], ['challenge', 'synthetic-inbox-challenge']]
        ws.send(t.canonical(['OK', signed['id'], True, 'accepted']).decode())
        repeated = json.loads(ws.recv(timeout=3)); frames.append(repeated)
        assert repeated == request
        ws.send(t.canonical(['EOSE', repeated[1]]).decode())
    with local_server(handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        url = f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        relay = n.PrimalRelay(codec.keyer, C, frozenset({O}), auth=True, local_test=True)
        assert relay.fetch(url, since=int(time.time())-60) == []
        assert len(frames) == 3 and frames[0] == frames[2]
        server.shutdown(); worker.join(timeout=3)


@pytest.mark.parametrize('reason', ['ERROR: blocked: forbidden', 'not auth-required:',
                                    'ERROR: ERROR: auth-required: nested', 'AUTH-REQUIRED:'])
def test_auth_reason_compatibility_does_not_match_other_errors(reason):
    assert m.auth_required_reason(reason) is False
