"""Fail-closed public demo boundary; local owner mode remains unchanged."""
import re
import time
from collections import deque
from fastapi.responses import JSONResponse


def mount_public_demo(app, settings):
    if not settings.public_demo:
        return
    if not settings.graph.startswith('orbit_public_'):
        raise ValueError('Public demo requires a dedicated registry graph.')
    requests = deque()
    reads = re.compile(r'^/api/(?:story/(?:state|checklist)|graph/impact/[^/]+|nodes(?:/[^/]+(?:/(?:neighbors|dependencies|affected))?)?|relationships/[^/]+|chat/(?:bots/[^/]+/latest|activity/[^/]+)|conversations/[^/]+(?:/(?:messages|context))?|receipts(?:/[^/]+)?|evidence/[^/]+|actions)$')
    writes = re.compile(r'^/api/(?:chat|story/(?:workspaces|conversations|checklist/[^/]+)|graph/(?:traverse|subgraph|impact)|actions/(?:session|[^/]+/(?:approve|reject|retry|verify|refresh)))$')

    @app.middleware('http')
    async def public_boundary(request, call_next):
        path = request.url.path
        def deny(message, status=403):
            return JSONResponse({'error': {'code': 'public_demo_policy', 'message': message}}, status_code=status)
        if request.method == 'OPTIONS' or (request.method == 'GET' and path == '/api/health'):
            return await call_next(request)
        if request.method == 'GET' and path == '/api/onboarding/connections':
            return JSONResponse({'connections': [{'id': name, 'status': 'unavailable', 'can_connect': False, 'detail': 'Personal integrations are disabled in this public demo.'} for name in ['gmail','calendar','slack','drive','tasks','excel','teams']], 'writes_performed': False})
        if not ((request.method == 'GET' and reads.fullmatch(path)) or (request.method == 'POST' and writes.fullmatch(path))):
            return deny('This operation is unavailable in the public demo.')
        # A random workspace capability is mandatory; never fall back to owner data.
        if path != '/api/story/workspaces' and not re.fullmatch(r'[a-f0-9]{32}', request.headers.get('x-orbit-story','')):
            return deny('Open an isolated demo workspace first.', 401)
        # Global process bound cannot be bypassed by spoofing forwarding headers.
        now = time.monotonic()
        while requests and requests[0] < now - 60:
            requests.popleft()
        if len(requests) >= 120:
            return deny('Demo capacity reached. Please retry shortly.', 429)
        requests.append(now)
        length = request.headers.get('content-length', '0')
        if not length.isdigit() or int(length) > 65536:
            return deny('Request is too large.', 413)
        if request.method == 'POST':
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return deny('Request is too large.', 413)
            request._body = bytes(body)
        return await call_next(request)
