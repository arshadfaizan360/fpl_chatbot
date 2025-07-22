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
# Switched to Google Gemini Pro model
GEMINI_MODEL_NAME = "gemini-2.0-flash" 
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Sanity Check for API Token ---
if GOOGLE_API_KEY:
    print("✅ Google API Key loaded successfully from .env file.")
else:
    print("❌ WARNING: GOOGLE_API_KEY not found. Please get a key from Google AI Studio and add it to your .env file.")


# --- FPL Data Functions (Our "Tool") ---

def get_fpl_bootstrap_data():
    """Fetches the main bootstrap data from the FPL API."""
    try:
        response = requests.get(f"{FPL_API_BASE_URL}bootstrap-static/")
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
    """Fetches FPL team data for a given user_id. This is our primary 'tool'."""
    if not user_id:
        return {"error": "FPL User ID was not provided."}

    bootstrap_data = get_fpl_bootstrap_data()
    if "error" in bootstrap_data:
        return bootstrap_data

    current_gameweek = get_current_gameweek(bootstrap_data)
    if not current_gameweek:
        return {"error": "Could not determine the current or next gameweek."}

    try:
        picks_url = f"{FPL_API_BASE_URL}entry/{user_id}/event/{current_gameweek}/picks/"
        picks_response = requests.get(picks_url)
        picks_response.raise_for_status()
        team_picks = picks_response.json()

        info_url = f"{FPL_API_BASE_URL}entry/{user_id}/"
        info_response = requests.get(info_url)
        info_response.raise_for_status()
        user_info = info_response.json()

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
            return {"error": "Team Not Found. Please ensure your User ID is correct and you have saved your initial squad on the FPL website."}
        return {"error": f"An HTTP error occurred: {http_err}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}

# --- AI Interaction ---

def ask_ai_assistant(full_prompt):
    """
    Sends a prompt to the Google Gemini API.
    """
    if not GOOGLE_API_KEY:
        return "GOOGLE_API_KEY not found in environment variables. Please check your .env file."

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
    data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(api_url, data=data, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            response_body = response.read().decode("utf-8")
            json_response = json.loads(response_body)
            
            # Navigate the Gemini API's response structure
            if "candidates" in json_response and len(json_response["candidates"]) > 0:
                content = json_response["candidates"][0].get("content", {})
                if "parts" in content and len(content["parts"]) > 0:
                    return content["parts"][0].get("text", "").strip()
            
            # Handle cases where the response is unexpected or blocked
            print(f"--- GOOGLE API UNEXPECTED RESPONSE ---\n{json_response}\n------------------------------------")
            return f"Error: Received an unexpected or empty response from the AI assistant."

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

def handle_query(user_query, user_id):
    """
    Processes a natural language query using a two-step LLM process.
    """
    print(f"Received query: '{user_query}' for user_id: {user_id}")

    router_prompt = (
        "You are an AI assistant that determines if a user's request requires accessing their Fantasy Premier League (FPL) team data. "
        "Based on the following query, do you need to see the user's current team, budget, and players to give a helpful answer? "
        "Answer with only the word 'yes' or 'no'.\n\n"
        f"User Query: '{user_query}'"
    )
    
    decision = ask_ai_assistant(router_prompt).lower().strip()
    print(f"Decision from AI router: '{decision}'")

    if 'yes' in decision and 'no' not in decision:
        print("Fetching FPL data based on AI decision...")
        team_data = get_fpl_team_data(user_id)
        if isinstance(team_data, dict) and "error" in team_data:
            return team_data["error"]

        responder_prompt = (
            "You are an expert Fantasy Premier League (FPL) assistant. Your responses must be in British English. "
            "Analyse the following team data and answer the user's request concisely and helpfully.\n\n"
            f"Team Data:\n{team_data}\n\n"
            f"User Request: {user_query}"
        )
        return ask_ai_assistant(responder_prompt)
    
    else:
        print("Handling as general conversation based on AI decision...")
        conversational_prompt = (
            "You are a friendly and helpful FPL (Fantasy Premier League) assistant. Your responses must be in British English. "
            "Answer the following user query conversationally. Keep the response brief and engaging. "
            "If asked about something other than FPL, politely steer the conversation back to fantasy football (the proper kind).\n\n"
            f"User: {user_query}\n"
            "Assistant:"
        )
        return ask_ai_assistant(conversational_prompt)

# --- Flask Web Server ---
app = Flask(__name__)
CORS(app)

@app.route('/ask', methods=['POST'])
def ask():
    """API endpoint for the chat UI to call."""
    data = request.json
    user_query = data.get('query')
    user_id = data.get('userId')

    if not user_query or not user_id:
        return jsonify({"error": "Missing 'query' or 'userId' in request"}), 400

    response_text = handle_query(user_query, user_id)
    return jsonify({"response": response_text})

if __name__ == '__main__':
    print("--- FPL Chatbot Backend Server (Google Gemini) ---")
    print("Starting Flask server for local development at http://127.0.0.1:5000")
    app.run(port=5000, debug=True)
