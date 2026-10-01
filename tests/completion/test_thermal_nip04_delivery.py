"""Real loopback WebSockets and disposable-key signatures; no public relays."""
from datetime import timedelta
import json
import threading

import pytest

from test_thermal_nip04_ledger import codec, signed, policy, queue, C, O, NOW
import thermal_confirmation as t
import thermal_messaging as m
import thermal_nip04 as n


def local_server(handler):
    from websockets.sync.server import serve
    return serve(handler,'127.0.0.1',0,compression=None)


def test_kind4_publication_requires_exact_signed_event_ack(codec, monkeypatch):
    assert hasattr(n,'PrimalRelay'), 'bounded Primal relay is not implemented'
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    outgoing=signed(codec,monkeypatch,'synthetic question',outgoing=True)
    messages=[]
    def handler(ws):
        frame=json.loads(ws.recv(timeout=3)); messages.append(frame)
        ws.send(t.canonical(['OK',frame[1]['id'],True,'accepted']).decode())
    with local_server(handler) as server:
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        url=f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        n.PrimalRelay(codec.keyer,C,frozenset({O}),local_test=True).publish(url,outgoing)
        server.shutdown(); worker.join(timeout=3)
    assert messages==[['EVENT',outgoing]]


def test_kind4_fetch_uses_author_recipient_kind_and_time_filter(codec, monkeypatch):
    assert hasattr(n,'PrimalRelay'), 'bounded Primal relay is not implemented'
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(m.time,'time',lambda:NOW.timestamp())
    reply=signed(codec,monkeypatch,'yes '+policy().prompts[0].event_id)
    filters=[]
    def handler(ws):
        request=json.loads(ws.recv(timeout=3)); filters.append(request[2]); sid=request[1]
        ws.send(t.canonical(['EVENT',sid,reply]).decode())
        ws.send(t.canonical(['EOSE',sid]).decode())
    with local_server(handler) as server:
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        url=f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        result=n.PrimalRelay(codec.keyer,C,frozenset({O}),local_test=True).fetch(
            url,since=int((NOW-timedelta(minutes=5)).timestamp()))
        server.shutdown(); worker.join(timeout=3)
    assert result==[reply]
    assert filters==[{'kinds':[4],'authors':[O],'#p':[C],
                     'since':int((NOW-timedelta(minutes=5)).timestamp()),
                     'until':int(NOW.timestamp()),'limit':64}]


def test_primal_relay_default_off_refuses_before_connect(monkeypatch):
    assert hasattr(n,'PrimalRelay'), 'bounded Primal relay is not implemented'
    monkeypatch.setattr(m.time,'time',lambda:NOW.timestamp())
    relay=n.PrimalRelay(None,C,frozenset({O}))
    with pytest.raises(t.Refused,match='release'):
        relay.publish('wss://relay.example',{})
    with pytest.raises(t.Refused,match='release'):
        relay.fetch('wss://relay.example',since=int(NOW.timestamp()))


@pytest.mark.parametrize('tamper',['signature','recipient','author','kind'])
def test_invalid_incoming_envelope_cannot_escape_relay_validation(codec, monkeypatch, tamper):
    assert hasattr(n,'PrimalRelay'), 'bounded Primal relay is not implemented'
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(m.time,'time',lambda:NOW.timestamp())
    event=signed(codec,monkeypatch,'synthetic invalid-scope fixture')
    if tamper=='signature':
        event['sig']='0'*128
    else:
        fields={key:value for key,value in event.items() if key not in {'id','sig'}}
        if tamper=='recipient': fields['tags']=[['p',O]]
        if tamper=='author':
            monkeypatch.setenv('NOSTR_SECRET_KEY',format(2,'064x')); fields['pubkey']=C
        if tamper=='kind': fields['kind']=14
        else: fields['kind']=4
        if tamper!='author': monkeypatch.setenv('NOSTR_SECRET_KEY',format(1,'064x'))
        event=t.strict_json(codec.keyer.call(['event'],t.canonical(fields)+b'\n',identity=True))
        monkeypatch.setenv('NOSTR_SECRET_KEY',format(2,'064x'))
    def handler(ws):
        request=json.loads(ws.recv(timeout=3))
        ws.send(t.canonical(['EVENT',request[1],event]).decode())
        ws.send(t.canonical(['EOSE',request[1]]).decode())
    with local_server(handler) as server:
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        url=f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        with pytest.raises(t.Refused):
            n.PrimalRelay(codec.keyer,C,frozenset({O}),local_test=True).fetch(
                url,since=int((NOW-timedelta(minutes=5)).timestamp()))
        server.shutdown(); worker.join(timeout=3)


class FixtureCodec(n.Nip04Codec):
    """Only synthetic outbound fixture construction uses stock argv encryption.

    Incoming verification/decryption and all stored signatures remain real.
    This adapter is not production stdin-encoder qualification.
    """
    def __init__(self, codec, monkeypatch):
        super().__init__(codec.keyer)
        self.base, self.patch = codec, monkeypatch

    def encode(self, text, *, author, recipient, created_at):
        assert author==C and recipient==O
        return signed(self.base,self.patch,text,outgoing=True,
                      at=NOW.fromtimestamp(created_at,NOW.tzinfo))


def routes(codec, monkeypatch, p, url):
    announcements=[]
    for scalar,public in ((1,O),(2,C)):
        monkeypatch.setenv('NOSTR_SECRET_KEY',format(scalar,'064x'))
        announcements.append(t.strict_json(codec.keyer.call(['event'],t.canonical({
            'kind':10050,'pubkey':public,'created_at':int((NOW-timedelta(minutes=10)).timestamp()),
            'content':'','tags':[['relay',url]]})+b'\n',identity=True)))
    monkeypatch.setenv('NOSTR_SECRET_KEY',format(2,'064x'))
    return m.Routes(t.canonical({'version':1,'announcements':announcements}),p,codec.keyer,local_test=True)


class ReceiptSink:
    """Explicit external-journal double; real PostgreSQL is covered separately."""
    def __init__(self):
        self.records={}
        self.fail=False
    def require_v2_storage(self):
        pass
    def store(self, records, payload, *, vocabulary_version):
        assert vocabulary_version==2 and t.strict_json(payload)['kind']==4
        if self.fail: raise t.Retryable('synthetic journal outage')
        key=records[0]['idempotency_key']; value=(records,payload)
        assert key not in self.records or self.records[key]==value
        self.records[key]=value


def test_primal_delivery_persists_one_cipher_across_retry_and_restart(codec, monkeypatch, tmp_path):
    assert hasattr(n,'PrimalDelivery') and hasattr(n,'PrimalOutbox'), 'Primal coordinator is not implemented'
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(m.time,'time',lambda:NOW.timestamp())
    received=[]
    def handler(ws):
        frame=json.loads(ws.recv(timeout=3)); received.append(frame[1])
        ws.send(t.canonical(['OK',frame[1]['id'],len(received)>1,'test']).decode())
    root=tmp_path/'state'; ledger=n.PrimalLedger(root); outbox=n.PrimalOutbox(root)
    try:
        with local_server(handler) as server:
            worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            url=f'ws://127.0.0.1:{server.socket.getsockname()[1]}'; p=policy()
            signed_routes=routes(codec,monkeypatch,p,url)
            relay=n.PrimalRelay(codec.keyer,C,p.operators,local_test=True)
            d=n.PrimalDelivery(p,signed_routes,ledger,outbox,FixtureCodec(codec,monkeypatch),relay,ReceiptSink())
            d.queue_prompts(NOW)
            original=ledger.question(p,p.prompts[0].event_id,codec)
            assert d.flush(NOW)['retryable']==1
            ledger.close(); outbox.close()
            ledger=n.PrimalLedger(root); outbox=n.PrimalOutbox(root)
            d=n.PrimalDelivery(p,signed_routes,ledger,outbox,FixtureCodec(codec,monkeypatch),relay,ReceiptSink())
            assert d.flush(NOW+timedelta(seconds=5))['deferred']==1
            assert d.flush(NOW+timedelta(seconds=11))['relay_acceptances']==1
            assert received==[original,original]
            assert d.flush(NOW+timedelta(seconds=12))['relay_acceptances']==0
            server.shutdown(); worker.join(timeout=3)
    finally:
        outbox.close(); ledger.close()


def test_poll_commit_ack_and_restart_recover_same_receipt_without_duplicates(codec, monkeypatch, tmp_path):
    assert hasattr(n,'PrimalDelivery') and hasattr(n,'PrimalOutbox'), 'Primal coordinator is not implemented'
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(m.time,'time',lambda:NOW.timestamp())
    root=tmp_path/'state'; ledger=n.PrimalLedger(root); outbox=n.PrimalOutbox(root)
    p=policy(); q=queue(ledger,codec,monkeypatch,p)
    reply=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id,extra=(['e',q['id']],))
    received=[]
    def handler(ws):
        frame=json.loads(ws.recv(timeout=3))
        if frame[0]=='REQ':
            ws.send(t.canonical(['EVENT',frame[1],reply]).decode())
            ws.send(t.canonical(['EOSE',frame[1]]).decode())
        else:
            received.append(frame[1]); ws.send(t.canonical(['OK',frame[1]['id'],True,'stored']).decode())
    sink=ReceiptSink()
    try:
        with local_server(handler) as server:
            worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            url=f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
            signed_routes=routes(codec,monkeypatch,p,url)
            relay=n.PrimalRelay(codec.keyer,C,p.operators,local_test=True)
            d=n.PrimalDelivery(p,signed_routes,ledger,outbox,FixtureCodec(codec,monkeypatch),relay,sink)
            assert d.poll_replies(NOW)['accepted']==1
            first=ledger.get(reply['id'])
            assert first['acknowledgement'] is not None
            assert len(sink.records)==1
            assert d.poll_replies(NOW)['accepted']==0
            # The queued ACK is an actual signed kind4 cipher and survives reopen.
            queued=outbox.rows()[0]; envelope=t.strict_json(queued['wrapped'].encode())
            ledger.close(); outbox.close()
            ledger=n.PrimalLedger(root); outbox=n.PrimalOutbox(root)
            d=n.PrimalDelivery(p,signed_routes,ledger,outbox,FixtureCodec(codec,monkeypatch),relay,sink)
            assert d.recover_acks(NOW+timedelta(hours=2))['retryable']==0
            assert d.flush(NOW+timedelta(hours=2))['relay_acceptances']==1
            assert received==[envelope] and ledger.get(reply['id'])==first
            monkeypatch.setenv('NOSTR_SECRET_KEY',format(1,'064x'))
            clear=codec.decode(t.canonical(envelope),recipient=O,authors=frozenset({C}))
            assert t.canonical(t.strict_json(first['acknowledgement'].encode())).decode() in clear.plaintext
            monkeypatch.setenv('NOSTR_SECRET_KEY',format(2,'064x'))
            server.shutdown(); worker.join(timeout=3)
    finally:
        outbox.close(); ledger.close()


def test_primal_coordinator_default_off_refuses_before_dependencies():
    assert hasattr(n,'PrimalDelivery'), 'Primal coordinator is not implemented'
    with pytest.raises(t.Refused,match='release'):
        n.PrimalDelivery(None,None,None,None,None,None,None)


@pytest.mark.parametrize('deadline',[float('nan'),float('inf'),True,-1])
def test_deadline_refuses_without_opening_a_connection(codec, monkeypatch, deadline):
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    event=signed(codec,monkeypatch,'synthetic deadline fixture',outgoing=True)
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append(args); raise AssertionError('must not connect')
    relay=n.PrimalRelay(codec.keyer,C,frozenset({O}),connect=forbidden)
    with pytest.raises(t.Refused,match='deadline'):
        relay.publish('wss://relay.example',event,deadline=deadline)
    assert calls==[]


def test_journal_failure_leaves_reply_retryable_and_recovers_ack_after_expiry(codec, monkeypatch, tmp_path):
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(m.time,'time',lambda:NOW.timestamp())
    p=policy(); root=tmp_path/'state'; ledger=n.PrimalLedger(root); outbox=n.PrimalOutbox(root)
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        relay=n.PrimalRelay(codec.keyer,C,p.operators,local_test=True)
        signed_routes=routes(codec,monkeypatch,p,'ws://127.0.0.1:9999')
        sink=ReceiptSink(); sink.fail=True
        d=n.PrimalDelivery(p,signed_routes,ledger,outbox,FixtureCodec(codec,monkeypatch),relay,sink)
        with pytest.raises(t.Retryable):
            d.receive(t.canonical(event),NOW)
        first=ledger.get(event['id'])
        assert first['acknowledgement'] is None and outbox.rows()==[]
        assert not outbox.ingress_recorded(event)
        sink.fail=False
        assert d.recover_acks(NOW+timedelta(hours=2))==dict(retryable=0,withheld=0,deferred=0)
        assert len(outbox.rows())==1 and len(sink.records)==1
        assert ledger.get(event['id'])['first_received_at']==first['first_received_at']
    finally:
        outbox.close(); ledger.close()


def test_primal_outbox_rejects_legacy_unsigned_intents(tmp_path):
    outbox=n.PrimalOutbox(tmp_path/'state'); p=policy()
    try:
        with pytest.raises(t.Refused,match='kind4'):
            outbox.queue('prompt:'+p.prompts[0].event_id,t.prompt_event(p.prompts[0],C),C,O)
        assert outbox.rows()==[]
        assert not (tmp_path/'state'/'delivery.sqlite3').exists()
    finally:
        outbox.close()


@pytest.mark.parametrize('stale', ['expired', 'removed'])
def test_stale_questions_do_not_starve_a_later_active_delivery(codec, monkeypatch, tmp_path, stale):
    """A batch-sized stale prefix must not indefinitely hide active ciphertext."""
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    prompts=[{'operator':O,
              'issued_at':(NOW-timedelta(minutes=60+i)).isoformat(),
              'expires_at':(NOW-timedelta(minutes=1)).isoformat(),
              'actions':{'window':'open'}} for i in range(16)]
    prompts.append({'operator':O,'issued_at':(NOW-timedelta(minutes=5)).isoformat(),
                    'expires_at':(NOW+timedelta(minutes=30)).isoformat(),
                    'actions':{'window':'closed'}})
    retained=t.Policy.load(t.canonical({'version':2,'recipient':C,'operators':[O],
                                       'prompts':prompts}),assign_ids=True)
    current=retained if stale=='expired' else t.Policy(C,frozenset({O}),(retained.prompts[-1],),2)
    root=tmp_path/'state'; ledger=n.PrimalLedger(root); outbox=n.PrimalOutbox(root)
    received=[]
    def handler(ws):
        frame=json.loads(ws.recv(timeout=3)); received.append(frame[1])
        ws.send(t.canonical(['OK',frame[1]['id'],True,'stored']).decode())
    try:
        for prompt in retained.prompts:
            event=signed(codec,monkeypatch,n.question_text(retained,prompt.event_id),
                         outgoing=True,at=prompt.issued_at)
            ledger.queue_question(event,retained,prompt.event_id,codec)
            outbox.queue_cipher('prompt',prompt.event_id,event,codec,C,O)
        active=ledger.question(current,current.prompts[-1].event_id,codec)
        with local_server(handler) as server:
            worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            url=f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
            relay=n.PrimalRelay(codec.keyer,C,current.operators,local_test=True)
            d=n.PrimalDelivery(current,routes(codec,monkeypatch,current,url),ledger,outbox,
                              FixtureCodec(codec,monkeypatch),relay,ReceiptSink())
            result=d.flush(NOW)
            server.shutdown(); worker.join(timeout=3)
        assert result==dict(relay_acceptances=1,retryable=0,withheld=16,deferred=0)
        assert received==[active]
        assert len(outbox.rows())==17  # No evidence is erased to make progress.
    finally:
        outbox.close(); ledger.close()
