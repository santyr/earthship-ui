"""Pure guard tests; no REST calls or provider mutations."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('bitcoin_migration',
    Path(__file__).with_name('migrate-bitcoin-change-item.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MigrationGuards(unittest.TestCase):
    def test_decimal_formatting_preserves_exact_value(self):
        self.assertTrue(m.same_number('-0.120000000','-0.12'))
        self.assertFalse(m.same_number('0.120000001','0.12'))

    def test_unknown_nonfinite_and_missing_never_match(self):
        for state in ('NULL','UNDEF','NaN','Infinity','',None):
            self.assertFalse(m.same_number(state,'0'))

    def test_wait_allows_transient_null_before_restoration(self):
        base={**m.EXPECTED,'editable':False,'metadata':{},'stateDescription':{'pattern':'%.2f %%'}}
        with patch.object(m,'item',side_effect=[{**base,'state':'NULL'},
                                               {**base,'state':'1.000'}]), \
             patch.object(m.time,'sleep'):
            m.wait(False,'1')

    def test_category_none_equivalent_but_label_difference_rejected(self):
        m.validate({**m.EXPECTED,'category':None,'stateDescription':{'pattern':'%.2f %%'}})
        with self.assertRaises(ValueError):
            m.validate({**m.EXPECTED,'label':'different'})

    def test_wrong_provider_cannot_pass_state_restoration(self):
        with patch.object(m,'item',return_value={**m.EXPECTED,'editable':True,'state':'1'}), \
             patch.object(m.time,'sleep'):
            with self.assertRaises(RuntimeError):m.wait(False,'1')

    def test_original_rollback_and_normalized_format_are_distinct(self):
        m.validate(m.ORIGINAL, False)
        with self.assertRaises(ValueError):m.validate(m.ORIGINAL)
        with self.assertRaises(ValueError):m.validate({**m.EXPECTED,'stateDescription':{'pattern':'%.0f'}})


if __name__=='__main__':unittest.main()
