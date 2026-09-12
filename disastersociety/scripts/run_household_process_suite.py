"""Frozen, offline protocol scenarios using production modules, without an LLM.

Each scenario is one denominator item, regardless of its number of assertions.
Keep the complete traces and failures; this is process validation, not behavior
scoring, a population simulation, or a comparison with a competing agent method.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path

import networkx as nx

from ds.agents.carr_empirical_v2 import CarrEmpiricalResidentV2
from ds.agents.e1_contracts import E1Decision, PartyProposal
from ds.households.state import CareRequirement, Household, VehicleResource
from ds.interaction.carr_empirical_v2 import CarrEmpiricalInteractionV2
from ds.kernel.actions import IntentEnvelope
from ds.kernel.clock import Clock
from ds.world.carr_empirical_v2 import CarrEmpiricalWorldV2
from scripts.audit_archived_run import digest, dump, read_json

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'experiments/carr/process_suite/cases_v1.json'


class Scene:
    def __init__(self):
        self.trace = []
        self.residents = {r: CarrEmpiricalResidentV2(agent_id=r,
            household_id='G' if r == 'x' else 'H',
            profile={'age': 40, 'decision_capable': True}, vehicles={}) for r in ('a', 'b', 'c', 'x')}
        self.hh = Household(id='H', member_ids=('a', 'b', 'c', 'child'),
            decision_member_ids=('a', 'b', 'c'), dependent_ids=('child',),
            vehicles={'v': VehicleResource(id='v', location=('home', 'H'), capacity=4)})
        other = Household(id='G', member_ids=('x',), decision_member_ids=('x',),
            vehicles={'vx': VehicleResource(id='vx', location=('home', 'G'), capacity=4)})
        self.care = {'child': CareRequirement('child', 'minor', None)}
        self.world = CarrEmpiricalWorldV2(households={'H': self.hh, 'G': other}, residents=self.residents,
            config={'primary_route_id': 'primary', 'alternate_route_id': 'alternate',
                'closure_step': 3, 'safe_zone': 'safe', 'care_requirements': self.care}, run_seed=7)
        graph = nx.Graph([('a', 'x'), ('a', 'b'), ('a', 'c')])
        self.ix = CarrEmpiricalInteractionV2(run_seed=7, household_dm_probability=1,
            community_message_probability=1, social_graph=graph, residents=self.residents,
            households=self.world.households, decision_capable={r: True for r in self.residents},
            care_requirements=self.care, world=self.world)

    def capture(self, operation, step, **details):
        self.trace.append({'operation': operation, 'step': step, **details,
            'world': deepcopy(self.world.snapshot()), 'interaction': deepcopy(self.ix.snapshot())})

    def proposal(self, step=1, depart=5, **changes):
        p = dict(traveler_ids=['a', 'b', 'c'], accompanying_member_ids=['child'],
            caregiver_by_member={'child': 'a'}, vehicle_id='v', route_id='alternate',
            depart_step=depart, content='Please agree to this exact party.')
        p.update(changes)
        d = self.residents['a']._normalize_proposal(E1Decision(action='prepare',
            party_proposal=PartyProposal(**p)), step=step)
        self.ix.emit(self.residents['a'], d, Clock(30, step))
        mid = list(self.ix.messages)[-1]
        self.ix.deliver(Clock(30, step))
        self.capture('proposal', step, decision=d.model_dump(), message_id=mid)
        return mid

    def response(self, rid, mid, step=2, disposition='accepted'):
        d = E1Decision(action='prepare', message_responses=[{'message_id': mid, 'disposition': disposition}])
        self.ix.process(self.residents[rid], d, Clock(30, step))
        self.capture('response', step, resident_id=rid, decision=d.model_dump())

    def agree(self, mid, step=2):
        self.response('b', mid, step)
        self.response('c', mid, step)

    def execute(self, cid, step, residents=('a', 'b', 'c'), route='alternate'):
        return self.apply(step, {r: E1Decision(action='evacuate', departure_mode='commitment',
            commitment_id=cid, vehicle_id='v', route_id=route, depart_step=step) for r in residents})

    def apply(self, step, decisions):
        clock = Clock(30, step)
        self.world.update(clock)
        envelopes = [IntentEnvelope(decision_id=f'{step}:{r}', agent_id=r,
            agent=self.residents[r], decision=d) for r, d in decisions.items()]
        before = deepcopy(self.world.snapshot())
        resolved = self.world.resolve_batch(envelopes, clock, 7)
        assert self.world.snapshot() == before, 'arbitration mutated world before execution'
        outcomes = self.world.apply_batch(resolved, clock)
        for r, d in decisions.items():
            self.residents[r].commit_execution(d, outcomes[f'{step}:{r}'], step=step)
        self.capture('execute', step, decisions={r: d.model_dump() for r, d in decisions.items()},
            outcomes={k: v.__dict__ for k, v in outcomes.items()})
        return outcomes

    def mark_assisted(self, rid):
        self.care[rid] = CareRequirement(rid, 'mobility', None)
        self.world._care_requirements[rid] = self.care[rid]
        self.residents[rid].profile['needs_execution_assistance'] = True


def run_case(cid, s):
    if cid == 'capabilities_in_input':
        p = s.residents['a']._prompt_payload(world=s.world, step=1)
        s.capture('decision_input', 1, payload=p)
        c = p.get('coordination_capabilities', {})
        assert c.get('scope') == 'within_household', 'household scope missing from actual input'
        assert c.get('traveler_ids') == ['a', 'b', 'c'], 'decision-member IDs not explicit'
        assert c.get('accompanying_member_ids') == ['child'], 'dependent IDs not explicit'
        assert c.get('cross_household_transport') is False and c.get('return_pickup') is False
        return
    if cid == 'empty_recipient_feedback':
        d = E1Decision(action='seek_help', messages=[{'to': 'broadcast', 'kind': 'notice', 'content': 'Need a ride.'}])
        s.ix.emit(s.residents['a'], d, Clock(30, 1))
        s.capture('unreachable_message', 1, decision=d.model_dump())
        assert not next(iter(s.ix.messages.values()))['recipient_ids']
        assert any(n['payload'].get('reason_code') == 'no_reachable_recipient'
                   for n in s.ix.commitment_notifications), 'no failure feedback for empty recipient set'
        return
    if cid == 'independent_departure':
        out = s.apply(2, {'a': E1Decision(action='evacuate', departure_mode='solo',
            vehicle_id='v', route_id='alternate', depart_step=2)})
        assert out['2:a'].status == 'executed'
        assert s.world.member_locations['a'] == 'safe'
        assert s.world.member_locations['b'] == ('home', 'H')
        return
    if cid == 'notice_acceptance':
        d = E1Decision(action='prepare', messages=[{'to': 'b', 'kind': 'notice', 'content': 'Maybe travel together.'}])
        s.ix.emit(s.residents['a'], d, Clock(30, 1)); s.ix.deliver(Clock(30, 1))
        s.response('b', next(iter(s.ix.messages)))
        assert not s.hh.v2_commitments
        return
    changes = {}
    if cid == 'cross_household_feedback':
        changes = {'traveler_ids': ['a', 'x'], 'accompanying_member_ids': [], 'caregiver_by_member': {}}
    if cid == 'dependent_role_feedback':
        changes = {'traveler_ids': ['a', 'b', 'c', 'child']}
    if cid == 'vehicle_capacity':
        s.hh.vehicles['v'].capacity = 3
    if cid in ('assisted_adult', 'self_caregiver'):
        s.mark_assisted('b')
        if cid == 'self_caregiver':
            changes = {'caregiver_by_member': {'child': 'a', 'b': 'b'}}
    route = 'primary' if cid in ('closed_route', 'revised_route_execution') else 'alternate'
    mid = s.proposal(route_id=route, **changes)
    key = 'commit:' + mid
    if cid in ('cross_household_feedback', 'dependent_role_feedback'):
        record = s.ix.messages[mid]
        assert record['status'] == 'rejected' and not s.hh.v2_commitments
        payload = s.ix.commitment_notifications[-1]['payload']
        expected = 'cross_household_transport_unsupported' if cid == 'cross_household_feedback' else 'nondecision_traveler'
        assert payload.get('reason_code') == expected, 'rejection gives no precise capability/role reason'
        assert payload.get('invalid_member_ids'), 'rejection does not identify invalid members'
        assert payload.get('correction_hint'), 'rejection does not explain the applicable contract'
        return
    if cid == 'undelivered_acceptance':
        st = s.ix.messages[mid]['recipient_states']['c']
        st['delivered_step'] = None
        s.residents['c'].inbox.clear()
        s.residents['c']._delivered_message_ids.discard(mid)
        s.agree(mid)
        assert not s.hh.v2_commitments
        return
    if cid == 'partial_acceptance':
        s.response('b', mid)
        assert not s.hh.v2_commitments
        return
    if cid == 'participant_declines':
        s.response('b', mid); s.response('c', mid, disposition='rejected')
        assert not s.hh.v2_commitments and s.ix.messages[mid]['status'] == 'rejected'
        return
    if cid == 'expired_acceptance':
        s.agree(mid, step=6)
        assert not s.hh.v2_commitments
        assert s.ix.messages[mid]['acceptance']['reason_code'] == 'depart_step_too_early'
        return
    if cid == 'version_specific_acceptance':
        new_mid = s.proposal(step=2, depart=6, route_id='primary')
        s.agree(mid, step=3)
        assert key in s.hh.v2_commitments
        assert 'commit:' + new_mid not in s.hh.v2_commitments, 'old acceptance counted towards new version'
        assert s.hh.v2_commitments[key].party.route_id == 'alternate'
        return
    s.agree(mid)
    if cid in ('vehicle_capacity', 'assisted_adult', 'self_caregiver'):
        assert not s.hh.v2_commitments, 'invalid resource/care arrangement became an agreement'
        expected = {'vehicle_capacity': 'vehicle_capacity', 'assisted_adult': 'missing_caregiver',
                    'self_caregiver': 'caregiver_is_recipient'}[cid]
        assert s.ix.messages[mid]['acceptance']['reason_code'] == expected
        return
    assert key in s.hh.v2_commitments, 'all valid acceptances failed to create an agreement'
    assert s.hh.v2_commitments[key].accepted_by == frozenset(('a', 'b', 'c'))
    if cid == 'valid_joint':
        assert len(s.hh.v2_commitments) == 1
        return
    if cid == 'duplicate_acceptance':
        before = deepcopy(s.hh.v2_commitments)
        s.agree(mid, step=3)
        assert s.hh.v2_commitments == before
        return
    if cid == 'cancelled_execution':
        d = E1Decision(action='prepare', cancel_commitment_ids=[key])
        s.ix.process(s.residents['b'], d, Clock(30, 3))
        s.capture('cancel', 3, decision=d.model_dump())
        before = s.world.physical_snapshot()
        out = s.execute(key, 5)
        assert all(o.status == 'rejected' for o in out.values())
        assert s.world.physical_snapshot() == before
        return
    before = s.world.physical_snapshot()
    out = s.execute(key, 5, residents=('a', 'b') if cid == 'missing_current_intent' else ('a', 'b', 'c'), route=route)
    assert all(o.status == 'rejected' for o in out.values())
    assert s.world.physical_snapshot() == before
    if cid == 'missing_current_intent':
        assert all(o.reason == 'missing_traveler_intent' for o in out.values())
        return
    assert all(o.reason == 'route_closed' for o in out.values())
    assert all(s.residents[r].perceived_routes['primary']['open'] is False for r in ('a', 'b', 'c'))
    if cid == 'revised_route_execution':
        revised = s.proposal(step=6, depart=8)
        s.agree(revised, step=7)
        out = s.execute('commit:' + revised, 8)
        assert all(o.status == 'executed' for o in out.values())
        assert all(s.world.member_locations[m] == 'safe' for m in s.hh.member_ids)
        assert s.hh.vehicles['v'].location == 'safe'
        assert len([d for d in s.hh.departure_records if d.outcome == 'executed']) == 1


def run_suite(output, manifest=MANIFEST):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Existing process results are protected')
    spec = read_json(manifest)
    ids = [c['id'] for c in spec['cases']]
    assert len(ids) == len(set(ids))
    output.mkdir(parents=True, exist_ok=True)
    (output / 'traces').mkdir()
    rows = []
    for case in spec['cases']:
        s = Scene()
        try:
            run_case(case['id'], s)
            passed, error = True, None
        except Exception as exc:
            passed, error = False, f'{type(exc).__name__}: {exc}'
        rows.append({**case, 'passed': passed, 'error': error, 'trace_file': f"traces/{case['id']}.json"})
        dump(output / rows[-1]['trace_file'], s.trace)
    groups = {g: {'passed': sum(r['passed'] for r in rows if r['group'] == g),
                  'total': sum(r['group'] == g for r in rows)} for g in sorted({r['group'] for r in rows})}
    result = {'kind': 'controlled_process_scenario_validation', 'suite_id': spec['suite_id'],
        'manifest_sha256': digest(manifest), 'cases': rows, 'passed': sum(r['passed'] for r in rows),
        'total': len(rows), 'groups': groups, 'model_service_requests': 0,
        'autonomous_behavior_score': None, 'method_comparison': False,
        'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in [
            ROOT / 'ds/agents/carr_empirical_v2.py', ROOT / 'ds/interaction/carr_empirical_v2.py',
            ROOT / 'ds/households/state.py', ROOT / 'ds/world/carr_empirical_v2.py', Path(__file__).resolve()]}}
    result['pass_rate'] = result['passed'] / result['total']
    dump(output / 'results.json', result)
    dump(output / 'frozen_cases.json', spec)
    report = '# 固定场景过程检查\n\n'
    report += f"通过 {result['passed']}/{result['total']}（{result['pass_rate']:.1%}），模型服务调用 0 次。\n\n"
    report += spec['selection'] + '\n\n' + spec['scope'] + '\n\n'
    report += '| 案例 | 预期 | 结果 |\n|---|---|---|\n'
    for row in rows:
        report += f"| {row['id']} | {row['expected']} | {'通过' if row['passed'] else row['error']} |\n"
    (output / 'results.md').write_text(report, encoding='utf-8')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    r = run_suite(args.output)
    print({'passed': r['passed'], 'total': r['total'], 'groups': r['groups'],
           'failed': [x['id'] for x in r['cases'] if not x['passed']]})
    if r['passed'] != r['total']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
