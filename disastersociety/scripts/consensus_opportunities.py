"""Read-only formation obligations reconstructed from proposals and responses.

This oracle does not call production acceptance code, and does not use its
accepted/rejected verdict to decide whether formation was required. Existing
agreement state-transition checks remain separate to avoid changing old rates.
"""
from __future__ import annotations

from scripts.audit_archived_run import commitments, metric


def formation_blockers(audit, raw, step, world, own_commitment_id):
    p = raw['message'].get('payload', {})
    hid = audit.member_h[raw['sender']]
    profile = audit.profile_h[hid]
    decision = set(profile['decision_resident_ids'])
    dependents = set(profile['nondecision_member_ids'])
    travelers = set(p.get('traveler_ids', []))
    companions = set(p.get('accompanying_member_ids', []))
    members = travelers | companions
    blockers = []
    if not travelers or not travelers <= decision:
        blockers.append('invalid_decision_members')
    if not companions <= dependents:
        blockers.append('invalid_dependent_members')
    if raw['sender'] not in travelers:
        blockers.append('proposer_not_traveler')
    if raw['message'].get('to') not in {'household', 'family'} | (decision - {raw['sender']}):
        blockers.append('not_household_channel')
    depart = p.get('depart_step')
    if type(depart) is not int or depart < max(raw['step'] + 2, step + 1):
        blockers.append('invalid_departure_time')
    origin = ['home', hid]
    # E1's world snapshot serializes member locations with str(tuple), while
    # vehicle locations and physical snapshots use JSON arrays.
    if any(world['member_locations'].get(m) not in (origin, str(('home', hid))) for m in members):
        blockers.append('member_not_at_origin')
    vehicle = world['vehicles'].get(hid, {}).get(p.get('vehicle_id'))
    if vehicle is None:
        blockers.append('vehicle_unknown')
    elif vehicle['location'] != origin or vehicle['capacity'] < len(members):
        blockers.append('vehicle_unavailable_or_insufficient')
    if p.get('route_id') not in world['route_state']:
        blockers.append('unknown_route')
    caregivers = p.get('caregiver_by_member', {})
    needs_care = {m['resident_id'] for m in profile['member_profiles']
                  if m.get('needs_execution_assistance')}
    for rid in members & needs_care:
        if rid not in caregivers or caregivers[rid] not in travelers or caregivers[rid] == rid:
            blockers.append('missing_valid_caregiver')
    if any(rid not in travelers for rid in caregivers.values()):
        blockers.append('caregiver_not_traveler')
    current = {cid: c for cid, (h, c) in commitments(world).items() if h == hid}
    replaced = p.get('supersedes_id')
    for cid, c in current.items():
        if cid == own_commitment_id:
            continue
        old_members = set(c['party']['traveler_ids']) | set(c['party'].get('accompanying_member_ids', []))
        if c['status'] == 'accepted' and cid != replaced and (
                c['party']['vehicle_id'] == p.get('vehicle_id') or old_members & members):
            blockers.append('active_commitment_conflict')
    if replaced is not None:
        old = current.get(replaced)
        if old is None or not set(old['accepted_by']) & travelers:
            blockers.append('invalid_supersession')
    return sorted(set(blockers))


def audit_formation_opportunities(audit):
    rows = []
    events = {e['step']: e for e in audit.events}
    for mid, raw in sorted(audit.raw_messages.items(), key=lambda x: (x[1]['step'], x[0])):
        if raw['message'].get('kind') != 'proposal':
            continue
        sent = audit.messages.get(mid)
        if sent is None:
            rows.append({'record_id': mid, 'status': 'unverifiable', 'issues': ['proposal_missing_from_message_ledger']})
            continue
        travelers = set(raw['message'].get('payload', {}).get('traveler_ids', []))
        responses = [(t, rid, reply, d['decision_id'])
            for (t, rid), d in sorted(audit.decisions.items()) if t >= raw['step']
            for reply in d['decision'].get('message_responses', []) if reply['message_id'] == mid]
        cid = 'commit:' + mid
        observed_creations = {e['step'] for e in audit.events
            if cid in commitments(e['world']) and cid not in commitments(e['state_before_decisions']['world'])}
        opportunities = sorted({raw['step']} | {r[0] for r in responses} | observed_creations)
        authorized = {raw['sender']}
        declined = False
        for step in opportunities:
            event = events[step]
            pre = event['state_before_decisions']['world']
            post = event['world']
            if cid in commitments(pre):
                continue  # existing agreement updates are audited by the original checker
            refs = [raw['decision_id']]
            for t, rid, reply, did in responses:
                if t != step or rid not in travelers or rid == raw['sender']:
                    continue
                delivered = sent.get('recipient_states', {}).get(rid, {}).get('delivered_step')
                payload = audit.inputs.get((t, rid), {}).get('payload', {})
                observed = payload.get('observed_now', {}).get('inbox', []) + payload.get('private_process', {}).get('memories', [])
                seen = any(m.get('message_id') == mid for m in observed)
                if delivered is None or delivered >= t or not seen:
                    continue
                refs.append(did)
                if reply['disposition'] == 'rejected':
                    declined = True
                    authorized.discard(rid)
                elif reply['disposition'] == 'accepted':
                    authorized.add(rid)
            # Proposals are emitted after action execution, whereas responses
            # are processed before action execution. Use the corresponding phase.
            phase = post if step == raw['step'] else pre
            blockers = formation_blockers(audit, raw, step, phase, cid)
            if declined:
                blockers.append('participant_declined')
            if not travelers <= authorized:
                blockers.append('missing_effective_acceptance')
            expected = not blockers
            actual = commitments(post).get(cid)
            issues = []
            if expected and actual is None:
                issues.append('effective_acceptance_without_recorded_agreement')
            if not expected and actual is not None:
                issues.append('agreement_created_without_valid_formation')
            rows.append({'record_id': f'{mid}@{step}', 'proposal_id': mid,
                'household_id': audit.member_h[raw['sender']], 'step': step,
                'expected_formation': expected, 'actual_agreement_id': cid if actual else None,
                'blockers': sorted(set(blockers)), 'issues': issues,
                'evidence': refs + [f'events/events.jsonl#step={step}/world/household_commitments']})
    positive = [r for r in rows if r.get('expected_formation') is True]
    negative = [r for r in rows if r.get('expected_formation') is False]
    result = metric(rows, '每个原始提案的提交时刻及针对该提案的回应时刻，独立核验应当创建／不得创建共识。',
        ['这是新增的形成机会检查，与旧版已创建状态变更错误率分开报告。',
         '正向机会与负向机会分别统计；只有拒绝或未同意样本时，不证明有效同意能够形成共识。',
         '当前核验家庭内协议及显式照护约束；不把跨家庭接送尝试当作有效家庭内提案。'])
    result.update(version='formation_opportunities_20260912',
        positive=metric(positive, '条件满足时必须创建共识。'),
        negative=metric(negative, '条件不满足时不得创建共识。'))
    return result, rows
