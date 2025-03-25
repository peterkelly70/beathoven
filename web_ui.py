"""Web UI for Beathoven"""
import os
import logging
from typing import Optional
from flask import Flask, render_template, jsonify, request
import dotenv
from models import Track, Playlist
from playlist_manager import PlaylistManager
from database import Database
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Reduce logging noise
logging.getLogger('werkzeug').setLevel(logging.WARNING)

app = Flask(__name__, 
           template_folder='web/templates',
           static_folder='web/static')
_playlist_manager = PlaylistManager()
db = Database()

# Cache state to reduce unnecessary updates
_last_state = None
_last_state_time = 0
_STATE_CACHE_TIME = 0.5  # seconds

_active_sessions = {}

class WebUI:
    """Web UI class for backward compatibility"""
    _instance = None
    
    def __new__(cls, playlist_manager: Optional[PlaylistManager] = None):
        if cls._instance is None:
            cls._instance = super(WebUI, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, playlist_manager: Optional[PlaylistManager] = None):
        global _playlist_manager
        if playlist_manager:
            _playlist_manager = playlist_manager
            
    def run(self, host='0.0.0.0', port=None, debug=False):
        """Start the web server"""
        start_web_server()

@app.route('/')
def index():
    """Render main page"""
    try:
        playlists = db.get_all_playlists()
        current_playlist = None
        current_track = None
        
        # Get current playlist if one is set
        if _playlist_manager.current_playlist:
            current_playlist = db.get_playlist(_playlist_manager.current_playlist)
            
        # Get current track if playing
        current_track = _playlist_manager.get_current_track()
        
        return render_template(
            'dashboard.html',  
            playlists=playlists,
            current_playlist=current_playlist,
            current_track=current_track,
            is_playing=_playlist_manager.is_playing,
            is_paused=_playlist_manager.is_paused,
            volume=_playlist_manager.volume,
            repeat_mode=_playlist_manager.repeat_mode
        )
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        return str(e), 500

@app.route('/dashboard/<session_id>')
def dashboard(session_id: str):
    """Web UI dashboard"""
    try:
        # Store session ID
        if session_id not in _active_sessions:
            _active_sessions[session_id] = {
                'created_at': datetime.now(),
                'last_active': datetime.now()
            }
        else:
            _active_sessions[session_id]['last_active'] = datetime.now()
            
        # Get playlists
        playlists = _playlist_manager.get_all_playlists()
        
        # Get current state
        current_playlist = _playlist_manager.current_playlist
        current_track = _playlist_manager.get_current_track()
        
        return render_template(
            'dashboard.html',
            playlists=playlists,
            current_playlist=current_playlist,
            current_track=current_track,
            is_playing=_playlist_manager.is_playing,
            is_paused=_playlist_manager.is_paused,
            volume=_playlist_manager.volume,
            repeat_mode=_playlist_manager.repeat_mode,
            session_id=session_id
        )
    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}", exc_info=True)
        return f"Error: {str(e)}", 500

@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    """Get all playlists"""
    try:
        playlists = db.get_all_playlists()
        return jsonify([{
            'name': p.name,
            'type': getattr(p, 'type', 'local'),  
            'description': getattr(p, 'description', ''),  
            'track_count': len(p.tracks),
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'modified_at': p.modified_at.isoformat() if p.modified_at else None
        } for p in playlists])
    except Exception as e:
        logger.error(f"Error getting playlists: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlists/<name>', methods=['GET'])
def get_playlist(name: str):
    """Get a specific playlist"""
    try:
        playlist = db.get_playlist(name)
        if not playlist:
            return jsonify({'error': 'Playlist not found'}), 404
        
        return jsonify({
            'name': playlist.name,
            'type': getattr(playlist, 'type', 'local'),  
            'description': getattr(playlist, 'description', ''),  
            'tracks': [{
                'title': t.title,
                'artist': t.artist,
                'url': t.url,
                'type': getattr(t, 'type', 'local'),  
                'duration': getattr(t, 'duration', 0),  
                'thumbnail_url': getattr(t, 'thumbnail_url', '')  
            } for t in playlist.tracks],
            'created_at': playlist.created_at.isoformat() if playlist.created_at else None,
            'modified_at': playlist.modified_at.isoformat() if playlist.modified_at else None
        })
    except Exception as e:
        logger.error(f"Error getting playlist: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlists/<playlist_name>/play', methods=['POST'])
def play_playlist(playlist_name: str):
    """Start playing a playlist"""
    try:
        playlist = db.get_playlist(playlist_name)
        if not playlist:
            return jsonify({'error': 'Playlist not found'}), 404
            
        # Load the playlist and its tracks
        _playlist_manager.set_current_playlist(playlist_name)
        _playlist_manager.set_playing(True)
        
        # Get the current track info
        current_track = _playlist_manager.get_current_track()
        
        return jsonify({
            'status': 'success',
            'playlist': playlist_name,
            'current_track': {
                'title': current_track.title,
                'artist': current_track.artist,
                'url': current_track.url,
                'type': getattr(current_track, 'type', 'local'),  
                'duration': getattr(current_track, 'duration', 0),  
                'thumbnail_url': getattr(current_track, 'thumbnail_url', '')  
            } if current_track else None,
            'tracks': [{
                'title': t.title,
                'artist': t.artist,
                'url': t.url,
                'type': getattr(t, 'type', 'local'),  
                'duration': getattr(t, 'duration', 0),  
                'thumbnail_url': getattr(t, 'thumbnail_url', '')  
            } for t in playlist.tracks] if playlist.tracks else []
        })
    except Exception as e:
        logger.error(f"Error playing playlist: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlists/<name>/delete', methods=['POST'])
def delete_playlist(name: str):
    """Delete a playlist"""
    try:
        # Check admin password
        admin_password = request.json.get('admin_password')
        if not admin_password or admin_password != os.getenv('ADMIN_PASSWORD'):
            return jsonify({'error': 'Invalid admin password'}), 403
            
        if _playlist_manager.delete_playlist(name):
            return jsonify({'status': 'success'})
        else:
            return jsonify({'error': 'Playlist not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting playlist: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/state', methods=['GET'])
def get_player_state():
    """Get current player state"""
    global _last_state, _last_state_time
    
    try:
        current_time = time.time()
        
        # Return cached state if it's fresh enough
        if _last_state and (current_time - _last_state_time) < _STATE_CACHE_TIME:
            return jsonify(_last_state)
        
        current_track = _playlist_manager.get_current_track()
        current_playlist = None
        if _playlist_manager.current_playlist:
            current_playlist = db.get_playlist(_playlist_manager.current_playlist)
        
        state = {
            'is_playing': _playlist_manager.is_playing,
            'is_paused': _playlist_manager.is_paused,
            'volume': _playlist_manager.volume,
            'repeat_mode': _playlist_manager.repeat_mode,
            'current_playlist': {
                'name': current_playlist.name,
                'type': getattr(current_playlist, 'type', 'local'),  
                'track_count': len(current_playlist.tracks)
            } if current_playlist else None,
            'current_track': {
                'title': current_track.title,
                'artist': current_track.artist,
                'url': current_track.url,
                'type': getattr(current_track, 'type', 'local'),  
                'duration': getattr(current_track, 'duration', 0),  
                'thumbnail_url': getattr(current_track, 'thumbnail_url', '')  
            } if current_track else None
        }
        
        # Cache the state
        _last_state = state
        _last_state_time = current_time
        
        return jsonify(state)
    except Exception as e:
        logger.error(f"Error getting player state: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/play', methods=['POST'])
def play():
    """Resume playback"""
    try:
        _playlist_manager.set_paused(False)
        _playlist_manager.set_playing(True)
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error playing: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/pause', methods=['POST'])
def pause():
    """Pause playback"""
    try:
        _playlist_manager.set_playing(False)
        _playlist_manager.set_paused(True)
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error pausing: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/next', methods=['POST'])
def next_track():
    """Skip to next track"""
    try:
        track = _playlist_manager.next_track()
        if track:
            _playlist_manager.set_playing(True)  # Ensure we're playing
            return jsonify({
                'status': 'success',
                'track': {
                    'title': track.title,
                    'url': track.url,
                    'artist': track.artist,
                    'duration': track.duration
                }
            })
        else:
            _playlist_manager.set_playing(False)  # Stop if no next track
            return jsonify({'status': 'end'})
    except Exception as e:
        logger.error(f"Error skipping track: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/previous', methods=['POST'])
def previous_track():
    """Go to previous track"""
    try:
        track = _playlist_manager.previous_track()
        return jsonify({
            'status': 'success',
            'current_track': {
                'title': track.title,
                'artist': track.artist,
                'url': track.url,
                'type': getattr(track, 'type', 'local'),  
                'duration': getattr(track, 'duration', 0),  
                'thumbnail_url': getattr(track, 'thumbnail_url', '')  
            } if track else None
        })
    except Exception as e:
        logger.error(f"Error going to previous track: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/volume', methods=['POST'])
def set_volume():
    """Set player volume"""
    try:
        volume = request.json.get('volume', 100)
        _playlist_manager.set_volume(volume)
        return jsonify({'status': 'success', 'volume': volume})
    except Exception as e:
        logger.error(f"Error setting volume: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/repeat', methods=['POST'])
def set_repeat():
    """Set repeat mode"""
    try:
        mode = request.json.get('mode', 'none')
        _playlist_manager.set_repeat_mode(mode)
        return jsonify({'status': 'success', 'repeat_mode': mode})
    except Exception as e:
        logger.error(f"Error setting repeat mode: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sessions/<session_id>/validate', methods=['POST'])
def validate_session(session_id: str):
    """Validate a session"""
    try:
        if session_id in _active_sessions:
            _active_sessions[session_id]['last_active'] = datetime.now()
            return jsonify({'status': 'valid'})
        return jsonify({'status': 'invalid'}), 404
    except Exception as e:
        logger.error(f"Error validating session: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def start_web_server():
    """Start the web server"""
    dotenv.load_dotenv()
    host = os.getenv('WEB_UI_HOST', '0.0.0.0')
    port = int(os.getenv('WEB_UI_PORT', 5000))
    
    logger.info(f"Starting web server on {host}:{port}")
    app.run(host=host, port=port)
