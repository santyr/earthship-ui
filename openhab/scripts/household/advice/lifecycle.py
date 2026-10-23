"""Immutable as-issued reports and evidence-separated human feedback/evaluation."""
from collections import Counter
from datetime import timedelta
from ..codec import canonical,loads,identity
from ..control_contracts import instant
from ..evidence import utc
from .contracts import validate_report
from .shade_state import ShadeHistory

FEEDBACK_KINDS={'acknowledge','dismiss','snooze','report_action_taken','undo','target_observed'}


def feedback_status(rec,events,*,now):
    now=utc(now)
    rows=[e for e in events if e['episode_id']==rec['episode_id'] and instant(e['at'])<=now]
    undone={e['corrects'] for e in rows if e['kind']=='undo'}
    rows=[e for e in rows if e['event_id'] not in undone and e['kind']!='undo']
    if not rows:return 'unseen'
    event=rows[-1];kind=event['kind']
    if kind=='snooze':return 'snoozed' if now<instant(event['snooze_until']) else 'unseen'
    return {'dismiss':'dismissed','acknowledge':'seen','report_action_taken':'action_self_reported','target_observed':'target_observed'}.get(kind,'unseen')


class AdviceHistory(ShadeHistory):
    def __init__(self,path):
        super().__init__(path)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, at TEXT, raw BLOB, inputs BLOB, runtime BLOB)')
            db.execute('CREATE TABLE IF NOT EXISTS physical_feedback (id TEXT PRIMARY KEY, raw BLOB)')

    def retain(self,report,*,inputs,runtime):
        report=validate_report(report);raw=canonical(report);frozen=canonical(inputs);rt=canonical(runtime)
        if len(frozen)>2097152 or len(rt)>65536:raise ValueError('bounded retained source context required')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT raw,inputs,runtime FROM reports WHERE id=?',(report['report_id'],)).fetchone()
            if old:
                if tuple(bytes(x) for x in old)!=(raw,frozen,rt):raise ValueError('as-issued report or original context changed')
                return 'duplicate'
            if db.execute('SELECT count(*) FROM reports').fetchone()[0]>=4096:raise ValueError('advice history capacity exhausted')
            db.execute('INSERT INTO reports VALUES (?,?,?,?,?)',(report['report_id'],report['evaluated_at'],raw,frozen,rt))
            return 'retained'

    def reports(self):
        with self._connect() as db:return [loads(r[0]) for r in db.execute('SELECT raw FROM reports ORDER BY at,id')]

    def recent_reports(self,limit=128):
        if type(limit) is not int or not 1<=limit<=128:raise ValueError('bounded recent report window required')
        with self._connect() as db:return [loads(r[0]) for r in db.execute('SELECT raw FROM reports ORDER BY at DESC,id DESC LIMIT ?',(limit,))][::-1]

    def observe_targets(self,events,*,now):
        from .shade_state import target_observed
        now=utc(now);records=[]
        for report in self.recent_reports(32):
            for rec in report['recommendations']:
                if rec['kind']!='SHADE_POSITION' or now<instant(rec['decision_at']):continue
                spec=rec['action_spec'];targets={shade:spec['position_open_pct'] for shade in spec['shade_ids']}
                if not target_observed(events,targets,now=now):continue
                refs=[e['event_sha256'] for e in events if e['shade_id'] in targets]
                if any(not instant(rec['decision_at'])<=instant(e['observed_at'])<instant(rec['valid_until']) for e in events if e['shade_id'] in targets):continue
                event=dict(event_id=identity(['target_observed',rec['episode_id']]),episode_id=rec['episode_id'],kind='target_observed',at=now.isoformat(),
                    snooze_until=None,corrects=None,evidence_refs=refs,target=rec['target'],position_open_pct=spec['position_open_pct'],shade_ids=spec['shade_ids'],origin='device_observation',user_motivation_known=False,thermal_benefit_verified=False)
                with self._connect() as db:
                    db.execute('INSERT OR IGNORE INTO physical_feedback VALUES (?,?)',(event['event_id'],canonical(event)))
                    event=loads(db.execute('SELECT raw FROM physical_feedback WHERE id=?',(event['event_id'],)).fetchone()[0])
                records.append(event)
        return records


def evaluate_usefulness(reports,feedback,outcomes):
    for report in reports:validate_report(report)
    reasons=Counter();coverage={domain:Counter() for domain in ('shades','ventilation','energy')};episodes=set();recommendations=0
    for report in reports:
        recommendations+=len(report['recommendations']);episodes.update(r['episode_id'] for r in report['recommendations'])
        for domain,row in report['domains'].items():coverage[domain][row['status']]+=1;reasons[row['reason']]+=1
    counts=Counter(row['kind'] for row in feedback)
    return dict(schema='earthship-household-advice-evaluation/v1',report_count=len(reports),recommendation_count=recommendations,independent_episode_count=len(episodes),
        coverage={k:dict(v) for k,v in coverage.items()},withheld_reasons=dict(reasons),feedback_counts=dict(counts),observed_outcome_count=len(outcomes),
        acknowledgement_proves_action=False,user_report_proves_observed_target=False,position_proves_thermal_benefit=False,
        stale_action_rate=None,unwanted_reversal_rate=None,operator_burden_minutes=None,unchosen_alternatives_observed=False,causal_benefit_qualified=False,
        limitations=['Usage and action effects require independently retained observations; absent metrics are not zero.','No unchosen alternative is labeled as an observed outcome.'])
