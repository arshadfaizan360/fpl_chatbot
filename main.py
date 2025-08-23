# fpl_chatbot/main.py
from flask import Flask, render_template, request, jsonify
from backend import get_chatbot_advice, get_key_status

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
async def chat():
    data = request.get_json()
    message = data.get('message')
    image_data_url = data.get('image')
    session_id = data.get('session_id')

    if not message:
        return jsonify({'error': 'A message is required.'}), 400

    response = await get_chatbot_advice(message, image_data_url, session_id=session_id)
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
