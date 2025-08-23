from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio

from backend import get_chatbot_advice, get_key_status

app = FastAPI()

templates = Jinja2Templates(directory="templates")


# Maximum allowed incoming base64 image size (characters) to avoid exhausting worker memory.
INCOMING_IMAGE_MAX_CHARS = 500_000


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

    try:
        # run the advice call with a timeout to avoid unbounded waits
        response = await asyncio.wait_for(get_chatbot_advice(message, image_data_url, session_id=session_id), timeout=40)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail='AI provider timed out. Try again with a smaller image or shorter message.')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({"response": response})


@app.get('/status')
async def status():
    try:
        status = get_key_status()
    except Exception:
        status = {"error": "could not retrieve key status"}
    return JSONResponse(status)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
# fpl_chatbot/main.py
from flask import Flask, render_template, request, jsonify
from backend import get_chatbot_advice, get_key_status
import asyncio

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


# Maximum allowed incoming base64 image size (characters) to avoid exhausting worker memory.
# Base64 inflates binary by ~33%, so 500_000 chars ~ 375 KB binary; adjust as needed.
INCOMING_IMAGE_MAX_CHARS = 500_000


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json() or {}
    message = data.get('message')
    image_data_url = data.get('image')
    session_id = data.get('session_id')

    if not message:
        return jsonify({'error': 'A message is required.'}), 400

    # Basic guard: reject overly large incoming base64 images early to avoid OOM.
    if image_data_url and len(image_data_url) > INCOMING_IMAGE_MAX_CHARS:
        return jsonify({'error': f'Image too large. Please resize or compress to under {INCOMING_IMAGE_MAX_CHARS} characters.'}), 413

    # Run the async chatbot call in a fresh event loop with a timeout to prevent worker hangs.
    try:
        # 25s timeout is conservative for a single request; tune as needed or make configurable.
        response = asyncio.run(asyncio.wait_for(get_chatbot_advice(message, image_data_url, session_id=session_id), timeout=25))
    except asyncio.TimeoutError:
        return jsonify({'error': 'AI provider timed out. Try again with a smaller image or shorter message.'}), 504
    except Exception as e:
        return jsonify({'error': f'Internal server error: {e}'}), 500

    return jsonify({'response': response})


@app.route('/status', methods=['GET'])
def status():
    """Return masked status about API keys and configured provider (no secrets)."""
    try:
        status = get_key_status()
    except Exception:
        status = {"error": "could not retrieve key status"}
    return jsonify(status)


if __name__ == '__main__':
    app.run(debug=True)
