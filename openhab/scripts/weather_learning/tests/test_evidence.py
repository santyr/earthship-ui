from datetime import datetime,timedelta,timezone
import unittest
from weather_learning.evidence import EvidenceWindow,audit_evidence
T=datetime(2026,10,10,tzinfo=timezone.utc)
class Reader:
 def __init__(self,rows,issues=()):self.rows=rows;self.issues=issues
 def windows(self,start,end):return iter(self.rows)
 def original_issues(self,start,end):return iter(self.issues)
def window(**kwargs):
 values=dict(variable='temperature',source_identity='Weather_Temperature_Evidence_JSON:outdoor',start=T,end=T+timedelta(days=1),cutover=T,assessed_at=T+timedelta(days=2),source_digest='a'*64,hardware_epoch='outdoor-phase-1',qualification='qualified',fully_covered=True)
 return EvidenceWindow(**(values|kwargs))
class EvidenceTests(unittest.TestCase):
 def test_audit_separates_qualified_and_diagnostic_rows(self):
  r=audit_evidence(Reader([window(),window(qualification='diagnostic'),{'value':72}]),T,T+timedelta(days=2))
  self.assertEqual(r['variables']['temperature']['qualified_windows'],1)
  self.assertEqual(r['rejected_rows'],2)
 def test_audit_keeps_hardware_epochs_separate(self):
  r=audit_evidence(Reader([window(),window(hardware_epoch='outdoor-phase-2')]),T,T+timedelta(days=2))
  self.assertEqual(len(r['variables']['temperature']['by_hardware_epoch']),2)
  self.assertEqual(r['variables']['temperature']['maximum_single_epoch_windows'],1)
 def test_partial_activation_and_unfinished_days_excluded(self):
  r=audit_evidence(Reader([window(cutover=T+timedelta(hours=1)),window(fully_covered=False),window(assessed_at=T+timedelta(hours=1))]),T,T+timedelta(days=2))
  self.assertEqual(r['rejected_rows'],3)
  self.assertEqual(r['variables'],{})
 def test_missing_original_forecast_issue_is_not_reconstructed_from_current_state(self):
  r=audit_evidence(Reader([window()]),T,T+timedelta(days=2))
  self.assertEqual(r['original_forecast_issues'],0)
  self.assertEqual(r['prospective_paired_windows'],0)
 def test_duplicate_window_does_not_inflate_counts(self):
  r=audit_evidence(Reader([window(),window()]),T,T+timedelta(days=2))
  self.assertEqual(r['variables']['temperature']['qualified_windows'],1)
 def test_naive_or_oversized_range_refused(self):
  with self.assertRaises(ValueError):audit_evidence(Reader([]),T.replace(tzinfo=None),T+timedelta(days=2))
  with self.assertRaises(ValueError):audit_evidence(Reader([]),T,T+timedelta(days=367))
if __name__=='__main__':unittest.main()

class ConflictingEvidenceTests(unittest.TestCase):
 def test_conflicting_proof_for_same_window_refused(self):
  with self.assertRaises(ValueError):
   audit_evidence(Reader([window(),window(source_digest='b'*64)]),T,T+timedelta(days=2))
