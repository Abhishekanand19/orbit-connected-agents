"""Server-only Gemini transport. Never logs provider bodies or credentials."""
import json
import logging
import os
import re
import httpx
from .database import GraphError

logger = logging.getLogger(__name__)


def diagnostic(model, status, exception_type, response=None):
    """Allowlisted classifications only: never emit bodies, prompts, headers or URLs."""
    reason = 'Provider rejected the request; unrecognized error details withheld.'
    provider_status = None
    if response is not None:
        try:
            error = response.json().get('error', {})
            message = str(error.get('message', '')).lower()
            known = {'INVALID_ARGUMENT', 'NOT_FOUND', 'RESOURCE_EXHAUSTED',
                     'UNAVAILABLE', 'PERMISSION_DENIED', 'UNAUTHENTICATED', 'INTERNAL'}
            provider_status = error.get('status') if error.get('status') in known else None
            classifications = (
                ('api key expired', 'API key expired. Renew the Gemini API key.'),
                ('api key not valid', 'Gemini API key is invalid.'),
                ('api key was reported as leaked', 'Gemini API key was reported as leaked and blocked.'),
                ('api has not been used', 'Generative Language API is disabled or has not been enabled for this project.'),
                ('not found for api version', 'Configured model is unavailable for v1beta or does not support generateContent.'),
                ('is not found', 'Configured model/resource was not found.'),
                ('quota exceeded', 'Gemini quota exceeded; inspect project/model quota and billing.'),
                ('rate limit', 'Gemini rate limit exceeded.'),
                ('overloaded', 'Gemini service/model is overloaded.'),
                ('high demand', 'Gemini service/model is experiencing high demand.'),
                ('response_json_schema', 'Provider rejected the response JSON schema configuration.'),
                ('invalid json payload', 'Provider rejected the request JSON structure.'),
                ('permission denied', 'Provider denied permission for this project or credential.'),
            )
            for fragment, safe in classifications:
                if fragment in message:
                    reason = safe
                    break
            if status == 429 and ('limit: 0' in message or 'limit:0' in message):
                reason = 'Gemini quota is zero for the requested model/project; waiting alone will not restore access.'
        except (ValueError, TypeError, AttributeError):
            reason = 'Provider returned an unreadable error body; body withheld.'
    elif status is None:
        reason = 'Provider request timed out.' if 'Timeout' in exception_type else 'Provider transport failed.'
    elif status == 200:
        reason = 'Provider returned incomplete or invalid generation content; content withheld.'
    record = {'provider': 'Gemini', 'model': model if re.fullmatch(r'[A-Za-z0-9._-]{1,120}', model) else '[invalid model name redacted]',
              'http_status': status, 'exception_type': exception_type,
              'provider_status': provider_status, 'reason': reason}
    logger.error('llm_diagnostic %s', json.dumps(record))


def generate(system, payload, schema=None, *, max_output_tokens=8192):
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise GraphError(503, 'llm_unconfigured', 'Set GEMINI_API_KEY in the backend .env and restart the API.')
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    config = {'maxOutputTokens': max_output_tokens}
    if schema:
        # Keep size validation local; deeply nested bounds exceed Gemini's grammar budget.
        def compact(value):
            if isinstance(value, dict):
                return {k:compact(v) for k,v in value.items() if k not in ('maxLength','minLength','maxItems','minItems','title','additionalProperties')}
            if isinstance(value,list):return [compact(v) for v in value]
            return value
        config.update(responseMimeType='application/json', responseJsonSchema=compact(schema))
    try:
        response = httpx.post('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
            headers={'x-goog-api-key':key}, timeout=60,
            json={'systemInstruction':{'parts':[{'text':system}]},
                  'contents':[{'role':'user','parts':[{'text':json.dumps(payload,ensure_ascii=False)}]}],
                  'generationConfig':config})
    except httpx.TimeoutException as exc:
        diagnostic(model, None, type(exc).__name__)
        raise GraphError(504,'llm_timeout','The model timed out. Retry the same message.') from None
    except httpx.HTTPError as exc:
        diagnostic(model, None, type(exc).__name__)
        raise GraphError(503,'llm_unavailable','Cannot reach the model provider. Please retry.') from None
    if response.status_code != 200:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            diagnostic(model, response.status_code, type(exc).__name__, response)
        code = 429 if response.status_code == 429 else 502
        raise GraphError(code,'llm_failed','Model rate limit reached. Retry later.' if code==429 else 'Model request failed. Check the backend model and credentials.')
    try:
        candidate=response.json()['candidates'][0]
        if candidate.get('finishReason') != 'STOP':
            raise ValueError('Incomplete generation')
        result=''.join(p.get('text','') for p in candidate['content']['parts'] if not p.get('thought'))
        if not result.strip(): raise ValueError('Empty response')
        return json.loads(result) if schema else result
    except (KeyError, IndexError, ValueError) as exc:
        diagnostic(model, response.status_code, type(exc).__name__)
        raise GraphError(502,'llm_invalid','The model returned an incomplete or invalid response. Please retry.') from None
