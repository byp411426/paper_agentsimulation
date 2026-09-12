"""Artificial parser fixtures only; no model calls or behavioral evidence."""
import json
from pathlib import Path
import pytest
from scripts.audit_archived_run import dump, digest
from scripts.evaluate_published_comparison import collect


@pytest.fixture
def review(tmp_path):
    review=tmp_path/'anonymous'; review.mkdir()
    (review/'rubric.md').write_text('Artificial parser fixture')
    cases=[]; key=[]
    methods=('generative_agents','agentsociety','disastersociety')
    for i,m in enumerate(methods,1):
        cid=f'C{i}';p=review/(cid+'.json')
        dump(p,{'case_id':cid,'profile':{'member_profiles':[{'resident_id':'R'}]},
                'steps':[{'step':1},{'step':2}]})
        cases.append({'case_id':cid,'file':p.name,'sha256':digest(p)})
        key.append({'case_id':cid,'method':m,'household_id':'H'})
    pairs=[{'pair_id':'P1','A':'C3','B':'C1'}, {'pair_id':'P2','A':'C2','B':'C3'}]
    batches=[]; judgments=tmp_path/'judgments';judgments.mkdir()
    for order in ('forward','reverse'):
        bid='batch_1_'+order
        ordered=pairs if order=='forward' else [{**p,'A':p['B'],'B':p['A']} for p in pairs]
        ids=['C1','C2','C3'] if order=='forward' else ['C1']
        assignment={'score_case_ids':ids,'pairs':ordered,'output_file':bid+'_judgments.json'}
        p=review/(bid+'.json');dump(p,assignment)
        batches.append({'batch_id':bid,'file':p.name,'sha256':digest(p)})
        scores=[{'case_id':c,'score':3,'confidence':'low','rationale_zh':'Parser fixture',
            'evidence':[{'step':i,'resident_id':'R','assessment_zh':'Fixture'} for i in (1,2)],
            'input_issues':[],'limitations':['Artificial']} for c in ids]
        preferences=[]
        for pair in ordered:
            # The same substantive preference after swapping sides; P2 is tied.
            winner=('A' if pair['A']=='C3' else 'B') if pair['pair_id']=='P1' else 'tie'
            preferences.append({'pair_id':pair['pair_id'],'winner':winner,'rationale_zh':'Fixture',
                'evidence':[{'side':s,'step':1,'resident_id':'R','assessment_zh':'Fixture'} for s in ('A','B')]})
        dump(judgments/assignment['output_file'],{'scores':scores,'pairs':preferences})
    dump(tmp_path/'private_method_key.json',key)
    dump(tmp_path/'manifest.json',{'kind':'scripted_software_check','cases':cases,'pairs':pairs,
        'batches':batches,'rubric_sha256':digest(review/'rubric.md')})
    return tmp_path,judgments


def test_order_swap_maps_back_to_method_and_scripted_check_stays_labeled(review):
    output,judgments=review
    result=collect(output,judgments)
    assert result['kind']=='scripted_review_pipeline_check'
    assert result['pairwise']['generative_agents']['ours_win_rate_with_half_ties']==1
    assert result['pairwise']['agentsociety']['ours_win_rate_with_half_ties']==.5
    assert result['pairwise']['generative_agents']['order_disagreements']==0
    assert len(result['repeat_scores'])==1


def test_missing_or_changed_judgments_cannot_inflate_result(review):
    output,judgments=review
    p=judgments/'batch_1_forward_judgments.json';data=json.loads(p.read_text())
    data['pairs'].pop();dump(p,data)
    with pytest.raises(ValueError,match='Missing/duplicate pairwise'):
        collect(output,judgments)
    assert not (output/'behavior_comparison.json').exists()


def test_changed_case_is_rejected(review):
    output,judgments=review
    (output/'anonymous/C1.json').write_text('{}')
    with pytest.raises(ValueError,match='Case changed'):
        collect(output,judgments)


def test_reference_audit_detects_unlogged_copy_and_wrong_source(tmp_path):
    from types import SimpleNamespace
    from ds.llm.cache import LLMCache
    from scripts.evaluate_published_comparison import audit_reference_resolutions
    raw={'action':'evacuate','departure_mode':'commitment','commitment_id':'c',
         'vehicle_id':None,'route_id':None,'depart_step':None}
    fill={'vehicle_id':'v','route_id':'alternate','depart_step':5}
    source={'commitment_id':'c','status':'accepted',**fill}
    cache=LLMCache(tmp_path/'llm_cache.sqlite');cache.put('k','mock',json.dumps(raw),0,0);cache.close()
    (tmp_path/'llm_calls.jsonl').write_text(json.dumps({'step':5,'agent_id':'r','status':'ok','key':'k'})+'\n')
    audit=SimpleNamespace(run=tmp_path,decisions={(5,'r'):{'decision':{**raw,**fill}}},
        inputs={(5,'r'):{'payload':{'own_commitment_statuses':[source]}}})
    assert audit_reference_resolutions(audit)['errors']==1  # copy without a record
    record={'step':5,'resident_id':'r','raw_request':raw,'source_record':source,'resolved_fields':fill}
    (tmp_path/'decision_reference_resolutions.jsonl').write_text(json.dumps(record)+'\n')
    assert audit_reference_resolutions(audit)['errors']==0
    audit.inputs[(5,'r')]['payload']['own_commitment_statuses'][0]['route_id']='primary'
    assert audit_reference_resolutions(audit)['errors']==1  # logged source disagrees with actual input
