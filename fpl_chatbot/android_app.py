# fpl_chatbot/android_app.py
import threading
from functools import partial
import backend
import constants

# --- Kivy UI Imports ---
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex

# --- Kivy-Specific Color Conversions ---
KIVY_FPL_DARK_PURPLE = get_color_from_hex(constants.FPL_DARK_PURPLE)
KIVY_FPL_LIGHT_PURPLE = get_color_from_hex(constants.FPL_LIGHT_PURPLE)
KIVY_FPL_GREEN = get_color_from_hex(constants.FPL_GREEN)
KIVY_FPL_WHITE = get_color_from_hex(constants.FPL_TEXT)
KIVY_FPL_BLACK = get_color_from_hex(constants.FPL_BLACK)
KIVY_FPL_GREY = get_color_from_hex(constants.FPL_GREY)


# --- Kivy UI and Application Logic ---

class WrappedLabel(Label):
    """A custom Label that automatically wraps text to fit its width."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            width=lambda *x: self.setter('text_size')(self, (self.width, None)),
            texture_size=lambda *x: self.setter('height')(self, self.texture_size[1])
        )

class ChatBubble(BoxLayout):
    """A custom widget for displaying a chat message with a rounded background."""
    def __init__(self, text, author, **kwargs):
        super().__init__(**kwargs)
        self.padding = [15, 12]
        self.size_hint_y = None
        self.height = self.minimum_height
        self.size_hint_x = 0.75
        label = WrappedLabel(text=text, markup=True)
        
        if author == 'user':
            bg_color = KIVY_FPL_GREEN
            label.color = KIVY_FPL_BLACK
        else:
            bg_color = KIVY_FPL_LIGHT_PURPLE
            label.color = KIVY_FPL_WHITE

        with self.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*bg_color)
            self.rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[15, 15, 15, 15])

        self.bind(pos=self.update_rect, size=self.update_rect)
        self.add_widget(label)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

class FplChatbotLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10
        self.chat_history = []
        self.fpl_user_id = None
        self.google_api_key = None
        self.thinking_bubble_container = None

        header = BoxLayout(size_hint=(1, None), height=50)
        header.add_widget(Label(text='FPL AI Assistant', font_size='24sp', bold=True, color=KIVY_FPL_WHITE))
        self.add_widget(header)

        self.scroll_view = ScrollView(size_hint=(1, 1))
        self.chat_display = BoxLayout(orientation='vertical', size_hint_y=None, spacing=15, padding=[10, 10])
        self.chat_display.bind(minimum_height=self.chat_display.setter('height'))
        self.scroll_view.add_widget(self.chat_display)
        self.add_widget(self.scroll_view)

        input_layout = BoxLayout(size_hint=(1, None), height=50, spacing=10)
        self.text_input = TextInput(
            hint_text='Ask a question...', multiline=False, background_color=KIVY_FPL_LIGHT_PURPLE,
            foreground_color=KIVY_FPL_WHITE, cursor_color=KIVY_FPL_GREEN,
            hint_text_color=(1,1,1,0.5), font_size='16sp', padding=[15, 15, 15, 15]
        )
        self.text_input.bind(on_text_validate=self.send_message)
        self.send_button = Button(
            text='Send', size_hint_x=None, width=100, background_color=KIVY_FPL_GREEN,
            color=KIVY_FPL_BLACK, bold=True, background_normal='', background_down=''
        )
        self.send_button.bind(on_press=self.send_message)
        input_layout.add_widget(self.text_input)
        input_layout.add_widget(self.send_button)
        self.add_widget(input_layout)

    def add_message(self, author, text):
        """Adds a message to the chat display."""
        container = BoxLayout(size_hint_y=None)
        container.bind(minimum_height=container.setter('height'))
        bubble = ChatBubble(text=f"[b]{author.capitalize()}:[/b] {text}", author=author)
        if author == 'user':
            container.add_widget(Widget(size_hint_x=0.25))
            container.add_widget(bubble)
        else:
            container.add_widget(bubble)
            container.add_widget(Widget(size_hint_x=0.25))
        self.chat_display.add_widget(container)
        if text == "Thinking...":
            self.thinking_bubble_container = container
        Clock.schedule_once(lambda dt: setattr(self.scroll_view, 'scroll_y', 0), 0.1)

    def send_message(self, instance):
        """Handles sending a message from the user."""
        user_query = self.text_input.text
        if not user_query: return
        self.add_message("user", user_query)
        self.text_input.text = ""
        self.chat_history.append({"role": "user", "parts": [{"text": user_query}]})
        self.send_button.disabled = True
        self.text_input.disabled = True
        self.add_message("ai", "Thinking...")
        threading.Thread(target=self.run_chatbot_logic, args=(user_query,), daemon=True).start()

    def run_chatbot_logic(self, user_query):
        """Orchestrates the AI response logic."""
        response = backend.get_chatbot_response(self.google_api_key, self.fpl_user_id, user_query, self.chat_history)
        Clock.schedule_once(partial(self.update_ui_with_response, response))

    def update_ui_with_response(self, response, dt):
        """Updates the UI with the AI's response."""
        if self.thinking_bubble_container:
            self.chat_display.remove_widget(self.thinking_bubble_container)
            self.thinking_bubble_container = None
        self.add_message("ai", response)
        self.chat_history.append({"role": "model", "parts": [{"text": response}]})
        self.send_button.disabled = False
        self.text_input.disabled = False
        self.text_input.focus = True

class FplChatbotApp(App):
    def build(self):
        self.title = 'FPL AI Assistant'
        Window.clearcolor = KIVY_FPL_DARK_PURPLE
        self.layout = FplChatbotLayout()
        return self.layout

    def on_start(self):
        self.get_user_config()

    def get_user_config(self):
        """Loads user config or prompts for it."""
        config = backend.load_user_config()
        fpl_id = config.get("FPL_USER_ID")
        api_key = config.get("GOOGLE_API_KEY")
        needs_save = False

        if not fpl_id:
            needs_save = True
            fpl_id = self.show_config_popup("Enter FPL User ID:", "Find this on the FPL website's 'Points' page URL.")
            if not fpl_id: self.stop()
            config["FPL_USER_ID"] = fpl_id

        if not api_key:
            needs_save = True
            api_key = self.show_config_popup("Enter Google API Key:", "Get a free key from Google AI Studio.")
            if not api_key: self.stop()
            config["GOOGLE_API_KEY"] = api_key

        if needs_save:
            backend.save_user_config(config)

        self.layout.fpl_user_id = fpl_id
        self.layout.google_api_key = api_key
        self.layout.add_message("ai", "Alright? How can I help with your FPL team?")

    def show_config_popup(self, title, content_text):
        """Helper to create a text input popup."""
        input_text = TextInput(multiline=False, background_color=KIVY_FPL_WHITE, foreground_color=KIVY_FPL_BLACK)
        content_label = WrappedLabel(text=content_text, color=KIVY_FPL_BLACK)
        submit_button = Button(text='Save', background_color=KIVY_FPL_GREEN, color=KIVY_FPL_BLACK, bold=True, background_normal='')
        
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        with popup_layout.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*KIVY_FPL_GREY)
            self.rect = RoundedRectangle(size=popup_layout.size, pos=popup_layout.pos)
        popup_layout.bind(pos=lambda *x: setattr(self.rect, 'pos', popup_layout.pos), size=lambda *x: setattr(self.rect, 'size', popup_layout.size))

        popup_layout.add_widget(content_label)
        popup_layout.add_widget(input_text)
        popup_layout.add_widget(submit_button)
        
        popup = Popup(title=title, content=popup_layout, size_hint=(0.9, 0.5), auto_dismiss=False, title_color=KIVY_FPL_DARK_PURPLE, separator_color=KIVY_FPL_GREEN)
        
        result = [None]
        def on_submit(instance):
            result[0] = input_text.text.strip()
            popup.dismiss()
        
        submit_button.bind(on_press=on_submit)
        
        from kivy.base import EventLoop
        EventLoop.window.add_widget(popup)
        popup.open()
        while popup.parent:
            EventLoop.idle()
        
        return result[0]

def run():
    FplChatbotApp().run()

if __name__ == '__main__':
    run()
