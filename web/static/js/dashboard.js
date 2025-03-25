// Get session ID from URL path
const sessionId = window.location.pathname.split('/').filter(p => p).pop();

// Global variables
let currentPlaylistName = null;
let youtubeCache = new Map(); // Cache for YouTube video titles
let selectedTrackIndex;
let currentState = null;
let socketConnected = false;

// Initialize DOM elements
document.addEventListener('DOMContentLoaded', () => {
    // Initialize playlist containers
    window.localPlaylists = document.getElementById('localPlaylists');
    window.youtubePlaylists = document.getElementById('youtubePlaylists');
    window.radioPlaylists = document.getElementById('radioPlaylists');
    window.playlistTracks = document.getElementById('playlistTracks');
    
    // Initialize player controls
    window.currentTrack = document.getElementById('currentTrack');
    window.playlistTitle = document.getElementById('playlist-title');
    window.playPauseBtn = document.getElementById('playPauseBtn');
    window.prevBtn = document.getElementById('prevBtn');
    window.nextBtn = document.getElementById('nextBtn');
    window.stopBtn = document.getElementById('stopBtn');
    window.repeatTrackBtn = document.getElementById('repeatTrackBtn');
    window.repeatPlaylistBtn = document.getElementById('repeatPlaylistBtn');
    window.volumeSlider = document.getElementById('volumeSlider');
    window.createPlaylistBtn = document.getElementById('createPlaylistBtn');
    
    // Initialize modal elements
    window.editPlaylistModal = document.getElementById('editPlaylistModal');
    window.editPlaylistName = document.getElementById('editPlaylistName');
    window.editPlaylistType = document.getElementById('editPlaylistType');
    window.editPlaylistTracks = document.getElementById('editPlaylistTracks');
    window.savePlaylistBtn = document.getElementById('savePlaylistBtn');
    window.deletePlaylistBtn = document.getElementById('deletePlaylistBtn');
    
    // Initialize Socket.IO
    const socket = io();
    socket.on('connect', () => {
        console.log('Socket connected');
        socketConnected = true;
        socket.emit('join', { session_id: sessionId });
    });
    
    socket.on('bot_state', (state) => {
        console.log('Received state update:', state);
        updatePlayerState(state);
    });
    
    // Load initial playlists
    loadPlaylists();
    
    // Initialize playback controls
    initPlaybackControls();
});

// Load playlists
function loadPlaylists() {
    console.log('[Dashboard] Loading playlists...');
    fetch(`/api/${sessionId}/playlists`)
        .then(response => {
            console.log('[Dashboard] Got playlists response:', response);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(playlists => {
            console.log('[Dashboard] Loaded playlists:', playlists);
            // Clear existing playlists
            localPlaylists.innerHTML = '';
            youtubePlaylists.innerHTML = '';
            radioPlaylists.innerHTML = '';

            // Group playlists by type
            playlists.forEach(playlist => {
                console.log('[Dashboard] Processing playlist:', playlist);
                const container = playlist.type === 'local' ? localPlaylists :
                                playlist.type === 'youtube' ? youtubePlaylists :
                                radioPlaylists;

                const item = document.createElement('a');
                item.href = '#';
                item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                item.innerHTML = `
                    <div>
                        <h6 class="mb-1">${playlist.name}</h6>
                        <small class="text-muted">${playlist.track_count} tracks</small>
                    </div>
                    <span class="badge bg-${playlist.type} rounded-pill">${playlist.type}</span>
                `;
                container.appendChild(item);

                // Add click handler
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    console.log('[Dashboard] Loading tracks for playlist:', playlist.name);
                    currentPlaylistName = playlist.name;
                    playlistTitle.textContent = playlist.name;
                    loadPlaylistTracks(playlist.name);
                    
                    // Update active state
                    document.querySelectorAll('.list-group-item').forEach(el => {
                        el.classList.remove('active');
                    });
                    item.classList.add('active');
                });
            });
        })
        .catch(error => {
            console.error('[Dashboard] Error loading playlists:', error);
            showError('Failed to load playlists. Please try again.');
        });
}

// YouTube title fetcher
async function getYouTubeTitle(videoId) {
    if (youtubeCache.has(videoId)) {
        return youtubeCache.get(videoId);
    }
    
    try {
        const response = await fetch(`/api/${sessionId}/youtube-info/${videoId}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        youtubeCache.set(videoId, data.title);
        return data.title;
    } catch (error) {
        console.error('Error fetching YouTube title:', error);
        return videoId; // Fallback to video ID if fetch fails
    }
}

// Load playlist tracks
function loadPlaylistTracks(playlistName) {
    console.log(`[Dashboard] Loading tracks for playlist: ${playlistName}`);
    fetch(`/api/${sessionId}/playlist/${playlistName}`)
        .then(response => {
            console.log('[Dashboard] Got tracks response:', response);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(tracks => {
            console.log('[Dashboard] Loaded tracks:', tracks);
            // Update track list
            playlistTracks.innerHTML = '';
            tracks.forEach((track, index) => {
                console.log('[Dashboard] Processing track:', track);
                const trackElement = document.createElement('div');
                trackElement.className = 'track';
                trackElement.innerHTML = `
                    <div class="track-info">
                        <span class="track-title">${track.title || track}</span>
                    </div>
                `;
                playlistTracks.appendChild(trackElement);

                // Add click handler
                trackElement.addEventListener('click', () => {
                    console.log('[Dashboard] Playing track:', track);
                    playTrack(playlistName, index);
                });
            });
        })
        .catch(error => {
            console.error('[Dashboard] Error loading tracks:', error);
            showError('Failed to load tracks. Please try again.');
        });
}

// Function to load playlist and start playing
async function loadPlaylistAndPlay(playlistName) {
    await loadPlaylistTracks(playlistName);
    playTrack(0); // Start playing from the first track
}

// Function to play a track from the current playlist
async function playTrack(trackIndex) {
    console.log(`Playing track ${trackIndex} from playlist ${currentPlaylistName}`);
    
    try {
        // Validate we have a playlist loaded
        if (!currentPlaylistName) {
            showError("No playlist selected. Please select a playlist first.");
            return;
        }
        
        // Highlight the active track
        document.querySelectorAll('.track-item').forEach((item, idx) => {
            if (parseInt(item.dataset.index) === trackIndex) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
        
        // Send command to server
        const response = await fetch(`/api/${sessionId}/control`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                command: 'play',
                playlist: currentPlaylistName,
                track_index: trackIndex
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to play track');
        }
        
        const data = await response.json();
        console.log('Play response:', data);
        
        // Update play button to show pause icon
        playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
        playPauseBtn.title = 'Pause';
        
        // Update player state
        updatePlayerState(data);
    } catch (error) {
        console.error('Error playing track:', error);
        showError(`Failed to play track: ${error.message}`);
    }
}

// Playback controls
function initPlaybackControls() {
    playPauseBtn.onclick = () => {
        const isPlaying = playPauseBtn.querySelector('i').classList.contains('fa-pause');
        
        if (isPlaying) {
            // Pause
            fetch(`/api/${sessionId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'pause' })
            })
            .then(response => response.json())
            .then(data => {
                console.log('Pause response:', data);
                playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
                playPauseBtn.title = 'Play';
            })
            .catch(error => {
                console.error('Error pausing:', error);
                showError('Failed to pause playback');
            });
        } else {
            // Resume or start playing
            if (currentPlaylistName && document.querySelector('.track-item.active')) {
                // Resume the current track
                fetch(`/api/${sessionId}/control`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: 'resume' })
                })
                .then(response => response.json())
                .then(data => {
                    console.log('Resume response:', data);
                    playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
                    playPauseBtn.title = 'Pause';
                })
                .catch(error => {
                    console.error('Error resuming:', error);
                    showError('Failed to resume playback');
                });
            } else if (currentPlaylistName) {
                // Start playing from first track
                playTrack(0);
            } else {
                showError('No playlist selected');
            }
        }
    };

    nextBtn.onclick = () => {
        fetch(`/api/${sessionId}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'next' })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Next track response:', data);
        })
        .catch(error => {
            console.error('Error changing track:', error);
            showError('Failed to skip to next track');
        });
    };

    prevBtn.onclick = () => {
        fetch(`/api/${sessionId}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'previous' })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Previous track response:', data);
        })
        .catch(error => {
            console.error('Error changing track:', error);
            showError('Failed to go to previous track');
        });
    };

    stopBtn.onclick = () => {
        fetch(`/api/${sessionId}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'stop' })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Stop response:', data);
            playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
            playPauseBtn.title = 'Play';
        })
        .catch(error => {
            console.error('Error stopping:', error);
            showError('Failed to stop playback');
        });
    };
}

// Function to update player controls based on state
function updatePlayerState(data) {
    console.log('Updating player state with:', data);
    
    // Update current state
    currentState = data;
    
    // Update play/pause button
    if (data.playing) {
        playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
        playPauseBtn.title = 'Pause';
    } else {
        playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        playPauseBtn.title = 'Play';
    }
    
    // Update repeat buttons based on repeat state
    if (data.repeat === 'one') {
        repeatTrackBtn.classList.add('active');
        repeatPlaylistBtn.classList.remove('active');
    } else if (data.repeat === 'all') {
        repeatPlaylistBtn.classList.add('active');
        repeatTrackBtn.classList.remove('active');
    } else {
        repeatPlaylistBtn.classList.remove('active');
        repeatTrackBtn.classList.remove('active');
    }
    
    // Update volume
    if (data.volume !== undefined) {
        volumeSlider.value = data.volume;
    }
    
    // Update current track display
    if (data.current_track) {
        currentTrack.textContent = data.current_track;
    } else {
        currentTrack.textContent = 'No track playing';
    }
    
    // Update current playlist
    if (data.current_playlist && data.current_playlist !== currentPlaylistName) {
        // If the current playlist changed, load it
        loadPlaylistTracks(data.current_playlist);
    }
    
    // Update current track highlight
    if (data.current_track_index !== undefined) {
        document.querySelectorAll('.track-item').forEach((item, index) => {
            if (parseInt(item.dataset.index) === data.current_track_index) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }
}

// Create new playlist
function initCreatePlaylist() {
    createPlaylistBtn.onclick = async () => {
        const name = document.getElementById('playlistName').value;
        const type = document.getElementById('playlistType').value;
        const tracks = document.getElementById('playlistTracks').value.split('\n').filter(t => t.trim());
        
        try {
            const response = await fetch(`/api/${sessionId}/playlist/${name}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ type, tracks })
            });
            
            if (!response.ok) {
                if (response.status === 404) {
                    showError("Session expired. Please get a new link from Discord.");
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            bootstrap.Modal.getInstance(document.getElementById('newPlaylistModal')).hide();
            loadPlaylists();
        } catch (error) {
            console.error('Error creating playlist:', error);
            showError('Failed to create playlist. Please try again.');
        }
    };
}

// Function to open edit modal
function openEditModal(playlist) {
    editPlaylistName.value = playlist.name;
    editPlaylistType.value = playlist.type;
    editPlaylistTracks.value = playlist.tracks.join('\n');
    deletePlaylistBtn.onclick = () => deletePlaylist(playlist.name);
    savePlaylistBtn.onclick = () => savePlaylistChanges(playlist.name);
    editPlaylistModal.show();
}

// Function to save playlist changes
async function savePlaylistChanges(name) {
    const tracks = editPlaylistTracks.value.split('\n').filter(t => t.trim());
    
    try {
        const response = await fetch(`/api/${sessionId}/playlist/${name}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tracks: tracks
            })
        });
        
        if (!response.ok) {
            if (response.status === 404) {
                showError("Session expired. Please get a new link from Discord.");
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        editPlaylistModal.hide();
        loadPlaylists();
        showSuccess('Playlist updated successfully');
    } catch (error) {
        console.error('Error updating playlist:', error);
        showError('Failed to update playlist. Please try again.');
    }
}

// Function to delete playlist
async function deletePlaylist(name) {
    if (!confirm(`Are you sure you want to delete playlist "${name}"?`)) return;
    
    try {
        const response = await fetch(`/api/${sessionId}/playlist/${name}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            if (response.status === 404) {
                showError("Session expired. Please get a new link from Discord.");
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        editPlaylistModal.hide();
        loadPlaylists();
        if (currentPlaylistName === name) {
            playlistTracks.innerHTML = '';
            currentPlaylistName = null;
        }
        showSuccess('Playlist deleted successfully');
    } catch (error) {
        console.error('Error deleting playlist:', error);
        showError('Failed to delete playlist. Please try again.');
    }
}

// Function to show success message
function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'alert alert-success alert-dismissible fade show';
    successDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.querySelector('.container-fluid').insertBefore(successDiv, document.querySelector('.row'));
    setTimeout(() => successDiv.remove(), 3000);
}

// Show error message
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'alert alert-danger alert-dismissible fade show';
    errorDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.querySelector('.container-fluid').insertBefore(errorDiv, document.querySelector('.row'));
}

// Track selection
function selectTrack(index) {
    console.log(`Selecting track at index ${index}`);
    const tracks = document.querySelectorAll('.track-item');
    tracks.forEach(track => track.classList.remove('selected'));
    
    // Find the track with the matching index
    const selectedTrack = document.querySelector(`.track-item[data-index="${index}"]`);
    if (selectedTrack) {
        selectedTrack.classList.add('selected');
        selectedTrackIndex = index;
    }
}

// Repeat mode controls
function initRepeatModeControls() {
    repeatTrackBtn.onclick = () => {
        const isActive = repeatTrackBtn.classList.contains('active');
        if (isActive) {
            // Turn off repeat
            repeatTrackBtn.classList.remove('active');
            socket.emit('playback_control', { action: 'repeat', session_id: sessionId, mode: 'none' });
        } else {
            // Turn on track repeat, disable playlist repeat
            repeatTrackBtn.classList.add('active');
            repeatPlaylistBtn.classList.remove('active');
            socket.emit('playback_control', { action: 'repeat', session_id: sessionId, mode: 'song' });
        }
    };

    repeatPlaylistBtn.onclick = () => {
        const isActive = repeatPlaylistBtn.classList.contains('active');
        if (isActive) {
            // Turn off repeat
            repeatPlaylistBtn.classList.remove('active');
            socket.emit('playback_control', { action: 'repeat', session_id: sessionId, mode: 'none' });
        } else {
            // Turn on playlist repeat, disable track repeat
            repeatPlaylistBtn.classList.add('active');
            repeatTrackBtn.classList.remove('active');
            socket.emit('playback_control', { action: 'repeat', session_id: sessionId, mode: 'list' });
        }
    };
}

volumeSlider.oninput = (e) => {
    const value = parseInt(e.target.value);
    console.log(`Sending volume change: ${value}`);
    socket.emit('volume', { value, session_id: sessionId });
};

// Handle bot state updates
socket.on('connect', () => {
    console.log('Connected to server');
    socket.emit('bot_state_request', { session_id: sessionId });
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    showError('Lost connection to server. Reconnecting...');
});

socket.on('player_state', function(data) {
    updatePlayerState(data);
});

socket.on('current_playlist', (data) => {
    console.log('Received current playlist:', data);
    if (data.playlist) {
        // Load the current playlist
        loadPlaylistTracks(data.playlist);
        // Select the current track
        if (data.index !== undefined) {
            setTimeout(() => {
                selectTrack(data.index);
            }, 1000); // Small delay to ensure playlist is loaded
        }
    }
});

socket.on('bot_state', function(data) {
    console.log('Bot state update:', data);
    
    // Update UI based on state
    const isPlaying = data.playing || data.state === 'playing';
    const isPaused = data.state === 'paused';
    const hasPlaylist = data.current_playlist !== null;
    
    // Update play/pause button
    playPauseBtn.disabled = !hasPlaylist;
    if (isPlaying) {
        playPauseBtn.querySelector('i').classList.remove('fa-play');
        playPauseBtn.querySelector('i').classList.add('fa-pause');
    } else {
        playPauseBtn.querySelector('i').classList.remove('fa-pause');
        playPauseBtn.querySelector('i').classList.add('fa-play');
    }
    
    // Update controls
    stopBtn.disabled = !isPlaying && !isPaused;
    nextBtn.disabled = !hasPlaylist;
    prevBtn.disabled = !hasPlaylist;
    
    // Update volume slider
    if (data.volume !== undefined) {
        volumeSlider.value = data.volume;
    }
    
    // Update repeat mode buttons
    if (data.repeat) {
        if (data.repeat === 'song') {
            repeatTrackBtn.classList.add('active');
            repeatPlaylistBtn.classList.remove('active');
        } else if (data.repeat === 'list') {
            repeatPlaylistBtn.classList.add('active');
            repeatTrackBtn.classList.remove('active');
        } else {
            repeatTrackBtn.classList.remove('active');
            repeatPlaylistBtn.classList.remove('active');
        }
    }
    
    // Highlight active playlist
    if (data.current_playlist) {
        const playlistItems = document.querySelectorAll('.playlist-item');
        playlistItems.forEach(item => {
            if (item.dataset.name === data.current_playlist) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
        
        // Update playlist title if not already set
        if (playlistTitle && (!playlistTitle.textContent || playlistTitle.textContent === 'Now Playing')) {
            playlistTitle.textContent = data.current_playlist;
        }
    }
    
    // Mark current track in playlist if applicable
    if (data.current_track_index !== undefined && data.current_track_index !== null) {
        const tracks = document.querySelectorAll('.track-item');
        tracks.forEach(track => track.classList.remove('active'));
        
        // Find track with matching index and mark as active
        const activeTrack = document.querySelector(`.track-item[data-index="${data.current_track_index}"]`);
        if (activeTrack) {
            activeTrack.classList.add('active');
            
            // If we're in a different view, automatically scroll to the active track
            if (!isElementInViewport(activeTrack)) {
                activeTrack.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }
    
    // Update now playing display
    if (currentTrack) {
        if (data.current_track) {
            currentTrack.textContent = data.current_track;
        } else if (hasPlaylist) {
            currentTrack.textContent = 'Ready to play';
        } else {
            currentTrack.textContent = 'No track playing';
        }
    }
    
    // Store current state
    currentState = data;
}

// Helper function to check if element is in viewport
function isElementInViewport(el) {
    if (!el) {
        return false;
    }
    
    const rect = el.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}
