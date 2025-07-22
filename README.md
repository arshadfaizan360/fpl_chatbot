# FPL AI Assistant Chatbot

This is a simple, standalone application that uses AI to give you personalised advice about your Fantasy Premier League (FPL) team.

---

## For the User: How to Install and Run

Follow these simple steps to get the chatbot running on your computer. No technical knowledge is needed!

### Step 1: Download and Run the Application
1.  Download the application file for your operating system (e.g., `fpl-chatbot.app` for Mac or `fpl-chatbot.exe` for Windows).
2.  On Mac, you may need to drag the `fpl-chatbot.app` file into your Applications folder.
3.  Double-click the application to run it. A chat window will open.

### Step 2: First-Time Setup
The first time you run the app, it will ask for two pieces of information in popup windows:

1.  **Your FPL User ID:** You can find this in the URL of the 'Points' page on the FPL website.
2.  **Your Google API Key:** You can get a free key from [Google AI Studio](https://aistudio.google.com/).

The application will save these details securely on your computer, so you will only need to enter them once.

### Step 3: Start Chatting!
That's it! The assistant is now ready. Type your questions into the input box and press 'Send'.

---

## For the Developer: How to Build the Application

Follow these steps to package the script into a distributable application.

### Step 1: Install Dependencies
1.  Open your computer's Terminal (on Mac) or Command Prompt (on Windows).
2.  Navigate into the main project folder using the `cd` command.
3.  Run the following command to install the necessary tools:
    ```bash
    pip install -r requirements.txt
    ```

### Step 2: Build the Application
1.  In the same terminal window, run the following command to build the application.

    * **For Windows (to hide the console window):**
        ```bash
        pyinstaller --windowed --name fpl-chatbot fpl_chatbot/main.py
        ```

    * **For Mac (using the recommended directory mode):**
        ```bash
        pyinstaller --windowed --name "FPL Chatbot" fpl_chatbot/main.py
        ```

2.  This command will create a `dist` folder. Inside this folder, you will find the final, standalone application bundle (e.g., `FPL Chatbot.app`). This is the file you can share with your users.

