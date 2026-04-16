# api/v1/profile/username_stream.py
import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/profile", tags=["profile"])

# one stream per client
subscribers: dict[str, asyncio.Queue] = {}

@router.get("/username/stream")
async def username_stream(request: Request):
    client_id = str(id(request))
    queue = asyncio.Queue()
    subscribers[client_id] = queue

    async def stream():
        try:
            while True:
                msg = await queue.get()
                yield json.dumps(msg) + "\n"
        except asyncio.CancelledError:
            pass
        finally:
            subscribers.pop(client_id, None)

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
