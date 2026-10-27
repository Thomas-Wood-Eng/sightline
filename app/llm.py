"""Every model call goes through this file, so switching provider (e.g. to Claude) touches nothing else.

The model never moves money or speaks numbers: callers give it tools without price fields, and say_ok() rejects any
money in its text before anything reaches the user.
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

from google import genai
from google.genai import errors, types

PRIMARY = 'gemini-flash-lite-latest'   # D1 timing: median 0.87 s for a tool call
FALLBACK = 'gemini-3.5-flash-lite'     # D1 timing: median 1.43 s
TIMEOUT_MS = 4000                      # free-tier calls occasionally stall 15-30 s; never make the user wait that long

MONEY = re.compile(r'[$€£]|\b\d+(?:\.\d{1,2})?\s*(?:dollars?|cents?|bucks|usd)\b|\bprice\s+(?:is|of)\b', re.I)

_client = None
_pool = ThreadPoolExecutor(max_workers=8)  # the API rejects short server deadlines, so we stop waiting client-side


def _key():
    if os.environ.get('GEMINI_API_KEY'):
        return os.environ['GEMINI_API_KEY']
    env = Path(__file__).resolve().parent.parent / '.env'
    return dict(l.split('=', 1) for l in env.read_text().splitlines() if '=' in l)['GEMINI_API_KEY'].strip()


def client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=_key())
    return _client


def say_ok(text):
    """False if the model's text contains a money figure; only server templates may speak amounts."""
    return not MONEY.search(text or '')


def chat(system, contents, tools):
    """One model turn. tools: list of function-declaration dicts. Returns {'text', 'calls', 'model', 'ms'} or None.

    Tries PRIMARY, then FALLBACK once; None means the caller should fall back to its no-AI menu."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=tools)] if tools else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # we run tools ourselves
        max_output_tokens=300,
    )
    for model in (PRIMARY, FALLBACK):
        t = time.perf_counter()
        try:
            job = _pool.submit(client().models.generate_content, model=model, contents=contents, config=config)
            r = job.result(timeout=TIMEOUT_MS / 1000)  # shortcut: a stalled call keeps its thread until it returns; fine at demo load
        except (errors.APIError, OSError, FutureTimeout) as e:  # 429/503, our timeout, network
            print(f'llm: {model} failed after {time.perf_counter() - t:.1f}s: {type(e).__name__} {str(e)[:80]}')
            continue
        parts = (r.candidates[0].content.parts or []) if r.candidates and r.candidates[0].content else []
        return {
            'text': ''.join(p.text for p in parts if getattr(p, 'text', None)).strip() or None,
            'calls': [(p.function_call.name, dict(p.function_call.args or {})) for p in parts if p.function_call],
            'parts': parts,  # append to the history as the model turn
            'model': model,
            'ms': int((time.perf_counter() - t) * 1000),
        }
    return None


if __name__ == '__main__':  # live smoke test: python -m app.llm
    assert not say_ok('It costs $34.99') and not say_ok('only 35 dollars') and say_ok('Fleece-lined, heather grey, 4.6 stars')
    tool = {'name': 'search_products', 'description': 'Search the store',
            'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'max_price': {'type': 'number'}},
                           'required': ['query']}}
    for q in ['find me a warm hoodie under 40 dollars', 'something for my mum who likes tea']:
        out = chat('You are a concise voice shopping assistant. Use tools.', q, [tool])
        print(q, '->', out and (out['model'], out['ms'], out['calls'], out['text']))
