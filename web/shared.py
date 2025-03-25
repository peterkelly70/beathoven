"""Shared functionality between bot and web app"""
import os
import discord
from discord.ext import commands
from typing import Dict, Any, Optional
import json
import time

# Simple state enums as strings to avoid serialization issues
PLAYER_STATE = {
    'IDLE': 'idle',
    'LOADED': 'loaded',
    'PLAYING': 'playing',
    'PAUSED': 'paused'
}

REPEAT_MODE = {
    'NONE': 'none',
    'SONG': 'song',
    'PLAYLIST': 'playlist'
}

class Player:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = PLAYER_STATE['IDLE']
        self.repeat_mode = REPEAT_MODE['NONE']
        self.volume = 100
        self.current_playlist = None
        self.current_track_index = None
        self.current_track = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'state': self.state,
            'playing': self.state == PLAYER_STATE['PLAYING'],
            'repeat': self.repeat_mode,
            'volume': self.volume,
            'current_playlist': self.current_playlist,
            'current_track': self.current_track,
            'current_track_index': self.current_track_index
        }
        
    def load_playlist(self, playlist_name: str) -> None:
        """Load a playlist"""
        self.current_playlist = playlist_name
        self.current_track_index = 0
        self.current_track = None
        self.state = PLAYER_STATE['LOADED']
        
    def play(self, track_index: Optional[int] = None) -> None:
        """Start or resume playback"""
        if track_index is not None:
            self.current_track_index = track_index
        self.state = PLAYER_STATE['PLAYING']
        
    def pause(self) -> None:
        """Pause playback"""
        if self.state == PLAYER_STATE['PLAYING']:
            self.state = PLAYER_STATE['PAUSED']
            
    def resume(self) -> None:
        """Resume playback"""
        if self.state == PLAYER_STATE['PAUSED']:
            self.state = PLAYER_STATE['PLAYING']
            
    def stop(self) -> None:
        """Stop playback"""
        if self.state in (PLAYER_STATE['PLAYING'], PLAYER_STATE['PAUSED']):
            self.state = PLAYER_STATE['LOADED']
            
    def next_track(self) -> None:
        """Move to next track"""
        if self.current_track_index is not None:
            self.current_track_index += 1
            
    def previous_track(self) -> None:
        """Move to previous track"""
        if self.current_track_index is not None and self.current_track_index > 0:
            self.current_track_index -= 1
            
    def set_volume(self, volume: int) -> None:
        """Set volume level"""
        self.volume = max(0, min(100, volume))
        
    def set_repeat_mode(self, mode: str) -> None:
        """Set repeat mode"""
        if mode == 'none':
            self.repeat_mode = REPEAT_MODE['NONE']
        elif mode == 'song':
            self.repeat_mode = REPEAT_MODE['SONG']
        elif mode == 'playlist':
            self.repeat_mode = REPEAT_MODE['PLAYLIST']
        
    def toggle_repeat(self, mode: str = None) -> None:
        """Toggle between repeat modes or set a specific mode
        
        Args:
            mode (str, optional): The repeat mode to set. Can be 'none', 'song', or 'list'.
                If not provided, will cycle between modes.
        """
        if mode:
            self.set_repeat_mode(mode)
        else:
            # Cycle to next mode if no specific mode provided
            if self.repeat_mode == REPEAT_MODE['NONE']:
                self.repeat_mode = REPEAT_MODE['SONG']
            elif self.repeat_mode == REPEAT_MODE['SONG']:
                self.repeat_mode = REPEAT_MODE['PLAYLIST']
            else:
                self.repeat_mode = REPEAT_MODE['NONE']

class SessionManager:
    def __init__(self):
        self.sessions = {}  # session_id -> {guild_id, created_at}
        self.players = {}   # session_id -> Player
        self.guild_data = {} # guild_id -> {playlists: []}
        self.load_sessions()
    
    def create_session(self, guild_id: str) -> str:
        """Create a new session for a guild"""
        from uuid import uuid4
        session_id = str(uuid4())[:8]
        
        self.sessions[session_id] = {
            'guild_id': str(guild_id),
            'created_at': time.time()
        }
        
        self.players[session_id] = Player(session_id)
        
        if str(guild_id) not in self.guild_data:
            self.guild_data[str(guild_id)] = {'playlists': []}
            
        self.save_sessions()
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data if it exists and is not expired"""
        if session_id not in self.sessions:
            return None
            
        session = self.sessions[session_id]
        if time.time() - session['created_at'] > 3600:  # 1 hour expiration
            self.delete_session(session_id)
            return None
            
        return session
    
    def get_player(self, session_id: str) -> Optional[Player]:
        """Get player for a session"""
        return self.players.get(session_id)

    def create_player(self, session_id: str) -> Optional[Player]:
        """Create a new player for a session"""
        if session_id in self.sessions:
            self.players[session_id] = Player(session_id)
            return self.players[session_id]
        return None

    def get_guild_data(self, guild_id: str) -> Dict:
        """Get guild data, creating if it doesn't exist"""
        if str(guild_id) not in self.guild_data:
            self.guild_data[str(guild_id)] = {'playlists': []}
        return self.guild_data[str(guild_id)]
    
    def save_guild_data(self, guild_id: str, data: dict) -> None:
        """Save guild data and persist to disk"""
        self.guild_data[str(guild_id)] = data
        self.save_sessions()
    
    def delete_session(self, session_id: str):
        """Delete a session and its associated data"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.players:
            del self.players[session_id]
        self.save_sessions()
    
    def save_sessions(self) -> None:
        """Save sessions to disk"""
        try:
            with open('sessions.json', 'w') as f:
                json.dump(self.sessions, f)
        except Exception as e:
            print(f"Error saving sessions: {e}")
    
    def load_sessions(self):
        """Load sessions from disk"""
        try:
            if os.path.exists('sessions.json'):
                with open('sessions.json', 'r') as f:
                    self.sessions = json.load(f)
                    
                # Recreate players for existing sessions
                for session_id in self.sessions:
                    if session_id not in self.players:
                        self.players[session_id] = Player(session_id)
        except Exception as e:
            print(f"Error loading sessions: {e}")

# Create global session manager
session_manager = SessionManager()

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def run_bot_command(guild_id, command_name, args=None):
    """Run a bot command programmatically from the web app
    
    Args:
        guild_id (int): Discord guild ID
        command_name (str): Name of the command to run
        args (list, optional): List of arguments to pass to the command
    """
    if args is None:
        args = []
        
    command = bot.get_command(command_name)
    if not command:
        raise ValueError(f"Command {command_name} not found")
        
    # Create a mock context for the command
    guild = bot.get_guild(guild_id)
    if not guild:
        raise ValueError(f"Guild {guild_id} not found")
        
    # We're creating a minimal mock context that has just what we need
    class MockContext:
        def __init__(self, guild):
            self.guild = guild
            self.voice_client = guild.voice_client
            self.bot = bot
            
    ctx = MockContext(guild)
    
    # Call the command
    return await command.callback(ctx, *args)
