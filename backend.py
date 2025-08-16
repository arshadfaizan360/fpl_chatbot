# fpl_chatbot/backend.py
import os
import google.generativeai as genai
from openai import AsyncOpenAI, AuthenticationError
import base64
from io import BytesIO
from PIL import Image
import aiohttp
from datetime import datetime
import asyncio
import random

# --- Configuration ---

# Set the AI provider: "OPENAI" or "GEMINI"
AI_PROVIDER = "GEMINI" 

# Load API keys from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- FPL Data Fetching ---

GITHUB_BASE_URL = "https://arshadfaizan360.github.io/fpl-data-mirror"

async def get_fpl_data():
    """
    Fetches FPL data from GitHub mirror (bootstrap, fixtures, live points).
    Falls back to official API if running locally and mirror is unavailable.
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
    }
    
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        try:
            # --- Bootstrap (players, teams, events) ---
            async with session.get(f"{GITHUB_BASE_URL}/bootstrap-static.json") as response:
                response.raise_for_status()
                bootstrap_data = await response.json()

            # --- Fixtures (full season) ---
            async with session.get(f"{GITHUB_BASE_URL}/fixtures.json") as response:
                response.raise_for_status()
                fixtures = await response.json()

            # --- Live points (current GW only) ---
            async with session.get(f"{GITHUB_BASE_URL}/live.json") as response:
                response.raise_for_status()
                live_data = await response.json()

            # --- Current GW fixtures ---
            async with session.get(f"{GITHUB_BASE_URL}/fixtures-current.json") as response:
                response.raise_for_status()
                fixtures_current = await response.json()

            # Format players data
            players_info = []
            for player in bootstrap_data["elements"]:
                team_name = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == player["team"]), "N/A")
                position = bootstrap_data["element_types"][player["element_type"] - 1]["singular_name_short"]

                # Check if live points are available
                live_points = None
                if live_data and "elements" in live_data and str(player["id"]) in live_data["elements"]:
                    live_points = live_data["elements"][str(player["id"])]["stats"]["total_points"]

                players_info.append(
                    f"- {player['web_name']} ({team_name}, {position}, £{player['now_cost']/10.0}m) - "
                    f"Season Points: {player['total_points']}, "
                    f"Form: {player['form']}, "
                    f"Status: {player['status']}"
                    + (f", Live Points: {live_points}" if live_points is not None else "")
                )

            # Format fixtures data (upcoming season fixtures)
            fixtures_info = []
            for fixture in fixtures:
                home_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_h"]), "N/A")
                away_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_a"]), "N/A")
                fixtures_info.append(f"- GW {fixture['event']}: {home_team} vs {away_team}")

            # Format current GW fixtures (with live data if available)
            fixtures_current_info = []
            for fixture in fixtures_current:
                home_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_h"]), "N/A")
                away_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_a"]), "N/A")
                score = f"{fixture['team_h_score']} - {fixture['team_a_score']}" if fixture["started"] else "Not started"
                fixtures_current_info.append(f"- GW {fixture['event']}: {home_team} {score} {away_team}")

            # Get current gameweek
            current_gameweek = next((event["id"] for event in bootstrap_data["events"] if event["is_current"]), "N/A")

            return {
                "players": "\n".join(players_info),
                "fixtures": "\n".join(fixtures_info),
                "fixtures_current": "\n".join(fixtures_current_info),
                "current_gameweek": current_gameweek,
                "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            return {"error": f"Error fetching FPL data: {e}"}

# --- AI Interaction ---

async def get_ai_response_with_image(prompt, image_data_url):
    # ... (rest of the function remains the same)
    if AI_PROVIDER != "GEMINI":
        return "Error: Image analysis is only supported with the GEMINI provider in this configuration."
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY environment variable not set."
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        header, encoded = image_data_url.split(",", 1)
        image_data = base64.b64decode(encoded)
        image = Image.open(BytesIO(image_data))
        content = [prompt, image]
        response = await model.generate_content_async(content)
        return response.text
    except Exception as e:
        return f"Error with Gemini: {e}"


async def get_ai_response_text_only(prompt):
    # ... (rest of the function remains the same)
    if AI_PROVIDER == "OPENAI":
        if not OPENAI_API_KEY:
            return "Error: OPENAI_API_KEY environment variable not set."
        try:
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o", messages=[{"role": "user", "content": prompt}], temperature=0.3)
            return response.choices[0].message.content
        except AuthenticationError:
            return "Error: Invalid OpenAI API key."
        except Exception as e:
            return f"Error with OpenAI: {e}"
    elif AI_PROVIDER == "GEMINI":
        if not GEMINI_API_KEY:
            return "Error: GEMINI_API_KEY environment variable not set."
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = await model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            return f"Error with Gemini: {e}"
    else:
        return "Error: Invalid AI_PROVIDER configured."

# --- Main Chatbot Logic ---

async def get_chatbot_advice(user_query, image_data_url=None):
    """
    Main function to get FPL advice, now with live data context.
    """
    fpl_data = await get_fpl_data()
    if "error" in fpl_data:
        return fpl_data["error"]

    # Construct the data context string
    data_context = (
        f"Current Date: {fpl_data['current_date']}\n"
        f"Current Gameweek: {fpl_data['current_gameweek']}\n\n"
        f"**Available Players & Stats:**\n{fpl_data['players']}\n\n"
        f"**Upcoming Fixtures:**\n{fpl_data['fixtures']}"
    )

    if image_data_url:
        prompt = f"""
        You are a friendly and knowledgeable FPL AI assistant. Your tone is conversational and you use British English.

        **FPL Data Context:**
        {data_context}

        **User's Request:**
        The user has uploaded a screenshot of their team and asked a question.

        **IMPORTANT INSTRUCTIONS FOR IMAGE ANALYSIS:**
        1.  Identify the players in the user's squad from the screenshot.
        2.  A player's actual team is indicated by their jersey. The team name *underneath* a player is their **next opponent**. Do not confuse them.
        3.  Use the provided FPL Data Context to inform your response.

        After correctly identifying the squad and considering the live data, provide a helpful and conversational response to the user's question.

        User's question: "{user_query}"
        """
        return await get_ai_response_with_image(prompt, image_data_url)
    else:
        prompt = f"""
        You are a friendly and knowledgeable FPL AI assistant. Your tone is conversational and you use British English.

        **FPL Data Context:**
        {data_context}

        **User's Request:**
        The user has asked a general question about FPL. Use the provided FPL Data Context to give the most accurate and up-to-date answer possible.

        User's question: "{user_query}"
        """
        return await get_ai_response_text_only(prompt)
