"""Server-only Gemini transport. Never logs provider bodies or credentials."""
import json
import os
import httpx
from .database import GraphError

def generate(system, payload, schema=None):
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise GraphError(503, 'llm_unconfigured', 'Set GEMINI_API_KEY in the backend .env and restart the API.')
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    config = {'maxOutputTokens': 8192}
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
    except httpx.TimeoutException:
        raise GraphError(504,'llm_timeout','The model timed out. Retry the same message.') from None
    except httpx.HTTPError:
        raise GraphError(503,'llm_unavailable','Cannot reach the model provider. Please retry.') from None
    if response.status_code != 200:
        code = 429 if response.status_code == 429 else 502
        raise GraphError(code,'llm_failed','Model rate limit reached. Retry later.' if code==429 else 'Model request failed. Check the backend model and credentials.')
    try:
        candidate=response.json()['candidates'][0]
        if candidate.get('finishReason') != 'STOP':
            raise ValueError('Incomplete generation')
        result=''.join(p.get('text','') for p in candidate['content']['parts'] if not p.get('thought'))
        if not result.strip(): raise ValueError('Empty response')
        return json.loads(result) if schema else result
    except (KeyError, IndexError, ValueError):
        raise GraphError(502,'llm_invalid','The model returned an incomplete or invalid response. Please retry.') from None
