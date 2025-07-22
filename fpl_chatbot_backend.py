# fpl_chatbot_backend.py
import os
import requests
import json
import urllib.request
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- Configuration ---
load_dotenv()

# --- Constants ---
FPL_API_BASE_URL = "https://fantasy.premierleague.com/api/"
GEMINI_MODEL_NAME = "gemini-2.0-flash" 
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# NEW: Add a browser-like User-Agent header to all FPL API requests
FPL_REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
}

# --- Sanity Check for API Token ---
if GOOGLE_API_KEY:
    print("✅ Google API Key loaded successfully from .env file.")
else:
    print("❌ WARNING: GOOGLE_API_KEY not found. Please get a key from Google AI Studio and add it to your .env file.")


# --- FPL Data Functions (Our "Tool") ---

def get_fpl_bootstrap_data():
    """Fetches the main bootstrap data from the FPL API."""
    try:
        # UPDATED: Added headers to the request
        response = requests.get(f"{FPL_API_BASE_URL}bootstrap-static/", headers=FPL_REQUEST_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Error fetching FPL bootstrap data: {e}"}

def get_current_gameweek(bootstrap_data):
    """Finds the current gameweek, or the next one if the season hasn't started."""
    if not bootstrap_data or 'events' not in bootstrap_data:
        return None
    for event in bootstrap_data.get('events', []):
        if event.get('is_current'):
            return event['id']
    for event in bootstrap_data.get('events', []):
        if event.get('is_next'):
            return event['id']
    return None

def get_fpl_team_data(user_id):
    """Fetches FPL team data for a given user_id, with improved pre-season error handling."""
    if not user_id:
        return {"error": "FPL User ID was not provided."}

    # --- NEW DIAGNOSTIC STEP ---
    # First, check if the user ID is valid by fetching general info.
    try:
        info_url = f"{FPL_API_BASE_URL}entry/{user_id}/"
        info_response = requests.get(info_url, headers=FPL_REQUEST_HEADERS)
        info_response.raise_for_status()
        user_info = info_response.json()
        print(f"✅ Successfully fetched general info for team: {user_info.get('name')}")
    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 404:
            return {"error": "User ID Not Found. Please double-check the FPL User ID you entered as it appears to be incorrect."}
        return {"error": f"An HTTP error occurred while verifying your User ID: {http_err}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred while verifying your User ID: {e}"}

    bootstrap_data = get_fpl_bootstrap_data()
    if "error" in bootstrap_data:
        return bootstrap_data

    current_gameweek = get_current_gameweek(bootstrap_data)
    if not current_gameweek:
        return {"error": "Could not determine the current or next gameweek."}

    # Now, try to get the detailed picks for the gameweek.
    try:
        picks_url = f"{FPL_API_BASE_URL}entry/{user_id}/event/{current_gameweek}/picks/"
        picks_response = requests.get(picks_url, headers=FPL_REQUEST_HEADERS)
        picks_response.raise_for_status()
        team_picks = picks_response.json()

        player_map = {player['id']: player['web_name'] for player in bootstrap_data['elements']}
        
        formatted_team = ["--- My FPL Squad ---"]
        for pick in team_picks['picks']:
            player_name = player_map.get(pick['element'], "Unknown")
            position = "Starter" if pick['position'] <= 11 else "Bench"
            captain_status = " (C)" if pick.get('is_captain') else " (VC)" if pick.get('is_vice_captain') else ""
            formatted_team.append(f"- {player_name}{captain_status} [{position}]")
        
        bank = user_info.get('last_deadline_bank', 1000) / 10.0
        free_transfers = team_picks.get('entry_history', {}).get('event_transfers', 1)
        
        team_summary = [f"\n--- Team Info ---", f"Bank: £{bank}m", f"Free Transfers: {free_transfers}"]
        return "\n".join(formatted_team + team_summary)

    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 404:
            # If we get here, the User ID was valid, but the picks for GW1 are not available.
            return {"error": "Your User ID is correct, but your detailed team data for Gameweek 1 is not yet available via the API. This is common during pre-season. Please try again closer to the season's start date."}
        return {"error": f"An HTTP error occurred while fetching team picks: {http_err}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred while fetching team picks: {e}"}

# --- AI Interaction ---

def ask_ai_assistant(history):
    """
    Sends a conversation history to the Google Gemini API.
    """
    if not GOOGLE_API_KEY:
        return "GOOGLE_API_KEY not found in environment variables. Please check your .env file."

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    # The Gemini API expects a specific format for conversation history
    payload = {"contents": history}
    data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(api_url, data=data, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            response_body = response.read().decode("utf-8")
            json_response = json.loads(response_body)
            
            if "candidates" in json_response and len(json_response["candidates"]) > 0:
                content = json_response["candidates"][0].get("content", {})
                if "parts" in content and len(content["parts"]) > 0:
                    return content["parts"][0].get("text", "").strip()
            
            print(f"--- GOOGLE API UNEXPECTED RESPONSE ---\n{json_response}\n------------------------------------")
            return "Error: Received an unexpected or empty response from the AI assistant."

    except urllib.error.HTTPError as e:
        error_content = e.read().decode("utf-8")
        print(f"--- GOOGLE API HTTP ERROR ---")
        print(f"Status Code: {e.code}")
        print(f"Details: {error_content}")
        print(f"-----------------------------")
        return f"Error contacting AI assistant. Details: {error_content}"
    except Exception as e:
        print(f"--- GENERIC NETWORK/REQUEST ERROR ---")
        print(f"Exception Type: {type(e)}")
        print(f"Exception Details: {repr(e)}")
        print(f"-----------------------------------")
        return f"A fundamental error occurred. Please check your terminal for details. Error: {repr(e)}"

# --- Main Handler ---

def handle_query(user_query, user_id, history):
    """
    Processes a query and its conversation history.
    """
    print(f"Received query: '{user_query}' for user_id: {user_id}")

    # Step 1: Use the AI to decide if the FPL data tool is needed.
    router_history = [
        {"role": "user", "parts": [{"text": "You are an AI assistant that determines if a user's request requires accessing their Fantasy Premier League (FPL) team data. Based on the following query, do you need to see the user's current team, budget, and players to give a helpful answer? Answer with only the word 'yes' or 'no'."}]},
        {"role": "model", "parts": [{"text": "Okay, I understand. I will answer with only 'yes' or 'no'."}]},
        {"role": "user", "parts": [{"text": f"User Query: '{user_query}'"}]}
    ]
    
    decision = ask_ai_assistant(router_history).lower().strip()
    print(f"Decision from AI router: '{decision}'")

    # Append the user's actual query to the main history for the next step
    history.append({"role": "user", "parts": [{"text": user_query}]})

    # Step 2: Act on the decision.
    if 'yes' in decision and 'no' not in decision:
        print("Fetching FPL data based on AI decision...")
        team_data = get_fpl_team_data(user_id)
        if isinstance(team_data, dict) and "error" in team_data:
            return team_data["error"]

        # Prepend the system prompt and the FPL data to the history
        responder_history = [
            {"role": "user", "parts": [{"text": "You are an expert FPL assistant. Your responses must be in British English. Analyse the provided team data to answer the user's questions concisely and helpfully."}]},
            {"role": "model", "parts": [{"text": "Understood. I will act as an FPL expert and respond in British English."}]},
            {"role": "user", "parts": [{"text": f"Here is the user's team data:\n{team_data}"}]},
            {"role": "model", "parts": [{"text": "Thank you. I have the team data."}]}
        ] + history
        
        return ask_ai_assistant(responder_history)
    
    else:
        print("Handling as general conversation based on AI decision...")
        # Prepend a simpler conversational prompt to the history
        conversational_history = [
            {"role": "user", "parts": [{"text": "You are a friendly and helpful FPL (Fantasy Premier League) assistant. Your responses must be in British English. Answer the user's query conversationally. Keep the response brief and engaging."}]},
            {"role": "model", "parts": [{"text": "Right then, I'll be a friendly FPL assistant and reply in British English."}]}
        ] + history
        
        return ask_ai_assistant(conversational_history)

# --- Flask Web Server ---
app = Flask(__name__)
CORS(app)

@app.route('/ask', methods=['POST'])
def ask():
    """API endpoint for the chat UI to call."""
    data = request.json
    user_query = data.get('query')
    user_id = data.get('userId')
    history = data.get('history', []) # Receive the history

    if not user_query or not user_id:
        return jsonify({"error": "Missing 'query' or 'userId' in request"}), 400

    response_text = handle_query(user_query, user_id, history)
    return jsonify({"response": response_text})

if __name__ == '__main__':
    print("--- FPL Chatbot Backend Server (Google Gemini) ---")
    print("Starting Flask server for local development at http://127.0.0.1:5000")
    app.run(port=5000, debug=True)
