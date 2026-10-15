from enum import Enum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

Id = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')]
Text = Annotated[str, Field(min_length=1, max_length=20000)]
Name = Annotated[str, Field(min_length=1, max_length=240)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class EntityType(str, Enum):
    Person='Person'; Event='Event'; Task='Task'; Booking='Booking'
    Conversation='Conversation'; Message='Message'; Bot='Bot'; Source='Source'
    Claim='Claim'; Decision='Decision'; Action='Action'; Outcome='Outcome'

class RelationType(str, Enum):
    ASSIGNED_TO='ASSIGNED_TO'; DEPENDS_ON='DEPENDS_ON'; RELATED_TO='RELATED_TO'
    PARTICIPATES_IN='PARTICIPATES_IN'; AFFECTS='AFFECTS'; MENTIONED_IN='MENTIONED_IN'
    SUPPORTED_BY='SUPPORTED_BY'; MOTIVATED_BY='MOTIVATED_BY'; MUTATED='MUTATED'
    PRODUCED='PRODUCED'; VERIFIED_BY='VERIFIED_BY'
    HAS_CONVERSATION='HAS_CONVERSATION'; HAS_MESSAGE='HAS_MESSAGE'
    AUTHORED_BY='AUTHORED_BY'; SUPERSEDES='SUPERSEDES'

class EvidenceState(str, Enum):
    UNVERIFIED='UNVERIFIED'; PENDING='PENDING'; CONFIRMED='CONFIRMED'
    REFUTED='REFUTED'; SUPERSEDED='SUPERSEDED'

class CommonProperties(StrictModel):
    name: Name | None = None
    description: Annotated[str, Field(max_length=4000)] | None = None

class PersonProperties(CommonProperties):
    email: Annotated[str, Field(max_length=320)] | None = None

class EventProperties(CommonProperties):
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: Name | None = None

class TaskProperties(CommonProperties):
    due_at: AwareDatetime | None = None
    status: Literal['OPEN','IN_PROGRESS','DONE','CANCELLED'] | None = None

class BookingProperties(EventProperties):
    reference: Name | None = None
    status: Literal['PENDING','CONFIRMED','CANCELLED'] | None = None

class BotProperties(CommonProperties):
    instructions: Annotated[str, Field(max_length=4000)] | None = None

class SourceProperties(CommonProperties):
    uri: Annotated[str, Field(max_length=2048)] | None = None
    external_id: Name | None = None
    kind: Literal['USER_MESSAGE','DOCUMENT','MANUAL','SYSTEM'] | None = None
    observed_at: AwareDatetime | None = None

class RecordProperties(CommonProperties):
    summary: Text | None = None

PROPERTY_MODELS = {EntityType.Person:PersonProperties, EntityType.Event:EventProperties,
    EntityType.Task:TaskProperties, EntityType.Booking:BookingProperties,
    EntityType.Bot:BotProperties, EntityType.Source:SourceProperties,
    EntityType.Decision:RecordProperties, EntityType.Action:RecordProperties,
    EntityType.Outcome:RecordProperties}

class NodeUpsert(StrictModel):
    type: EntityType
    properties: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_properties(self):
        if self.type not in PROPERTY_MODELS:
            raise ValueError('Use the dedicated conversation, message or claim endpoint')
        parsed = PROPERTY_MODELS[self.type].model_validate(self.properties)
        self.properties = parsed.model_dump(mode='json', exclude_unset=True)
        if any(value is None for value in self.properties.values()):
            raise ValueError('Null properties are not supported; omit unchanged fields')
        return self

class EdgeProperties(StrictModel):
    evidence_state: EvidenceState = EvidenceState.UNVERIFIED
    note: Annotated[str, Field(max_length=2000)] | None = None

class RelationshipUpsert(StrictModel):
    source: Id
    target: Id
    type: RelationType
    properties: EdgeProperties = Field(default_factory=EdgeProperties)

class ConversationCreate(StrictModel):
    id: Id
    bot_id: Id
    title: Name

class MessageCreate(StrictModel):
    id: Id
    role: Literal['user','assistant','system']
    content: Text
    mentioned_ids: list[Id] = Field(default_factory=list, max_length=50)

class ClaimCreate(StrictModel):
    id: Id
    text: Text
    status: EvidenceState = EvidenceState.UNVERIFIED
    source_id: Id
    message_id: Id | None = None
    subject_ids: list[Id] = Field(min_length=1, max_length=50)
    observed_at: AwareDatetime
    supersedes_id: Id | None = None

    @model_validator(mode='after')
    def validate_claim(self):
        if self.status == EvidenceState.SUPERSEDED:
            raise ValueError('SUPERSEDED is set only by a new claim referencing this claim')
        if self.id == self.supersedes_id:
            raise ValueError('A claim cannot supersede itself')
        return self

class TraversalRequest(StrictModel):
    root_id: Id
    hops: int = Field(default=2, ge=1, le=4, strict=True)
    direction: Literal['both','outgoing','incoming'] = 'both'
    relationship_types: list[RelationType] = Field(default_factory=list, max_length=16)
    target_id: Id | None = None
    limit: int = Field(default=100, ge=1, le=500, strict=True)

class NodeView(StrictModel):
    id: str
    type: EntityType
    created_at: int
    updated_at: int
    properties: dict

class EdgeView(StrictModel):
    id: str
    type: RelationType
    source: str
    target: str
    created_at: int
    updated_at: int
    properties: dict

class EvidencePath(StrictModel):
    node_ids: list[str]
    edge_ids: list[str]

class Subgraph(StrictModel):
    nodes: list[NodeView]
    edges: list[EdgeView]
    paths: list[EvidencePath] = Field(default_factory=list)
    truncated: bool = False

class HealthView(StrictModel):
    status: Literal['ok']
    database: Literal['FalkorDB'] = 'FalkorDB'
    graph: str
