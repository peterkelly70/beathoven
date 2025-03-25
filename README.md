# Beathoven
A Discord music bot with web interface (v0.3)

## Architecture
Beathoven uses a modular architecture with three main components:

1. **PlaylistManager** (playlist_manager.py)
   - Core component that handles playlist operations and state management
   - Implements Singleton pattern to ensure single source of truth
   - Manages playlists, tracks, playback state, and volume

2. **DiscordBot** (discord_bot.py)
   - Handles Discord interactions and music playback
   - Uses PlaylistManager for playlist/track management
   - Provides Discord commands for controlling playback

3. **WebUI** (web_ui.py)
   - Provides web interface for playlist and playback control
   - Uses PlaylistManager for playlist/track management
   - Offers modern Bootstrap UI with real-time updates via WebSocket

The main script (beathoven.py) coordinates these components.

## Setup
1. Clone the repo:
   ```bash
   git clone https://github.com/peterkelly70/beathoven.git
   cd beathoven
   ```

2. Create and configure environment:
   ```bash
   # Create virtual environment
   python3 -m venv botenv
   # Or with conda: conda create -n botenv python=3.8

   # Activate virtual environment
   source botenv/bin/activate  # On Windows: .\botenv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt

   # Create .env file with required variables
   touch .env
   ```

3. Configure .env file:
   ```
   DISCORD_BOT_TOKEN='YOUR_DISCORD_TOKEN'
   PLAYLIST_DIR='/path/to/playlists'
   ```

4. Run the bot:
   ```bash
   chmod +x beathoven.py
   ./beathoven.py
   ```

## Discord Commands
- `!join` - Join voice channel
- `!leave` - Leave voice channel
- `!play <name/url>` - Play playlist or track
- `!pause` - Pause playback
- `!resume` - Resume playback
- `!stop` - Stop playback
- `!next` - Skip to next track
- `!previous` - Go to previous track
- `!volume <0-100>` - Set volume

## Web Interface
The web interface is available at http://localhost:5000 and provides:
- Playlist management (create, edit, delete)
- Track management (add, remove, reorder)
- Playback controls (play, pause, stop, next, previous)
- Real-time status updates

## Development
- Python 3.8+
- Ubuntu 22.04 recommended
- Uses discord.py for Discord integration
- Flask + Socket.IO for web interface
- Bootstrap for UI styling

## To Do
- Make the bot a systemd service
- Add playlist import/export
- Support more audio sources
- Improve error handling

## Credits
Originally developed by Peter Kelly. Uses ChatGPT and CodeGPT for boilerplate code and Discord.py learning.
