#!/usr/bin/env python3
"""DIS intake preflight. Uses the existing data contract; never calculates a KPI."""
from __future__ import annotations
import argparse
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from jsonschema import Draft202012Validator, FormatChecker

DEFAULT_CONTRACT=Path(__file__).resolve().parents[1]/'data_contract.json'
RECEIVED={'not_received','received_unmapped','mapped_partial','mapped'}
COVERAGE={'unknown','known_partial','known_complete'}
FK={
 'work_items':{'parent_work_item_id':'work_items','initiative_id':'initiatives','product_id':'products','team_id':'teams','calendar_id':'calendars'},
 'work_events':{'work_item_id':'work_items'},
 'commitments':{'work_item_id':'work_items'},
 'research_questions':{'initiative_id':'initiatives'},
 'decisions':{'initiative_id':'initiatives','research_question_ids':'research_questions'},
 'report_runs':{'source_batch_ids':'source_batches','supersedes_run_id':'report_runs'},
 'metric_results':{'report_run_id':'report_runs','population_id':'measurement_populations','source_batch_ids':'source_batches','product_scope_ids':'products','team_scope_ids':'teams','effect_protocol_id':'effect_protocols'}
}

def load(path):
    p=Path(path)
    if p.stat().st_size>64*1024*1024: raise ValueError('JSON exceeds the intake 64 MiB bound')
    return json.loads(p.read_text(encoding='utf-8'),parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))

def sha_file(path):
    before=Path(path).stat()
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    after=Path(path).stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('Source changed while hashing')
    return h.hexdigest()

def stamp(value):
    match=re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-](?P<offset_hour>\d{2}):(?P<offset_minute>\d{2}))',value)
    if not match: raise ValueError('Explicit RFC3339 timestamp is required')
    if match.group('offset_hour') is not None and (int(match.group('offset_hour'))>23 or int(match.group('offset_minute'))>59):
        raise ValueError('Timezone offset is out of RFC3339 range')
    if value.endswith('-00:00'): raise ValueError('Unknown timezone offset is not supported')
    dt=datetime.fromisoformat(value.replace('t','T').replace('z','Z').replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('Timezone offset is required')
    return dt

def format_checker():
    # These two formats are the contract's temporal formats. Register explicit
    # standard-library checks rather than silently omitting an optional checker.
    checker=FormatChecker()
    @checker.checks('date-time',raises=(ValueError,TypeError))
    def datetime_format(value):
        if not isinstance(value,str): return True
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})',value): return False
        if value.endswith('-00:00'): return False
        return stamp(value.replace('t','T').replace('z','Z')).tzinfo is not None
    @checker.checks('date',raises=(ValueError,TypeError))
    def date_format(value):
        if not isinstance(value,str): return True
        return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',value)) and date.fromisoformat(value) is not None
    return checker

def checked_path(root,relative):
    if not isinstance(relative,str) or '\\' in relative: raise ValueError('Invalid relative source path')
    rel=PurePosixPath(relative)
    if rel.is_absolute() or relative!=rel.as_posix() or any(x in {'.','..'} for x in rel.parts) or not rel.parts or ':' in rel.parts[0]:
        raise ValueError('Source path must stay inside files-root')
    root=Path(root).resolve(strict=True);p=root
    for part in rel.parts:
        p=p/part
        if p.is_symlink(): raise ValueError('Symlink source path is not allowed')
    if not p.resolve(strict=True).is_relative_to(root) or not p.is_file(): raise ValueError('Source file is unavailable')
    return p

def preflight(data,contract,intake,files_root,as_of):
    errors=[];notes=[];file_checks=[]
    def error(code,path,detail): errors.append({'code':code,'path':path,'detail':detail})
    Draft202012Validator.check_schema(contract)
    checker=format_checker()
    validator=Draft202012Validator(contract,format_checker=checker)
    for failure in validator.iter_errors(data):
        error('SCHEMA','/'.join(map(str,failure.absolute_path)),failure.message)
        if len(errors)>=100: break
    structure='fail' if errors else 'pass'
    if not isinstance(intake,dict): raise ValueError('Intake receipt metadata must be an object')
    selection=intake.get('selection',{});product=selection.get('product_id')
    scope_confirmed=selection.get('selection_status')=='confirmed' and isinstance(product,str) and bool(product)
    period_valid=False
    try:
        period=selection['period'];zone=ZoneInfo(period['report_timezone'])
        start=stamp(period['start']).astimezone(zone);end=stamp(period['end_exclusive']).astimezone(zone)
        after=(start.year+1,1) if start.month==12 else (start.year,start.month+1)
        expected=datetime(after[0],after[1],1,tzinfo=zone)
        if start.day!=1 or start.timetz().replace(tzinfo=None)!=time() or end!=expected: raise ValueError('Pilot period must be one whole calendar month')
        if date.fromisoformat(as_of)<end.date(): raise ValueError('Pilot month is not completed as of the supplied date')
        period_valid=True
    except (KeyError,TypeError,ValueError,ZoneInfoNotFoundError) as exc: error('PILOT_PERIOD','selection/period',str(exc))
    if not scope_confirmed: notes.append('pilot_product_not_confirmed; no department-wide extrapolation')

    statuses=intake.get('source_statuses',{})
    if not isinstance(statuses,dict): raise ValueError('source_statuses must be an object')
    for kind,entry in statuses.items():
        if not isinstance(entry,dict) or entry.get('received_status') not in RECEIVED or entry.get('coverage_status') not in COVERAGE:
            error('RECEIPT_STATE',f'source_statuses/{kind}','Unknown receipt or coverage state')
        elif entry['coverage_status']!='known_complete' and not entry.get('coverage_limitations'):
            error('COVERAGE',f'source_statuses/{kind}','Unknown/partial coverage needs an explicit limitation')
    receipts=intake.get('received_files',[])
    if not isinstance(receipts,list): raise ValueError('received_files must be a list')
    receipt_batches={};seen_paths=set()
    for i,receipt in enumerate(receipts):
        location=f'received_files/{i}'
        try:
            if not isinstance(receipt,dict): raise ValueError('Receipt must be an object')
            if set(receipt)!={'path','sha256','source_kind','source_batch_id','row_count'}: raise ValueError('Receipt fields: path, sha256, source_kind, source_batch_id, row_count')
            if receipt['path'] in seen_paths: raise ValueError('Duplicate file path in receipts')
            seen_paths.add(receipt['path'])
            if not isinstance(receipt['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',receipt['sha256']): raise ValueError('Expected SHA-256 must be 64 lowercase hex digits')
            if receipt['row_count'] is not None and (type(receipt['row_count']) is not int or receipt['row_count']<0): raise ValueError('row_count must be observed nonnegative integer or null')
            if receipt['source_kind'] not in contract['$defs']['source_batch']['properties']['source_kind']['enum']: raise ValueError('Unknown source_kind')
            path=checked_path(files_root,receipt['path']);actual=sha_file(path)
            if actual!=receipt['sha256']: raise ValueError('Raw source checksum mismatch')
            batch=receipt['source_batch_id']
            if batch is not None:
                if not isinstance(batch,str) or not batch or batch in receipt_batches: raise ValueError('Invalid or duplicate canonical source_batch_id; use explicit separate batches for separate files')
                receipt_batches[batch]=receipt
            file_checks.append({'path':receipt['path'],'sha256':actual,'bytes':path.stat().st_size,'row_count':receipt['row_count'],'row_count_check':'supplied_observation_not_reparsed','status':'bytes_verified'})
        except (OSError,ValueError,KeyError,TypeError) as exc: error('SOURCE_RECEIPT',location,str(exc))
    if structure=='pass':
        primary=contract['x-entity-primary-keys'];indices={}
        for entity,key in primary.items():
            index={}
            for i,row in enumerate(data.get(entity,[])):
                if row[key] in index: error('KEY-01',f'{entity}/{i}/{key}','Duplicate primary key')
                index[row[key]]=row
            indices[entity]=index
        for entity,key in primary.items():
            for i,row in enumerate(data.get(entity,[])):
                loc=f'{entity}/{i}'
                lineage=row.get('lineage')
                if lineage:
                    for batch in lineage['source_batch_ids']:
                        if batch not in indices['source_batches']: error('FK-01',loc+'/lineage/source_batch_ids','Unresolved source batch')
                for field,target in FK.get(entity,{}).items():
                    refs=row.get(field);refs=refs if isinstance(refs,list) else [refs]
                    for ref in refs:
                        if ref is not None and ref not in indices.get(target,{}): error('FK-01',loc+'/'+field,'Unresolved reference to '+target)
                if entity=='work_items' and scope_confirmed and row['product_id']!=product:
                    error('PILOT_SCOPE',loc+'/product_id','Work item has unknown or different product membership')
                for first,last in [('started_at','ended_at'),('started_at','final_accepted_at'),('accepted_request_at','started_at')]:
                    if row.get(first) is not None and row.get(last) is not None and stamp(row[first])>stamp(row[last]): error('TIME-01',loc,'Timestamp order '+first+' > '+last)
        for batch_id,batch in indices['source_batches'].items():
            receipt=receipt_batches.get(batch_id)
            if receipt is None: error('LINEAGE_RECEIPT','source_batches/'+batch_id,'No verified raw file receipt for canonical batch')
            elif batch['source_kind']!=receipt['source_kind']:
                error('LINEAGE_RECEIPT','source_batches/'+batch_id,'Canonical source kind differs from raw receipt')
            elif batch['content_checksum'] not in {receipt['sha256'],'sha256:'+receipt['sha256']}:
                error('LINEAGE_RECEIPT','source_batches/'+batch_id,'Canonical checksum does not match raw receipt')
            elif receipt['row_count'] is not None and batch['row_count']!=receipt['row_count']:
                error('LINEAGE_RECEIPT','source_batches/'+batch_id,'Canonical row count differs from supplied raw row count')
        for batch in receipt_batches:
            if batch not in indices['source_batches']: error('FK-01','received_files/source_batch_id','Mapped receipt has no canonical source batch')
        if scope_confirmed and product not in indices['products']: notes.append('selected_product_not_yet_normalized')
    rows={entity:len(data.get(entity,[])) for entity in contract['x-entity-primary-keys']} if isinstance(data,dict) and structure=='pass' else {}
    candidates={}
    requirements={
      'DP01':(['products','research_attempts','measurement_populations'],'First valid attempts, success/assistance rules, cohort membership and independent participants require metric-specific verification.'),
      'DO01':(['products','teams','initiatives','work_items','work_events','calendars','measurement_populations'],'Start/final acceptance, reopen sequence, business calendar and completed-work cohort require metric-specific verification.'),
      'DO02':(['work_items','commitments','measurement_populations'],'Original frozen commitment cohort, unchanged original due date and cancellation coverage require metric-specific verification.')
    }
    for metric,(entities,gate) in requirements.items():
        missing=[name for name in entities if not rows.get(name)]
        candidates[metric]={'status':'candidate_for_metric_checks' if not errors and not missing and scope_confirmed and period_valid else 'blocked_at_intake','missing_or_empty_entities':missing,'scope_confirmed':scope_confirmed,'additional_checks':gate,'value':None}
    if errors: status='invalid'
    elif not receipts: status='awaiting_sources'
    elif not scope_confirmed: status='awaiting_scope'
    elif not rows.get('work_items') and not rows.get('research_attempts'): status='awaiting_mapping'
    else: status='preflight_pass_metric_checks_pending'
    return {'schema':'dis-intake-preflight/1','as_of':as_of,'status':status,'canonical_structure':structure,'errors':errors,'notes':notes,
      'verified_raw_files':file_checks,'canonical_row_counts':rows,'metric_intake_readiness':candidates,
      'kpi_values':None,'publication_allowed_by_this_check':False,
      'implemented_checks':['existing JSON Schema with format checker','primary keys','source batch references and receipts','listed pilot foreign keys','selected work-item product scope','completed monthly selection','basic timestamp ordering'],
      'not_implemented':['complete x-semantic-checks set','all foreign keys outside the pilot entities','independent coverage/denominator verification','research study-to-product attribution','raw row parsing and normalization','reopen state machine','metric calculation','comparison/causal/economic publication gates'],
      'empty_data_meaning':'No normalized records supplied; this is never a zero KPI or proof of no activity.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',required=True);p.add_argument('--intake',required=True)
    p.add_argument('--contract',default=str(DEFAULT_CONTRACT));p.add_argument('--files-root',required=True)
    p.add_argument('--as-of',required=True);p.add_argument('--output')
    args=p.parse_args()
    try:
        result=preflight(load(args.data),load(args.contract),load(args.intake),args.files_root,args.as_of)
        text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
        if args.output:
            target=Path(args.output)
            if target.resolve() in {Path(args.data).resolve(),Path(args.intake).resolve(),Path(args.contract).resolve()}: raise ValueError('Output must not overwrite an input')
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if target.read_text(encoding='utf-8')!=text: raise ValueError('Output exists with different content; use a new report path')
            else:
                with target.open('x',encoding='utf-8') as handle: handle.write(text)
        print(json.dumps({'status':result['status'],'canonical_structure':result['canonical_structure'],'errors':len(result['errors']),'kpi_values':None},ensure_ascii=False))
        return 2 if result['status']=='invalid' else 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'error','error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__': raise SystemExit(main())
