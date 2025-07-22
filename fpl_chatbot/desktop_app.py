# fpl_chatbot/desktop_app.py
import customtkinter as ctk
from tkinter import simpledialog, messagebox
import threading
import backend
import constants

# --- CustomTkinter UI and Application Logic ---

class FplChatbotApp(ctk.CTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("FPL AI Assistant")
        self.geometry("500x650")
        self.configure(fg_color=constants.FPL_DARK_PURPLE)
        self.resizable(False, False)

        self.fpl_user_id = None
        self.google_api_key = None
        self.chat_history = []

        # --- Configure grid layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header_frame.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        header_label = ctk.CTkLabel(header_frame, text="FPL AI Assistant", font=("Helvetica", 20, "bold"), text_color=constants.FPL_TEXT)
        header_label.pack(side="left")
        self.user_id_label = ctk.CTkLabel(header_frame, text="User ID: Not Set", font=("Helvetica", 10), text_color=constants.FPL_GREEN)
        self.user_id_label.pack(side="right")

        # --- Chat display frame ---
        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color=constants.FPL_DARK_PURPLE, corner_radius=0)
        self.chat_frame.grid(row=1, column=0, padx=10, pady=0, sticky="nsew")

        # --- Input frame ---
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_frame, placeholder_text="Ask a question...", fg_color=constants.FPL_LIGHT_PURPLE,
            text_color=constants.FPL_TEXT, border_width=0, corner_radius=15, font=("Helvetica", 14)
        )
        self.entry.grid(row=0, column=0, padx=(0, 10), sticky="ew", ipady=5)
        self.entry.bind("<Return>", self.send_message)

        self.send_button = ctk.CTkButton(
            input_frame, text="Send", fg_color=constants.FPL_GREEN, text_color=constants.FPL_BLACK,
            hover_color=constants.FPL_PINK, width=80, corner_radius=15, font=("Helvetica", 14, "bold"),
            command=self.send_message
        )
        self.send_button.grid(row=0, column=1, sticky="e")

        self.after(100, self.get_user_config)

    def get_user_config(self):
        """Loads user config or prompts for it."""
        config = backend.load_user_config()
        self.fpl_user_id = config.get("FPL_USER_ID")
        self.google_api_key = config.get("GOOGLE_API_KEY")
        needs_save = False

        if not self.fpl_user_id:
            needs_save = True
            self.fpl_user_id = simpledialog.askstring("FPL User ID", "Please enter your FPL User ID:")
            if not self.fpl_user_id: self.destroy(); return
            config["FPL_USER_ID"] = self.fpl_user_id

        if not self.google_api_key:
            needs_save = True
            self.google_api_key = simpledialog.askstring("Google API Key", "Please enter your Google API Key:")
            if not self.google_api_key: self.destroy(); return
            config["GOOGLE_API_KEY"] = self.google_api_key

        if needs_save:
            backend.save_user_config(config)
            messagebox.showinfo("Success", "Configuration saved!")

        self.user_id_label.configure(text=f"User ID: {self.fpl_user_id}")
        self.add_message("ai", "Alright? How can I help with your FPL team?")

    def add_message(self, author, text):
        """Adds a message bubble to the chat frame."""
        anchor = "e" if author == "user" else "w"
        bg_color = constants.FPL_GREEN if author == "user" else constants.FPL_LIGHT_PURPLE
        text_color = constants.FPL_BLACK if author == "user" else constants.FPL_TEXT
        
        bubble_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        bubble = ctk.CTkLabel(
            bubble_frame, text=text, fg_color=bg_color, text_color=text_color,
            corner_radius=15, wraplength=self.chat_frame.winfo_width() * 0.7,
            justify="left", padx=12, pady=8, font=("Helvetica", 14)
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
        response = backend.get_chatbot_response(self.google_api_key, self.fpl_user_id, user_query, self.chat_history)
        self.after(0, lambda: self.update_ui_with_response(response))

    def update_ui_with_response(self, response):
        """Updates the UI with the AI's response on the main thread."""
        last_widget = self.chat_frame.winfo_children()[-1]
        if "Thinking..." in last_widget.winfo_children()[0].cget("text"):
            last_widget.destroy()
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
