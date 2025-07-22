# fpl_chatbot/backend.py
import os
import requests
import json
import urllib.request
from pathlib import Path
import ssl

# --- Constants ---
FPL_API_BASE_URL = "https://fantasy.premierleague.com/api/"
GEMINI_MODEL_NAME = "gemini-2.0-flash" 
CONFIG_FILE = Path.home() / ".fpl_chatbot_config.json"

# --- FPL Data Functions (Our "Tool") ---
def get_fpl_team_data(user_id, headers):
    """Fetches FPL team data for a given user_id."""
    try:
        info_url = f"{FPL_API_BASE_URL}entry/{user_id}/"
        info_response = requests.get(info_url, headers=headers)
        info_response.raise_for_status()
        user_info = info_response.json()

        bootstrap_data_url = f"{FPL_API_BASE_URL}bootstrap-static/"
        bootstrap_response = requests.get(bootstrap_data_url, headers=headers)
        bootstrap_response.raise_for_status()
        bootstrap_data = bootstrap_response.json()

        current_gameweek = next((event['id'] for event in bootstrap_data['events'] if event.get('is_next')), 1)

        picks_url = f"{FPL_API_BASE_URL}entry/{user_id}/event/{current_gameweek}/picks/"
        picks_response = requests.get(picks_url, headers=headers)
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
            return {"error": "Team Not Found. Please ensure your User ID is correct and you have saved your initial squad on the FPL website."}
        return {"error": f"An HTTP error occurred: {http_err}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}

# --- AI Interaction ---
def ask_ai_assistant(api_key, history):
    """Sends a conversation history to the Google Gemini API."""
    if not api_key:
        return "Error: Google API Key was not provided or found."

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    payload = {"contents": history}
    data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(api_url, data=data, headers=headers)
    context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, context=context) as response:
            response_body = response.read().decode("utf-8")
            json_response = json.loads(response_body)
            
            if "candidates" in json_response and len(json_response["candidates"]) > 0:
                content = json_response["candidates"][0].get("content", {})
                if "parts" in content and len(content["parts"]) > 0:
                    return content["parts"][0].get("text", "").strip()
            return "Error: Received an unexpected or empty response from the AI assistant."
    except Exception as e:
        return f"An error occurred while contacting the AI assistant: {e}"

# --- User Configuration ---
def load_user_config():
    """Loads user config from a file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_user_config(config):
    """Saves user config to a file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# --- Chatbot Core Logic ---
def get_chatbot_response(api_key, user_id, user_query, history):
    """Orchestrates the AI response logic."""
    router_history = [
        {"role": "user", "parts": [{"text": "You are an AI assistant that determines if a user's request requires accessing their Fantasy Premier League (FPL) team data. Answer with only 'yes' or 'no'."}]},
        {"role": "model", "parts": [{"text": "Okay, I understand."}]},
        {"role": "user", "parts": [{"text": f"User Query: '{user_query}'"}]}
    ]
    decision = ask_ai_assistant(api_key, router_history).lower().strip()

    if 'yes' in decision:
        team_data = get_fpl_team_data(user_id, {'User-Agent': 'Mozilla/5.0'})
        if isinstance(team_data, dict) and "error" in team_data:
            return f"Error: {team_data['error']}"
        
        responder_history = [
            {"role": "user", "parts": [{"text": "You are an expert FPL assistant. Your responses must be in British English. Analyse the provided team data to answer the user's questions."}]},
            {"role": "model", "parts": [{"text": "Understood."}]},
            {"role": "user", "parts": [{"text": f"Here is the user's team data:\n{team_data}"}]},
            {"role": "model", "parts": [{"text": "Thank you. I have the team data."}]}
        ] + history
        return ask_ai_assistant(api_key, responder_history)
    else:
        conversational_history = [
            {"role": "user", "parts": [{"text": "You are a friendly and helpful FPL assistant. Your responses must be in British English. Answer conversationally."}]},
            {"role": "model", "parts": [{"text": "Right then."}]}
        ] + history
        return ask_ai_assistant(api_key, conversational_history)
