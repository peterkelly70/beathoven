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
app.wsgi_app = ReverseProxied(app.wsgi_app, script_name='')
socketio = SocketIO(app, cors_allowed_origins="*", path='socket.io')
CORS(app)
bootstrap = Bootstrap5(app)
youtube_cache = {}

def get_track_info(track_path):
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
    return os.path.splitext(os.path.basename(track_path))[0]

def get_track_title_from_path(track_path):
    filename = os.path.basename(track_path)
    title = os.path.splitext(filename)[0]
    title = title.replace('_', ' ').replace('.', ' ')
    parts = title.split(' ', 1)
    if len(parts) > 1 and parts[0].replace('.', '').isdigit():
        title = parts[1]
    return title

def emit_player_state(session_id):
    player = session_manager.get_player(session_id)
    if player:
        state_dict = player.to_dict()
        print(f"Emitting player state: {state_dict}")
        socketio.emit('bot_state', state_dict, room=session_id)

@app.route('/<session_id>')
def index(session_id):
    if not session_manager.get_session(session_id):
        abort(404, description="Invalid or expired session")
    return render_template('index.html', session_id=session_id)

@app.route('/api/<session_id>/playlists')
def get_playlists(session_id):
    session = session_manager.get_session(session_id)
    if not session:
        abort(404)
    guild_data = session_manager.get_guild_data(session['guild_id'])
    playlists = guild_data.get('playlists', [])
    return jsonify(playlists)

@app.route('/api/<session_id>/playlist/<playlist_name>')
def get_playlist_tracks(session_id, playlist_name):
    session = session_manager.get_session(session_id)
    if not session:
        abort(404)
    guild_data = session_manager.get_guild_data(session['guild_id'])
    playlists = guild_data.get('playlists', [])
    for playlist in playlists:
        if playlist['name'] == playlist_name:
            tracks = playlist.get('tracks', [])
            enhanced_tracks = []
            for i, track in enumerate(tracks):
                if isinstance(track, str):
                    track_type = playlist.get('type', 'local')
                    if track_type == 'local':
                        enhanced_tracks.append({
                            'path': track,
                            'title': get_track_title_from_path(track),
                            'index': i,
                            'type': 'local'
                        })
                    else:
                        enhanced_tracks.append({
                            'path': track,
                            'title': track,
                            'index': i,
                            'type': track_type
                        })
                else:
                    track_obj = dict(track)
                    if 'title' not in track_obj:
                        track_obj['title'] = get_track_title_from_path(track_obj.get('path', f'Track {i+1}'))
                    track_obj['index'] = i
                    enhanced_tracks.append(track_obj)
            return jsonify(enhanced_tracks)
    return jsonify([])

@app.route('/api/<session_id>/control', methods=['POST'])
def control_playback(session_id):
    session = session_manager.get_session(session_id)
    if not session:
        return jsonify({'error': 'Invalid session ID'}), 404

    data = request.json
    command = data.get('command')
    print(f"Handling playback control: {command}")

    if command == 'play':
        playlist_name = data.get('playlist')
        track_index = data.get('track_index', 0)

        if isinstance(track_index, str) and track_index.isdigit():
            track_index = int(track_index)
        elif not isinstance(track_index, int):
            track_index = 0

        guild_data = session_manager.get_guild_data(session['guild_id'])
        guild_data['current_playlist'] = {
            'name': playlist_name,
            'track_index': track_index,
            'type': 'local'
        }
        session_manager.save_guild_data(session['guild_id'], guild_data)

        if not session_manager.get_player(session_id):
            session_manager.create_player(session_id)

        player = session_manager.get_player(session_id)
        player.current_playlist = playlist_name
        player.current_track_index = track_index
        player.state = PLAYER_STATE.PLAYING

        print(f"[control_playback] Emitting stop via playback_control")
        socketio.emit('playback_control', {
            'session_id': session_id,
            'action': 'stop'
        })

        time.sleep(0.5)

        print(f"[control_playback] Emitting play via playback_control")
        socketio.emit('playback_control', {
            'session_id': session_id,
            'action': 'play',
            'track_index': track_index
        })

        player_state = player.to_dict()
        player_state['current_playlist'] = playlist_name
        player_state['current_track_index'] = track_index
        player_state['playing'] = True

        guild_data['player_state'] = player_state
        session_manager.save_guild_data(session['guild_id'], guild_data)
        emit_player_state(session_id)
        return jsonify(player_state)

    elif command == 'stop':
        print(f"[control_playback] Received stop command, emitting to playback_control")
        socketio.emit('playback_control', {
            'session_id': session_id,
            'action': 'stop'
        })
        return jsonify({'status': 'ok'})

@app.route('/api/<session_id>/state')
def get_state(session_id):
    player = session_manager.get_player(session_id)
    if not player:
        abort(404)
    return jsonify(player.to_dict())

@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('join')
def handle_join(data):
    session_id = data.get('session_id')
    if session_id and session_manager.get_session(session_id):
        join_room(session_id)
        print(f"Client joined room {session_id}")

@socketio.on('leave')
def handle_leave(data):
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
    port = int(os.getenv('PORT', 5000))
    socketio.run(app, debug=True, use_reloader=False, port=port)
