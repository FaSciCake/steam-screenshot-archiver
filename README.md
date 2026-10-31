# Steam Screenshot Archiver

Save your Steam screenshots to your computer in one go.

The tool downloads the screenshots Steam makes available for your profile, sorts them into folders by game, and remembers what it has already downloaded. You can run it again later to pick up anything new.

## Getting started (Windows)

1. **Install Python.** Download Python 3.10 or newer from [python.org](https://www.python.org/downloads/). During installation, enable the option to add Python to PATH if the installer offers it.
2. **Download this project.** On this GitHub page, click the green **Code** button, then **Download ZIP**. Extract the ZIP somewhere you can find it.
3. **Run the tool.** Open the extracted folder and double-click `run_downloader.bat`.
4. **Enter your Steam details.** The tool will ask for your Steam Web API key and your Steam profile link or SteamID64.

The first launch creates a private Python environment in the project folder and installs the required package there. You don't need to set that up yourself.

## Getting a Steam Web API key

1. Open [Steam's API key page](https://steamcommunity.com/dev/apikey) and sign in.
2. Register a key. For the domain, you can enter `ilovecakes` or whatever that works!
3. Copy the key into the tool when it asks.

Your key is entered privately and is **not saved by this program**. Don't share it with anyone or post it online.

You can enter your Steam profile URL (for example, `https://steamcommunity.com/profiles/...` or `https://steamcommunity.com/id/...`) or your SteamID64.

## Where are my screenshots?

By default, they're saved in a folder named `SteamScreenshotArchive` inside the project folder. Each game gets its own folder. The `manifest.json` file keeps track of downloaded screenshots so the next run can skip them and retry failed downloads.

Keep the manifest with your screenshots if you want to use this tool again soon - or else the script loses its download history.

## A couple of things to know

- Steam only provides screenshots that are still available through its API. Deleted or inaccessible screenshots can't be recovered by this tool.
- File dates use the timestamp Steam provides for the published screenshot. This may differ from when the screenshot was originally taken.
- Your screenshots stay on your computer; this tool downloads them directly from Steam.

## Running it manually (optional)

If you prefer using a terminal, open the project folder in PowerShell and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe steam_screenshot_archiver.py
```

The `.venv` folder contains this project's dependencies and is safe to delete if you want to start the environment setup again. Your downloaded screenshots are stored separately.
