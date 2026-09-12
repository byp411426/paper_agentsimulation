"""Published cognitive architectures adapted to the common disaster action space.

GA retrieval and AS needs/planning/cognition run their pinned upstream code.
GA scheduling/reflection and the domain action translators are explicit ports.
All methods share the existing physical and household protocol services; this
comparison therefore isolates resident architectures, not whole simulators.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from typing import Any
from pydantic import BaseModel, Field, RootModel

from ds.agents.carr_empirical_v2 import CarrEmpiricalResidentV2
from ds.agents.e1_contracts import E1Decision
from ds.kernel.rng import stream_seed
from .ga_support import get_embedding


class JsonObject(RootModel[dict[str, Any]]):
    pass

class Importance(BaseModel):
    scores: list[int] = Field(min_length=1)

class FocalQuestions(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=3)

class Insight(BaseModel):
    thought: str
    evidence_ids: list[str] = Field(min_length=1)

class Reflection(BaseModel):
    insights: list[Insight] = Field(min_length=1, max_length=5)

class ScheduledActivity(BaseModel):
    due_step: int = Field(ge=0)
    activity: str

class Schedule(BaseModel):
    goal: str
    activities: list[ScheduledActivity] = Field(min_length=1, max_length=8)
    reason: str

class Reaction(BaseModel):
    revise: bool
    reason: str

class NativeStepDecision(E1Decision):
    cognitive_step_complete: bool = Field(description="Whether successful execution of this decision would complete the current native plan step. Sending a proposal does not complete agreement or departure.")
    cognitive_step_reason: str


class PublishedResident(CarrEmpiricalResidentV2):
    architecture = "abstract"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._seen_events = set()
        self._pending_events = []
        self._call_index = 0
        self._step = 0
        self._gateway = None

    async def _call(self, stage, prompt, schema=JsonObject):
        self._call_index += 1
        messages = prompt if isinstance(prompt, list) else [{"role":"user", "content":prompt}]
        if not any(x["role"] == "system" for x in messages):
            messages = [{"role":"system", "content":
                "You are a resident's internal cognitive module in a synthetic disaster simulation. "
                "Use only supplied information. Inferences are beliefs, not new world facts. "
                "Return concise valid JSON.\nSchema: " + json.dumps(schema.model_json_schema())}] + messages
        seed = stream_seed(self._gateway.run_seed, "baseline_module:"+stage,
                           entity_id=self.id, step=self._step*100+self._call_index)
        # Native AS blocks request free JSON dictionaries whose fields differ by
        # stage. A forced function with an unconstrained object schema elides
        # their requested fields. Preserve their original JSON-object interface.
        model = self._gateway.decision_model + ("_native_json" if schema is JsonObject else "")
        result = await self._gateway.complete(step=self._step, agent_id=self.id+"::"+stage+":"+str(self._call_index),
            model=model, messages=messages, schema=schema,
            seed=seed, temperature=self._gateway.temperature)
        self._write("architecture_calls.jsonl", {"step":self._step, "resident_id":self.id,
            "stage":stage,"input":messages,"output":result.model_dump()})
        return result

    def _write(self, filename, row):
        with (self._gateway.log_path.parent/filename).open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str)+"\n")

    def _begin(self, world, gateway, step):
        self._gateway, self._step, self._call_index = gateway, step, 0
        self._decision_inbox_step = step
        self._decision_inbox_keys = {(i.get("kind"), i.get("receipt_id") or i.get("message_id")) for i in self.inbox}
        payload = super()._prompt_payload(world=world,step=step)
        payload.pop("private_process")
        pending, self._pending_events = self._pending_events, []
        pending.append({"kind":"local_observation", "step":step, "content":{
            "hazard_distance_m":payload["observed_now"]["hazard_distance_m"],
            "resources":payload["observed_now"]["shared_resource_reservations"],
            "route_beliefs":payload["observed_now"]["perceived_routes"]}})
        for item in deepcopy(self.inbox):
            key=(item.get("kind"), item.get("receipt_id") or item.get("message_id"))
            if key not in self._seen_events:
                self._seen_events.add(key)
                pending.append({"kind":"received_information", "step":step, "content":item})
        return payload, pending

    async def _action(self, payload, architecture_context, schema=E1Decision):
        payload["private_process"] = architecture_context
        system = self.decision_system_prompt().replace(
            "You are one resident making protective-action decisions with private memory and a persistent plan. ",
            "Choose this resident's current behavior using the supplied cognitive state and plan. ",1)
        if schema is not E1Decision:
            system = system[:system.index("Output JSON matching this schema:")] + "Output JSON matching this schema:\n" + json.dumps(schema.model_json_schema())
        messages=[{"role":"system","content":system},
                  {"role":"user","content":json.dumps(payload,ensure_ascii=False,default=str)}]
        self._write("decision_inputs.jsonl",{"step":self._step,"resident_id":self.id,"payload":payload})
        result = await self._gateway.complete(step=self._step,agent_id=self.id,
            model=self._gateway.decision_model,messages=messages,schema=schema,
            seed=stream_seed(self._gateway.run_seed,"llm_decision",entity_id=self.id,step=self._step),
            temperature=self._gateway.temperature)
        return self._normalize_proposal(result,step=self._step)

    def commit_execution(self, decision, outcome, *, step):
        super().commit_execution(decision,outcome,step=step)
        self._pending_events.append({"kind":"own_action_and_feedback","step":step,
            "decision":decision.model_dump(),"feedback":deepcopy(self.recent_execution_feedback[-1])})


class GenerativeAgentsResident(PublishedResident):
    architecture = "generative_agents_disaster_adaptation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nodes=[]
        self._importance_sum=0
        self.schedule=None
        self.fine_schedule=None
        self.reflections=0
        self._last_schedule_window=-1

    def _add_node(self, description, importance, kind="event", evidence=None):
        node=SimpleNamespace(node_id=f"memory_{len(self.nodes)+1}",description=description,
            embedding_key=description,poignancy=importance,kind=kind,
            last_accessed=datetime(2026,1,1,8)+timedelta(minutes=self._step*30),
            created_step=self._step,evidence=evidence or [])
        self.nodes.append(node)
        return node

    def _retrieve(self, queries, count=20):
        from .vendor.ga_retrieve import new_retrieve
        if not self.nodes:
            return []
        persona=SimpleNamespace(
            scratch=SimpleNamespace(recency_decay=.995, recency_w=1,relevance_w=1,importance_w=1,
                curr_time=datetime(2026,1,1,8)+timedelta(minutes=self._step*30)),
            a_mem=SimpleNamespace(seq_event=[n for n in self.nodes if n.kind=="event"],
                seq_thought=[n for n in self.nodes if n.kind!="event"],
                id_to_node={n.node_id:n for n in self.nodes},
                embeddings={n.embedding_key:get_embedding(n.description) for n in self.nodes}))
        result=new_retrieve(persona,queries,n_count=count)
        found={n.node_id:n for nodes in result.values() for n in nodes}
        return [{"id":n.node_id,"description":n.description,"kind":n.kind,
                 "step":n.created_step,"evidence_ids":n.evidence} for n in found.values()]

    async def _reflect(self, has_conversation):
        if self._importance_sum < 150 and not has_conversation:
            return
        recent=[{"id":n.node_id,"description":n.description} for n in self.nodes[-100:]]
        questions=await self._call("ga_reflection_questions",
            "Given only these recent events and thoughts, identify up to three salient high-level "
            "questions about this resident's experiences, other people and plans.\n"+json.dumps(recent),FocalQuestions)
        relevant=self._retrieve(questions.questions,30)
        reflection=await self._call("ga_reflection_insights",
            "Infer up to five higher-level insights from these memories. Each insight must cite the "
            "actual memory IDs supporting it. Do not treat inference as verified world fact.\n"+json.dumps(relevant),Reflection)
        valid_ids={n.node_id for n in self.nodes}
        for insight in reflection.insights:
            if not set(insight.evidence_ids)<=valid_ids:
                raise ValueError("GA reflection cited nonexistent memory")
            self._add_node(insight.thought,5,"thought",insight.evidence_ids)
        self.reflections+=1
        self._importance_sum=0

    async def decide(self, *, events, world, gateway, step):
        payload, pending=self._begin(world,gateway,step)
        descriptions=[json.dumps(x,ensure_ascii=False) for x in pending]
        rated=await self._call("ga_importance",
            "Rate the poignancy of EACH memory from 1 (mundane) to 10 (extremely important). "
            "Return one integer per memory in the same order, under scores.\n"+json.dumps(descriptions),Importance)
        if len(rated.scores)!=len(descriptions) or any(not 1<=s<=10 for s in rated.scores):
            raise ValueError("GA importance requires one valid score per memory")
        for desc,score in zip(descriptions,rated.scores):
            self._add_node(desc,score)
            self._importance_sum+=score
        conversation=any(x["kind"]=="received_information" and x["content"].get("message_kind") in
                         ("proposal","notice","acknowledgement") for x in pending)
        await self._reflect(conversation)
        query="Current protective action and family situation. "+(self.schedule.goal if self.schedule else "")
        retrieved=self._retrieve([query],20)
        context={"resident":payload,"retrieved_memories":retrieved,"schedule":self.schedule.model_dump() if self.schedule else None}
        revise=self.schedule is None
        if self.schedule is not None:
            reaction=await self._call("ga_reaction",
                "Given the current schedule and newly perceived events, decide whether the remaining "
                "schedule should be revised or continued. Both are allowed.\n"+json.dumps(context),Reaction)
            revise=reaction.revise
        if revise:
            self.schedule=await self._call("ga_schedule",
                "Plan this resident's remaining disaster-response episode as 4-6 broad activities, "
                "with due_step times from the current step through step 25. Preserve plausible personal "
                "priorities and account for current experiences. Only use the supplied world's capabilities. "
                "Plans are intentions, not completed actions or others' consent.\n"+json.dumps(context),Schedule)
            self._add_node(json.dumps(self.schedule.model_dump()),5,"thought")
        window=step//4
        if revise or window!=self._last_schedule_window:
            self.fine_schedule=await self._call("ga_decompose",
                "Decompose the relevant part of the broad schedule into concrete activities for the next "
                "four half-hour steps. Include due_step and preserve room to react to new events. "
                "Do not assume messages were delivered, accepted, or actions executed.\n"+
                json.dumps({"current_step":step,"schedule":self.schedule.model_dump(),"current_situation":payload}),Schedule)
            self._last_schedule_window=window
        return await self._action(payload,{"retrieved_memories":retrieved,
            "broad_schedule":self.schedule.model_dump(),"detailed_schedule":self.fine_schedule.model_dump()})

    def snapshot(self):
        result=super().snapshot()
        result["architecture_state"]={"kind":self.architecture,"memory_nodes":len(self.nodes),
            "reflections":self.reflections,"importance_since_reflection":self._importance_sum,
            "schedule":self.schedule.model_dump() if self.schedule else None}
        return result


class NativeLLM:
    def __init__(self,resident):
        self.resident=resident
        self.stage="as_module"
    async def atext_request(self,dialog,**kwargs):
        result=await self.resident._call(self.stage,dialog)
        return result.model_dump_json()


class AgentSocietyResident(PublishedResident):
    architecture="agentsociety_2025_disaster_adaptation"

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        from .as_support import Environment, Memory, DotDict, AgentToolbox, Agent
        from .vendor.as_needs_block import NeedsBlock
        from .vendor.as_plan_block import PlanBlock
        from .vendor.as_cognition_block import CognitionBlock
        self.env=Environment()
        self.ctx=DotDict()
        p=self.profile.get("pums_static",{})
        traits=self.profile.get("latent_traits",{})
        status={k:p.get(k,"not provided") for k in
                ("gender","race","religion","marriage_status","occupation","education","income","skill")}
        status["gender"]=p.get("sex", "not provided")
        status["occupation"]=p.get("employment", "not provided")
        status.update(age=self.profile.get("age"),residence="synthetic household",
            personality=json.dumps({k:v for k,v in traits.items() if not k.endswith("_band")}),
            consumption="not provided",family_consumption="not provided",
            thought="No prior event history supplied.",emotion_types="neutral",
            emotion={k:5 for k in ["sadness","joy","fear","disgust","anger","surprise"]},
            attitude={},current_plan=None,plan_history=[],execution_context={},current_need="none",
            hunger_satisfaction=.8,energy_satisfaction=.8,safety_satisfaction=.8,social_satisfaction=.8,
            position={"aoi_position":self.household_id},home={"aoi_position":self.household_id},
            work={"aoi_position":"unavailable"},location_knowledge={})
        self.native_memory=Memory(status,self.env)
        self.native_llm=NativeLLM(self)
        toolbox=AgentToolbox(llm=self.native_llm,environment=self.env)
        self.needs=NeedsBlock(toolbox,self.native_memory,self.ctx)
        self.planner=PlanBlock(Agent(),toolbox,self.native_memory,self.ctx,max_plan_steps=6)
        self.cognition=CognitionBlock(toolbox,self.native_memory)
        # Domain action vocabulary replaces urban work/shopping in this emergency-only world.
        self.planner.guidance_options={
            "hungry":["Prepare available supplies", "Seek help", "Wait at current location"],
            "tired":["Wait and rest", "Seek assistance"],
            "safe":["Assess received warnings", "Prepare", "Coordinate with household", "Seek help", "Depart if chosen and feasible", "Wait"],
            "social":["Contact household", "Exchange information with known neighbors", "Offer help"],
            "whatever":["Wait", "Prepare", "Communicate", "Seek help", "Offer help", "Depart if chosen and feasible"]}
        self._last_native_feedback=None

    async def decide(self,*,events,world,gateway,step):
        payload,pending=self._begin(world,gateway,step)
        self.env.step=step
        self.env.payload=payload
        self.ctx.update(current_time=self.env.get_datetime(True)[1],current_position=str(payload["current_location"]),
            weather="not provided",temperature="not provided",other_information=json.dumps(payload),
            current_thought=self.native_memory.status.data["thought"])
        await self.native_memory.status.update("position",{"aoi_position":str(payload["current_location"])})
        for row in pending:
            await self.native_memory.stream.add(topic="environment",description=json.dumps(row,ensure_ascii=False))
        self.native_llm.stage="as_needs_initialize"
        await self.needs.initialize()
        await self.needs.time_decay()
        self.native_llm.stage="as_execution_needs_update"
        await self.needs.update_when_plan_completed()
        incoming=[x for x in pending if x["kind"]=="received_information"]
        if incoming or self._last_native_feedback:
            incident=json.dumps({"received":incoming,"last_execution":self._last_native_feedback},ensure_ascii=False)
            self.native_llm.stage="as_emotion_update"
            conclusion=await self.cognition.emotion_update(incident)
            await self.native_memory.stream.add(topic="cognition",description=conclusion)
            self.native_llm.stage="as_intervention_needs"
            await self.needs.reflect_to_intervention(incident)
        self.native_llm.stage="as_needs_priority"
        await self.needs.determine_current_need()
        if not self.native_memory.status.data["current_plan"]:
            self.native_llm.stage="as_plan_guidance_and_steps"
            self.ctx.current_thought=self.native_memory.status.data["thought"]
            cognition=await self.planner.forward()
            if not self.native_memory.status.data["current_plan"]:
                raise ValueError("AgentSociety native planning produced no valid plan")
            if cognition:
                await self.native_memory.status.update("thought",cognition)
        self.native_llm.stage="as_daily_cognition"
        await self.cognition.forward()
        status=deepcopy(self.native_memory.status.data)
        plan=status["current_plan"]
        relevant=await self.native_memory.stream.search(query=plan["target"],top_k=20)
        return await self._action(payload,{"needs":{k:status[k] for k in
            ["hunger_satisfaction","energy_satisfaction","safety_satisfaction","social_satisfaction","current_need"]},
            "emotion":status["emotion"],"emotion_word":status["emotion_types"],"thought":status["thought"],
            "native_plan":plan,"current_intention":plan["steps"][plan["index"]],
            "retrieved_stream":json.loads(relevant)},schema=NativeStepDecision)

    def commit_execution(self,decision,outcome,*,step):
        super().commit_execution(decision,outcome,step=step)
        status=self.native_memory.status.data
        plan=status.get("current_plan")
        self._last_native_feedback=deepcopy(self.recent_execution_feedback[-1])
        if plan:
            i=plan["index"]
            plan["steps"][i]["evaluation"]={"status":outcome.status,
                "evaluation":json.dumps({"requested":decision.action,"feedback":self._last_native_feedback}),
                "details":getattr(outcome,"reason",None)}
            if outcome.status=="rejected":
                plan["failed"]=True
            elif not decision.cognitive_step_complete:
                plan["steps"][i]["evaluation"]["status"]="pending"
            elif i+1<len(plan["steps"]):
                plan["index"]=i+1
            else:
                plan["completed"]=True

    def snapshot(self):
        result=super().snapshot()
        if hasattr(self,"native_memory"):
            result["architecture_state"]={"kind":self.architecture,"status":deepcopy(self.native_memory.status.data),
                "stream_size":len(self.native_memory.stream.rows)}
        return result


RESIDENT_TYPES={"disastersociety":CarrEmpiricalResidentV2,
    "generative_agents":GenerativeAgentsResident,"agentsociety":AgentSocietyResident}
