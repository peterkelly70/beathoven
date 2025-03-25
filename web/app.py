import os
import json
import time
from flask import Flask, render_template, jsonify, request, abort
from flask_socketio import SocketIO, join_room, leave_room
from flask_socketio import emit
import eyed3
from web.shared import session_manager, Player, PLAYER_STATE, REPEAT_MODE
import asyncio
import yt_dlp
from flask_cors import CORS
from flask_bootstrap import Bootstrap5
import re

class ReverseProxied(object):
    def __init__(self, app, script_name=None):
        self.app = app
        self.script_name = script_name

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '') or self.script_name
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        return self.app(environ, start_response)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev')

# Configure for reverse proxy
app.wsgi_app = ReverseProxied(app.wsgi_app, script_name='')

socketio = SocketIO(app, cors_allowed_origins="*", path='socket.io')
CORS(app)
bootstrap = Bootstrap5(app)

# YouTube info cache
youtube_cache = {}

def get_track_info(track_path):
    """Get track info from MP3 tags if available"""
    try:
        if track_path.lower().endswith('.mp3'):
            audiofile = eyed3.load(track_path)
            if audiofile and audiofile.tag:
                title = audiofile.tag.title
                artist = audiofile.tag.artist
                if title:
                    if artist:
                        return f"{artist} - {title}"
                    return title
    except Exception as e:
        print(f"Error reading MP3 tags: {e}")
    
    # Fallback to filename
    return os.path.splitext(os.path.basename(track_path))[0]

def get_track_title_from_path(track_path):
    """Extract a better title from the track path without reading MP3 tags"""
    filename = os.path.basename(track_path)
    
    # Remove file extension
    title = os.path.splitext(filename)[0]
    
    # Replace underscores and dots with spaces
    title = title.replace('_', ' ').replace('.', ' ')
    
    # If there are numbers at the start (like "01."), try to extract the main title
    parts = title.split(' ', 1)
    if len(parts) > 1 and parts[0].replace('.', '').isdigit():
        title = parts[1]
    
    return title

def emit_player_state(session_id):
    """Emit current player state to clients"""
    player = session_manager.get_player(session_id)
    if player:
        state_dict = player.to_dict()
        print(f"Emitting player state: {state_dict}")
        socketio.emit('bot_state', state_dict, room=session_id)

@app.route('/<session_id>')
def index(session_id):
    """Render web UI for a session"""
    if not session_manager.get_session(session_id):
        abort(404, description="Invalid or expired session")
    return render_template('index.html', session_id=session_id)

@app.route('/api/<session_id>/playlists')
def get_playlists(session_id):
    """Get all playlists for a session"""
    print(f"[GET /api/{session_id}/playlists] Getting playlists for session")
    session = session_manager.get_session(session_id)
    if not session:
        print(f"[GET /api/{session_id}/playlists] Session not found")
        abort(404)
    
    guild_data = session_manager.get_guild_data(session['guild_id'])
    playlists = guild_data.get('playlists', [])
    print(f"[GET /api/{session_id}/playlists] Found {len(playlists)} playlists")
    print(f"[GET /api/{session_id}/playlists] Playlists data: {json.dumps(playlists, indent=2)}")
    return jsonify(playlists)

@app.route('/api/<session_id>/playlist/<playlist_name>')
def get_playlist_tracks(session_id, playlist_name):
    """Get tracks for a specific playlist"""
    print(f"[GET /api/{session_id}/playlist/{playlist_name}] Getting tracks")
    session = session_manager.get_session(session_id)
    if not session:
        print(f"[GET /api/{session_id}/playlist/{playlist_name}] Session not found")
        abort(404)
        
    guild_data = session_manager.get_guild_data(session['guild_id'])
    playlists = guild_data.get('playlists', [])
    print(f"[GET /api/{session_id}/playlist/{playlist_name}] Found {len(playlists)} playlists in guild data")
    for playlist in playlists:
        if playlist['name'] == playlist_name:
            # Found the playlist
            print(f"[GET /api/{session_id}/playlist/{playlist_name}] Found playlist {playlist_name} with {len(playlist.get('tracks', []))} tracks")
            
            # Get the raw tracks
            tracks = playlist.get('tracks', [])
            
            # Convert raw tracks to rich track objects with better titles
            enhanced_tracks = []
            for i, track in enumerate(tracks):
                if isinstance(track, str):
                    # It's a simple file path, enhance it
                    track_type = playlist.get('type', 'local')
                    if track_type == 'local':
                        # For local tracks, extract better title from filename
                        enhanced_tracks.append({
                            'path': track,
                            'title': get_track_title_from_path(track),
                            'index': i,
                            'type': 'local'
                        })
                    else:
                        # For YouTube or radio tracks
                        enhanced_tracks.append({
                            'path': track,
                            'title': track,
                            'index': i,
                            'type': track_type
                        })
                else:
                    # It's already an object
                    track_obj = dict(track)
                    if 'title' not in track_obj:
                        track_obj['title'] = get_track_title_from_path(track_obj.get('path', f'Track {i+1}'))
                    track_obj['index'] = i
                    enhanced_tracks.append(track_obj)
            
            return jsonify(enhanced_tracks)
    
    # If we get here, playlist not found
    print(f"[GET /api/{session_id}/playlist/{playlist_name}] Playlist not found")
    return jsonify([])

@app.route('/api/<session_id>/playlist/<name>', methods=['POST'])
def create_playlist(session_id, name):
    print(f"[POST /api/{session_id}/playlist/{name}] Creating playlist")
    session = session_manager.get_session(session_id)
    if not session:
        print(f"[POST /api/{session_id}/playlist/{name}] Session not found")
        abort(404, description="Invalid or expired session")
        
    data = request.json
    tracks = data.get('tracks', [])
    
    guild_data = session_manager.get_guild_data(session['guild_id'])
    if 'playlists' not in guild_data:
        guild_data['playlists'] = []
    
    guild_data['playlists'].append({
        'name': name,
        'type': 'local',
        'tracks': tracks,
        'description': f"{len(tracks)} local track(s)"
    })
    
    session_manager.save_guild_data(session['guild_id'], guild_data)
    print(f"[POST /api/{session_id}/playlist/{name}] Playlist created successfully")
    
    return jsonify({'status': 'success'})

@app.route('/api/<session_id>/playlist/<name>', methods=['PUT'])
def update_playlist(session_id, name):
    print(f"[PUT /api/{session_id}/playlist/{name}] Updating playlist")
    session = session_manager.get_session(session_id)
    if not session:
        print(f"[PUT /api/{session_id}/playlist/{name}] Session not found")
        abort(404, description="Invalid or expired session")
    
    data = request.json
    tracks = data.get('tracks', [])
    
    guild_data = session_manager.get_guild_data(session['guild_id'])
    if 'playlists' in guild_data:
        for playlist in guild_data['playlists']:
            if playlist['name'] == name:
                playlist['tracks'] = tracks
                session_manager.save_guild_data(session['guild_id'], guild_data)
                print(f"[PUT /api/{session_id}/playlist/{name}] Playlist updated successfully")
                return jsonify({'status': 'success'})
    
    print(f"[PUT /api/{session_id}/playlist/{name}] Playlist not found")
    return jsonify({'error': 'Playlist not found'}), 404

@app.route('/api/<session_id>/playlist/<name>', methods=['DELETE'])
def delete_playlist(session_id, name):
    print(f"[DELETE /api/{session_id}/playlist/{name}] Deleting playlist")
    session = session_manager.get_session(session_id)
    if not session:
        print(f"[DELETE /api/{session_id}/playlist/{name}] Session not found")
        abort(404, description="Invalid or expired session")
        
    guild_data = session_manager.get_guild_data(session['guild_id'])
    if 'playlists' in guild_data:
        guild_data['playlists'] = [p for p in guild_data['playlists'] if p['name'] != name]
        session_manager.save_guild_data(session['guild_id'], guild_data)
        print(f"[DELETE /api/{session_id}/playlist/{name}] Playlist deleted successfully")
        return jsonify({'status': 'success'})
    print(f"[DELETE /api/{session_id}/playlist/{name}] Playlist not found")
    return jsonify({'error': 'Playlist not found'}), 404

@app.route('/api/<session_id>/youtube-info/<video_id>')
def get_youtube_info(session_id, video_id):
    session = session_manager.get_session(session_id)
    if not session:
        abort(404, description="Invalid or expired session")
    
    # Check cache first
    if video_id in youtube_cache:
        return jsonify(youtube_cache[video_id])
    
    try:
        # Configure yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f'https://www.youtube.com/watch?v={video_id}'
            info = ydl.extract_info(url, download=False)
            
            # Cache the result
            result = {
                'title': info.get('title', video_id),
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail')
            }
            youtube_cache[video_id] = result
            
            return jsonify(result)
            
    except Exception as e:
        print(f"Error fetching YouTube info: {e}")
        return jsonify({'title': video_id}), 500

@app.route('/api/<session_id>/player/play', methods=['POST'])
def player_play(session_id):
    session = session_manager.get_session(session_id)
    if not session:
        abort(404, description="Invalid or expired session")
        
    data = request.json or {}
    playlist_id = data.get('playlist')
    track_index = data.get('track')
    
    player = session_manager.get_player(session_id)
    if player:
        # Load playlist if specified
        if playlist_id:
            player.load_playlist(playlist_id)
            
        # Set track index if specified
        if track_index is not None:
            player.play(track_index=int(track_index))
        else:
            player.play()
            
        # Emit state update
        emit_player_state(session_id)
        
        return jsonify({'status': 'ok'})

@app.route('/api/<session_id>/control', methods=['POST'])
def control_playback(session_id):
    """Control playback for a guild session"""
    session = session_manager.get_session(session_id)
    if not session:
        return jsonify({'error': 'Invalid session ID'}), 404
        
    data = request.json
    
    command = data.get('command')
    print(f"Handling playback control: {command}")
    
    if command == 'play':
        # Check if we have a playlist and track index
        playlist_name = data.get('playlist')
        track_index = data.get('track_index', 0)
        print(f"Play command with playlist: {playlist_name}, track_index: {track_index}")
        
        if playlist_name:
            print(f"Invoking command: play_track_command")
            
            # Convert track_index to integer if it's a string
            if isinstance(track_index, str) and track_index.isdigit():
                track_index = int(track_index)
            elif not isinstance(track_index, int):
                track_index = 0
                
            print(f"Starting from track {track_index}")
            
            # Make sure we update the guild's current playlist in active_sessions
            guild_data = session_manager.get_guild_data(session['guild_id'])
            if 'current_playlist' not in guild_data:
                guild_data['current_playlist'] = {}
                
            guild_data['current_playlist'] = {
                'name': playlist_name,
                'track_index': track_index,
                'type': 'local'
            }
            
            session_manager.save_guild_data(session['guild_id'], guild_data)
            
            # Create a default player state if one doesn't exist
            if not session_manager.get_player(session_id):
                session_manager.create_player(session_id)
            
            # Update the player state
            player = session_manager.get_player(session_id)
            player.current_playlist = playlist_name
            player.current_track_index = track_index
            player.state = PLAYER_STATE.PLAYING
            
            # Instead of directly calling the bot command which requires a proper ctx object,
            # first stop any currently playing audio
            stop_command = {
                'type': 'playback',
                'action': 'stop',
                'guild_id': session['guild_id']
            }
            
            # Log the stop command
            print(f"Emitting stop command first: {stop_command}")
            
            # Send the stop command to the bot
            socketio.emit('command', stop_command)
            
            # Small delay to ensure stop completes
            time.sleep(0.5)
            
            # Now send the play command
            command = {
                'type': 'playback',
                'action': 'play',
                'guild_id': session['guild_id'],
                'session_id': session_id
            }
            
            if playlist_name:
                command['playlist'] = playlist_name
                
            if track_index is not None:
                command['track'] = int(track_index)
                
            print(f"Emitting playback command: {command}")
            
            # Send the command to the bot
            socketio.emit('command', command)
            
            # Prepare the player state to return
            player_state = player.to_dict()
            player_state['current_playlist'] = playlist_name
            player_state['current_track_index'] = track_index
            player_state['playing'] = True
            
            # Update the player state in active_sessions
            guild_data['player_state'] = player_state
            session_manager.save_guild_data(session['guild_id'], guild_data)
            
            # Emit the player state to all connected clients for this guild
            emit_player_state(session_id)
            
            return jsonify(player_state)

@app.route('/session/<guild_id>', methods=['POST'])
def create_session(guild_id):
    """Create a new session for a guild"""
    session_id = session_manager.create_session(guild_id)
    return jsonify({
        'session_id': session_id,
        'dashboard_url': f"{request.host_url}{session_id}"
    })

@app.route('/api/<session_id>/state')
def get_state(session_id):
    """Get current player state"""
    player = session_manager.get_player(session_id)
    if not player:
        abort(404)
    return jsonify(player.to_dict())

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print("Client disconnected")

@socketio.on('join')
def handle_join(data):
    """Handle client joining a session room"""
    session_id = data.get('session_id')
    if session_id and session_manager.get_session(session_id):
        join_room(session_id)
        print(f"Client joined room {session_id}")

@socketio.on('leave')
def handle_leave(data):
    """Handle client leaving a session room"""
    session_id = data.get('session_id')
    if session_id:
        leave_room(session_id)
        print(f"Client left room {session_id}")

@socketio.on('bot_state_request')
def handle_bot_state_request(data):
    session_id = data.get('session_id')
    if session_id and session_manager.get_player(session_id):
        emit_player_state(session_id)
        print(f"State requested for session {session_id}")

@socketio.on('playback_control')
def handle_playback_control(data):
    session_id = data.get('session_id')
    if not session_id or not session_manager.get_session(session_id):
        print(f"Invalid session for playback control: {session_id}")
        return
        
    action = data.get('action')
    if action not in ['play', 'pause', 'stop', 'next', 'previous', 'repeat']:
        print(f"Invalid playback action: {action}")
        return
        
    session = session_manager.get_session(session_id)
    print(f"Handling playback control: {action} for guild {session['guild_id']}")
    
    # Get the bot command based on action
    command_name = {
        'play': 'play_track_command',
        'pause': 'pause',
        'stop': 'stop',
        'next': 'next',  # Changed from 'skip' to 'next'
        'previous': 'previous',
        'repeat': 'repeat_mode'
    }.get(action)
    
    if command_name:
        command = bot.get_command(command_name)
        if command:
            guild = bot.get_guild(session['guild_id'])
            if guild:
                channel_id = session_manager.get_guild_data(session['guild_id']).get('channel_id')
                if channel_id:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        print(f"Invoking command: {command_name}")
                        player = session_manager.get_player(session_id)
                        
                        if action == 'play':
                            if data.get('track_index') is not None:
                                track_index = int(data['track_index'])
                                print(f"Starting from track {track_index}")
                                player.play(track_index=track_index)
                                asyncio.run_coroutine_threadsafe(
                                    command(channel, player.current_playlist, track_index), 
                                    bot.loop
                                )
                            elif player and player.current_playlist:
                                print(f"Starting/resuming playlist {player.current_playlist}")
                                player.play()
                                asyncio.run_coroutine_threadsafe(
                                    command(channel, player.current_playlist), 
                                    bot.loop
                                )
                            else:
                                print("No playlist loaded")
                        else:
                            # For other commands (pause, stop, next, previous)
                            if action == 'pause':
                                player.pause()
                            elif action == 'stop':
                                player.stop()
                            elif action == 'next':
                                player.next_track()
                            elif action == 'previous':
                                player.previous_track()
                            elif action == 'repeat':
                                repeat_mode = data.get('mode', None)
                                player.toggle_repeat(repeat_mode)
                                
                                # For repeat mode, we need to pass the mode parameter
                                if action == 'repeat':
                                    asyncio.run_coroutine_threadsafe(
                                        command(channel, repeat_mode), 
                                        bot.loop
                                    )
                                    # Skip the generic command call below
                                    emit_player_state(session_id)
                                    return
                                
                            asyncio.run_coroutine_threadsafe(
                                command(channel), 
                                bot.loop
                            )
                            
                        emit_player_state(session_id)
                    else:
                        print(f"Channel not found: {channel_id}")
                else:
                    print(f"No active session channel for guild {session['guild_id']}")
            else:
                print(f"Guild not found: {session['guild_id']}")
        else:
            print(f"Command not found: {command_name}")

@socketio.on('volume')
def handle_volume(data):
    session_id = data.get('session_id')
    if not session_id or not session_manager.get_player(session_id):
        return
        
    value = data.get('value')
    if not isinstance(value, int) or value < 0 or value > 100:
        return
        
    player = session_manager.get_player(session_id)
    player.set_volume(value)
    emit_player_state(session_id)

def start_server():
    """Start the Flask server"""
    port = int(os.getenv('PORT', 5000))
    socketio.run(app, debug=True, use_reloader=False, port=port)
