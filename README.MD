# FPL AI Assistant Chatbot

This is a standalone application that uses AI to give you personalised advice about your Fantasy Premier League (FPL) team. This project supports building for both Desktop (Mac/Windows) and Android.

---

## For the User: How to Install and Run

1.  **Download the Application:** Download the correct file for your operating system (`.app` for Mac, `.exe` for Windows, or `.apk` for Android).
2.  **Run the Application:** Install and run the application. A chat window will open.
3.  **First-Time Setup:** The first time you run the app, it will ask for your FPL User ID and your Google API Key. The application will save these details securely, so you only need to enter them once.
4.  **Start Chatting!** The assistant is now ready.

---

## For the Developer: How to Build the Application

This project has two separate frontends: one for desktop and one for Android.

### Step 1: Install All Dependencies
1.  Open your Terminal or Command Prompt.
2.  Navigate into the main project folder.
3.  Run the command:
    ```bash
    pip install -r requirements.txt
    ```

### Step 2: Build the Desktop Application (Mac/Windows)
This uses the `desktop_app.py` file and requires the `backend.py` and `constants.py` files.

1.  **Clean Project Files (Mac Only):** Before building, run the following command in your terminal from the root of your project folder. This removes problematic metadata that causes signing errors.
    ```bash
    xattr -cr .
    ```

2.  **Run the Build Command:** In your terminal, run the command for your operating system. The `--add-data` flag is crucial to include the backend and constants files, and `--hidden-import` forces PyInstaller to include packages it might miss.

    * **For Windows:**
        ```bash
        pyinstaller --windowed --name "FPL Chatbot" --add-data "fpl_chatbot\backend.py;." --add-data "fpl_chatbot\constants.py;." --hidden-import=requests --hidden-import=certifi fpl_chatbot\desktop_app.py
        ```
    * **For Mac:**
        ```bash
        pyinstaller --windowed --name "FPL Chatbot" --add-data "fpl_chatbot/backend.py:." --add-data "fpl_chatbot/constants.py:." --hidden-import=requests --hidden-import=certifi fpl_chatbot/desktop_app.py
        ```

3.  The final application will be in the `dist` folder.

### Step 3: Build the Android Application (APK)
This uses the `android_app.py` file and requires a tool called `buildozer`.

#### **Android Build Prerequisites (macOS)**
Before your first build, you must install the required dependencies using Homebrew.

1.  **Install Build Tools:** Open your terminal and run the following command. This will install all the necessary command-line tools for the build process.
    ```bash
    brew install autoconf automake libtool pkg-config cmake openssl@1.1
    ```
2.  **Install a Compatible Java Development Kit (JDK):** Buildozer now requires JDK 17. Run this command to install it:
    ```bash
    brew install openjdk@17
    ```
3.  **Set the `JAVA_HOME` Path:** You need to tell your system where to find this new JDK. Run the following command in your terminal:
    ```bash
    echo 'export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"' >> ~/.zshrc
    ```
4.  **Load the New Configuration:** To apply the change to your current terminal session, run this command:
    ```bash
    source ~/.zshrc
    ```
5.  **Verification:** Now, run `echo $JAVA_HOME`. It should print the correct path. If it does, you are ready to build.

#### **Troubleshooting the `source` command**
If you see an error like `not an identifier` after running the `source ~/.zshrc` command, it means your `.zshrc` file has a syntax error. To fix this safely, run the following two commands in your terminal:
1.  First, back up your old file:
    ```bash
    mv ~/.zshrc ~/.zshrc.bak
    ```
2.  Then, create a new, clean `.zshrc` file with the correct command:
    ```bash
    echo 'export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"' >> ~/.zshrc
    ```
3.  Now, try running `source ~/.zshrc` again. It should work without any errors.

#### **Buildozer Configuration and Build**
1.  **Install Buildozer:**
    ```bash
    pip install buildozer
    ```
2.  **Initialise Buildozer:** In your project's root directory, run:
    ```bash
    buildozer init
    ```
    This creates a `buildozer.spec` file.

3.  **Configure `buildozer.spec`:**
    * Open `buildozer.spec`.
    * Find the line `title = Your application name` and change it to `title = FPL Chatbot`.
    * Find `source.dir = .` and change it to `source.dir = fpl_chatbot`.
    * **Add the following line directly below `source.dir`:**
        ```
        source.main_py = android_app.py
        ```
    * Find the `requirements` line and change it to include all necessary build dependencies:
        ```
        requirements = python3,kivy,requests,certifi,cython,pyjnius
        ```
    * Add the `INTERNET` permission: `android.permissions = INTERNET`.
    * **Add the following line to use the latest development branch for Android dependencies:**
        ```
        p4a.branch = develop
        ```

4.  **Run the Build:**
    This command now explicitly tells buildozer where to find the correct Java version, making it more reliable.
    ```bash
    buildozer -v android debug
    ```
    The final `.apk` file will be in the `bin` directory.

