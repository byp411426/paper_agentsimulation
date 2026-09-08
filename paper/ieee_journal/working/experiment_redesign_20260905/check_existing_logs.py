"""Read-only inspection of selected existing runs; writes only review artifacts.

This checks record availability, not scientific validity or canonical-run selection.
Usage: python3 check_existing_logs.py RUN_DIR [RUN_DIR ...]
"""
import collections
import json
import sys
from pathlib import Path


def lines(path):
    if not path.exists():
        return []
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def inspect(root):
    profiles = lines(root / 'member_profiles.jsonl')
    events = lines(root / 'events/events.jsonl')
    departures = lines(root / 'household_departure_ledger.jsonl')
    commitments = lines(root / 'commitment_ledger.jsonl')
    messages = lines(root / 'message_ledger.jsonl')
    receipts = lines(root / 'official_receipts.jsonl')
    resident_states = lines(root / 'resident_state_timeline.jsonl')
    member_ids = {r['resident_id'] for r in profiles}
    executed = [r for r in departures if r.get('outcome') == 'executed']
    occurrences = collections.Counter()
    for row in executed:
        occurrences.update(set(row.get('traveler_ids', []) + row.get('accompanying_member_ids', [])))
    final_locations = events[-1].get('world', {}).get('member_locations', {}) if events else {}
    commitment_ids = {r['id'] for r in commitments}
    departure_commitment_ids = {r.get('commitment_id') for r in departures if r.get('commitment_id')}
    party_steps = collections.defaultdict(set)
    for r in executed:
        party_steps[r.get('party_id')].add(r.get('step'))
    return {
        'run_directory_name': root.parent.name + '/' + root.name,
        'canonical_selection_verified': False,
        'profile_members': len(member_ids),
        'profile_households': len({r['household_id'] for r in profiles}),
        'decision_capable_members': sum(r.get('decision_capable') is True for r in profiles),
        'event_snapshots': len(events),
        'event_steps': [r.get('step') for r in events],
        'resident_state_rows': len(resident_states),
        'resident_state_rows_with_step': sum('step' in r for r in resident_states),
        'official_receipt_rows': len(receipts),
        'message_rows': len(messages),
        'message_rows_with_multiple_recipients': sum(len(r.get('recipient_ids', [])) > 1 for r in messages),
        'commitment_rows': len(commitments),
        'commitment_rows_with_top_level_step': sum('step' in r for r in commitments),
        'commitment_status_counts': dict(collections.Counter(r.get('status') for r in commitments)),
        'departure_outcome_counts': dict(collections.Counter(r.get('outcome') for r in departures)),
        'executed_departure_records': len(executed),
        'unique_members_in_executed_records': len(occurrences),
        'members_in_more_than_one_executed_record': sum(n > 1 for n in occurrences.values()),
        'party_ids_executed_at_multiple_steps': sum(len(v) > 1 for k, v in party_steps.items() if k),
        'departure_commitment_id_count': len(departure_commitment_ids),
        'departure_commitment_ids_found': len(departure_commitment_ids & commitment_ids),
        'departure_commitment_ids_missing': len(departure_commitment_ids - commitment_ids),
        'final_location_entries': len(final_locations),
        'profile_members_missing_from_final_location_map': len(member_ids - set(final_locations)),
        'scope_note': 'Availability and consistency signals only. Repeated records need event-level interpretation; absent locations are unknown until reconciled, not automatically stayers. No new simulation run.',
    }


if __name__ == '__main__':
    rows = [inspect(Path(arg)) for arg in sys.argv[1:]]
    out = Path(__file__).resolve().parent / 'existing_log_check.json'
    out.write_text(json.dumps({'status': 'READ_ONLY_PRECHECK', 'runs': rows}, ensure_ascii=False, indent=2) + '\n')
    for r in rows:
        print(json.dumps({k: r[k] for k in (
            'run_directory_name', 'profile_households', 'profile_members',
            'event_snapshots', 'executed_departure_records',
            'members_in_more_than_one_executed_record',
            'party_ids_executed_at_multiple_steps',
            'profile_members_missing_from_final_location_map',
            'departure_commitment_ids_missing')}, ensure_ascii=False))
