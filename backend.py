# fpl_chatbot/backend.py
import os
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI, OpenAIError
import base64
from io import BytesIO
from PIL import Image
import aiohttp
import asyncio
from datetime import datetime
from typing import Optional

# Token / context sizing
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except Exception:
    _TIKTOKEN_AVAILABLE = False

# --- Configuration ---

# Set the AI provider: "OPENAI" or "GEMINI"
AI_PROVIDER = "OPENAI"

# Load API keys from environment variables
try:
    # Try to explicitly load a .env file located next to this module
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
except Exception:
    # If dotenv fails for any reason, continue without crashing — environment may be set externally
    pass


def _get_env_var_sanitized(name: str):
    """Read an environment variable, strip whitespace and surrounding quotes if present."""
    val = os.getenv(name)
    if val is None:
        return None
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return val


OPENAI_API_KEY = _get_env_var_sanitized("OPENAI_API_KEY")
GEMINI_API_KEY = _get_env_var_sanitized("GEMINI_API_KEY")

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

                # Always include both season and live points
                season_points = player["total_points"]

                live_points = None
                if live_data and "elements" in live_data and str(player["id"]) in live_data["elements"]:
                    live_points = live_data["elements"][str(player["id"])]["stats"]["total_points"]

                players_info.append(
                    f"- {player['web_name']} ({team_name}, {position}, £{player['now_cost']/10.0}m) - "
                    f"Season Points: {season_points}, "
                    f"Live Points: {live_points if live_points is not None else 'N/A'}, "
                    f"Form: {player['form']}, "
                    f"Status: {player['status']}"
                )

            # Format fixtures data (upcoming season fixtures)
            fixtures_info = []
            for fixture in fixtures:
                home_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_h"]), "N/A")
                away_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_a"]), "N/A")
                fixtures_info.append(f"- GW {fixture['event']}: {home_team} vs {away_team}")

            # Format current GW fixtures with consistent live scores
            fixtures_current_info = []
            for fixture in fixtures_current:
                home_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_h"]), "N/A")
                away_team = next((t["name"] for t in bootstrap_data["teams"] if t["id"] == fixture["team_a"]), "N/A")

                # Determine live score or placeholder
                home_score = fixture.get("team_h_score")
                away_score = fixture.get("team_a_score")
                if home_score is not None and away_score is not None:
                    score_str = f"{home_score} - {away_score}"
                else:
                    score_str = "Not started"

                fixtures_current_info.append(
                    f"- GW {fixture['event']}: {home_team} {score_str} {away_team}"
                )

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

# Simple in-memory session store for conversation history.
# Keys are session_id strings, values are lists of {"role": "user|assistant", "content": str}.
SESSION_HISTORY = {}
# Maximum number of messages to keep per session (user+assistant entries count individually).
SESSION_HISTORY_MAX = 12

# Maximum tokens allowed for the combined prompt (history + data context + instructions).
MAX_PROMPT_TOKENS = 400000

# Safety limits for images and prompt size
IMAGE_MAX_BYTES = 150_000  # target max bytes for embedded images (approx)
PROMPT_TRUNCATE_PLAYERS_CHARS = 3000
PROMPT_TRUNCATE_FIXTURES_CHARS = 2000


def estimate_tokens(text: str, model_name: str = 'gpt-4o') -> int:
    """Estimate token count for a given text. Uses tiktoken if available, else a heuristic."""
    if not text:
        return 0
    if _TIKTOKEN_AVAILABLE:
        try:
            # choose encoding by model when possible
            enc = tiktoken.encoding_for_model(model_name)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    # fallback heuristic: average 4 chars per token
    return max(1, int(len(text) / 4))


def compress_image_data_url(image_data_url: str, max_bytes: int = IMAGE_MAX_BYTES) -> Optional[str]:
    """Try to compress/rescale a data:...;base64,... image string until it's below max_bytes.
    Returns a new data URL string, or None if compression failed.
    """
    if not image_data_url or not image_data_url.startswith('data:'):
        return None
    try:
        header, encoded = image_data_url.split(',', 1)
        data = base64.b64decode(encoded)
        if len(data) <= max_bytes:
            return image_data_url

        img = Image.open(BytesIO(data)).convert('RGB')

        # iterative downscale + quality reduction
        quality = 85
        width, height = img.size
        # reduce until small enough or until dimensions/quality are low
        for scale in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4):
            new_size = (max(200, int(width * scale)), max(200, int(height * scale)))
            img_resized = img.resize(new_size, Image.LANCZOS)
            buf = BytesIO()
            img_resized.save(buf, format='JPEG', quality=quality)
            b = buf.getvalue()
            if len(b) <= max_bytes:
                new_encoded = base64.b64encode(b).decode('ascii')
                mime = 'image/jpeg'
                return f"data:{mime};base64,{new_encoded}"
            # progressively reduce quality
            quality = max(30, quality - 15)

        # final fallback: aggressively thumbnail
        img.thumbnail((400, 400), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=40)
        b = buf.getvalue()
        if len(b) <= max_bytes:
            new_encoded = base64.b64encode(b).decode('ascii')
            return f"data:image/jpeg;base64,{new_encoded}"
        # give up
        return None
    except Exception:
        return None


def truncate_fpl_sections(fpl_data: dict, players_chars: int = PROMPT_TRUNCATE_PLAYERS_CHARS, fixtures_chars: int = PROMPT_TRUNCATE_FIXTURES_CHARS) -> dict:
    """Return a shallow copy of fpl_data where long text sections are truncated for prompt size safety."""
    fd = fpl_data.copy()
    try:
        if 'players' in fd and fd['players'] and len(fd['players']) > players_chars:
            fd['players'] = fd['players'][:players_chars] + "\n... (players list truncated for prompt size)"
        if 'fixtures' in fd and fd['fixtures'] and len(fd['fixtures']) > fixtures_chars:
            fd['fixtures'] = fd['fixtures'][:fixtures_chars] + "\n... (fixtures truncated for prompt size)"
        if 'fixtures_current' in fd and fd['fixtures_current'] and len(fd['fixtures_current']) > fixtures_chars:
            fd['fixtures_current'] = fd['fixtures_current'][:fixtures_chars] + "\n... (current fixtures truncated for prompt size)"
    except Exception:
        pass
    return fd


def trim_history_to_fit(session_id: str, base_prompt: str, max_tokens: int = MAX_PROMPT_TOKENS, model_name: str = 'gpt-4o') -> None:
    """Trim oldest messages from session history until the combined tokens of history + base_prompt fit within max_tokens.

    This function mutates SESSION_HISTORY[session_id] in place (removing oldest entries first).
    """
    if not session_id:
        return
    history = SESSION_HISTORY.get(session_id)
    if not history:
        return

    # Build conversation text similar to _prepend_history_to_prompt
    def build_convo_text(entries):
        lines = ["Conversation so far:"]
        for e in entries:
            role = e.get('role', '')
            content = e.get('content', '')
            lines.append(f"{role.capitalize()}: {content}")
        return "\n".join(lines)

    # Current history + base prompt token estimate
    entries = history.copy()
    while True:
        convo_text = build_convo_text(entries)
        combined = convo_text + "\n\n" + (base_prompt or "")
        tokens = estimate_tokens(combined, model_name=model_name)
        if tokens <= max_tokens:
            break
        # if nothing to remove, break to avoid infinite loop
        if not entries:
            break
        # remove the oldest message and try again
        entries.pop(0)

    # Assign trimmed entries back to the session
    SESSION_HISTORY[session_id] = entries

async def get_ai_response_with_image(prompt, image_data_url):
    # Try OpenAI multimodal with GPT-5 mini first when provider is OPENAI
    openai_err = None
    if AI_PROVIDER == "OPENAI":
        if not OPENAI_API_KEY:
            return "Error: OPENAI_API_KEY environment variable not set."
        client = OpenAI(api_key=OPENAI_API_KEY)
        # Try structured multimodal Responses API using the official SDK shape
        try:
            try:
                # compress the image data URI if it's too large (avoid context-length errors)
                compressed = compress_image_data_url(image_data_url)
                send_image = compressed if compressed is not None else image_data_url

                # run blocking SDK call in a thread to keep this function async
                # Use the structured multimodal input shape: an array of content blocks
                # (input_text + input_image with base64 data URL) as shown in the user's example.
                structured_content = [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": send_image},
                ]
                response = await asyncio.to_thread(
                    client.responses.create,
                    model="gpt-5-mini",
                    input=[{"role": "user", "content": structured_content}]
                )
                out = getattr(response, 'output_text', None)
                if out:
                    return out
                try:
                    return response.output[0].content[0].text
                except Exception:
                    return str(response)
                out = getattr(response, 'output_text', None)
                if out:
                    return out
                try:
                    return response.output[0].content[0].text
                except Exception:
                    return str(response)
            except Exception as e:
                openai_err = e
                # Fallback: embed a compressed or placeholder data URI into the prompt and try text-only call
                try:
                    compressed = compress_image_data_url(image_data_url)
                    if compressed:
                        structured_content = [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": compressed},
                        ]
                        resp = await asyncio.to_thread(
                            client.responses.create,
                            model="gpt-5-mini",
                            input=[{"role": "user", "content": structured_content}]
                        )
                        out = getattr(resp, 'output_text', None)
                        if out:
                            return out
                        try:
                            return resp.output[0].content[0].text
                        except Exception:
                            return str(resp)
                    else:
                        # if we couldn't compress efficiently, include a short placeholder and ask user to upload a smaller image
                        fallback_prompt = prompt + "\n\n[Image omitted from prompt because it was too large to include. Please crop or upload a smaller image if more detailed analysis is required.]"
                        return await get_ai_response_text_only(fallback_prompt)
                except Exception as e2:
                    openai_err = openai_err or e2
        except OpenAIError:
            return "Error: Invalid OpenAI API key."
        except Exception as e:
            openai_err = e

    # If Gemini is configured (or OpenAI failed), try Gemini multimodal
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            header, encoded = image_data_url.split(",", 1)
            image_data = base64.b64decode(encoded)
            image = Image.open(BytesIO(image_data))
            model = genai.GenerativeModel('gemini-1.5-flash')
            content = [prompt, image]
            response = await model.generate_content_async(content)
            return response.text
        except Exception as e:
            if openai_err:
                return f"OpenAI error: {openai_err} | Gemini error: {e}"
            return f"Error with Gemini: {e}"

    # If we reach here, no provider could process the image
    if openai_err:
        return f"OpenAI error: {openai_err}"
    return "Error: No multimodal provider is configured to handle images."


async def get_ai_response_text_only(prompt):
    # ... (rest of the function remains the same)
    if AI_PROVIDER == "OPENAI":
        if not OPENAI_API_KEY:
            return "Error: OPENAI_API_KEY environment variable not set."
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            # Use the Responses API via a thread to avoid blocking the event loop
            try:
                response = await asyncio.to_thread(
                    client.responses.create,
                    model="gpt-5-mini",
                    input=prompt
                )
                out = getattr(response, 'output_text', None)
                if out:
                    return out
                try:
                    return response.output[0].content[0].text
                except Exception:
                    return str(response)
            except Exception as e:
                return f"Error with OpenAI: {e}"
        except OpenAIError:
            return "Error: Invalid OpenAI API key."
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


def _prepend_history_to_prompt(base_prompt, session_id: str):
    """Return prompt text with recent session history prepended (if available)."""
    if not session_id:
        return base_prompt
    history = SESSION_HISTORY.get(session_id)
    if not history:
        return base_prompt

    # Build a compact conversation log
    convo_lines = ["Conversation so far:"]
    for entry in history:
        role = entry.get('role')
        content = entry.get('content')
        convo_lines.append(f"{role.capitalize()}: {content}")

    convo_text = "\n".join(convo_lines)
    return f"{convo_text}\n\n{base_prompt}"

# --- Main Chatbot Logic ---

async def get_chatbot_advice(user_query, image_data_url=None, session_id: str = None):
    """
    Main function to get FPL advice, now with full live and season data context.
    """
    fpl_data = await get_fpl_data()
    if "error" in fpl_data:
        return fpl_data["error"]

    # --- Build context for the AI ---
    data_context = (
        f"Current Date: {fpl_data['current_date']}\n"
        f"Current Gameweek: {fpl_data['current_gameweek']}\n\n"
        f"**Available Players & Stats (Season + Live):**\n{fpl_data['players']}\n\n"
        f"**Upcoming Fixtures (Season):**\n{fpl_data['fixtures']}\n\n"
        f"**Current Gameweek Fixtures (Live Scores if available):**\n{fpl_data['fixtures_current']}"
    )

    # If the combined prompt is very large, truncate large FPL sections to keep under token limits
    try:
        preview_prompt = f"You are a friendly and knowledgeable FPL AI assistant.\n\n**FPL Data Context:**\n{data_context}\n\nUser's question: \"{user_query}\""
        if estimate_tokens(preview_prompt) > MAX_PROMPT_TOKENS:
            # create a truncated copy of fpl_data and rebuild the data_context
            small = truncate_fpl_sections(fpl_data)
            data_context = (
                f"Current Date: {small['current_date']}\n"
                f"Current Gameweek: {small['current_gameweek']}\n\n"
                f"**Available Players & Stats (Season + Live):**\n{small['players']}\n\n"
                f"**Upcoming Fixtures (Season):**\n{small['fixtures']}\n\n"
                f"**Current Gameweek Fixtures (Live Scores if available):**\n{small['fixtures_current']}"
            )
    except Exception:
        # best-effort: if anything goes wrong here, continue with original context
        pass

    if image_data_url:
        prompt = f"""
        You are a friendly and knowledgeable FPL AI assistant. 
        Your tone is conversational and you use British English.

        **FPL Data Context:**
        {data_context}

        **User's Request:**
        The user has uploaded a screenshot of their team and asked a question.

        **IMPORTANT INSTRUCTIONS FOR IMAGE ANALYSIS:**
        1. Identify the players in the user's squad from the screenshot.
        2. A player's actual team is shown by their jersey. 
           The team name underneath them is their **next opponent**. Do not confuse the two.
        3. Use both **season stats** and **live points / live scores** to inform your advice.
        4. When recommending transfers, captains, or lineup changes, consider both historical performance (season points, form) and current matchday performance (live points, live scores) where available.

        Provide a helpful, conversational response to the user's question.

        User's question: "{user_query}"
        """
        # append the user's message to history before calling the model
        if session_id:
            SESSION_HISTORY.setdefault(session_id, []).append({"role": "user", "content": user_query})
            # ensure history fits token budget
            trim_history_to_fit(session_id, prompt)

        # include recent conversation history in prompt (after trimming)
        full_prompt = _prepend_history_to_prompt(prompt, session_id)

        response_text = await get_ai_response_with_image(full_prompt, image_data_url)

        # store assistant reply
        if session_id:
            SESSION_HISTORY.setdefault(session_id, []).append({"role": "assistant", "content": response_text})
            # ensure history still fits budget after appending reply
            trim_history_to_fit(session_id, prompt)

        return response_text

    else:
        prompt = f"""
        You are a friendly and knowledgeable FPL AI assistant. 
        Your tone is conversational and you use British English.

        **FPL Data Context:**
        {data_context}

        **User's Request:**
        The user has asked a general question about FPL.

        **IMPORTANT INSTRUCTIONS:**
        1. Use both **season stats** and **live points / live scores** when reasoning.
        2. Give advice considering both historical performance (season points, form) and current matchday performance (live points, live scores) where available.
        3. Be conversational, clear, and precise. Use British English.

        User's question: "{user_query}"
        """
        # append the user's message to history before calling the model
        if session_id:
            SESSION_HISTORY.setdefault(session_id, []).append({"role": "user", "content": user_query})
            # ensure history fits token budget
            trim_history_to_fit(session_id, prompt)

        # include recent conversation history in prompt (after trimming)
        full_prompt = _prepend_history_to_prompt(prompt, session_id)

        response_text = await get_ai_response_text_only(full_prompt)

        if session_id:
            SESSION_HISTORY.setdefault(session_id, []).append({"role": "assistant", "content": response_text})
            # ensure history still fits budget after appending reply
            trim_history_to_fit(session_id, prompt)

        return response_text


def get_key_status():
    """Return a small, safe status dict about configured keys (masked, not full values)."""
    def _mask(key: str):
        if not key:
            return None
        if len(key) <= 8:
            return key[:1] + '...' + key[-1:]
        return key[:6] + '...' + key[-4:]

    return {
        "ai_provider": AI_PROVIDER,
        "openai_key_present": bool(OPENAI_API_KEY),
        "openai_key_masked": _mask(OPENAI_API_KEY),
        "gemini_key_present": bool(GEMINI_API_KEY),
        "gemini_key_masked": _mask(GEMINI_API_KEY),
    }
