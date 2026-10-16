"""Read-only provider adapters. Fixed API origins, bounded responses, safe errors."""
import base64
import os
from datetime import datetime, timezone
from urllib.parse import quote
import httpx
from .database import GraphError
from .integration_auth import google_auth


def now():
    return datetime.now(timezone.utc).isoformat()


def interval(start, end):
    try:
        a, b = (datetime.fromisoformat(v.replace('Z', '+00:00')) for v in (start, end))
        if not a.tzinfo or not b.tzinfo or b <= a or (b - a).days > 31:
            raise ValueError()
        return a, b
    except (ValueError, TypeError):
        raise GraphError(422, 'invalid_interval', 'Use an aware positive interval of at most 31 days.') from None


class Providers:
    def __init__(self, auth=None, transport=None):
        self.auth = auth or google_auth
        self.transport = transport

    def get(self, provider, path, params=None):
        google = provider in ('gmail', 'calendar')
        token = self.auth.token() if google else os.getenv('SLACK_BOT_TOKEN')
        if not token:
            raise GraphError(503, 'slack_unconfigured', 'Configure SLACK_BOT_TOKEN in the backend environment.')
        base = {'gmail': 'https://gmail.googleapis.com/gmail/v1/users/me/',
                'calendar': 'https://www.googleapis.com/calendar/v3/', 'slack': 'https://slack.com/api/'}[provider]
        for attempt in range(2):
            try:
                with httpx.Client(transport=self.transport, timeout=20, follow_redirects=False) as client:
                    with client.stream('GET', base + path, params=params, headers={'Authorization': 'Bearer ' + token}) as response:
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 2_000_000:
                                raise GraphError(502, 'provider_response_large', 'Provider response exceeds the bounded read limit.')
                            chunks.append(chunk)
                        import json
                        data = json.loads(b''.join(chunks))
            except (httpx.HTTPError, ValueError):
                raise GraphError(502, 'provider_unavailable', provider + ' read failed; retry later.') from None
            if response.status_code == 401 and google and attempt == 0:
                token = self.auth.token(force=True)
                continue
            if response.status_code == 429:
                raise GraphError(429, 'provider_rate_limit', provider + ' rate limited this request; retry later.')
            if response.status_code in (401, 403):
                raise GraphError(response.status_code, 'provider_authorization', provider + ' access denied; reconnect or check read permissions.')
            if response.status_code != 200 or not isinstance(data, dict):
                raise GraphError(502, 'provider_failed', provider + ' read failed.')
            if provider == 'slack' and not data.get('ok'):
                code = data.get('error')
                allowed = {'invalid_auth', 'token_revoked', 'missing_scope', 'not_in_channel', 'channel_not_found', 'ratelimited'}
                raise GraphError(403, 'slack_access', 'Slack read failed: ' + (code if code in allowed else 'provider_error'))
            return data
        raise GraphError(401, 'google_reconnect', 'Reconnect Google.')

    def gmail_search(self, query, limit=10):
        data = self.get('gmail', 'messages', {'q': query, 'maxResults': limit})
        return {'source': 'gmail', 'observed_at': now(), 'items': data.get('messages', [])[:limit], 'truncated': bool(data.get('nextPageToken'))}

    def gmail_read(self, message_id):
        data = self.get('gmail', 'messages/' + quote(message_id, safe=''), {'format': 'full'})
        headers = {h['name'].lower(): h.get('value', '') for h in data.get('payload', {}).get('headers', [])}
        bodies = []
        def walk(part, depth=0):
            if depth > 10 or len(bodies) >= 20:
                return
            encoded = part.get('body', {}).get('data')
            if encoded and part.get('mimeType') in ('text/plain', 'text/html'):
                try:
                    bodies.append(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode('utf-8', errors='replace')[:8000])
                except ValueError:
                    pass
            for child in part.get('parts', [])[:20]:
                walk(child, depth + 1)
        walk(data.get('payload', {}))
        return {'source': 'gmail', 'observed_at': now(), 'id': data['id'], 'thread_id': data.get('threadId'),
                'sender': headers.get('from', '')[:500], 'subject': headers.get('subject', '')[:500],
                'timestamp': data.get('internalDate'), 'date_header': headers.get('date', '')[:100],
                'content': '\n'.join(bodies)[:8000] or data.get('snippet', '')[:8000], 'evidence_state': 'UNVERIFIED'}

    def calendar_list(self):
        data = self.get('calendar', 'users/me/calendarList', {'maxResults': 30})
        return {'source': 'calendar', 'observed_at': now(), 'items': [{k: c.get(k) for k in ('id', 'summary', 'timeZone', 'accessRole')} for c in data.get('items', [])[:30]], 'truncated': bool(data.get('nextPageToken'))}

    @staticmethod
    def event(data):
        return {k: data.get(k) for k in ('id', 'etag', 'summary', 'description', 'start', 'end', 'status', 'transparency', 'attendees', 'organizer', 'updated', 'htmlLink', 'attendeesOmitted')}

    def calendar_events(self, calendar_id, start, end):
        interval(start, end)
        data = self.get('calendar', 'calendars/' + quote(calendar_id, safe='') + '/events',
                        {'timeMin': start, 'timeMax': end, 'singleEvents': 'true', 'orderBy': 'startTime', 'maxResults': 50, 'maxAttendees': 30})
        return {'source': 'calendar', 'observed_at': now(), 'calendar_id': calendar_id, 'time_zone': data.get('timeZone', 'UTC'),
                'items': [self.event(e) for e in data.get('items', [])[:50]], 'truncated': bool(data.get('nextPageToken'))}

    def calendar_event(self, calendar_id, event_id):
        data = self.get('calendar', 'calendars/' + quote(calendar_id, safe='') + '/events/' + quote(event_id, safe=''), {'maxAttendees': 30})
        return {'source': 'calendar', 'observed_at': now(), 'calendar_id': calendar_id, 'item': self.event(data)}

    def calendar_conflicts(self, calendar_id, start, end):
        from .intelligence import calendar_constraints
        result = self.calendar_events(calendar_id, start, end)
        return {**result, **calendar_constraints(result, start, end)}

    def slack_channels(self):
        data = self.get('slack', 'conversations.list', {'types': 'public_channel', 'exclude_archived': 'true', 'limit': 100})
        return {'source': 'slack', 'observed_at': now(), 'items': [{'id': c['id'], 'name': c['name']} for c in data.get('channels', []) if c.get('is_member')][:100],
                'truncated': bool(data.get('response_metadata', {}).get('next_cursor'))}

    def slack_messages(self, channel_id, limit=15):
        # The bot token's membership is enforced by Slack; no private-channel scopes requested.
        data = self.get('slack', 'conversations.history', {'channel': channel_id, 'limit': limit})
        return {'source': 'slack', 'observed_at': now(), 'channel_id': channel_id,
                'items': [{'id': m.get('ts'), 'timestamp': m.get('ts'), 'sender': m.get('user') or m.get('bot_id'), 'content': m.get('text', '')[:4000]} for m in data.get('messages', [])[:limit]],
                'truncated': bool(data.get('has_more') or data.get('response_metadata', {}).get('next_cursor'))}
