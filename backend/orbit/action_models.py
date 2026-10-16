"""Exact, reviewable action contracts. No arbitrary provider request bodies."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .models import StrictModel, Id, AwareDatetime, TaskProperties

Address = Annotated[str, Field(pattern=r'^[^\s<>@,;\r\n]+@[^\s<>@,;\r\n]+\.[^\s<>@,;\r\n]+$',max_length=320)]
Short = Annotated[str, Field(min_length=1,max_length=320)]
Kind = Literal['calendar_create','calendar_update','gmail_send','slack_post','task_create','task_update']

class EventChanges(StrictModel):
    summary: str | None = Field(default=None,min_length=1,max_length=240)
    description: str | None = Field(default=None,max_length=4000)
    location: str | None = Field(default=None,max_length=500)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    attendees: list[Address] | None = Field(default=None,max_length=30)

    @model_validator(mode='after')
    def valid(self):
        if bool(self.starts_at)!=bool(self.ends_at) or (self.starts_at and self.ends_at<=self.starts_at):
            raise ValueError('Supply a positive start/end interval together')
        if not self.model_dump(exclude_none=True):raise ValueError('Specify the exact event changes')
        return self

class CalendarCreate(StrictModel):
    calendar_id: Short
    changes: EventChanges
    send_updates: Literal['none','all','externalOnly'] = 'none'

    @model_validator(mode='after')
    def required(self):
        if not self.changes.summary or not self.changes.starts_at:raise ValueError('New events require a title and interval')
        return self

class CalendarUpdate(StrictModel):
    calendar_id: Short
    event_id: Short
    expected_etag: Short
    changes: EventChanges
    send_updates: Literal['none','all','externalOnly'] = 'none'

class EmailSend(StrictModel):
    to: list[Address] = Field(min_length=1,max_length=20)
    cc: list[Address] = Field(default_factory=list,max_length=20)
    subject: str = Field(min_length=1,max_length=240,pattern=r'^[^\r\n]+$')
    body: str = Field(min_length=1,max_length=16000)

class SlackPost(StrictModel):
    channel_id: Annotated[str,Field(pattern=r'^C[A-Z0-9]{5,30}$')]
    text: str = Field(min_length=1,max_length=4000)

class TaskChange(StrictModel):
    task_id: Id
    changes: TaskProperties
    assignee_id: Id | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if not self.changes.model_dump(exclude_none=True) and not self.assignee_id:raise ValueError('Specify task changes or an assignee')
        return self

PAYLOADS={'calendar_create':CalendarCreate,'calendar_update':CalendarUpdate,'gmail_send':EmailSend,
          'slack_post':SlackPost,'task_create':TaskChange,'task_update':TaskChange}
TOOLS={kind:'action_'+kind for kind in PAYLOADS}
ROLES={'planner':{'calendar_create','calendar_update'},'tasks':{'task_create','task_update'},
       'communication':{'gmail_send','slack_post'},'research':set()}

class ActionDraft(StrictModel):
    kind: Kind
    payload: dict
    reason: str = Field(min_length=1,max_length=2000)
    affected_ids: list[Id] = Field(min_length=1,max_length=12)
    evidence_ids: list[Id] = Field(min_length=1,max_length=12)
    decision_id: Id | None = None

    @model_validator(mode='after')
    def payload_contract(self):
        self.payload=PAYLOADS[self.kind].model_validate(self.payload).model_dump(mode='json',exclude_none=True)
        if self.kind=='task_create' and not self.payload['changes'].get('name'):raise ValueError('New tasks require a name')
        return self

class ProposalRequest(StrictModel):
    message_id: Id
    draft: ActionDraft

class ApprovalRequest(StrictModel):
    digest: Annotated[str,Field(pattern=r'^[a-f0-9]{64}$')]
