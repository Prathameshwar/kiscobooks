"""Build findings, reusable cases, coverage and individual result CSVs from evidence."""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import xml.etree.ElementTree as ET
import argparse
import urllib.parse as urlparse
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'docs/testing/tenant-admin'
ARTIFACTS = ROOT / '.test_artifacts/tenant-admin-20261029'

def clean(value):
    value = re.sub(r'\x1b\[[0-9;]*m', '', str(value or ''))
    return value

def write(name, rows, fields):
    with (OUTPUT / name).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows({k: clean(v) for k, v in row.items()} for row in rows)

def main():
    global OUTPUT, ARTIFACTS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,default=ARTIFACTS)
    parser.add_argument('--report-dir',type=Path,default=OUTPUT)
    args=parser.parse_args()
    ARTIFACTS=args.artifacts.resolve();OUTPUT=args.report_dir.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    live = []
    for file in sorted(ARTIFACTS.rglob('*-results.json')):
        data = json.loads(file.read_text(encoding='utf-8'))
        for row in data.get('results', []):
            live.append({**row, 'run_evidence': file.relative_to(ROOT).as_posix()})
    canonical = {}
    for row in sorted(live, key=lambda r: r.get('started_utc', '')):
        global_case=row['id'].startswith(('TA-SHELL-','TA-THEME-','TA-VOUCHER-','TA-AUTH-','TA-TENANT-','TA-BOUNDARY-')) or row['id']=='TA-AUDIT-COMPANY-WRITES'
        key=(row['id'], '' if global_case else row.get('company', ''))
        previous=canonical.get(key)
        row['initial_status']=previous.get('initial_status',previous['status']) if previous else row['status']
        row['initial_actual']=previous.get('initial_actual',previous.get('actual','')) if previous else row.get('actual','')
        row['initial_evidence']=previous.get('initial_evidence',previous.get('evidence') or previous.get('run_evidence','')) if previous else row.get('evidence') or row.get('run_evidence','')
        row['retest_status']=row['status'] if previous else ''
        canonical[key] = row
    live = list(canonical.values())
    valid_inventory_keys={(item['company'],item['route']) for p in ARTIFACTS.rglob('surface-inventory-*.json') for item in json.loads(p.read_text(encoding='utf-8'))}
    for file in ARTIFACTS.rglob('authentication-redirect-inventory.json'):
        for item in json.loads(file.read_text(encoding='utf-8')):
            identifier='TA-ROUTE-'+item['company']+'-'+item['route']
            row=next((r for r in live if r['id']==identifier),None)
            # A later valid inventory proves the new UI check; older sign-in
            # pages can never establish a successful application route check.
            valid=(item['company'],item['route']) in valid_inventory_keys
            if row and not valid:
                row.update(status='BLOCKED',execution_level='INVALID_AUTHENTICATION_REDIRECT; intended feature not exercised',actual='Intended '+item['route']+' reached '+item['actualPath']+' after failed session refresh. Initial rendering-only PASS is invalid; fresh authenticated UI retest required.',evidence=file.relative_to(ROOT).as_posix())
    for row in live:
        if row.get('area')=='Voucher entry' and ('not built yet' in row.get('actual','') or 'Loading the sales bill' in row.get('actual','')):
            row['status']='BLOCKED';row['execution_level']='LIVE_UI_NAVIGATION; entry implementation unavailable or load not verified'
    automated = []
    for file in sorted(ARTIFACTS.rglob('*-results.csv')):
        if file.name=='console-results.csv' and (file.parent/'duplicate-console-cancelled.json').exists():
            continue
        with file.open(encoding='utf-8-sig', newline='') as stream:
            occurrences=Counter()
            for row in csv.DictReader(stream):
                key=(row['suite'],row['test']);occurrences[key]+=1;row['case_instance']=occurrences[key];automated.append(row)
    automated.sort(key=lambda row:row.get('started_utc',''))
    auto_canonical = {}
    for row in automated:
        key=(row['suite'], row['test'],row.get('case_instance',1))
        previous=auto_canonical.get(key)
        row['initial_status']=previous.get('initial_status',previous['status']) if previous else row['status']
        row['initial_evidence']=previous.get('initial_evidence',previous['evidence']) if previous else row['evidence']
        row['initial_actual']=previous.get('initial_actual',previous.get('actual','')) if previous else row.get('actual','')
        row['retest_status']=row['status'] if previous else ''
        auto_canonical[key]=row
    automated = list(auto_canonical.values())
    regression=ARTIFACTS/'audit-cursor-regression.xml'
    if regression.exists():
        for case in ET.parse(regression).iter('testcase'):
            issue=next((child for child in case if child.tag in ('failure','error','skipped')),None)
            automated.append({'suite':'audit-cursor-regression','test':case.get('classname','')+'::'+case.get('name',''),'status':'PASS' if issue is None else 'SKIP' if issue.tag=='skipped' else 'FAIL','execution_level':'pure regression; no database or app changes','seconds':case.get('time',''),'actual':'' if issue is None else issue.get('message','')+' '+(issue.text or ''),'evidence':regression.relative_to(ROOT).as_posix()})
    write('live-results-2026-10-29.csv', live, ['id','area','company','status','initial_status','retest_status','execution_level','preconditions','steps','expected','actual','initial_actual','started_utc','evidence','run_evidence','initial_evidence'])
    write('automated-results-2026-10-29.csv', automated, ['suite','test','case_instance','status','initial_status','retest_status','execution_level','seconds','actual','initial_actual','started_utc','evidence','initial_evidence'])
    findings = []
    for row in live:
        if row['status'] not in ('FAIL','BLOCKED'):
            continue
        actual = clean(row.get('actual', ''))
        evidence=ROOT/row.get('evidence','')
        evidence_text=evidence.with_suffix('.txt').read_text(encoding='utf-8') if evidence.with_suffix('.txt').is_file() else ''
        creation_rechecked=any(r['id']==row['id'].replace('-CREATE','-CREATION-READBACK') and r.get('company')==row.get('company') and r['status']=='PASS' for r in live)
        recovery=next((r for r in live if r['id']==row['id'].replace('-PRODUCT','-PUBLICATION-READBACK') and r.get('company')==row.get('company') and r['status']=='PASS'),None)
        route_rechecked=any(r['id']=='TA-FINAL-ROUTE-/'+row['id'].split('/',1)[1] and r.get('company')==row.get('company') and r['status']=='PASS' for r in live) if row['id'].startswith('TA-ROUTE-') and '/' in row['id'] else False
        harness = any(phrase in actual for phrase in ["name: 'Scope kind'", "name: 'Switch company'", 'filter is not a function']) or ('Open this company' in actual and 'Already open' in evidence_text) or ('waitForURL' in actual and (creation_rechecked or 'record created' in evidence_text.lower())) or ('waitForResponse' in actual and ('Enter legal name' in evidence_text or 'Use uppercase letters' in evidence_text))
        prerequisite=row['status']=='BLOCKED' and ('Activation prerequisites:' in actual or 'No Sales bill type' in actual)
        findings.append({'finding_id':f'TAF-{len(findings)+1:04}', 'severity':'REVIEW' if harness else 'HIGH' if re.search('HTTP 500|Internal Server Error|Application error', actual) else 'MEDIUM', 'category':'HARNESS_OR_PREREQUISITE' if harness else 'CONFIGURATION_PREREQUISITE' if prerequisite else 'RECOVERED_UI_CONFLICT' if recovery else 'TRANSIENT_ROUTE_FAILURE' if route_rechecked else 'BLOCKED_CAPABILITY' if row['status']=='BLOCKED' else 'LIVE_FAILURE', 'status':'RETESTED_WITH_CORRECTED_EXPECTATION' if harness and creation_rechecked else 'NEEDS_RETEST' if harness else 'RECOVERED' if recovery or route_rechecked else 'BLOCKED' if prerequisite else 'OPEN', 'test_id':row['id'], 'area':row['area'], 'company':row.get('company',''), 'steps':row.get('steps',''), 'expected':row.get('expected',''), 'actual':actual, 'evidence':row.get('evidence') or row.get('run_evidence',''), 'fix_scope':'Complete the listed published inventory/tax/voucher configuration through UI, then rerun; this is not evidence of an activation defect' if prerequisite else 'Draft published after refreshed UI review; retain original stale-preview UX evidence' if recovery else 'Creation succeeded and persisted; correct the automatic-navigation assertion to follow the View link' if creation_rechecked else 'Application unchanged; investigate using evidence before fixing', 'retest_acceptance':row.get('expected','')})
    for row in automated:
        if row['status'] not in ('FAIL','SKIP'):
            continue
        stale=row['suite']=='reports' and any(name in row['test'] for name in ['test_discovery_has_typed_parameters_and_only_ready_capabilities','test_corrected_definition_defaults_to_latest_and_rejects_retired_version'])
        findings.append({'finding_id':f'TAF-{len(findings)+1:04}', 'severity':'REVIEW' if row['status']=='SKIP' else 'LOW' if stale else 'MEDIUM', 'category':'AUTOMATED_SKIP' if row['status']=='SKIP' else 'STALE_TEST_EXPECTATION' if stale else 'AUTOMATED_REGRESSION_FAILURE', 'status':'BLOCKED' if row['status']=='SKIP' else 'OPEN', 'test_id':row['test'], 'area':row['suite'], 'company':'isolated test fixtures', 'steps':('apis/audit/.venv/Scripts/python.exe -m pytest docs/testing/tenant-admin/test_audit_cursor_capacity.py' if row['suite']=='audit-cursor-regression' else 'Run python docs/testing/tenant-admin/run_suites.py --suite '+row['suite']), 'expected':'Existing regression passes against current unchanged implementation', 'actual':row.get('actual',''), 'evidence':row.get('evidence',''), 'fix_scope':'Update stale 37-report/version-5 expectations against the current documented 38-report/version-6 catalogue in a later authorized test fix' if stale else 'Confirm implementation defect versus stale test/environment before fixing', 'retest_acceptance':'Run the named test and affected suite; preserve original failure evidence'})
    for finding in findings:
        if finding['test_id'].startswith('TA-LINK-') and any(message in finding.get('actual','') for message in ['Unexpected authentication origin','Unexpected sign-in redirect']):
            finding.update(category='HARNESS_OR_PREREQUISITE',severity='REVIEW',status='NEEDS_FRESH_SESSION_HTTP_RECHECK',fix_scope='This HTTP-only request reached the provider refresh/sign-in route after session expiry. An HTTP client does not execute the browser refresh page. Repeat with a fresh authenticated session; this result does not establish a defect in the target entity page.')
        if finding['test_id'].startswith('TA-RUN-') and ('provider sign-in' in finding.get('actual','').lower() or 'returned to the Auth login' in finding.get('actual','')) and (ARTIFACTS/'authentik-tunnel-recovery.json').exists():
            finding.update(category='ENVIRONMENT_AUTHENTICATION_FAILURE',severity='REVIEW',status='RECOVERED',fix_scope='The Authentik forwarding listener was restored through the existing managed helper. Preserve the failed execution attempt; use the later successful authenticated route/report checks for feature conclusions.')
        if finding['test_id'].startswith('TA-REPORTS-') and finding['test_id'].endswith('-RUN-READINESS'):
            finding.update(category='DEPLOYMENT_AND_SOURCE_PREREQUISITE',status='BLOCKED',fix_scope='Provide released report-run configuration and a READY source snapshot through the supported deployment/source workflow, then execute typed-parameter runs and exports. The current metadata explicitly disables new runs and contains no READY snapshots.')
        if 'Page crashed' in finding.get('actual',''):
            finding.update(severity='REVIEW',category='BROWSER_EXECUTION_FAILURE',status='NEEDS_UI_RETEST',fix_scope='The browser page crashed during a prolonged development-server run, before the stated page assertions completed. Investigate browser/environment stability and rerun in a fresh isolated UI session. A later HTTP-only link check does not establish that this UI workflow passed.')
        if 'Initial rendering-only PASS is invalid' in finding.get('actual',''):
            finding.update(severity='REVIEW',category='INVALID_AUTHENTICATION_REDIRECT',status='NEEDS_UI_RETEST',fix_scope='Repeat the intended page in an authenticated browser; sign-in-page rendering is excluded from feature coverage.')
        if finding['test_id'].endswith('test_registry_only_exposes_real_native_columns'):
            finding.update(severity='LOW',category='STALE_TEST_MODEL_MAP',fix_scope='The test supplies a manual model map that omits registered real BOM, authoring/configuration and promotion models. Update the fixture map against the current complete model catalogue before treating these missing-supplied-model errors as registry defects.')
        if finding['test_id'].endswith('test_template_evidence_respects_write_denies_and_rolls_back'):
            finding.update(severity='LOW',category='STALE_TEST_INITIAL_STATE',fix_scope='accounting/tasks/commands.py initialize now calls seed_initial_chart. This test assumes no groups or template installation after initialize; the later install returned a no-change 200. Prepare an actually new installation to test field write-deny rollback, and retain separate coverage for idempotent no-change replay. Do not infer an authorization bypass from this no-op response.')
        if finding['test_id']=='TA-BOUNDARY-RANDOM-COMPANY-CONTEXT':
            finding.update(category='BOUNDARY_ERROR_RESPONSE',severity='MEDIUM',fix_scope='Inaccessible random company returned 502 while the previous authorized company cookie was retained. Inspect Identity session selection and Company context refusal semantics; this is a response/UX defect, not evidence of cross-tenant data access.')
    cases = [{**r, 'case_id':r['id'], 'latest_status':r['status'], 'verification_scope':r['execution_level']} for r in live]
    for file in sorted(ARTIFACTS.rglob('report-form-inventory-*.json')):
        for item in json.loads(file.read_text(encoding='utf-8')):
            cases.append({'case_id':'TA-REPORT-'+item['company']+'-'+item['code']+'-RUN','area':'Report execution','company':item['company'],'preconditions':'Enabled report execution; a READY company source snapshot; active QA tenant; valid parameters from this report schema','steps':'Load report workspace; select '+item['code']+'; select READY snapshot and a view; fill typed parameters; Create report; poll/refresh to completion; verify scoped result rows, typed totals and retained history; exercise populated pagination/drilldown after preparing QA data','expected':'Immutable report result matches the chosen company/snapshot/parameters; exact decimal totals; new empty-company results are distinguished from later populated test data','latest_status':'BLOCKED_PREREQUISITES' if not item['run_enabled'] or not item['ready_snapshots'] else 'NOT_RUN_INDIVIDUALLY','verification_scope':'REUSABLE_EXECUTION_CASE; configuration rendering is not report execution','evidence':file.relative_to(ROOT).as_posix()})
    report_companies={item['company'] for file in ARTIFACTS.rglob('report-form-inventory-*.json') for item in json.loads(file.read_text(encoding='utf-8'))}
    for company in sorted(report_companies):
        for format in ['CSV','XLSX','JSON','HTML','PDF']:
            cases.append({'case_id':'TA-REPORT-EXPORT-'+company+'-'+format,'area':'Report exports','company':company,'preconditions':'Completed verified QA report; report.export permission; this format offered by the selected definition; permitted row/cell/package limits','steps':'Open completed report; choose an offered compatible view; Export '+format+'; follow job to completion; download through UI; open file; compare rows, exact values, headers and company/snapshot scope; reload export history; verify inaccessible-company download refusal','expected':'Supported export completes and matches immutable report rows and display configuration; limit/admission failures are explicit and recoverable','latest_status':'BLOCKED_PREREQUISITES','verification_scope':'REUSABLE_EXPORT_CASE; no live report run was available in this deployment','evidence':'Report workspace run-readiness results and report-form inventories'})
    surfaces = []
    for file in sorted(ARTIFACTS.rglob('surface-inventory-*.json')):
        surfaces.extend(json.loads(file.read_text(encoding='utf-8')))
    api_issues={}
    for item in surfaces:
        for response in item.get('network',[]):
            if response['status']>=500 and response['path'].startswith('/api/'):api_issues[response['path']]=(item,response)
    for endpoint,(item,response) in api_issues.items():
        audit=endpoint.startswith('/api/audit/')
        findings.append({'finding_id':f'TAF-{len(findings)+1:04}','severity':'HIGH','category':'LIVE_API_SERVER_ERROR','status':'OPEN','test_id':'TA-API-'+endpoint,'area':item['route'],'company':item['company'],'steps':'Login as broad tenant administrator; open '+('/activity' if endpoint.endswith('/activity') else '/audit' if audit else item['route'])+'; request '+endpoint+' with enough records for a next cursor','expected':'200, page data and a bounded signed next cursor; recoverable safe response','actual':'HTTP '+str(response['status'])+' at '+endpoint+('; live Audit log reports ValueError: cursor exceeds maximum size. Audit cursor context embeds the full serialized grants/policies; the shared encoder rejects tokens exceeding 4096 characters.' if audit else ''),'evidence':'surface-inventory-'+item['company']+'.json; start/win/logs/audit.stderr.log' if audit else 'surface-inventory-'+item['company']+'.json','fix_scope':'Later fix: bound the audit cursor binding while retaining tenant/user/query/grant/policy isolation; apis/audit/src/audit/api/listing.py:29 and :95; libs/platform/src/billing_platform/pagination.py:92' if audit else 'Investigate the live API failure before changing code','retest_acceptance':'New broad-admin cursor regression passes; audit and Activity pages paginate with built-in tenant/company grants; wrong-user/query/grant replay remains rejected'})
    session_http=[r for r in live if r['status']=='FAIL' and r['id'].startswith('TA-LINK-') and 'HTTP 500' in r.get('actual','')]
    if session_http:
        findings.append({'finding_id':f'TAF-{len(findings)+1:04}','severity':'HIGH','category':'SESSION_SERVICE_ERROR_HANDLING','status':'OPEN','test_id':'TA-SESSION-UPSTREAM-FAILURE','area':'Server-rendered session resolution','company':'QA tenant; repeated authenticated record-link reads','steps':'Run the repeated-link sweep with a signed-in tenant administrator; inspect the failing record URLs and Console server stderr','expected':'Authorized pages render, or upstream/session unavailability gives a recoverable response rather than a server exception','actual':'Authenticated record URLs returned HTTP 500. Console server stderr reports Error: Unable to load your session at app/session.ts:54. The upstream status is not included in that exception, so expiry versus temporary service unavailability remains to be distinguished. Concurrent cold development compilation also caused long request times.','evidence':'start/win/logs/web-console.stderr.log; start/win/logs/web-console.stdout.log; '+session_http[0].get('run_evidence',''),'fix_scope':'Investigate the non-OK Identity response and getSession fallback in mfes/apps/console/app/session.ts:54; retain service/auth failure distinctions instead of converting them into an unhandled server error','retest_acceptance':'Single-browser and concurrent authorized record navigation recover from an unavailable/expired session without HTTP 500; valid-company and wrong-tenant boundaries remain enforced'})
    outage=ARTIFACTS/'authentik-tunnel-recovery.json'
    if outage.exists():
        recovery=json.loads(outage.read_text(encoding='utf-8'))
        findings.append({'finding_id':f'TAF-{len(findings)+1:04}','severity':'REVIEW','category':'ENVIRONMENT_OUTAGE','status':'RECOVERED','test_id':'TA-ENV-AUTHENTIK-TUNNEL','area':'Authentication test environment','company':'QA tenant','steps':'Continue a long signed-in UI run; refresh/sign in after the provider forwarding listener stops','expected':'Existing Authentik tunnel/provider remains reachable; authenticated coverage is preserved','actual':'Ports 9000 and 9443 refused connections, which blocked token refresh and fresh sign-in. '+recovery['actual'],'evidence':outage.relative_to(ROOT).as_posix()+'; authentication-redirect-inventory.json; start/win/logs/authentik-tunnel.stderr.log','fix_scope':'Keep the managed local provider tunnel available during long tests; review process/runtime supervision. Sign-in-page captures were invalidated and affected pages require fresh authenticated coverage.','retest_acceptance':'Provider ports stay reachable; fresh sign-in succeeds; intended application origin is verified for every route and repeated link'})
    preview_seen=set()
    for item in surfaces:
        if 'Sample figures only' in item.get('text','') and 'overview' not in preview_seen:
            preview_seen.add('overview')
            findings.append({'finding_id':f'TAF-{len(findings)+1:04}','severity':'MEDIUM','category':'IMPLEMENTATION_GAP','status':'OPEN','test_id':'TA-OVERVIEW-LIVE-DATA','area':'Business overview','company':item['company'],'steps':'Sign into the new empty tenant; open Business overview','expected':'A working overview reflects the selected company transactions, including zero balances in a new company','actual':'The UI explicitly says Sample figures only and displays example invoices, amounts and customers for the new empty tenant','evidence':'surface-inventory-'+item['company']+'.json; route-'+item['company']+'-_.png','fix_scope':'Connect implemented overview controls to company-scoped live data in a later authorized fix','retest_acceptance':'New company has zero live totals; known QA transaction appears only in its own company'})
        if re.search('alignment|not connected|not yet available|not available yet|book cards are currently disabled|coming soon',item.get('text',''),re.I) and item['route'] not in preview_seen:
            preview_seen.add(item['route'])
            findings.append({'finding_id':f'TAF-{len(findings)+1:04}','severity':'REVIEW','category':'PREVIEW_OR_UNAVAILABLE_CAPABILITY','status':'BLOCKED','test_id':'TA-CAPABILITY-'+item['route'],'area':item['route'],'company':item['company'],'steps':'Open '+item['route']+' and inspect the offered actions','expected':'Working actions complete against the live services','actual':item['text'][-3500:],'evidence':'surface-inventory-'+item['company']+'.json','fix_scope':'Review planned capability/admission prerequisites before any application change','retest_acceptance':'Documented implementation becomes executable through the UI and live output is verified'})
    coverage = []
    live_by_id={r['id']:r for r in live}
    def exercised_control(item,control):
        route=item['route'].split('?')[0];company=item['company'];label=clean(control.get('label','')).strip();kind=control.get('type')
        if kind=='search':
            identifier='TA-SEARCH-'+company+'-'+item['route']
            return identifier if live_by_id.get(identifier,{}).get('status')=='PASS' else ''
        match=re.match(r'^/masters/(brands|manufacturers|item-groups)/([^/]+)(/edit)?$',route)
        if match and re.search(r'^(?:Name|Save changes|Deactivate |Activate |Confirm change)',label,re.I):
            identifier='TA-MASTER-'+company+'-'+match.group(1)+'-EDIT-LIFECYCLE'
            return identifier if live_by_id.get(identifier,{}).get('status')=='PASS' else ''
        if route=='/masters/items/new' and re.search(r'^(?:Product code|Product name|Code|Name|Kind|Published product type|Base unit|Primary product group|Create product)',label,re.I):
            identifier='TA-PRODUCT-'+company+'-CREATE'
            return identifier if live_by_id.get(identifier,{}).get('status')=='PASS' else ''
        if route.startswith('/users/') and re.search(r'^(?:Display name|Save changes|Edit user|View user)$',label,re.I):
            return 'TA-ORG-USER-EDIT' if live_by_id.get('TA-ORG-USER-EDIT',{}).get('status')=='PASS' else ''
        if route.startswith('/departments/') and re.search(r'^(?:Name|Save changes|Deactivate department|Reactivate department|Reason|Edit details|View department)$',label,re.I):
            identifier='TA-ORG-'+company+'-DEPARTMENT-LIFECYCLE'
            return identifier if live_by_id.get(identifier,{}).get('status')=='PASS' else ''
        if route=='/reports/workspace' and label in ('Load report workspace','Classic reports and banking','Report workspace'):
            identifier='TA-REPORTS-'+company+('-LOAD' if label=='Load report workspace' else '-CLASSIC-TAB')
            return identifier if live_by_id.get(identifier,{}).get('status')=='PASS' else ''
        return ''
    for item in surfaces:
        result = next((r for r in live if r['id']=='TA-ROUTE-'+item['company']+'-'+item['route']), None)
        for control in item['controls']:
            label = clean(control.get('label', '')).strip()
            exercised=exercised_control(item,control)
            coverage.append({'company':item['company'], 'route':item['route'], 'element':control.get('tag',''), 'role_or_type':control.get('role') or control.get('type'), 'label':label, 'disabled':control.get('disabled',False), 'route_status':result['status'] if result else 'OBSERVED', 'functional_status':'WORKFLOW_CONTROL_EXERCISED' if exercised else 'NOT_INDIVIDUALLY_EXERCISED', 'functional_test_id':exercised, 'evidence':'surface-inventory-'+item['company']+'.json'})
        for link in item['links']:
            if not link.get('href','').startswith('/'):
                continue
            path = link['href'].split('?')[0]
            reached = live_by_id.get('TA-ROUTE-'+item['company']+'-'+path)
            target=urlparse.urlsplit(link['href']);params=urlparse.parse_qs(target.query);params.pop('returnTo',None);http_route=target.path+('?' + urlparse.urlencode({k:v[0] for k,v in params.items()}) if params else '')
            http=live_by_id.get('TA-LINK-'+item['company']+'-'+http_route)
            coverage.append({'company':item['company'], 'route':item['route'], 'element':'A', 'role_or_type':'link', 'label':link['label'], 'destination':link['href'], 'disabled':False, 'route_status':reached['status'] if reached else http['status'] if http else 'NOT_VISITED', 'functional_status':'DESTINATION_ROUTE_SMOKE' if reached else 'AUTHENTICATED_LINK_HTTP_ONLY' if http else 'NOT_INDIVIDUALLY_EXERCISED', 'functional_test_id':reached['id'] if reached else http['id'] if http else '', 'evidence':'surface-inventory-'+item['company']+'.json'})
    for file in sorted(ARTIFACTS.rglob('report-form-inventory-*.json')):
        for item in json.loads(file.read_text(encoding='utf-8')):
            identifier='TA-REPORT-'+item['company']+'-'+item['code']+'-SETTINGS'
            for control in item['controls']:
                coverage.append({'company':item['company'],'route':'/reports/workspace?report='+item['code'],'element':control['tag'],'role_or_type':control.get('type',''),'label':clean(control.get('label','')).strip(),'disabled':control.get('disabled',False),'route_status':'SETTINGS_RENDERED_BY_UI_SELECTION' if live_by_id.get(identifier,{}).get('status')=='PASS' else 'NEEDS_RETEST','functional_status':'NOT_INDIVIDUALLY_EXERCISED','evidence':file.relative_to(ROOT).as_posix()+'; '+identifier})
    reusable_keys=set()
    for index, item in enumerate(coverage):
        if item['element']=='A' or item['disabled'] or not item['label'] or item.get('functional_test_id'):
            continue
        route_template=re.sub(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',':record_id',item['route'],flags=re.I)
        key=(item['company'],route_template,item['element'],item['role_or_type'],item['label'])
        if key in reusable_keys:continue
        reusable_keys.add(key)
        identifier='TA-REUSE-'+hashlib.sha256(json.dumps(key,ensure_ascii=False).encode()).hexdigest()[:12].upper()
        cases.append({'case_id':identifier, 'area':'Discovered UI control', 'company':item['company'], 'preconditions':'Use a new/retained active QA tenant and the named company profile; substitute current fixture IDs for :record_id and prepare permitted dependencies', 'steps':f'Open {route_template}; exercise {item["label"]}; test valid, invalid, cancel, save/reload and permitted failure branches appropriate to this control', 'expected':'Action performs documented behavior; saved state read back via UI/API; scope maintained; clear recoverable failure', 'latest_status':'NOT_RUN_INDIVIDUALLY', 'verification_scope':'REUSABLE_MANUAL_CASE; route inventory is not functional completion', 'evidence':item['evidence']})
    case_counts=Counter(row['case_id'] for row in cases)
    fixture_path=ARTIFACTS/'live/resources.json'
    profiles={c['id']:c['key'] for c in json.loads(fixture_path.read_text(encoding='utf-8')).get('companies',[])} if fixture_path.exists() else {}
    for row in cases:
        if case_counts[row['case_id']]>1:row['case_id']+='-'+profiles.get(row.get('company',''),row.get('company',''))
    write('reusable-test-cases.csv', cases, ['case_id','area','company','preconditions','steps','expected','latest_status','verification_scope','evidence'])
    write('menu-link-control-coverage.csv', coverage, ['company','route','element','role_or_type','label','destination','disabled','route_status','functional_status','functional_test_id','evidence'])
    finding_fields=['finding_id','severity','category','status','test_id','area','company','steps','expected','actual','evidence','fix_scope','retest_acceptance']
    harness_findings=[row for row in findings if row['category']=='HARNESS_OR_PREREQUISITE']
    findings=[row for row in findings if row['category']!='HARNESS_OR_PREREQUISITE']
    write('harness-findings.csv',harness_findings,finding_fields)
    write('findings-2026-10-29.csv', findings, finding_fields)
    with (ROOT/'docs/tenant-admin-findings-2026-10-29.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['finding_id','severity','category','status','test_id','area','company','steps','expected','actual','evidence','fix_scope','retest_acceptance']);writer.writeheader();writer.writerows({k:clean(v) for k,v in row.items()} for row in findings)
    resources_file = ARTIFACTS/'live/resources.json'
    if resources_file.exists():
        resources=json.loads(resources_file.read_text())
        fixtures=[]
        fixtures.append({'resource':'tenant','id':resources.get('tenant',''),'name':resources.get('tenantName',''),'status':'active; last verified in setup API readback'})
        for key,resource,status in [('testRole','tenant_role','UI-created company.read role'),('testGroup','user_group','active; membership addition/removal tested; left empty'),('backupUser','user','synthetic invited user; profile edit tested; external email delivery not claimed'),('testAssignment','role_assignment','company-scoped grant/revoke/regrant tested; left revoked')]:
            if resources.get(key):fixtures.append({'resource':resource,'id':resources[key],'status':status})
        for row in resources.get('companies',[]):
            fixtures.append({'resource':'company','id':row['id'],'name':row['name'],'code':row.get('code',''),'profile':row['key'],'state':row['state'],'amount_precision':row['amount'],'quantity_precision':row['quantity'],'rounding':row['rounding'],'grouping':row.get('grouping',''),'inventory':row['inventory'],'barcode_option':row.get('productOption',{}).get('value',''),'bill_wise':row.get('accountOption',{}).get('value',''),'payment_term':row.get('paymentTerm',''),'product_revision':row.get('productRevision',''),'account_policy':row.get('accountPolicy',''),'product':row.get('product',''),'supplier':row.get('supplier','')})
            for key,resource,status in [('productType','product_type','type created; requirements published'),('typeRevision','product_type_revision','published'),('productScope','product_configuration_scope','company scope'),('productDraft','product_configuration_draft','saved; publication/recovery recorded'),('productRevision','product_configuration_revision','published'),('paymentTerm','payment_term','active; one 100.0000% instalment'),('accountPolicy','party_accounting_policy','saved; profile-specific bill-wise/payment hold'),('supplier','supplier','active; legal identity created through UI')]:
                if row.get(key):fixtures.append({'resource':resource,'id':row[key],'company':row['id'],'profile':row['key'],'status':status})
        for row in resources.get('records',[]):fixtures.append({'resource':row['resource'],'id':row['id'],'name':row.get('name',''),'company':row['company'],'kind':row.get('kind',''),'status':'Retained QA fixture; name is creation input or latest verified review name; use ID for retesting'})
        write('test-fixtures.csv',fixtures,['resource','id','name','code','company','profile','kind','status','state','amount_precision','quantity_precision','rounding','grouping','inventory','barcode_option','bill_wise','payment_term','product_revision','account_policy','product','supplier'])
    summary={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'live':dict(Counter(r['status'] for r in live)),'live_execution_levels':dict(Counter(r['execution_level'] for r in live)),'automated':dict(Counter(r['status'] for r in automated)),'findings':len(findings),'finding_statuses':dict(Counter(r['status'] for r in findings)),'harness_or_prerequisite_issues':len(harness_findings),'visited_company_routes':len(surfaces),'inventoried_elements':len(coverage),'coverage_statuses':dict(Counter(r['functional_status'] for r in coverage)),'reusable_cases':len(cases),'application_code_changed_by_this_task':False,'direct_application_database_writes':False,'coverage_note':'Route smoke, individual workflows, HTTP-only repeated links and isolated automated regression are separate. NOT_RUN_INDIVIDUALLY entries are not claimed as tested features.'}
    (OUTPUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
