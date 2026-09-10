"""Evaluator sensitivity tests; mutate in-memory copies, never archived logs."""
import copy
import os
import unittest
from pathlib import Path

from scripts.audit_archived_run import Audit, metric


ROOT = Path(os.environ.get("DISASTERSOCIETY_REPO", Path(__file__).resolve().parents[2]))
BATCH = ROOT / "paper/ieee_journal/working/main_experiments_20260905"
RUN = BATCH / "runs/24hh_seed7201/attempt3/carr_s_e1_repaired_24_20260905"


class AuditSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.audit = Audit(RUN, BATCH)

    def test_archived_run_and_legitimate_rejections_are_not_errors(self):
        result = self.audit.run_checks()
        self.assertEqual((result['metrics']['information']['errors'], result['metrics']['information']['checked']), (0, 124))
        self.assertEqual((result['metrics']['consensus']['errors'], result['metrics']['consensus']['checked']), (0, 12))
        self.assertEqual((result['metrics']['execution']['errors'], result['metrics']['execution']['checked']), (0, 28))
        self.assertEqual(result['additional_checks']['departure_outcomes']['rejected'], 13)
        self.assertEqual(result['additional_checks']['nondeparture_checks']['errors'], 0)
        self.assertEqual(result['additional_checks']['all_member_transition_checks']['errors'], 0)
        self.assertEqual(len(result['input_checks']['household_description_contradictions']), 4)

    def test_adding_another_residents_receipt_is_detected(self):
        event = self.audit.events[6]
        source = next(a for a in event['agents'] if a['id'] == 'syn_t001_h0000002_r001')
        target = next(a for a in event['agents'] if a['id'] == 'syn_t001_h0000002_r002')
        target['receipts'].append(copy.deepcopy(source['receipts'][0]))
        self.assertGreater(self.audit.audit_information()['errors'], 0)

    def test_message_seen_before_delivery_is_detected(self):
        target = self.audit.events[0]['agents'][0]
        msg = copy.deepcopy(next(iter(self.audit.messages.values())))
        msg['kind'] = 'message'
        target['inbox'].append(msg)
        self.assertGreater(self.audit.audit_information()['errors'], 0)

    def test_fabricated_receipt_only_in_model_input_is_detected(self):
        item = self.audit.inputs[(10, 'syn_t001_h0000002_r002')]
        item['payload']['observed_now']['inbox'].append({'kind': 'official_receipt',
            'source_event_id': 'order_m_4', 'severity': 'mandatory'})
        self.assertGreater(self.audit.audit_information()['errors'], 0)

    def test_missing_real_acceptance_cannot_be_replaced_by_accepted_flag(self):
        mid = 'm7:syn_t002_h0000013_r001:0'
        for d in self.audit.decisions.values():
            d['decision']['message_responses'] = [x for x in d['decision']['message_responses'] if x['message_id'] != mid]
        self.assertGreater(self.audit.audit_consensus()['errors'], 0)

    def test_old_acceptance_does_not_authorize_changed_route(self):
        cid = 'commit:m7:syn_t002_h0000013_r001:0'
        self.audit.events[7]['world']['household_commitments']['syn_t002_h0000013'][cid]['party']['route_id'] = 'invented_route'
        self.assertGreater(self.audit.audit_consensus()['errors'], 0)

    def test_rejected_action_cannot_move_the_resident(self):
        event = next(e for e in self.audit.events if any(d['outcome']['status'] == 'rejected' for d in e['decisions']))
        d = next(d for d in event['decisions'] if d['outcome']['status'] == 'rejected')
        event['world']['member_locations'][d['agent']] = self.audit.cfg['experiment']['safe_zone']
        self.assertGreater(self.audit.audit_execution()['errors'], 0)

    def test_physical_change_without_any_decision_is_detected_separately(self):
        rid = self.audit.events[0]['agents'][0]['id']
        self.audit.events[0]['world']['member_locations'][rid] = self.audit.cfg['experiment']['safe_zone']
        self.audit.audit_execution()
        self.assertGreater(self.audit.extras['all_member_transition_checks']['errors'], 0)

    def test_unexplained_predecision_position_change_is_detected(self):
        rid = self.audit.events[0]['agents'][0]['id']
        self.audit.events[0]['state_before_decisions']['world']['member_locations'][rid] = 'elsewhere'
        self.audit.audit_execution()
        self.assertIn('unexplained_location_change_before_decision_phase', self.audit.evidence['all_member_transition_checks'][0]['issues'])

    def test_private_false_belief_is_not_a_fabricated_receipt(self):
        self.audit.events[0]['agents'][0]['memories'].append({'kind': 'belief', 'content': 'I suspect the primary road is closed.'})
        self.assertEqual(self.audit.audit_information()['errors'], 0)

    def test_no_opportunity_is_not_zero_error(self):
        result = metric([], 'no events')
        self.assertIsNone(result['rate'])
        self.assertIsNone(result['errors'])
        self.assertEqual(result['status'], 'no_check_opportunity')


if __name__ == '__main__':
    unittest.main(verbosity=2)
