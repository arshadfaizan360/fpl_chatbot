from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio

from backend import get_chatbot_advice, get_key_status

app = FastAPI()

templates = Jinja2Templates(directory="templates")


# Maximum allowed incoming base64 image size (characters) to avoid exhausting worker memory.
INCOMING_IMAGE_MAX_CHARS = 500_000

# Also protect against overly large overall request payloads by rejecting requests early
# when the Content-Length header indicates the body is too large. This avoids parsing huge
# JSON bodies and gives a clear error to clients.
# Set slightly larger than INCOMING_IMAGE_MAX_CHARS to allow for JSON wrapper overhead.
MAX_CONTENT_LENGTH_BYTES = 700_000


@app.middleware("http")
async def reject_oversized_requests(request: Request, call_next):
    """Reject requests where the Content-Length header is larger than our allowed limit.

    This returns a JSON 413 response before the request body is parsed to avoid
    consuming large amounts of memory in the app.
    """
    try:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            # Some clients may send non-integer values; guard with a safe int conversion
            try:
                cl = int(content_length)
            except Exception:
                cl = None
            if cl and cl > MAX_CONTENT_LENGTH_BYTES:
                return JSONResponse(status_code=413, content={
                    "error": "Payload too large. Please upload a smaller image (try under ~500KB) or compress it client-side."
                })
    except Exception:
        # If anything in this lightweight check fails, continue to the endpoint and let
        # existing checks handle the body safely.
        pass

    return await call_next(request)


@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})


@app.post('/chat')
async def chat(payload: dict):
    message = payload.get('message')
    image_data_url = payload.get('image')
    session_id = payload.get('session_id')

    if not message:
        raise HTTPException(status_code=400, detail='A message is required.')

    if image_data_url and len(image_data_url) > INCOMING_IMAGE_MAX_CHARS:
        raise HTTPException(status_code=413, detail=f'Image too large. Please resize or compress to under {INCOMING_IMAGE_MAX_CHARS} characters.')

    # Configurable timeout for the AI provider call. Increase if your provider needs more time.
    CHATBOT_TIMEOUT_SECONDS = 90
    try:
        # run the advice call with a timeout to avoid unbounded waits
        response = await asyncio.wait_for(
            get_chatbot_advice(message, image_data_url, session_id=session_id),
            timeout=CHATBOT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        # Include session_id in server logs to help debugging slow calls
        print(f"AI provider timeout after {CHATBOT_TIMEOUT_SECONDS}s for session: {session_id}")
        raise HTTPException(status_code=504, detail='AI provider timed out. Try again with a smaller image or shorter message.')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({"response": response})


@app.post('/chat/stream')
async def chat_stream(request: Request):
    """Stream periodic heartbeat events while waiting for the AI response, then send the final response.

    The endpoint accepts the same JSON payload as /chat and returns a text/event-stream style
    stream which the client can read incrementally. This implementation does not stream tokens from
    the AI provider; it sends periodic heartbeats and then the complete final message when ready.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid JSON payload.')

    message = payload.get('message')
    image_data_url = payload.get('image')
    session_id = payload.get('session_id')

    if not message:
        raise HTTPException(status_code=400, detail='A message is required.')

    async def event_generator():
        # Start with an initial thinking event
        try:
            yield f"data: {JSONResponse({'type': 'heartbeat', 'message': 'thinking'}).body.decode()}\n\n"
        except Exception:
            # fallback simple text if JSONResponse didn't work as expected
            yield "data: {\"type\": \"heartbeat\", \"message\": \"thinking\"}\n\n"

        # Run the AI call in a background task and periodically send heartbeats
        task = asyncio.create_task(
            asyncio.wait_for(
                get_chatbot_advice(message, image_data_url, session_id=session_id),
                timeout=90,
            )
        )

        try:
            while not task.done():
                # send simple heartbeat so client can show progress
                yield "data: {\"type\": \"heartbeat\", \"message\": \"thinking\"}\n\n"
                await asyncio.sleep(1)
                # stop if client disconnected
                if await request.is_disconnected():
                    task.cancel()
                    return

            # task finished — get result or exception
            try:
                result = task.result()
                payload_out = {"type": "message", "response": result}
                yield f"data: {JSONResponse(payload_out).body.decode()}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"type\": \"error\", \"error\": \"AI provider timed out\"}\n\n"
            except Exception as e:
                err = str(e)
                yield f"data: {{\"type\": \"error\", \"error\": {JSONResponse({ 'error': err }).body.decode()} }}\n\n"

        except asyncio.CancelledError:
            return

    return StreamingResponse(event_generator(), media_type='text/event-stream')


@app.get('/status')
async def status():
    try:
        status = get_key_status()
    except Exception:
        status = {"error": "could not retrieve key status"}
    return JSONResponse(status)


@app.get('/debug', response_class=HTMLResponse)
async def debug(request: Request):
        """Simple debug page without JS/CSS to verify server rendering independent of templates."""
        html = """
        <html><head><title>Debug</title></head>
        <body style='background: #fff; color: #000; font-family: Arial, sans-serif;'>
            <h1>Debug page</h1>
            <p>If you see this, the server is returning HTML correctly.</p>
            <p>Now open the browser console (Cmd+Option+J on mac) and check for errors when loading <a href="/">/</a>.</p>
        </body></html>
        """
        return HTMLResponse(content=html)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
