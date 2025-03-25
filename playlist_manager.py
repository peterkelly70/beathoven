"""
PlaylistManager - Handles playlist operations and state management
"""
import os
import logging
from typing import Dict, List, Optional
import dotenv
from models import Playlist, Track
from datetime import datetime
from database import Database

logger = logging.getLogger(__name__)

class PlaylistManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PlaylistManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        
        # Load environment variables
        dotenv.load_dotenv()
        
        # Initialize database
        self.db = Database()
        
        # State
        self.current_playlist: Optional[str] = None
        self.current_track_index: int = 0
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.volume: int = 100
        self.repeat_mode: str = "none"  # none, one, all
        
        # Check for playlists to migrate
        playlist_dir = os.getenv('PLAYLIST_DIR')
        if playlist_dir and os.path.exists(playlist_dir):
            self.db.migrate_from_files(playlist_dir)
    
    def get_all_playlists(self) -> List[Playlist]:
        """Get all playlists"""
        return self.db.get_all_playlists()
    
    def get_playlist(self, name: str) -> Optional[Playlist]:
        """Get a playlist by name"""
        return self.db.get_playlist(name)
    
    def create_playlist(self, name: str, tracks: List[Track] = None, playlist_type: str = "local", description: str = "") -> Optional[Playlist]:
        """Create a new playlist"""
        if self.get_playlist(name):
            return None
            
        playlist = Playlist(
            name=name,
            tracks=tracks or [],
            type=playlist_type,
            description=description,
            created_at=datetime.now(),
            modified_at=datetime.now()
        )
        
        self.db.add_playlist(playlist)
        return playlist
    
    def delete_playlist(self, name: str) -> bool:
        """Delete a playlist"""
        if self.current_playlist == name:
            self.current_playlist = None
            self.current_track_index = 0
            self.is_playing = False
            self.is_paused = False
            
        return self.db.delete_playlist(name)
    
    def add_track(self, playlist_name: str, track: Track) -> bool:
        """Add track to playlist"""
        playlist = self.get_playlist(playlist_name)
        if not playlist:
            return False
            
        playlist.tracks.append(track)
        return self.db.update_playlist(playlist)
    
    def remove_track(self, playlist_name: str, index: int) -> bool:
        """Remove track from playlist"""
        playlist = self.get_playlist(playlist_name)
        if not playlist or index >= len(playlist.tracks):
            return False
            
        if self.current_playlist == playlist_name and index == self.current_track_index:
            self.is_playing = False
            self.is_paused = False
            
        playlist.tracks.pop(index)
        return self.db.update_playlist(playlist)
    
    def move_track(self, playlist_name: str, old_index: int, new_index: int) -> bool:
        """Move track within playlist"""
        playlist = self.get_playlist(playlist_name)
        if not playlist or old_index >= len(playlist.tracks) or new_index >= len(playlist.tracks):
            return False
            
        track = playlist.tracks.pop(old_index)
        playlist.tracks.insert(new_index, track)
        
        if self.current_playlist == playlist_name:
            if old_index == self.current_track_index:
                self.current_track_index = new_index
            elif old_index < self.current_track_index <= new_index:
                self.current_track_index -= 1
            elif old_index > self.current_track_index >= new_index:
                self.current_track_index += 1
                
        return self.db.update_playlist(playlist)
    
    def get_current_track(self) -> Optional[Track]:
        """Get current track"""
        if not self.current_playlist:
            return None
            
        playlist = self.get_playlist(self.current_playlist)
        if not playlist or not playlist.tracks:
            return None
            
        if self.current_track_index >= len(playlist.tracks):
            self.current_track_index = 0
            
        track = playlist.tracks[self.current_track_index]
        self.db.update_track_play(track.url, track.type)
        return track
    
    def set_current_playlist(self, name: str) -> bool:
        """Set current playlist"""
        if not self.get_playlist(name):
            return False
            
        self.current_playlist = name
        self.current_track_index = 0
        self.is_playing = False
        self.is_paused = False
        return True
    
    def set_track_index(self, index: int) -> Optional[Track]:
        """Set current track index"""
        if not self.current_playlist:
            return None
            
        playlist = self.get_playlist(self.current_playlist)
        if not playlist or not playlist.tracks:
            return None
            
        if 0 <= index < len(playlist.tracks):
            self.current_track_index = index
            return playlist.tracks[index]
            
        return None
    
    def set_playing(self, playing: bool) -> None:
        """Set playing state"""
        self.is_playing = playing
        if playing:
            self.is_paused = False  # Can't be playing and paused
            
    def set_paused(self, paused: bool) -> None:
        """Set paused state"""
        self.is_paused = paused
        if paused:
            self.is_playing = False  # Can't be playing and paused
            
    def set_volume(self, volume: int) -> None:
        """Set volume (0-100)"""
        self.volume = max(0, min(100, volume))
        
    def set_repeat_mode(self, mode: str) -> None:
        """Set repeat mode (none, one, all)"""
        if mode in ["none", "one", "all"]:
            self.repeat_mode = mode
            
    def _update_playback_state(self, track: Optional[Track] = None) -> Optional[Track]:
        """Update playback state after track change"""
        if track is None:
            self.is_playing = False
            self.is_paused = False
            return None
        
        # Keep playing if we were playing
        if self.is_playing and not self.is_paused:
            self.is_playing = True
            self.is_paused = False
            
        return track
    
    def next_track(self) -> Optional[Track]:
        """Get next track"""
        if not self.current_playlist:
            return self._update_playback_state(None)
            
        playlist = self.get_playlist(self.current_playlist)
        if not playlist or not playlist.tracks:
            return self._update_playback_state(None)
            
        if self.repeat_mode == "one":
            return self._update_playback_state(self.get_current_track())
            
        self.current_track_index += 1
        if self.current_track_index >= len(playlist.tracks):
            if self.repeat_mode == "all":
                self.current_track_index = 0
            else:
                self.current_track_index = len(playlist.tracks) - 1
                return self._update_playback_state(None)
                
        return self._update_playback_state(self.get_current_track())
    
    def previous_track(self) -> Optional[Track]:
        """Get previous track"""
        if not self.current_playlist:
            return self._update_playback_state(None)
            
        playlist = self.get_playlist(self.current_playlist)
        if not playlist or not playlist.tracks:
            return self._update_playback_state(None)
            
        if self.repeat_mode == "one":
            return self._update_playback_state(self.get_current_track())
            
        self.current_track_index -= 1
        if self.current_track_index < 0:
            if self.repeat_mode == "all":
                self.current_track_index = len(playlist.tracks) - 1
            else:
                self.current_track_index = 0
                return self._update_playback_state(None)
                
        return self._update_playback_state(self.get_current_track())
