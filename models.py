"""
Models for Beathoven music bot
"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Track:
    """Model representing a music track"""
    title: str
    url: str
    duration: Optional[int] = None  # Duration in seconds
    type: str = "youtube"  # youtube, spotify, local, etc.
    added_at: datetime = field(default_factory=datetime.now)
    artist: Optional[str] = None
    thumbnail_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert track to dictionary for JSON serialization"""
        return {
            "title": self.title,
            "url": self.url,
            "duration": self.duration,
            "type": self.type,
            "added_at": self.added_at.isoformat(),
            "artist": self.artist,
            "thumbnail_url": self.thumbnail_url
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Track':
        """Create track from dictionary"""
        if "added_at" in data and isinstance(data["added_at"], str):
            data["added_at"] = datetime.fromisoformat(data["added_at"])
        return cls(**data)

@dataclass
class Playlist:
    """Model representing a playlist"""
    name: str
    tracks: List[Track] = field(default_factory=list)
    type: str = "local"  # local, youtube, spotify, etc.
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    
    def add_track(self, track: Track) -> None:
        """Add track to playlist"""
        self.tracks.append(track)
        self.modified_at = datetime.now()
    
    def remove_track(self, index: int) -> Optional[Track]:
        """Remove track from playlist by index"""
        if 0 <= index < len(self.tracks):
            track = self.tracks.pop(index)
            self.modified_at = datetime.now()
            return track
        return None
    
    def move_track(self, old_index: int, new_index: int) -> bool:
        """Move track from old_index to new_index"""
        if 0 <= old_index < len(self.tracks) and 0 <= new_index < len(self.tracks):
            track = self.tracks.pop(old_index)
            self.tracks.insert(new_index, track)
            self.modified_at = datetime.now()
            return True
        return False
    
    def clear(self) -> None:
        """Clear all tracks from playlist"""
        self.tracks.clear()
        self.modified_at = datetime.now()
    
    def to_dict(self) -> dict:
        """Convert playlist to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "tracks": [track.to_dict() for track in self.tracks],
            "type": self.type,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Playlist':
        """Create playlist from dictionary"""
        tracks_data = data.pop("tracks", [])
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "modified_at" in data and isinstance(data["modified_at"], str):
            data["modified_at"] = datetime.fromisoformat(data["modified_at"])
            
        playlist = cls(**data)
        playlist.tracks = [Track.from_dict(track) for track in tracks_data]
        return playlist
