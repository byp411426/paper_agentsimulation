"""Independent checks on executed logs, not thresholds for favorable behavior."""
import json,sys,collections
from pathlib import Path
def check(run,analysis,expected_households,expected_seed):
    read=lambda f:[json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    r=json.loads((analysis/'results.json').read_text());es=read(run/'events/events.jsonl');profiles=read(run/'selected_profiles.jsonl');initial=json.loads((run/'initial_state.json').read_text());provenance=json.loads((run/'provenance.json').read_text());fail=[]
    if not r['software_check_passed']:fail.append('analyzer_contract_checks_failed')
    if [e['step'] for e in es]!=list(range(1,26)):fail.append('missing_or_repeated_steps')
    if len(profiles)!=expected_households or provenance['seed']!=expected_seed:fail.append('run_identity_mismatch')
    g=r['gateway'];decisions=sum(len(e['decisions']) for e in es)
    if g.get('n_failed',0) or g.get('n_fallback',0) or g.get('n_ok',0)+g.get('n_cache',0)!=decisions:fail.append('model_call_accounting_mismatch')
    roster={m['resident_id'] for h in profiles for m in h['member_profiles']};old=initial['world']['member_locations'];seen=set();safe='controlled_safe_zone'
    if set(old)!=roster:fail.append('initial_roster_mismatch')
    for e in es:
        now=e['world']['member_locations'];moved={m for m in roster if now.get(m)!=old.get(m)};expected=set();routes=collections.Counter()
        for hh,cs in e['world']['household_commitments'].items():
            for cid,c in cs.items():
                if c['status']!='executed' or cid in seen:continue
                seen.add(cid);party=c['party'];members=set(party['traveler_ids'])|set(party['accompanying_member_ids'])
                if expected&members:fail.append(f'double_member_execution:{e["step"]}')
                expected|=members;routes[party['route_id']]+=1
                if any(now.get(m)!=safe or old.get(m)!=str(('home',hh)) for m in members):fail.append(f'illegal_party_movement:{cid}')
                if c['created_step']>e['step'] or party['depart_step']!=e['step']:fail.append(f'party_time_mismatch:{cid}')
        if moved!=expected:fail.append(f'all_member_movement_mismatch:{e["step"]}')
        for route,count in routes.items():
            state=e['world']['route_state'][route]
            if not state['open'] or count>state['capacity_per_step']:fail.append(f'route_execution_constraint:{e["step"]}:{route}')
        old=now
    result={'passed':not fail,'failures':fail,'households':expected_households,'seed':expected_seed,'steps':len(es),'logical_decisions':decisions,'checked_departure_parties':len(seen),'behavior_threshold_applied':False}
    (analysis/'acceptance.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
    r=check(Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]));print(json.dumps(r));raise SystemExit(0 if r['passed'] else 2)
