# fpl_chatbot/main.py
import os
import requests
import json
import urllib.request
from pathlib import Path
import threading
import ssl
import customtkinter as ctk
from tkinter import simpledialog, messagebox

# --- Constants ---
FPL_API_BASE_URL = "https://fantasy.premierleague.com/api/"
GEMINI_MODEL_NAME = "gemini-2.0-flash" 
CONFIG_FILE = Path.home() / ".fpl_chatbot_config.json"

# --- FPL Color Palette ---
FPL_DARK_PURPLE = '#37003c'
FPL_LIGHT_PURPLE = '#4a0050'
FPL_GREEN = '#00ff85'
FPL_PINK = '#e90052'
FPL_TEXT = '#ffffff'
FPL_BLACK = '#000000'

# --- FPL Data Functions (Our "Tool") ---
# This section remains the same as before
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

# --- CustomTkinter UI and Application Logic ---

class FplChatbotApp(ctk.CTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("FPL AI Assistant")
        self.geometry("500x650")
        self.configure(fg_color=FPL_DARK_PURPLE)
        self.resizable(False, False)

        self.fpl_user_id = None
        self.google_api_key = None
        self.chat_history = []

        # --- Configure grid layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1) # Chat frame will expand

        # --- Header ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header_frame.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        header_label = ctk.CTkLabel(header_frame, text="FPL AI Assistant", font=("Helvetica", 20, "bold"), text_color=FPL_TEXT)
        header_label.pack(side="left")
        self.user_id_label = ctk.CTkLabel(header_frame, text="User ID: Not Set", font=("Helvetica", 10), text_color=FPL_GREEN)
        self.user_id_label.pack(side="right")


        # --- Chat display frame ---
        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color=FPL_DARK_PURPLE, corner_radius=0)
        self.chat_frame.grid(row=1, column=0, padx=10, pady=0, sticky="nsew")

        # --- Input frame ---
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Ask a question...",
            fg_color=FPL_LIGHT_PURPLE,
            text_color=FPL_TEXT,
            border_width=0,
            corner_radius=15,
            font=("Helvetica", 14)
        )
        self.entry.grid(row=0, column=0, padx=(0, 10), sticky="ew", ipady=5)
        self.entry.bind("<Return>", self.send_message)

        self.send_button = ctk.CTkButton(
            input_frame,
            text="Send",
            fg_color=FPL_GREEN,
            text_color=FPL_BLACK,
            hover_color=FPL_PINK,
            width=80,
            corner_radius=15,
            font=("Helvetica", 14, "bold"),
            command=self.send_message
        )
        self.send_button.grid(row=0, column=1, sticky="e")

        # --- Load config after window is created ---
        self.after(100, self.get_user_config)

    def get_user_config(self):
        """Loads user config or prompts for it."""
        config = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                try: config = json.load(f)
                except: pass

        self.fpl_user_id = config.get("FPL_USER_ID")
        self.google_api_key = config.get("GOOGLE_API_KEY")
        needs_save = False

        if not self.fpl_user_id:
            needs_save = True
            self.fpl_user_id = simpledialog.askstring(
                "FPL User ID",
                "Please enter your FPL User ID:\n(Find this in the URL of the 'Points' page on the FPL website)"
            )
            if not self.fpl_user_id: self.destroy(); return
            config["FPL_USER_ID"] = self.fpl_user_id

        if not self.google_api_key:
            needs_save = True
            self.google_api_key = simpledialog.askstring(
                "Google API Key",
                "Please enter your Google API Key:\n(Get a free key from Google AI Studio)"
            )
            if not self.google_api_key: self.destroy(); return
            config["GOOGLE_API_KEY"] = self.google_api_key

        if needs_save:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
            messagebox.showinfo("Success", "Configuration saved!")

        self.user_id_label.configure(text=f"User ID: {self.fpl_user_id}")
        self.add_message("ai", "Alright? How can I help with your FPL team?")

    def add_message(self, author, text):
        """Adds a message bubble to the chat frame."""
        if author == "user":
            anchor = "e"
            bg_color = FPL_GREEN
            text_color = FPL_BLACK
        else: # AI
            anchor = "w"
            bg_color = FPL_LIGHT_PURPLE
            text_color = FPL_TEXT

        # Use a frame to contain the label for better padding and alignment
        bubble_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        
        bubble = ctk.CTkLabel(
            bubble_frame,
            text=text,
            fg_color=bg_color,
            text_color=text_color,
            corner_radius=15,
            wraplength=self.chat_frame.winfo_width() * 0.7,
            justify="left",
            padx=12,
            pady=8,
            font=("Helvetica", 14)
        )
        bubble.pack(padx=5, pady=2)
        
        bubble_frame.pack(anchor=anchor, padx=5, pady=5, fill="x")

        self.update_idletasks()
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    def send_message(self, event=None):
        """Handles sending a message from the user."""
        user_query = self.entry.get()
        if not user_query: return

        self.add_message("user", user_query)
        self.entry.delete(0, "end")
        self.chat_history.append({"role": "user", "parts": [{"text": user_query}]})

        self.send_button.configure(state="disabled")
        self.entry.configure(state="disabled")
        
        threading.Thread(target=self.run_chatbot_logic, args=(user_query,), daemon=True).start()

    def run_chatbot_logic(self, user_query):
        """Orchestrates the AI response logic in a background thread."""
        self.after(0, lambda: self.add_message("ai", "Thinking..."))

        router_history = [
            {"role": "user", "parts": [{"text": "You are an AI assistant that determines if a user's request requires accessing their Fantasy Premier League (FPL) team data. Answer with only 'yes' or 'no'."}]},
            {"role": "model", "parts": [{"text": "Okay, I understand."}]},
            {"role": "user", "parts": [{"text": f"User Query: '{user_query}'"}]}
        ]
        decision = ask_ai_assistant(self.google_api_key, router_history).lower().strip()

        if 'yes' in decision:
            team_data = get_fpl_team_data(self.fpl_user_id, {'User-Agent': 'Mozilla/5.0'})
            if isinstance(team_data, dict) and "error" in team_data:
                response = f"Error: {team_data['error']}"
            else:
                responder_history = [
                    {"role": "user", "parts": [{"text": "You are an expert FPL assistant. Your responses must be in British English. Analyse the provided team data to answer the user's questions."}]},
                    {"role": "model", "parts": [{"text": "Understood."}]},
                    {"role": "user", "parts": [{"text": f"Here is the user's team data:\n{team_data}"}]},
                    {"role": "model", "parts": [{"text": "Thank you. I have the team data."}]}
                ] + self.chat_history
                response = ask_ai_assistant(self.google_api_key, responder_history)
        else:
            conversational_history = [
                {"role": "user", "parts": [{"text": "You are a friendly and helpful FPL assistant. Your responses must be in British English. Answer conversationally."}]},
                {"role": "model", "parts": [{"text": "Right then."}]}
            ] + self.chat_history
            response = ask_ai_assistant(self.google_api_key, conversational_history)
        
        self.after(0, lambda: self.update_ui_with_response(response))

    def update_ui_with_response(self, response):
        """Updates the UI with the AI's response on the main thread."""
        # Find and remove the "Thinking..." bubble
        for widget in self.chat_frame.winfo_children():
            if isinstance(widget, ctk.CTkFrame):
                label = widget.winfo_children()[0]
                if "Thinking..." in label.cget("text"):
                    widget.destroy()
                    break

        self.add_message("ai", response)
        self.chat_history.append({"role": "model", "parts": [{"text": response}]})
        
        self.send_button.configure(state="normal")
        self.entry.configure(state="normal")
        self.entry.focus_set()

def run():
    ctk.set_appearance_mode("dark")
    app = FplChatbotApp()
    app.mainloop()

if __name__ == '__main__':
    run()
