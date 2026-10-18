"""Read-only inventory over existing qualified source readers.

Readers supply validated windows, never raw numeric history. This inventory
records coverage; it does not authorize fitting, promotion, or equipment control.
"""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from itertools import islice
import re


def utc(value):
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError('aware timestamp required')
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class EvidenceWindow:
    variable:str
    source_identity:str
    start:datetime
    end:datetime
    cutover:datetime
    assessed_at:datetime
    source_digest:str
    hardware_epoch:str
    qualification:str
    fully_covered:bool

    def eligible(self,start,end):
        clocks=[utc(getattr(self,k)) for k in ('start','end','cutover','assessed_at')]
        first,last,cutover,assessed=clocks
        return (start<=first<last<=end and cutover<=first and last<=assessed
            and self.qualification=='qualified' and self.fully_covered is True
            and isinstance(self.source_digest,str) and re.fullmatch('[0-9a-f]{64}',self.source_digest)
            and all(isinstance(x,str) and 1<=len(x)<=256 for x in
                    (self.variable,self.source_identity,self.hardware_epoch)))


@dataclass(frozen=True)
class OriginalIssue:
    """A retained original issue; a current forecast cannot stand in for one."""
    provider:str
    issued_at:datetime
    available_at:datetime
    target_start:datetime
    target_end:datetime
    source_digest:str

    def eligible(self,start,end):
        issued,available,first,last=map(utc,(self.issued_at,self.available_at,self.target_start,self.target_end))
        return (available<=issued<=first<last and first<end and last>start
                and isinstance(self.provider,str) and 1<=len(self.provider)<=64
                and isinstance(self.source_digest,str) and re.fullmatch('[0-9a-f]{64}',self.source_digest))


def audit_evidence(reader,start,end):
    start,end=map(utc,(start,end))
    if not start<end or end-start>timedelta(days=366):
        raise ValueError('bounded increasing audit range required')
    result=dict(schema='earthship-weather-evidence-inventory/v1',start=start.isoformat(),end=end.isoformat(),
                variables={},rejected_rows=0,original_forecast_issues=0,prospective_paired_windows=0,
                qualification='not_assessed',automatic_actuation=False)
    windows=[];seen={}
    for index,row in enumerate(islice(reader.windows(start,end),10001)):
        if index==10000:raise ValueError('audit row cap exceeded')
        if not isinstance(row,EvidenceWindow) or not row.eligible(start,end):
            result['rejected_rows']+=1;continue
        key=(row.variable,row.source_identity,row.hardware_epoch,utc(row.start),utc(row.end))
        if key in seen:
            if seen[key]!=row.source_digest:raise ValueError('conflicting original window proof')
            continue
        seen[key]=row.source_digest;windows.append(row)
        variable=result['variables'].setdefault(row.variable,dict(qualified_windows=0,by_hardware_epoch={},maximum_single_epoch_windows=0))
        variable['qualified_windows']+=1
        phase=variable['by_hardware_epoch'].setdefault(row.hardware_epoch,dict(sources={},qualified_windows=0,first_start=utc(row.start).isoformat(),last_end=utc(row.end).isoformat()))
        phase['qualified_windows']+=1
        phase['sources'][row.source_identity]=phase['sources'].get(row.source_identity,0)+1
        phase['first_start']=min(phase['first_start'],utc(row.start).isoformat())
        phase['last_end']=max(phase['last_end'],utc(row.end).isoformat())
        variable['maximum_single_epoch_windows']=max(variable['maximum_single_epoch_windows'],phase['qualified_windows'])
    issues=[];seen_issues=set()
    for index,row in enumerate(islice(reader.original_issues(start,end),10001)):
        if index==10000:raise ValueError('original issue cap exceeded')
        if not isinstance(row,OriginalIssue) or not row.eligible(start,end):continue
        if row.source_digest in seen_issues:continue
        seen_issues.add(row.source_digest);issues.append(row)
    result['original_forecast_issues']=len(issues)
    result['prospective_paired_windows']=sum(any(utc(i.target_start)<=utc(w.start) and utc(w.end)<=utc(i.target_end) for i in issues) for w in windows)
    return result


def temperature_window(result,request,*,cutover):
    """Adapt the existing native daily validator; never duplicate its policy."""
    from daily_temperature_runtime import validate_result_v2
    phase=result.get('sensor_epoch')
    validated=validate_result_v2(result,request,sensor_epoch=phase)
    summary=validated['summary']
    return EvidenceWindow(variable='temperature',source_identity='Weather_Temperature_Evidence_JSON:outdoor',
        start=datetime.fromisoformat(request['start']),end=datetime.fromisoformat(request['end']),
        cutover=cutover,assessed_at=datetime.fromisoformat(request['assessed_at']),
        source_digest=summary['history_sha256'],hardware_epoch=phase,qualification='qualified',
        fully_covered=summary['fully_covered'])
