# fpl_chatbot/main.py
from flask import Flask, render_template, request, jsonify
from backend import get_chatbot_advice

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
async def chat():
    data = request.get_json()
    message = data.get('message')
    image_data_url = data.get('image')

    if not message:
        return jsonify({'error': 'A message is required.'}), 400

    response = await get_chatbot_advice(message, image_data_url)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True)
