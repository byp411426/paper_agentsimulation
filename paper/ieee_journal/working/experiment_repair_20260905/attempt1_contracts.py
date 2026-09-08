"""E1-only explicit plans and household proposals; E2/E3 schemas stay unchanged."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from ds.agents.decide import ResidentDecision, OutMsg

class PlanStep(BaseModel):
    action: Literal['monitor','prepare','coordinate','depart','seek_help']
    due_step: int = Field(ge=0)
    description: str = Field(max_length=180)

class ProtectivePlan(BaseModel):
    goal: str = Field(max_length=180)
    steps: list[PlanStep] = Field(min_length=1,max_length=3)
    reason: str = Field(max_length=240)

class PartyProposal(BaseModel):
    traveler_ids: list[str] = Field(min_length=1)
    accompanying_member_ids: list[str] = Field(default_factory=list)
    caregiver_by_member: dict[str,str] = Field(default_factory=dict)
    vehicle_id: str
    route_id: str
    depart_step: int = Field(ge=0)
    supersedes_id: str | None = None
    content: str = Field(max_length=240)

class InformationMessage(OutMsg):
    kind: Literal['notice','acknowledgement'] = 'notice'

class E1Decision(ResidentDecision):
    messages: list[InformationMessage] = Field(default_factory=list)
    party_proposal: PartyProposal | None = None
    departure_mode: Literal['solo','commitment'] | None = None
    commitment_id: str | None = None
    cancel_commitment_ids: list[str] = Field(default_factory=list)
    plan_update: ProtectivePlan | None = None

    @model_validator(mode='after')
    def explicit_departure(self):
        if self.action=='evacuate':
            if self.departure_mode is None or self.depart_step is None or not self.route_id or not self.vehicle_id:
                raise ValueError('evacuate requires explicit departure_mode, depart_step, route_id and vehicle_id')
            if self.departure_mode=='commitment' and not self.commitment_id:
                raise ValueError('commitment departure requires commitment_id from a received acceptance notification')
            if self.departure_mode=='solo' and self.party_proposal is not None:
                raise ValueError('do not depart solo and propose a shared trip in the same decision; choose prepare while proposing')
        return self
