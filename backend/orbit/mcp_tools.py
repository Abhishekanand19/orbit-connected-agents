"""Official MCP SDK server and client over private in-process message streams."""
from datetime import timedelta
from typing import Annotated
import anyio
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ToolAnnotations
from pydantic import Field
from .database import GraphError
from .integration_providers import Providers

Short = Annotated[str, Field(min_length=1, max_length=320)]
Query = Annotated[str, Field(min_length=1, max_length=500)]
Channel = Annotated[str, Field(pattern=r'^C[A-Z0-9]{5,30}$')]
Limit = Annotated[int, Field(ge=1, le=15)]


def build_server(service, providers=None):
    provider = providers or Providers()
    server = FastMCP('ORBIT read-only integrations', log_level='ERROR')
    annotation = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

    async def read(fn, *args):
        try:
            result = await anyio.to_thread.run_sync(fn, *args)
            return {'ok': True, 'result': result}
        except GraphError as exc:
            return {'ok': False, 'error': {'code': exc.code, 'message': exc.message}}
        except Exception:
            return {'ok': False, 'error': {'code': 'tool_failed', 'message': 'Read failed; provider response was not recorded.'}}

    @server.tool(annotations=annotation)
    async def gmail_search(query: Query, limit: Limit = 10) -> dict:
        """Search the connected owner's Gmail. Returns IDs for gmail_read; never sends mail."""
        return await read(provider.gmail_search, query, limit)

    @server.tool(annotations=annotation)
    async def gmail_read(message_id: Short) -> dict:
        """Read a selected Gmail message with sender, subject, timestamp and untrusted content."""
        return await read(provider.gmail_read, message_id)

    @server.tool(annotations=annotation)
    async def calendar_list() -> dict:
        """List calendars readable by the connected Google account; pagination is bounded."""
        return await read(provider.calendar_list)

    @server.tool(annotations=annotation)
    async def calendar_events(calendar_id: Short, start: Short, end: Short) -> dict:
        """Read events and participants within an explicit RFC3339 interval, at most 31 days."""
        return await read(provider.calendar_events, calendar_id, start, end)

    @server.tool(annotations=annotation)
    async def calendar_event(calendar_id: Short, event_id: Short) -> dict:
        """Read details of one selected event. Does not modify calendars."""
        return await read(provider.calendar_event, calendar_id, event_id)

    @server.tool(annotations=annotation)
    async def calendar_conflicts(calendar_id: Short, start: Short, end: Short) -> dict:
        """Check overlapping stored calendar events for a proposed time; incomplete reads never imply availability."""
        return await read(provider.calendar_conflicts, calendar_id, start, end)

    @server.tool(annotations=annotation)
    async def slack_channels() -> dict:
        """List public channels the installed Slack bot has joined. No private conversation access."""
        return await read(provider.slack_channels)

    @server.tool(annotations=annotation)
    async def slack_messages(channel_id: Channel, limit: Limit = 15) -> dict:
        """Read recent work updates in a public channel the bot is authorized to read. Never posts."""
        return await read(provider.slack_messages, channel_id, limit)

    @server.tool(annotations=annotation)
    async def graph_dependencies(entity_id: Short) -> dict:
        """Read actual FalkorDB dependency paths around an existing entity, bounded to three hops."""
        return await read(service.dependencies, entity_id, 3, 'both', 30)

    return server


def session(server):
    # Real initialize, tools/list and tools/call messages; no HTTP endpoint is exposed.
    return create_connected_server_and_client_session(server, read_timeout_seconds=timedelta(seconds=50))
