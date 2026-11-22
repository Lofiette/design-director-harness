"""Synthetic fixtures only. No instance observations or KPI outputs are created."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from jsonschema import Draft202012Validator

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('intake',BASE/'validate_intake.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
CONTRACT=json.loads((BASE.parent/'data_contract.json').read_text())
PERIOD={'start':'2026-10-01T00:00:00+03:00','end_exclusive':'2026-11-01T00:00:00+03:00','report_timezone':'Europe/Moscow'}

def empty():
    return {'contract_version':'0.3.0','source_batches':[],'measurement_populations':[],'report_runs':[],'metric_results':[]}

def intake():
    return {'selection':{'product_id':None,'selection_status':'proposed','period':copy.deepcopy(PERIOD)},'source_statuses':{},'received_files':[]}

def report():
    return {'report_run_id':'synthetic-report','report_period':copy.deepcopy(PERIOD),'report_kind':'month','status':'draft','freeze_at':'2026-11-02T00:00:00Z','source_batch_ids':['synthetic-batch'],'metric_catalog_version':'0.3.0','calculation_code_version':'synthetic-v1','data_contract_version':'0.3.0','supersedes_run_id':None,'restatement_reason':None,'approved_by_role':None}

def lineage():
    return {'source_batch_ids':['synthetic-batch'],'source_record_ids':['synthetic-record'],'source_revision':'synthetic-v1','source_schema_version':'synthetic-v1','observed_at':'2026-11-02T00:00:00Z','ingested_at':'2026-11-02T00:00:00Z','transform_version':'synthetic-v1','evidence_refs':[]}

def batch(checksum):
    return {'source_batch_id':'synthetic-batch','source_system_id':'synthetic-source','source_kind':'tracker','source_locator':'synthetic.txt','source_revision':'synthetic-v1','source_schema_version':'synthetic-v1','extracted_at':'2026-11-02T00:00:00Z','coverage_period':copy.deepcopy(PERIOD),'coverage_description':'Synthetic unit test only','row_count':1,'content_checksum':checksum,'inventory_status':'declared_partial','verification_status':'not_checked','access_scope':'internal_restricted'}

def item():
    return {'work_item_id':'synthetic-task','parent_work_item_id':None,'initiative_id':'synthetic-init','product_id':'synthetic-product','team_id':'synthetic-team','work_class':'synthetic','complexity_rule':'synthetic-v1','complexity_class':None,'dod_version':'synthetic-v1','accepted_request_at':'2026-10-01T09:00:00Z','started_at':'2026-10-01T10:00:00Z','final_accepted_at':'2026-10-01T11:00:00Z','cancelled_at':None,'current_state':'accepted','calendar_id':'synthetic-calendar','lineage':lineage()}

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def run_check(self,data=None,meta=None): return mod.preflight(data or empty(),CONTRACT,meta or intake(),self.root,'2026-11-22')
    def errors(self,data=None,meta=None): return {x['code'] for x in self.run_check(data,meta)['errors']}
    def received(self):
        raw=b'SYNTHETIC TEST ONLY\n';(self.root/'synthetic.txt').write_bytes(raw)
        checksum=hashlib.sha256(raw).hexdigest();meta=intake()
        meta['received_files']=[{'path':'synthetic.txt','sha256':checksum,'source_kind':'tracker','source_batch_id':'synthetic-batch','row_count':1}]
        data=empty();data['source_batches']=[batch(checksum)]
        return data,meta
    def test_empty_valid_structure_is_awaiting_data_not_zero(self):
        r=self.run_check();self.assertEqual(r['canonical_structure'],'pass');self.assertEqual(r['status'],'awaiting_sources')
        self.assertIsNone(r['kpi_values']);self.assertFalse(r['publication_allowed_by_this_check'])
        self.assertTrue(all(x['value'] is None for x in r['metric_intake_readiness'].values()))
    def test_new_report_versions_pass_and_old_each_fail(self):
        data=empty();data['report_runs']=[report()]
        v=Draft202012Validator(CONTRACT,format_checker=mod.format_checker())
        self.assertFalse(list(v.iter_errors(data)))
        for key in ('metric_catalog_version','data_contract_version'):
            invalid=copy.deepcopy(data);invalid['report_runs'][0][key]='0.2'
            self.assertTrue(list(v.iter_errors(invalid)),key)
    def test_format_checker_rejects_impossible_date_and_unknown_offset(self):
        for value in ('2026-02-30T00:00:00Z','2026-11-02 00:00:00Z','2026-11-02T00:00:00-00:00','2026-11-02T00:00:00','2026-11-02T00:00:00+03:99','2026-11-02T00:00:00+00:60','2026-11-02T00:00:00-03:99','2026-11-02T00:00:00+24:00'):
            data=empty();data['report_runs']=[report()];data['report_runs'][0]['freeze_at']=value
            self.assertIn('SCHEMA',self.errors(data))
    def test_source_hash_tamper_and_missing_file_block(self):
        data,meta=self.received();(self.root/'synthetic.txt').write_bytes(b'changed')
        self.assertIn('SOURCE_RECEIPT',self.errors(data,meta))
        (self.root/'synthetic.txt').unlink();self.assertIn('SOURCE_RECEIPT',self.errors(data,meta))
    def test_duplicate_primary_keys_block(self):
        data,meta=self.received();data['source_batches'].append(copy.deepcopy(data['source_batches'][0]))
        self.assertIn('KEY-01',self.errors(data,meta))
    def test_dangling_lineage_and_work_event_reference_block(self):
        data=empty();data['work_events']=[{'work_event_id':'synthetic-event','work_item_id':'missing','occurred_at':'2026-10-02T00:00:00Z','event_type':'started','from_state':None,'to_state':'active','reason':None,'lineage':lineage()}]
        self.assertIn('FK-01',self.errors(data))
    def test_raw_batch_checksum_and_count_mismatch_block(self):
        data,meta=self.received();data['source_batches'][0]['content_checksum']='f'*64
        self.assertIn('LINEAGE_RECEIPT',self.errors(data,meta))
        data,meta=self.received();data['source_batches'][0]['row_count']=2
        self.assertIn('LINEAGE_RECEIPT',self.errors(data,meta))
    def test_raw_batch_source_kind_mismatch_blocks(self):
        data,meta=self.received();data['source_batches'][0]['source_kind']='research'
        self.assertIn('LINEAGE_RECEIPT',self.errors(data,meta))
    def test_traversal_and_symlink_rejected(self):
        data,meta=self.received();meta['received_files'][0]['path']='../synthetic.txt'
        self.assertIn('SOURCE_RECEIPT',self.errors(data,meta))
        (self.root/'link.txt').symlink_to(self.root/'synthetic.txt');meta['received_files'][0]['path']='link.txt'
        self.assertIn('SOURCE_RECEIPT',self.errors(data,meta))
    def test_uncompleted_month_blocks(self):
        meta=intake();meta['selection']['period']={'start':'2026-11-01T00:00:00+03:00','end_exclusive':'2026-12-01T00:00:00+03:00','report_timezone':'Europe/Moscow'}
        self.assertIn('PILOT_PERIOD',self.errors(meta=meta))
    def test_selected_product_mismatch_and_reversed_time_block(self):
        data,meta=self.received();data['work_items']=[item()]
        meta['selection'].update(product_id='different-product',selection_status='confirmed')
        data['work_items'][0]['final_accepted_at']='2026-10-01T08:00:00Z'
        found=self.errors(data,meta);self.assertIn('PILOT_SCOPE',found);self.assertIn('TIME-01',found)
    def test_verified_raw_without_records_remains_unmapped(self):
        data,meta=self.received();meta['selection'].update(product_id='synthetic-product',selection_status='confirmed')
        r=self.run_check(data,meta)
        self.assertEqual(r['status'],'awaiting_mapping');self.assertIsNone(r['kpi_values'])

if __name__=='__main__': unittest.main()
