"""Migrate playlists to database"""
import os
import sys
from pathlib import Path
import logging
import json
import dotenv
from database import Database
from models import Track, Playlist
import sqlite3
import yt_dlp
from mutagen import File
from mutagen.easyid3 import EasyID3

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_mp3_metadata(file_path):
    """Extract metadata from MP3 file using mutagen"""
    try:
        audio = File(file_path, easy=True)
        if audio is None:
            audio = EasyID3(file_path)
        
        # Extract duration
        duration = 0
        if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
            duration = int(audio.info.length)
        
        # Get basic metadata
        title = audio.get('title', [os.path.splitext(os.path.basename(file_path))[0]])[0]
        artist = audio.get('artist', ['Unknown'])[0]
        album = audio.get('album', ['Unknown'])[0]
        
        logger.info(f"Extracted metadata from {file_path}: {title} by {artist} ({duration}s)")
        
        return {
            'title': title,
            'artist': artist,
            'album': album,
            'duration': duration,
            'url': file_path,
            'thumbnail_url': None
        }
    except Exception as e:
        logger.warning(f"Error extracting metadata from {file_path}: {e}")
        return {
            'title': os.path.splitext(os.path.basename(file_path))[0],
            'artist': 'Unknown',
            'album': 'Unknown',
            'duration': 0,
            'url': file_path,
            'thumbnail_url': None
        }

def extract_url_metadata(url):
    """Extract metadata from URL using yt-dlp"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            duration = int(info.get('duration', 0))
            title = info.get('title', url)
            channel = info.get('channel', 'Unknown')
            thumbnail = info.get('thumbnail')
            
            logger.info(f"Extracted metadata from {url}: {title} by {channel} ({duration}s)")
            
            return {
                'title': title,
                'artist': channel,
                'duration': duration,
                'url': url,
                'thumbnail_url': thumbnail
            }
    except Exception as e:
        logger.warning(f"Error extracting metadata from URL {url}: {e}")
        return {
            'title': url,
            'artist': 'Unknown',
            'duration': 0,
            'url': url,
            'thumbnail_url': None
        }

def extract_radio_metadata(url):
    """Extract metadata from radio stream URL"""
    try:
        # For radio streams, we'll use the URL path as the title
        path = url.rstrip('/').split('/')[-1]
        title = path.replace('-', ' ').replace('_', ' ').title()
        
        logger.info(f"Extracted radio stream metadata: {title}")
        
        return {
            'title': title,
            'artist': 'Radio Stream',
            'duration': 0,  # Streams don't have duration
            'url': url,
            'thumbnail_url': None,
            'type': 'radio'
        }
    except Exception as e:
        logger.warning(f"Error extracting radio metadata from {url}: {e}")
        return {
            'title': url,
            'artist': 'Radio Stream',
            'duration': 0,
            'url': url,
            'thumbnail_url': None,
            'type': 'radio'
        }

def process_playlist(playlist_file):
    """Process a playlist file based on its extension"""
    playlist_name = playlist_file.stem
    extension = playlist_file.suffix.lower()
    
    tracks = []
    failed_tracks = 0
    
    try:
        with open(playlist_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            logger.info(f"Found {len(lines)} entries in {playlist_name}")
            
            for i, line in enumerate(lines, 1):
                logger.info(f"Processing track {i}/{len(lines)} in {playlist_name}")
                
                try:
                    if extension == '.blp':
                        # Local audio file
                        if not os.path.isabs(line):
                            # If path is relative, make it absolute from MUSIC_DIR
                            music_dir = os.getenv('MUSIC_DIR', '')
                            file_path = os.path.join(music_dir, line)
                        else:
                            file_path = line
                            
                        if not os.path.exists(file_path):
                            logger.warning(f"File not found: {file_path}")
                            failed_tracks += 1
                            continue
                            
                        metadata = extract_mp3_metadata(file_path)
                        track_type = 'local'
                        
                    elif extension == '.byp':
                        # YouTube video
                        if not (line.startswith('http://') or line.startswith('https://')):
                            logger.warning(f"Invalid YouTube URL: {line}")
                            failed_tracks += 1
                            continue
                            
                        metadata = extract_url_metadata(line)
                        track_type = 'youtube'
                        
                    elif extension == '.brp':
                        # Radio stream
                        if not (line.startswith('http://') or line.startswith('https://')):
                            logger.warning(f"Invalid radio stream URL: {line}")
                            failed_tracks += 1
                            continue
                            
                        metadata = extract_radio_metadata(line)
                        track_type = 'radio'
                        
                    else:
                        logger.warning(f"Unknown playlist type: {extension}")
                        continue
                    
                    track = Track(
                        title=metadata['title'],
                        artist=metadata['artist'],
                        duration=metadata['duration'],
                        type=track_type,
                        url=metadata['url'],
                        thumbnail_url=metadata.get('thumbnail_url')
                    )
                    tracks.append(track)
                    
                except Exception as e:
                    logger.error(f"Error processing track {i} in {playlist_name}: {e}")
                    failed_tracks += 1
                    continue
        
        if not tracks:
            logger.warning(f"No valid tracks found in playlist {playlist_name}")
            return None, failed_tracks
        
        # Create playlist with appropriate type
        playlist_type = {
            '.blp': 'local',
            '.byp': 'youtube',
            '.brp': 'radio'
        }.get(extension, 'unknown')
        
        playlist = Playlist(
            name=playlist_name,
            type=playlist_type,
            description=f"Migrated from {playlist_file.name}",
            tracks=tracks
        )
        
        return playlist, failed_tracks
        
    except Exception as e:
        logger.error(f"Error reading playlist {playlist_name}: {e}")
        return None, 0

def migrate_playlists():
    """Migrate playlists to database with enhanced metadata"""
    # Load environment variables from .env file in PWD
    dotenv.load_dotenv(os.path.join(os.getcwd(), '.env'), override=True)
    
    # Get playlist directory
    playlist_dir = os.getenv('PLAYLIST_DIR')
    if not playlist_dir:
        logger.error("PLAYLIST_DIR environment variable not set")
        sys.exit(1)
    
    logger.info(f"Using playlist directory: {playlist_dir}")
    music_dir = os.getenv('MUSIC_DIR')
    logger.info(f"Using music directory: {music_dir}")
    
    playlist_path = Path(playlist_dir)
    if not playlist_path.exists():
        logger.error(f"Playlist directory {playlist_dir} does not exist")
        sys.exit(1)
        
    # List all files in playlist directory
    logger.info("Directory contents:")
    try:
        for item in os.listdir(playlist_dir):
            item_path = os.path.join(playlist_dir, item)
            if os.path.isfile(item_path):
                logger.info(f"  File: {item} ({os.path.getsize(item_path)} bytes)")
            else:
                logger.info(f"  Dir:  {item}/")
    except Exception as e:
        logger.error(f"Error listing directory contents: {e}")
    
    # Get list of all playlist files
    playlist_extensions = ['*.blp', '*.byp', '*.brp']  # Beathoven playlist formats
    playlist_files = []
    for ext in playlist_extensions:
        playlist_files.extend(playlist_path.glob(ext))
    
    logger.info(f"\nFound {len(playlist_files)} playlist files:")
    for pf in playlist_files:
        logger.info(f"  - {pf.name} ({os.path.getsize(pf)} bytes)")
        
    if not playlist_files:
        logger.warning("No playlist files found! Looking for files with extensions: " + ", ".join(playlist_extensions))
        all_files = list(playlist_path.glob('*.*'))
        if all_files:
            logger.info("\nFound files with other extensions:")
            for f in all_files:
                logger.info(f"  - {f.name}")
    
    # Set up database
    try:
        db = Database()
        
        # Track migration stats
        total_playlists = 0
        total_tracks = 0
        total_failed = 0
        
        # Migrate each playlist
        for playlist_file in sorted(playlist_files):
            logger.info(f"\nProcessing playlist: {playlist_file.name}")
            
            playlist, failed_tracks = process_playlist(playlist_file)
            if playlist is None:
                continue
                
            # Try to add the playlist
            try:
                logger.info(f"Adding playlist {playlist.name} with {len(playlist.tracks)} tracks to database")
                db.add_playlist(playlist)
                total_playlists += 1
                total_tracks += len(playlist.tracks)
                total_failed += failed_tracks
                logger.info(f"Successfully migrated playlist {playlist.name}")
                logger.info(f"- Total tracks: {len(playlist.tracks)}")
                logger.info(f"- Failed tracks: {failed_tracks}")
                
            except sqlite3.IntegrityError:
                logger.warning(f"Playlist {playlist.name} already exists, updating instead")
                db.update_playlist(playlist)
                total_playlists += 1
                total_tracks += len(playlist.tracks)
                total_failed += failed_tracks
                logger.info(f"Successfully updated playlist {playlist.name}")
                logger.info(f"- Total tracks: {len(playlist.tracks)}")
                logger.info(f"- Failed tracks: {failed_tracks}")
        
        logger.info("\nMigration Summary:")
        logger.info(f"- Total playlists processed: {total_playlists}")
        logger.info(f"- Total tracks migrated: {total_tracks}")
        logger.info(f"- Total failed tracks: {total_failed}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    # When run directly, perform the migration
    migrate_playlists()
