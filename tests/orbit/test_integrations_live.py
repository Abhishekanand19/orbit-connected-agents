"""Explicit real authorized reads. Missing configuration is skipped, never passed."""
import os
import json
from datetime import datetime,timedelta,timezone
import anyio
import pytest
from backend.orbit.config import Settings
from backend.orbit.integration_auth import google_auth
from backend.orbit.mcp_tools import build_server,session


def call(name,arguments):
    async def read():
        async with session(build_server(None)) as client:
            assert name in {t.name for t in (await client.list_tools()).tools}
            response=await client.call_tool(name,arguments)
            assert not response.isError
            data=response.structuredContent or json.loads(response.content[0].text)
            assert data['ok'], 'Authorized provider read failed; reconnect/check backend credentials.'
            return data['result']
    return anyio.run(read)


def require_google():
    Settings.from_env()
    if not os.getenv('GOOGLE_CLIENT_ID') or not os.getenv('GOOGLE_CLIENT_SECRET'):
        pytest.skip('Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, then connect Google.')
    if not google_auth.vault.load():
        pytest.skip('Complete Google consent at http://127.0.0.1:8001/auth/google/connect.')


def test_live_google_oauth():
    require_google()
    # Force a real token endpoint request; never print its response.
    assert google_auth.token(force=True)


def test_live_gmail_search_read():
    require_google()
    result=call('gmail_search',{'query':'newer_than:30d','limit':1})
    if result['items']:
        assert call('gmail_read',{'message_id':result['items'][0]['id']})['id']
    else:
        pytest.skip('Gmail search succeeded but no message exists in the last 30 days to verify read.')


def test_live_calendar_reads():
    require_google()
    calendars=call('calendar_list',{})
    assert calendars['items'], 'No readable calendar returned.'
    start=datetime.now(timezone.utc)
    result=call('calendar_conflicts',{'calendar_id':calendars['items'][0]['id'],'start':start.isoformat(),'end':(start+timedelta(days=7)).isoformat()})
    assert 'items' in result
    if result['items']:
        assert call('calendar_event',{'calendar_id':calendars['items'][0]['id'],'event_id':result['items'][0]['id']})['item']['id']


def test_live_slack_reads():
    Settings.from_env()
    if not os.getenv('SLACK_BOT_TOKEN'):pytest.skip('Configure SLACK_BOT_TOKEN.')
    assert 'items' in call('slack_channels',{})
    assert 'items' in call('slack_messages',{'channel_id':'C0C9SH122US','limit':1})
