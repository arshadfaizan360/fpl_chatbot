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

async def get_fpl_data():
    """
    Fetches comprehensive live data directly from the FPL API with a more robust retry logic.
    """
    headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://fantasy.premierleague.com/",
    "Origin": "https://fantasy.premierleague.com",
    "Connection": "keep-alive"
}
    
    # Create a TCPConnector with SSL verification disabled.
    connector = aiohttp.TCPConnector(ssl=False)
    
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        for attempt in range(4): # Retry up to 4 times
            try:
                # Fetch bootstrap data directly
                async with session.get("https://arshadfaizan360.github.io/fpl-data-mirror/bootstrap-static.json") as response:
                    response.raise_for_status()
                    bootstrap_data = await response.json()

                # Fetch fixtures data directly
                async with session.get("https://arshadfaizan360.github.io/fpl-data-mirror/fixtures.json") as response:
                    response.raise_for_status()
                    fixtures = await response.json()

                # Format players data
                players_info = []
                for player in bootstrap_data["elements"]:
                    team_name = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == player["team"]), "N/A")
                    position = bootstrap_data["element_types"][player["element_type"] - 1]["singular_name_short"]
                    players_info.append(
                        f"- {player['web_name']} ({team_name}, {position}, £{player['now_cost']/10.0}m) - "
                        f"Points: {player['total_points']}, Form: {player['form']}, Status: {player['status']}"
                    )
                
                # Format fixtures data
                fixtures_info = []
                for fixture in fixtures:
                    home_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_h"]), "N/A")
                    away_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_a"]), "N/A")
                    fixtures_info.append(
                        f"- GW {fixture['event']}: {home_team} vs {away_team}"
                    )

                # Get current gameweek
                current_gameweek = next((event["id"] for event in bootstrap_data["events"] if event["is_current"]), "N/A")

                return {
                    "players": "\n".join(players_info),
                    "fixtures": "\n".join(fixtures_info),
                    "current_gameweek": current_gameweek,
                    "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            except aiohttp.ClientResponseError as e:
                if e.status == 403 and attempt < 3:
                    # Wait for a random, slightly longer delay before retrying
                    wait_time = 1 + random.uniform(0.5, 1.5)
                    await asyncio.sleep(wait_time) 
                    continue # Go to the next attempt
                return {"error": f"An error occurred while fetching FPL data after multiple retries: {e}"}
            except Exception as e:
                return {"error": f"An unexpected error occurred: {e}"}

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
