"""Database management for Beathoven"""
import os
import sqlite3
from datetime import datetime
import logging
from typing import Optional, List
import dotenv
from models import Track, Playlist

# Load environment variables from .env file in PWD
dotenv.load_dotenv(os.path.join(os.getcwd(), '.env'), override=True)

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        
        # Get database path from environment
        self.db_path = os.getenv('BEATHOVEN_DB')
        if not self.db_path:
            raise ValueError("BEATHOVEN_DB environment variable not set")
        
        # Initialize database immediately
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema"""
        logger.info(f"Initializing database at {self.db_path}")
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                
                # Create migrations table first
                c.execute('''
                    CREATE TABLE IF NOT EXISTS migrations (
                        source_dir TEXT PRIMARY KEY,
                        migrated_at TIMESTAMP NOT NULL,
                        num_playlists INTEGER NOT NULL,
                        num_tracks INTEGER NOT NULL
                    )
                ''')
                
                # Create playlists table with all required fields
                c.execute('''
                    CREATE TABLE IF NOT EXISTS playlists (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        type TEXT NOT NULL DEFAULT 'local',
                        description TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create tracks table with required metadata
                c.execute('''
                    CREATE TABLE IF NOT EXISTS tracks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        title TEXT NOT NULL,
                        artist TEXT DEFAULT 'Unknown',
                        duration INTEGER DEFAULT 0,
                        type TEXT NOT NULL DEFAULT 'local',
                        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        thumbnail_url TEXT,
                        last_played_at TIMESTAMP,
                        play_count INTEGER DEFAULT 0,
                        UNIQUE(url, type)
                    )
                ''')
                
                # Create playlist_tracks junction table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS playlist_tracks (
                        playlist_id INTEGER,
                        track_id INTEGER,
                        position INTEGER NOT NULL,
                        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE,
                        FOREIGN KEY (track_id) REFERENCES tracks (id) ON DELETE CASCADE,
                        PRIMARY KEY (playlist_id, track_id)
                    )
                ''')
                
                conn.commit()
                logger.info("Database schema initialized successfully")
                
                # Verify tables exist
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in c.fetchall()]
                logger.info(f"Existing tables: {', '.join(tables)}")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def add_playlist(self, playlist: Playlist) -> int:
        """Add a playlist to the database"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            now = datetime.now()
            
            # Insert playlist
            c.execute('''
                INSERT INTO playlists (name, type, description, created_at, modified_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (playlist.name, playlist.type, playlist.description, 
                  playlist.created_at or now, playlist.modified_at or now))
            
            playlist_id = c.lastrowid
            
            # Add tracks
            for i, track in enumerate(playlist.tracks):
                # First add/update track
                c.execute('''
                    INSERT INTO tracks (url, title, artist, duration, type, added_at, thumbnail_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url, type) DO UPDATE SET
                        title=excluded.title,
                        artist=excluded.artist,
                        duration=excluded.duration,
                        thumbnail_url=excluded.thumbnail_url
                    RETURNING id
                ''', (track.url, track.title, track.artist, track.duration,
                      track.type, track.added_at or now, track.thumbnail_url))
                track_id = c.fetchone()[0]
                
                # Then add to playlist_tracks
                c.execute('''
                    INSERT INTO playlist_tracks (playlist_id, track_id, position, added_at)
                    VALUES (?, ?, ?, ?)
                ''', (playlist_id, track_id, i, now))
            
            conn.commit()
            return playlist_id
    
    def update_playlist(self, playlist: Playlist) -> bool:
        """Update an existing playlist"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            
            # Get playlist ID
            c.execute('SELECT id FROM playlists WHERE name = ?', (playlist.name,))
            row = c.fetchone()
            if not row:
                return False
                
            playlist_id = row[0]
            now = datetime.now()
            
            # Update playlist metadata
            c.execute('''
                UPDATE playlists 
                SET type = ?, description = ?, modified_at = ?
                WHERE id = ?
            ''', (playlist.type, playlist.description, now, playlist_id))
            
            # Remove existing tracks
            c.execute('DELETE FROM playlist_tracks WHERE playlist_id = ?', (playlist_id,))
            
            # Add new tracks
            for i, track in enumerate(playlist.tracks):
                c.execute('''
                    INSERT INTO tracks (url, title, artist, duration, type, added_at, thumbnail_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url, type) DO UPDATE SET
                        title=excluded.title,
                        artist=excluded.artist,
                        duration=excluded.duration,
                        thumbnail_url=excluded.thumbnail_url
                    RETURNING id
                ''', (track.url, track.title, track.artist, track.duration,
                      track.type, track.added_at or now, track.thumbnail_url))
                track_id = c.fetchone()[0]
                
                c.execute('''
                    INSERT INTO playlist_tracks (playlist_id, track_id, position, added_at)
                    VALUES (?, ?, ?, ?)
                ''', (playlist_id, track_id, i, now))
            
            conn.commit()
            return True
    
    def delete_playlist(self, name: str) -> bool:
        """Delete a playlist"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM playlists WHERE name = ?', (name,))
            deleted = c.rowcount > 0
            conn.commit()
            return deleted
    
    def get_playlist(self, name: str) -> Optional[Playlist]:
        """Get a playlist by name"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            
            # Get playlist info
            c.execute('''
                SELECT id, type, description, created_at, modified_at
                FROM playlists WHERE name = ?
            ''', (name,))
            row = c.fetchone()
            if not row:
                return None
                
            playlist_id, ptype, desc, created, modified = row
            
            # Get tracks
            c.execute('''
                SELECT t.url, t.title, t.artist, t.duration, t.type, t.added_at, t.thumbnail_url
                FROM tracks t
                JOIN playlist_tracks pt ON pt.track_id = t.id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position
            ''', (playlist_id,))
            
            tracks = []
            for row in c.fetchall():
                url, title, artist, duration, ttype, added, thumb = row
                tracks.append(Track(
                    url=url,
                    title=title,
                    artist=artist,
                    duration=duration,
                    type=ttype,
                    added_at=datetime.fromisoformat(added) if added else None,
                    thumbnail_url=thumb
                ))
            
            return Playlist(
                name=name,
                tracks=tracks,
                type=ptype,
                description=desc,
                created_at=datetime.fromisoformat(created) if created else None,
                modified_at=datetime.fromisoformat(modified) if modified else None
            )
    
    def get_all_playlists(self) -> List[Playlist]:
        """Get all playlists"""
        playlists = []
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT name FROM playlists ORDER BY name')
            for (name,) in c.fetchall():
                playlist = self.get_playlist(name)
                if playlist:
                    playlists.append(playlist)
        return playlists
    
    def update_track_play(self, track_url: str, track_type: str):
        """Update track play count and last played time"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE tracks 
                SET play_count = play_count + 1,
                    last_played_at = ?
                WHERE url = ? AND type = ?
            ''', (datetime.now(), track_url, track_type))
            conn.commit()
    
    def migrate_from_files(self, playlist_dir: str):
        """Migrate playlists from flat files to database"""
        # Check if already migrated
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT migrated_at FROM migrations WHERE source_dir = ?', (playlist_dir,))
            if c.fetchone():
                logger.info(f"Playlists from {playlist_dir} already migrated, skipping...")
                return

        logger.info(f"Migrating playlists from {playlist_dir}")
        
        # Map extensions to playlist types
        ext_to_type = {
            '.blp': 'local',    # Beathoven Local Playlist
            '.byp': 'youtube',  # Beathoven YouTube Playlist
            '.brp': 'radio'     # Beathoven Radio Playlist
        }
        
        total_playlists = 0
        total_tracks = 0
        
        for filename in os.listdir(playlist_dir):
            file_path = os.path.join(playlist_dir, filename)
            if os.path.isfile(file_path):
                ext = os.path.splitext(filename)[1].lower()
                name = os.path.splitext(filename)[0]
                if ext in ext_to_type:
                    try:
                        logger.info(f"Migrating playlist: {filename}")
                        tracks = []
                        with open(file_path, 'r') as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    tracks.append(Track(
                                        title=os.path.splitext(os.path.basename(line))[0],
                                        url=line,
                                        type=ext_to_type[ext]
                                    ))
                        
                        if tracks:  # Only create playlist if it has tracks
                            playlist = Playlist(
                                name=name,
                                tracks=tracks,
                                type=ext_to_type[ext]
                            )
                            self.add_playlist(playlist)
                            total_playlists += 1
                            total_tracks += len(tracks)
                            logger.info(f"Successfully migrated playlist: {name} with {len(tracks)} tracks")
                    except Exception as e:
                        logger.error(f"Error migrating playlist {filename}: {e}")
        
        # Record successful migration with stats
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                'INSERT INTO migrations (source_dir, migrated_at, num_playlists, num_tracks) VALUES (?, ?, ?, ?)',
                (playlist_dir, datetime.now(), total_playlists, total_tracks)
            )
            conn.commit()
            
        logger.info(f"Migration complete. Imported {total_playlists} playlists with {total_tracks} tracks total")
