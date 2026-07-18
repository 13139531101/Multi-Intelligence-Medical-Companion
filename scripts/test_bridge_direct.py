"""Test bridge.py directly inside container."""
import asyncio, sys, json
sys.path.insert(0, '/app')
from A2AServer.common.A2Atypes import Message
from A2AServer.v2.bridge import v2_process_message_stream

async def main():
    msg = Message(
        role='user',
        parts=[{'type':'text', 'text':'你好, 我血压有点高'}],
        metadata={'conversation_id':'test1', 'user_id':''},
    )
    print('streaming...')
    n = 0
    last_event_type = None
    text_total = ""
    async for ev in v2_process_message_stream(msg):
        n += 1
        last_event_type = ev.get('event', '?')
        if last_event_type == 'routing':
            print(f'  [{n}] ROUTING: {ev.get("agent")}')
        elif last_event_type == 'tool_call':
            print(f'  [{n}] CALL: {ev.get("name")}')
        elif last_event_type == 'tool_result':
            print(f'  [{n}] RESULT: {ev.get("name")}')
        elif last_event_type == 'chunk':
            t = str(ev.get("text", ""))
            text_total += t
            if len(text_total) < 100:
                print(f'  [{n}] CHUNK: {t!r}')
        elif last_event_type == 'done':
            print(f'  [{n}] DONE (content len={len(ev.get("content", ""))})')
        else:
            print(f'  [{n}] {last_event_type}: {json.dumps(ev)[:120]}')
        if n > 50:
            print('  ... stopped after 50')
            break
    print(f'\ntotal events seen: {n}, last_event: {last_event_type}, text: {text_total[:80]}')

asyncio.run(main())
