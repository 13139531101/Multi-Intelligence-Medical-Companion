"""Test contextvar cross-task propagation."""
import asyncio
import contextvars

cv = contextvars.ContextVar('test', default='default')

def child():
    print(f'  child sees: {cv.get()}')
    return cv.get()

async def main():
    cv.set('parent_value')
    print(f'parent set: {cv.get()}')

    # Spawn a separate task
    task = asyncio.create_task(asyncio.to_thread(child))
    result = await task
    print(f'  task result: {result}')

asyncio.run(main())
