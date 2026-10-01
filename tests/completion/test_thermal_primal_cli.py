"""Explicit Primal command boundaries; no household identities or public relay."""
from datetime import datetime, timedelta
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_thermal_nip04_ledger import codec, signed, policy, C, O, NOW
from test_thermal_nip04_delivery import FixtureCodec, ReceiptSink
import thermal_confirmation as t
import thermal_messaging as m
import thermal_nip04 as n


@pytest.fixture(autouse=True)
def command_clock(monkeypatch):
    class Clock(datetime):
        current=NOW
        @classmethod
        def now(cls,tz=None):
            return cls.current
    monkeypatch.setattr(n,'datetime',Clock)
    return Clock


def command():
    path=Path(__file__).resolve().parents[2]/'openhab/scripts/thermal_primal.py'
    assert path.is_file(), 'explicit Primal command is not implemented'
    return importlib.import_module('thermal_primal')


@pytest.mark.parametrize('mode',['--send-prompts','--poll-replies','--process-reply','--flush'])
def test_mutating_modes_refuse_before_config_signer_or_state_access(tmp_path, capsys, mode):
    cli=command()
    assert cli.main([mode,'--state-dir',str(tmp_path/'absent'),
                     '--nak','/does/not/exist'])==2
    result=capsys.readouterr()
    assert result.out=='' and 'refused' in result.err
    assert not (tmp_path/'absent').exists()


def private_config(codec, monkeypatch, tmp_path, *, vocabulary=2):
    p=policy()
    if vocabulary==1:
        draft={'version':1,'recipient':C,'operators':[O],'prompts':[{
            'operator':O,'issued_at':(NOW-timedelta(minutes=5)).isoformat(),
            'expires_at':(NOW+timedelta(minutes=30)).isoformat(),'actions':{'vent':'closed'}}]}
        p=t.Policy.load(t.canonical(draft),assign_ids=True)
    directory=tmp_path/'config'; directory.mkdir(mode=0o700)
    policy_path=directory/'policy.json'; policy_path.write_bytes(t.canonical({
        'version':p.version,'recipient':C,'operators':[O],
        'prompts':[prompt.snapshot() for prompt in p.prompts]})); policy_path.chmod(0o600)
    announcements=[]
    for scalar,public in ((1,O),(2,C)):
        monkeypatch.setenv('NOSTR_SECRET_KEY',format(scalar,'064x'))
        announcements.append(t.strict_json(codec.keyer.call(['event'],t.canonical({
            'kind':10050,'pubkey':public,'created_at':int(NOW.timestamp()),
            'content':'','tags':[['relay','wss://relay.example']]})+b'\n',identity=True)))
    monkeypatch.setenv('NOSTR_SECRET_KEY',format(2,'064x'))
    route_path=directory/'routes.json'
    route_path.write_bytes(t.canonical({'version':1,'announcements':announcements})); route_path.chmod(0o600)
    return p,policy_path,route_path


def arguments(policy_path, route_path, state, mode='--check-config'):
    return [mode,'--policy',str(policy_path),'--routes',str(route_path),
            '--state-dir',str(state),'--nak',str(m.DEFAULT_NAK),
            '--nak-sha256',m.DEFAULT_SHA256,'--nak-version','nak version v0.20.7']


def test_config_check_verifies_real_public_routes_without_identity_or_state(codec, monkeypatch, tmp_path, capsys):
    cli=command(); p,policy_path,route_path=private_config(codec,monkeypatch,tmp_path)
    monkeypatch.delenv('NOSTR_SECRET_KEY')
    assert cli.main(arguments(policy_path,route_path,tmp_path/'absent'))==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='passed' and result['transport']=='nip04'
    assert result['signed_routes_verified'] is True and result['journal_writes']==0
    assert result['message_published'] is False and result['signer_identity_verified'] is False
    assert not (tmp_path/'absent').exists()


def test_empty_v2_policy_is_explicit_opt_in_and_legacy_remains_refused():
    raw=t.canonical({'version':2,'recipient':C,'operators':[O],'prompts':[]})
    with pytest.raises(t.Refused):
        t.Policy.load(raw)
    configured=t.Policy.load(raw,allow_empty=True)
    assert configured.version==2 and configured.prompts==()
    with pytest.raises(t.Refused):
        t.Policy.load(t.canonical({'version':1,'recipient':C,'operators':[O],'prompts':[]}),
                      allow_empty=True)


def test_primal_config_accepts_inactive_empty_policy_without_question_or_state(
        codec,monkeypatch,tmp_path,capsys):
    cli=command(); _,policy_path,route_path=private_config(codec,monkeypatch,tmp_path)
    policy_path.write_bytes(t.canonical({'version':2,'recipient':C,'operators':[O],'prompts':[]}))
    monkeypatch.delenv('NOSTR_SECRET_KEY')
    assert cli.main(arguments(policy_path,route_path,tmp_path/'absent'))==0
    result=json.loads(capsys.readouterr().out)
    assert result['message_published'] is False and result['journal_writes']==0
    assert not (tmp_path/'absent').exists()


@pytest.mark.parametrize('bad',['legacy','signature','permissions','version'])
def test_invalid_configuration_cannot_create_state(codec, monkeypatch, tmp_path, capsys, bad):
    cli=command(); p,policy_path,route_path=private_config(codec,monkeypatch,tmp_path,
                                                        vocabulary=1 if bad=='legacy' else 2)
    args=arguments(policy_path,route_path,tmp_path/'absent')
    if bad=='signature':
        raw=json.loads(route_path.read_bytes()); raw['announcements'][0]['sig']='0'*128
        route_path.write_bytes(t.canonical(raw))
    elif bad=='permissions': policy_path.chmod(0o644)
    elif bad=='version': args[-1]='nak version wrong'
    assert cli.main(args)==2
    assert capsys.readouterr().out=='' and not (tmp_path/'absent').exists()


def test_stock_signer_cannot_pass_primal_stdin_identity_challenge(codec, monkeypatch, tmp_path, capsys):
    cli=command(); p,policy_path,route_path=private_config(codec,monkeypatch,tmp_path)
    assert cli.main(arguments(policy_path,route_path,tmp_path/'absent','--check-keyer'))==2
    assert capsys.readouterr().out=='' and not (tmp_path/'absent').exists()


def test_invalid_arguments_never_echo_supplied_secret(capsys):
    cli=command()
    with pytest.raises(SystemExit) as exited:
        cli.main(['--unexpected-secret','synthetic-secret-do-not-print'])
    assert exited.value.code==2
    assert 'synthetic-secret-do-not-print' not in capsys.readouterr().err


def test_send_command_persists_cipher_and_retains_retry_status(codec, monkeypatch, tmp_path, capsys):
    """Only external journal/network and stock fixture encoder are doubled."""
    cli=command(); p,policy_path,route_path=private_config(codec,monkeypatch,tmp_path)
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(cli.m.Keyer,'check_identity',lambda self,c: {'signing_verified':c==C})
    monkeypatch.setattr(cli,'check_primal_identity',lambda keyer,collector: {'status':'passed'})
    monkeypatch.setattr(cli.n,'Nip04Codec',lambda keyer: FixtureCodec(codec,monkeypatch))
    monkeypatch.setattr(cli.t,'JournalSink',ReceiptSink)
    monkeypatch.setattr(cli,'utc_now',lambda:NOW)
    def unavailable(self,url,event,*,deadline=None):
        self.keyer.verify(event,4)
        assert event['pubkey']==C and t.tag_value(event,'p')==O
        raise t.Retryable('synthetic unavailable relay')
    monkeypatch.setattr(n.PrimalRelay,'publish',unavailable)
    state=tmp_path/'state'
    assert cli.main(arguments(policy_path,route_path,state,'--send-prompts'))==3
    result=json.loads(capsys.readouterr().out)
    assert result['retryable']==1 and result['relay_acceptances']==0
    assert result['operator_read_verified'] is False
    outbox=n.PrimalOutbox(state); ledger=n.PrimalLedger(state)
    try:
        rows=outbox.rows(); assert len(rows)==1 and rows[0]['attempts']==1
        assert t.strict_json(rows[0]['wrapped'].encode())==ledger.question(p,p.prompts[0].event_id,codec)
        assert not (state/'delivery.sqlite3').exists()
    finally:
        outbox.close(); ledger.close()


def test_real_process_default_off_exits_without_creating_state(tmp_path):
    command()
    script=Path(__file__).resolve().parents[2]/'openhab/scripts/thermal_primal.py'
    env={'PATH':os.defpath,'HOME':str(tmp_path),'PYTHONDONTWRITEBYTECODE':'1'}
    result=subprocess.run([sys.executable,str(script),'--poll-replies','--state-dir',str(tmp_path/'absent')],
                          env=env,capture_output=True,timeout=5)
    assert result.returncode==2 and result.stdout==b''
    assert not (tmp_path/'absent').exists()


@pytest.mark.parametrize('failure',['signer','journal','busy','event_missing'])
def test_startup_failure_leaves_no_new_databases(codec, monkeypatch, tmp_path, capsys, failure):
    cli=command(); p,policy_path,route_path=private_config(codec,monkeypatch,tmp_path)
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    def challenge(keyer,collector):
        if failure=='signer': raise t.Refused('synthetic identity mismatch')
        return {'status':'passed'}
    monkeypatch.setattr(cli,'check_primal_identity',challenge)
    class FailingSink(ReceiptSink):
        def require_v2_storage(self):
            if failure=='journal': raise t.Retryable('synthetic journal preflight failure')
    monkeypatch.setattr(cli.t,'JournalSink',FailingSink)
    state=tmp_path/'state'
    args=arguments(policy_path,route_path,state,
                   '--process-reply' if failure=='event_missing' else '--flush')
    if failure=='busy':
        with m.state_lock(state):
            assert cli.main(args)==3
    else:
        assert cli.main(args)==(2 if failure in {'signer','event_missing'} else 3)
    assert capsys.readouterr().out==''
    assert not (state/'primal.sqlite3').exists()
    assert not (state/'primal-delivery.sqlite3').exists()


def test_reply_command_journals_original_cipher_then_queues_receipt(codec, monkeypatch, tmp_path, capsys):
    cli=command(); p,policy_path,route_path=private_config(codec,monkeypatch,tmp_path)
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(cli,'check_primal_identity',lambda keyer,collector: {'status':'passed'})
    monkeypatch.setattr(cli.n,'Nip04Codec',lambda keyer: FixtureCodec(codec,monkeypatch))
    sink=ReceiptSink(); monkeypatch.setattr(cli.t,'JournalSink',lambda:sink)
    monkeypatch.setattr(cli,'utc_now',lambda:NOW)
    def unavailable(self,url,event,*,deadline=None):
        raise t.Retryable('synthetic unavailable relay')
    monkeypatch.setattr(n.PrimalRelay,'publish',unavailable)
    state=tmp_path/'state'; ledger=n.PrimalLedger(state)
    try:
        prompt=p.prompts[0]
        question=signed(codec,monkeypatch,n.question_text(p,prompt.event_id),
                        outgoing=True,at=prompt.issued_at)
        ledger.queue_question(question,p,prompt.event_id,codec)
    finally:
        ledger.close()
    event=signed(codec,monkeypatch,'yes '+prompt.event_id)
    event_path=policy_path.parent/'reply.json'
    event_path.write_bytes(t.canonical(event)); event_path.chmod(0o600)
    assert cli.main(arguments(policy_path,route_path,state,'--process-reply')+
                    ['--event-file',str(event_path)])==3
    result=json.loads(capsys.readouterr().out)
    assert result['retryable']==1 and result['operator_read_verified'] is False
    assert len(sink.records)==1
    records,payload=next(iter(sink.records.values()))
    assert payload==t.canonical(event)
    assert {record['idempotency_key'] for record in records}=={'nostr:'+event['id']}
    ledger=n.PrimalLedger(state); outbox=n.PrimalOutbox(state)
    try:
        assert ledger.get(event['id'])['acknowledgement'] is not None
        assert outbox.rows()[0]['intent']=='ack:'+event['id']
    finally:
        outbox.close(); ledger.close()


def test_command_rechecks_expiry_at_delivery_not_pass_start(codec, monkeypatch, tmp_path, capsys, command_clock):
    cli=command(); p,policy_path,route_path=private_config(codec,monkeypatch,tmp_path)
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(cli,'check_primal_identity',lambda keyer,collector: {'status':'passed'})
    monkeypatch.setattr(cli.n,'Nip04Codec',lambda keyer: FixtureCodec(codec,monkeypatch))
    monkeypatch.setattr(cli.t,'JournalSink',ReceiptSink)
    monkeypatch.setattr(cli,'utc_now',lambda:NOW)
    original=n.PrimalOutbox.queue_cipher
    def queue_then_elapsed(self,*args,**kwargs):
        original(self,*args,**kwargs)
        command_clock.current=NOW+timedelta(hours=1)
    monkeypatch.setattr(n.PrimalOutbox,'queue_cipher',queue_then_elapsed)
    published=[]
    def forbidden(self,url,event,*,deadline=None):
        published.append(event)
        raise t.Retryable('expired question must not be sent')
    monkeypatch.setattr(n.PrimalRelay,'publish',forbidden)
    assert cli.main(arguments(policy_path,route_path,tmp_path/'state','--send-prompts'))==2
    result=json.loads(capsys.readouterr().out)
    assert result['withheld']==1 and result['relay_acceptances']==0
    assert published==[]
