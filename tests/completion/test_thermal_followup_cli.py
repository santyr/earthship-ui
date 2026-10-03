"""Recurring command: disposable keys/ledger and external reader/journal doubles."""
from datetime import date, timedelta
import json

import pytest

import thermal_confirmation as t
import thermal_followup as f
import thermal_nip04 as n
from test_thermal_followup import evidence
from test_thermal_nip04_ledger import codec, C, O, NOW, signed
from test_thermal_nip04_delivery import FixtureCodec, ReceiptSink
from test_thermal_primal_cli import private_config, arguments, command, command_clock


def recommendation(number=1):
    return evidence(advisory='close_up_tomorrow', day=date(2026, 9, 30),
                    issued=NOW-timedelta(hours=24), number=number, result_number=100+number)


def settings():
    return dict(version=1, activated_at=(NOW-timedelta(hours=30)).isoformat(),
                bank_epoch='test-bank', site_timezone='America/Denver', max_questions_per_day=1)


def setup(codec, monkeypatch, tmp_path):
    cli = command()
    _, base, routes = private_config(codec, monkeypatch, tmp_path)
    base.write_bytes(t.canonical(dict(version=2, recipient=C, operators=[O], prompts=[])))
    config = base.parent/'followup.json'
    config.write_bytes(t.canonical(settings())); config.chmod(0o600)
    monkeypatch.setattr(n, 'PRIMAL_RELEASE_READY', True)
    monkeypatch.setattr(f, 'AUTOMATIC_RELEASE_READY', True)
    monkeypatch.setattr(f, 'reader_dsn', lambda: 'external reader double')
    monkeypatch.setattr(f, 'read_publications', lambda config, now: [recommendation()])
    monkeypatch.setattr(cli, 'check_primal_identity', lambda keyer, collector: {'status': 'passed'})
    monkeypatch.setattr(cli, 'utc_now', lambda: NOW)
    monkeypatch.setattr(cli.n, 'Nip04Codec', lambda keyer: FixtureCodec(codec, monkeypatch))
    sink = ReceiptSink()
    monkeypatch.setattr(cli.t, 'JournalSink', lambda: sink)
    monkeypatch.setattr(n.PrimalRelay, 'fetch', lambda *args, **kwargs: [])
    published = []
    monkeypatch.setattr(n.PrimalRelay, 'publish', lambda self, url, event, **kwargs: published.append(event))
    state = tmp_path/'state'
    argv = arguments(base, routes, state, '--follow-recommendations') + ['--followup-config', str(config)]
    return cli, argv, state, sink, published


def test_automatic_gate_refuses_before_configuration_or_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(n, 'PRIMAL_RELEASE_READY', True)
    assert command().main(['--follow-recommendations', '--state-dir', str(tmp_path/'absent')]) == 2
    assert 'refused' in capsys.readouterr().err
    assert not (tmp_path/'absent').exists()


def test_idle_advice_polls_without_fabricating_a_question(codec, monkeypatch, tmp_path, capsys):
    cli, argv, state, sink, published = setup(codec, monkeypatch, tmp_path)
    monkeypatch.setattr(f, 'read_publications', lambda config, now: [evidence(advisory='none',
        day=date(2026, 9, 30), issued=NOW-timedelta(hours=24))])
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)['followup_status'] == 'idle'
    ledger = n.PrimalLedger(state)
    try:
        assert ledger.db.execute('SELECT count(*) FROM automatic_questions').fetchone()[0] == 0
        assert ledger.db.execute('SELECT count(*) FROM questions').fetchone()[0] == 0
    finally: ledger.close()
    assert published == [] and sink.records == {}


def test_real_question_cipher_and_daily_limit_survive_command_restart(codec, monkeypatch, tmp_path, capsys):
    cli, argv, state, sink, published = setup(codec, monkeypatch, tmp_path)
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)['followup_status'] == 'reserved_or_retained'
    assert len(published) == 1
    original = published[0]
    monkeypatch.setattr(f, 'read_publications', lambda config, now: [recommendation(2)])
    assert cli.main(argv) == 0
    capsys.readouterr()
    assert published == [original] and sink.records == {}
    ledger = n.PrimalLedger(state)
    try:
        assert ledger.db.execute('SELECT count(*) FROM automatic_questions').fetchone()[0] == 1
        assert ledger.db.execute('SELECT count(*) FROM questions').fetchone()[0] == 1
        p = f.combined_policy(ledger.db, policy=t.Policy.load(t.canonical(dict(
            version=2, recipient=C, operators=[O], prompts=[])), allow_empty=True))
        assert ledger.question(p, p.prompts[0].event_id, codec) == original
    finally: ledger.close()


@pytest.mark.parametrize('crash', ['reservation', 'ledger', 'outbox'])
def test_retry_keeps_question_id_and_original_cipher_at_each_crash_boundary(
        codec, monkeypatch, tmp_path, capsys, crash):
    cli, argv, state, sink, published = setup(codec, monkeypatch, tmp_path)
    if crash == 'reservation':
        original = FixtureCodec.encode
        monkeypatch.setattr(FixtureCodec, 'encode', lambda *args, **kwargs: (_ for _ in ()).throw(t.Retryable('fixture')))
    elif crash == 'ledger':
        original = n.PrimalOutbox.queue_cipher
        monkeypatch.setattr(n.PrimalOutbox, 'queue_cipher', lambda *args, **kwargs: (_ for _ in ()).throw(t.Retryable('fixture')))
    else:
        original = n.PrimalRelay.publish
        monkeypatch.setattr(n.PrimalRelay, 'publish', lambda *args, **kwargs: (_ for _ in ()).throw(t.Retryable('fixture')))
    assert cli.main(argv) == 3
    capsys.readouterr()
    ledger = n.PrimalLedger(state)
    try:
        reserved = f.retained_prompts(ledger.db, policy=t.Policy(C, frozenset({O}), (), 2))[0]
        questions = ledger.db.execute('SELECT original_event FROM questions').fetchall()
    finally: ledger.close()
    if crash == 'reservation': monkeypatch.setattr(FixtureCodec, 'encode', original)
    elif crash == 'ledger': monkeypatch.setattr(n.PrimalOutbox, 'queue_cipher', original)
    else: monkeypatch.setattr(n.PrimalRelay, 'publish', original)
    later = NOW+timedelta(minutes=5)
    monkeypatch.setattr(cli, 'utc_now', lambda: later)
    # The delivery clock is independently checked at actual publication.
    class Clock:
        @staticmethod
        def now(tz=None): return later
    monkeypatch.setattr(n, 'datetime', Clock)
    assert cli.main(argv) == 0
    capsys.readouterr()
    assert len(published) == 1
    ledger = n.PrimalLedger(state)
    try:
        assert f.retained_prompts(ledger.db, policy=t.Policy(C, frozenset({O}), (), 2)) == (reserved,)
        if questions:
            assert t.canonical(published[0]) == questions[0][0]
    finally: ledger.close()


@pytest.mark.parametrize('outage', ['unavailable', 'malformed'])
def test_reader_problem_does_not_block_existing_authenticated_reply(
        codec, monkeypatch, tmp_path, capsys, outage):
    cli, argv, state, sink, published = setup(codec, monkeypatch, tmp_path)
    assert cli.main(argv) == 0
    capsys.readouterr()
    ledger = n.PrimalLedger(state)
    try: prompt = f.retained_prompts(ledger.db, policy=t.Policy(C, frozenset({O}), (), 2))[0]
    finally: ledger.close()
    reply = signed(codec, monkeypatch, 'yes ' + prompt.event_id)
    monkeypatch.setattr(n.PrimalRelay, 'fetch', lambda *args, **kwargs: [reply])
    def failed(*args, **kwargs):
        raise t.Retryable('fixture unavailable') if outage == 'unavailable' else t.Refused('fixture malformed')
    monkeypatch.setattr(f, 'read_publications', failed)
    assert cli.main(argv) == (3 if outage == 'unavailable' else 2)
    result = json.loads(capsys.readouterr().out)
    assert result['accepted'] == 1
    assert len(sink.records) == 1 and len(published) == 2


def test_pinned_activation_drift_refuses_before_a_second_send(codec, monkeypatch, tmp_path, capsys):
    cli, argv, state, sink, published = setup(codec, monkeypatch, tmp_path)
    assert cli.main(argv) == 0
    capsys.readouterr()
    config = cli.Path(argv[-1])
    changed = settings(); changed['activated_at'] = (NOW-timedelta(hours=31)).isoformat()
    config.write_bytes(t.canonical(changed))
    assert cli.main(argv) == 2
    assert 'refused' in capsys.readouterr().err
    assert len(published) == 1 and sink.records == {}


def test_manual_reviewed_prompt_is_not_automatically_sent(codec, monkeypatch, tmp_path, capsys):
    cli, argv, state, sink, published = setup(codec, monkeypatch, tmp_path)
    from test_thermal_nip04_ledger import policy
    cli.Path(argv[argv.index('--policy')+1]).write_bytes(t.canonical(t.policy_object(policy())))
    assert cli.main(argv) == 0
    capsys.readouterr()
    assert published == [] and sink.records == {}
