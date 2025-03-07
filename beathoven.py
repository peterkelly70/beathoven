#!/usr/bin/env python3
import discord
import os
import re
import glob
import traceback
import yt_dlp
import ffmpeg
import time
import asyncio
import dotenv
import enum
import eyed3
import logging
from logging.handlers import TimedRotatingFileHandler
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord.ext.commands import BadArgument
from dotenv import load_dotenv
from enum import Enum
from urllib.parse import urlparse

# Setup logging with daily rotation
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler = TimedRotatingFileHandler('beathoven.log', when='midnight', interval=1, backupCount=7)
log_handler.setFormatter(log_formatter)
logger = logging.getLogger('Beathoven')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

class PLAYLIST_TYPE(Enum):
    LOCAL = "local"
    RADIO = "radio"
    YOUTUBE = "youtube"

class MODE(Enum):
    OFF = "OFF"
    SONG = "SONG"
    LIST = "LIST"

class STATUS(Enum):
    NOT_PLAYING = "Nothing is currently playing."
    NOT_CONNECTED = "Beathoven is not connected to voice Channel."
    NO_SONG = "No song is currently playing."
    NO_PLAYLIST = "Playlist is empty."
    CONNECTED = "Beathoven is connected to a voice channel."
    PLAYING = "Beathoven is currently playing a song."
    PAUSED = "Beathoven is currently paused."
    NO_STATUS = ""

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
PLAYLIST_DIR = os.getenv('PLAYLIST_DIR')
MAN_DIR = os.getenv('MAN_DIR')
PREFIX = '!'
intents = discord.Intents().all()

# Global variables
previous_volume = 0.5
current_playlist = {
    "name": None,
    "playlist": [],
    "currently_playing": 0,
    "duration": 0,
    "playlist_type": None
}
access_dir = None
current_type = PLAYLIST_TYPE.LOCAL.value
repeat = MODE.OFF.value
should_stop = False
skipping = False
keep_alive_interval = 1.0
stream_start_time = 0
bot = commands.Bot(command_prefix='!', intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'prefer_ffmpeg': True,
    'keepvideo': False
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'  # Ensure FFmpeg reconnects
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Helper functions
def count_playlists(playlist_type):
    ext = get_extension(playlist_type)
    playlists_number = len(glob.glob(f'{PLAYLIST_DIR}*.{ext}'))
    return playlists_number

def get_playlist():
    global current_playlist
    song_list = ""
    for i, url in enumerate(current_playlist['playlist']):
        if current_playlist['playlist_type'] == PLAYLIST_TYPE.YOUTUBE.value:
            try:
                with yt_dlp.YoutubeDL(ytdl_format_options) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info is None:
                        song_name = f"Unavailable ({url})"
                    else:
                        song_name = info.get('title', f"Unknown Title ({url})")
            except Exception as e:
                logger.error(f"Error getting title for {url}: {str(e)}")
                song_name = f"Error Retrieving Title ({url})"
        else:
            song_name = os.path.basename(url)
        
        if i == current_playlist['currently_playing']:
            song_list += f'{i+1}. **{song_name}**\n'
        else:
            song_list += f'{i+1}. {song_name}\n'
    return song_list

def convert_to_ffmpeg_time_format(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

def stream_audio_from_youtube(url):
    try:
        with yt_dlp.YoutubeDL(ytdl_format_options) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise ValueError("No info extracted from yt_dlp")
            stream_url = info.get('url')
            if not stream_url:
                raise ValueError("No stream URL found in info")
            logger.info(f"Extracted stream URL for {url}: {stream_url}")
        return info, stream_url
    except Exception as e:
        logger.error(f"Error in stream_audio_from_youtube for {url}: {str(e)}")
        return None, None

def play_audio_with_ffmpeg(stream_info, stream_url):
    try:
        audio_source = discord.FFmpegPCMAudio(source=stream_url, executable="ffmpeg", **ffmpeg_options)
        logger.info(f"Created FFmpegPCMAudio for stream: {stream_url}")
        return audio_source
    except Exception as e:
        logger.error(f"Error creating FFmpegPCMAudio: {str(e)}")
        raise

def get_extension(playlist_type):
    if playlist_type == PLAYLIST_TYPE.LOCAL.value:
        return "blp"
    elif playlist_type == PLAYLIST_TYPE.RADIO.value:
        return "brp"
    elif playlist_type == PLAYLIST_TYPE.YOUTUBE.value:
        return "byp"
    else:
        raise BadArgument(f"{playlist_type} is not a valid playlist type")

def load_playlist(playlist_name, playlist_type):
    playlist_type = playlist_type.lower()
    ext = get_extension(playlist_type)
    playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}{ext}")
    global current_playlist
    current_playlist['playlist'] = []
    current_playlist['name'] = playlist_name
    current_playlist['playlist_type'] = playlist_type
    current_playlist['currently_playing'] = 0
    current_playlist['duration'] = 0
    try:
        with open(playlist_path, 'r') as f:
            current_playlist['playlist'] = [line.rstrip() for line in f]
    except FileNotFoundError:
        logger.error(f"Playlist file not found: {playlist_path}")
        raise

async def wait_until_done(voice_client):
    while voice_client.is_playing() or voice_client.is_paused():
        await asyncio.sleep(0.5)

def strip_basepath(url):
    parsed_url = urlparse(url)
    return os.path.basename(parsed_url.path)

async def send_keep_alive():
    while True:
        await asyncio.sleep(keep_alive_interval)

# Bot Events
@bot.event
async def on_ready():
    logger.info(f'Bot {bot.user.name} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!join to get started."))
    bot.loop.create_task(send_keep_alive())

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.BadArgument):
        await ctx.send(f"Bad argument: {error}\nUse !help command to see the correct usage.")
    else:
        await ctx.send(f"An error occurred: {error}")
        logger.error(f"Command error: {str(error)}")

async def play_song(ctx):
    try:
        global should_stop, current_playlist, repeat, skipping
        voice_client = ctx.guild.voice_client
        
        if not voice_client:
            await ctx.send("Not connected to a voice channel.")
            logger.warning("Voice client not connected.")
            return
            
        if should_stop:
            should_stop = False
            logger.info("Playback stopped by should_stop flag.")
            return
            
        if skipping:
            skipping = False
            logger.info("Skipping to next track.")
            
        index = current_playlist['currently_playing']
        if not (0 <= index < len(current_playlist['playlist'])):
            await ctx.send("Invalid playlist position.")
            logger.warning(f"Invalid playlist index: {index}")
            return await ctx.invoke(bot.get_command('stop'))

        song = current_playlist['playlist'][index]
        song_title = ""
        
        logger.info(f"Attempting to play song #{index + 1}: {song}")
        
        if current_playlist['playlist_type'] == PLAYLIST_TYPE.YOUTUBE.value:
            stream_info, stream_url = stream_audio_from_youtube(song)
            if stream_info is None or stream_url is None:
                await ctx.send(f"Failed to retrieve stream for {song}. Skipping...")
                logger.error(f"Stream info or URL is None for {song}")
                return await advance_song(ctx)
            try:
                audio_source = play_audio_with_ffmpeg(stream_info, stream_url)
                song_title = stream_info.get('title', f"Unknown Title ({song})")
                current_playlist['duration'] = stream_info.get('duration', 0)
                voice_client.play(audio_source, after=lambda e: bot.loop.create_task(
                    handle_playback_error(ctx, voice_client, stream_url, e) if e else advance_song(ctx)))
                logger.info(f"Started YouTube playback: {song_title} (Duration: {current_playlist['duration']}s)")
                # Wait briefly to ensure playback starts
                await asyncio.sleep(2)
                if not voice_client.is_playing():
                    logger.warning(f"Playback not started for {song_title}")
                    await ctx.send(f"Playback failed to start for {song_title}. Skipping...")
                    voice_client.stop()
                    return await advance_song(ctx)
            except Exception as e:
                await ctx.send(f"Failed to stream YouTube video: {str(e)}")
                logger.error(f"YouTube streaming error: {str(e)}")
                return await advance_song(ctx)
            
        elif current_playlist['playlist_type'] == PLAYLIST_TYPE.RADIO.value:
            song_title = song
            voice_client.play(discord.FFmpegPCMAudio(source=song), 
                            after=lambda e: bot.loop.create_task(advance_song(ctx)))
            logger.info(f"Playing radio stream: {song}")
                            
        else:  # Local files
            song_title = strip_basepath(song)
            if not os.path.exists(song):
                await ctx.send(f"Local file not found: {song}")
                logger.warning(f"File not found: {song}")
                return
            voice_client.play(discord.FFmpegPCMAudio(source=song),
                            after=lambda e: bot.loop.create_task(advance_song(ctx)))
            logger.info(f"Playing local file: {song}")
                            
        await ctx.send(f'**Now playing:** {song_title} (#{index + 1}/{len(current_playlist["playlist"])})')
        logger.info(f"Playback message sent for: {song_title}")
        
    except Exception as e:
        logger.error(f'Error in play_song: {str(e)}')
        logger.error(traceback.format_exc())
        await ctx.send(f"Error playing song #{index + 1}: {str(e)}")

async def handle_playback_error(ctx, voice_client, stream_url, error):
    await ctx.send(f"Playback error: {str(error)}")
    logger.error(f"Playback error occurred: {str(error)}")
    await advance_song(ctx)

async def advance_song(ctx):
    try:
        global should_stop, skipping, current_playlist, repeat
        
        if not current_playlist["playlist"]:
            await ctx.send("Playlist is empty.")
            logger.warning("Playlist is empty.")
            return
            
        if should_stop:
            should_stop = False
            logger.info("Advancing stopped by should_stop flag.")
            return

        voice_client = ctx.guild.voice_client
        if not voice_client:
            logger.warning("Voice client disconnected during advance.")
            return

        if repeat == MODE.SONG.value:
            await ctx.send(f"Repeating song #{current_playlist['currently_playing'] + 1}")
            logger.info(f"Repeat song mode: #{current_playlist['currently_playing'] + 1}")
        elif repeat == MODE.LIST.value:
            current_playlist["currently_playing"] = (current_playlist["currently_playing"] + 1) % len(current_playlist["playlist"])
            await ctx.send(f"Playing next song in list: #{current_playlist['currently_playing'] + 1}")
            logger.info(f"Repeat list mode: advancing to #{current_playlist['currently_playing'] + 1}")
        else:  # MODE.OFF
            current_playlist["currently_playing"] += 1
            if current_playlist["currently_playing"] >= len(current_playlist["playlist"]):
                await ctx.send("Playlist has ended.")
                logger.info("Playlist has ended.")
                current_playlist["currently_playing"] = 0
                repeat = MODE.OFF.value
                return await ctx.invoke(bot.get_command('stop'))

        skipping = False
        logger.info(f"Advancing to song #{current_playlist['currently_playing'] + 1}")
        await play_song(ctx)
        
    except Exception as e:
        logger.error(f"Error in advance_song: {str(e)}")
        await ctx.send(f"Error advancing song: {str(e)}")

@bot.command(name='join', help='Tells the bot to join the voice channel')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send(f"{ctx.author.name} is not connected to a voice channel")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"I'm Beathoven, I've joined {channel} and I'm ready to play some music!\nType !help for commands.")
    logger.info(f"Joined voice channel: {channel.name}")

@bot.command(name='leave', help='Tells the bot to leave the voice channel')
async def leave(ctx):
    global should_stop
    voice_client = ctx.guild.voice_client
    if voice_client:
        should_stop = True
        await ctx.invoke(bot.get_command('stop'))
        await voice_client.disconnect()
        logger.info("Left voice channel.")

@bot.command(name='code', help='Where do I get this awesome code?')
async def code(ctx):
    await ctx.send("https://github.com/peterkelly70/beathoven")

@bot.command(name='new', help='Start a new playlist')
async def new(ctx, playlist_type: str):
    global current_playlist
    playlist_type = playlist_type.lower()
    if playlist_type == 'yt':
        playlist_type = 'youtube'
    if playlist_type not in [PLAYLIST_TYPE.LOCAL.value, PLAYLIST_TYPE.RADIO.value, PLAYLIST_TYPE.YOUTUBE.value]:
        await ctx.send(f"{playlist_type} is not a valid playlist type.")
        return
    current_playlist['playlist'] = []
    current_playlist['playlist_type'] = playlist_type
    current_playlist['currently_playing'] = 0
    await ctx.send(f'Started a new {playlist_type} playlist.')
    logger.info(f"Started new {playlist_type} playlist.")

@bot.command(name='yt', help='Play a youtube url')
async def play_yt(ctx, url): 
    global should_stop
    if should_stop:
        should_stop = False
        return
    
    voice_channel = ctx.message.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_connected():
        await voice_client.move_to(voice_channel)
    else:
        voice_client = await voice_channel.connect()

    await ctx.invoke(bot.get_command('new'), PLAYLIST_TYPE.YOUTUBE.value)
    await ctx.invoke(bot.get_command('add'), url)
    await play_song(ctx)

@bot.command(name='add', help='Add a single url to the current playlist')
async def add_to_playlist(ctx, url): 
    global current_playlist
    
    if not url:
        await ctx.send("No URL provided.")
        return
        
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc, result.path]):
            await ctx.send(f'Invalid URL: {url}')
            return

        if current_playlist['playlist_type'] is None:
            current_playlist['playlist_type'] = PLAYLIST_TYPE.YOUTUBE.value
        elif current_playlist['playlist_type'] != PLAYLIST_TYPE.YOUTUBE.value:
            await ctx.send("Current playlist is not a youtube playlist.")
            return
                
        with yt_dlp.YoutubeDL(ytdl_format_options) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise ValueError("Failed to extract info from URL")
            song_name = info.get('title', f"Unknown Title ({url})")

        current_playlist['playlist'].append(url)
        await ctx.send(f'Added {song_name} to the playlist.')
        logger.info(f"Added {song_name} to playlist: {url}")
        
    except Exception as e:
        await ctx.send(f'Error adding {url} to the playlist: {str(e)}')
        logger.error(f"Error adding {url} to playlist: {str(e)}")

@bot.command(name='remove', help='Remove a track from the playlist by its number')
async def remove(ctx, track_number: int):
    global current_playlist
    track_index = track_number - 1

    if not (0 <= track_index < len(current_playlist['playlist'])):
        await ctx.send('Invalid track number.')
        return

    removed_track = current_playlist['playlist'].pop(track_index)
    if current_playlist['playlist_type'] == PLAYLIST_TYPE.YOUTUBE.value:
        try:
            with yt_dlp.YoutubeDL(ytdl_format_options) as ydl:
                info = ydl.extract_info(removed_track, download=False)
                song_title = info.get('title', f"Unknown Title ({removed_track})") if info else f"Unavailable ({removed_track})"
        except Exception as e:
            song_title = f"Error Retrieving Title ({removed_track})"
            logger.error(f"Error getting title for removed track {removed_track}: {str(e)}")
    else:
        song_title = strip_basepath(removed_track)
    await ctx.send(f'Removed track {track_number}: {song_title}')
    logger.info(f"Removed track {track_number}: {song_title}")

    if track_index <= current_playlist['currently_playing']:
        current_playlist['currently_playing'] = max(0, current_playlist['currently_playing'] - 1)

@bot.command(name='list', help='Show available playlists[local,radio,youtube/yt]')
async def playlists(ctx, playlist_type=PLAYLIST_TYPE.LOCAL.value):
    global current_type 
    playlist_type = playlist_type.lower()
    if playlist_type == 'yt':
        playlist_type = 'youtube'
    ext = get_extension(playlist_type)
    current_type = playlist_type
    playlists = [f.replace(ext, '') for f in os.listdir(PLAYLIST_DIR) if f.endswith(ext)]
    response = "\n".join(f"{i+1}. {pl}" for i, pl in enumerate(playlists))
    await ctx.send(f"Available {playlist_type} playlists:\n{response}")

@bot.command(name='play', help='Play songs from a playlist [local,radio,youtube/yt] [playlist number]')
async def play_playlist(ctx, *, args=None):
    global current_playlist, current_type
    
    if args:
        split_args = args.split(" ")
    else:
        split_args = []

    if len(split_args) == 0:
        playlist_type = current_type
        playlist_number = 0
    elif len(split_args) == 1:
        playlist_type = current_type
        playlist_number = int(split_args[0])
    elif len(split_args) == 2:
        playlist_type = split_args[0].lower()
        if playlist_type == 'yt':
            playlist_type = 'youtube'
        playlist_number = int(split_args[1])
    else:
        return await ctx.send(f"Unrecognized command: {args}")

    if playlist_number < 0 or playlist_number > count_playlists(playlist_type):
        await ctx.send("Invalid playlist number!")
        return

    ext = get_extension(playlist_type)
    current_playlist['playlist_type'] = playlist_type
    current_type = playlist_type
    
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("Bot must be in a voice channel to play music.")
        return

    if playlist_number != 0:
        playlists = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith(ext)]
        if playlist_number > len(playlists):
            await ctx.send("Invalid playlist number!")
            return
        playlist_name = playlists[playlist_number - 1].replace(ext, '')
        await ctx.invoke(bot.get_command('stop'))
        current_playlist['playlist'] = []
        load_playlist(playlist_name, current_type)

    if current_playlist['playlist']:  
        await ctx.send('Songs in the playlist:')
        await ctx.send(get_playlist())
        await ctx.send(f"Repeat mode: {repeat}")
        await play_song(ctx)
    else:
        await ctx.send('No songs in the playlist')

@bot.command()
async def clear(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await asyncio.sleep(1)
    
    global current_playlist
    current_playlist['playlist'] = []
    current_playlist['currently_playing'] = 0
    await ctx.send("The playlist has been cleared and the current song has been stopped.")
    logger.info("Playlist cleared.")

@bot.command(name='show', help='Show the current playlist')
async def show_playlist(ctx):
    global repeat
    if not current_playlist['playlist']:
        await ctx.send('The playlist is currently empty.')
    else:
        await ctx.send('Songs in the playlist:')
        await ctx.send(get_playlist())
        await ctx.send(f"Repeat mode: {repeat}")

def check_status(ctx):
    status = []
    voice_client = ctx.guild.voice_client

    if not voice_client:
        status.append(STATUS.NOT_CONNECTED.value)
    else:
        if voice_client.is_playing():
            status.append(STATUS.PLAYING.value)
        elif voice_client.is_paused():
            status.append(STATUS.PAUSED.value)
        else:
            status.append(STATUS.NOT_PLAYING.value)
        status.append(STATUS.CONNECTED.value)
    
    if not current_playlist['playlist']:
        status.append(STATUS.NO_PLAYLIST.value)
    
    if not status:
        status.append(STATUS.NO_STATUS.value)
    
    return status

@bot.command(name='stop', help='stop playing')
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    global should_stop, repeat
    status = check_status(ctx)
    if STATUS.PLAYING.value in status or STATUS.PAUSED.value in status:
        voice_client.stop()
        should_stop = True
        repeat = MODE.OFF.value
        await ctx.send('Repeat is off.')
        await ctx.send('Stopping playback.')
        logger.info("Playback stopped.")

@bot.command(name='pause', help='Pause song')
async def pause(ctx):
    voice_client = ctx.guild.voice_client
    status = check_status(ctx)
    if STATUS.PLAYING.value in status:
        voice_client.pause()
        await ctx.send('Playback paused.')
        logger.info("Playback paused.")
    else:
        await ctx.send('Nothing is playing right now.')

@bot.command(name='resume', help='Resumes a song.')
async def resume(ctx):
    voice_client = ctx.guild.voice_client
    status = check_status(ctx)
    if STATUS.PAUSED.value in status:
        voice_client.resume()
        await ctx.send('Playback resumed.')
        logger.info("Playback resumed.")
    else:
        await ctx.send('No song is paused right now.')

@bot.command(name='track', help='Play a specific track')
async def track(ctx, track_number: int):
    global current_playlist, skipping
    
    track_index = track_number - 1
    if not (0 <= track_index < len(current_playlist['playlist'])):
        await ctx.send(f'Invalid track number. Please choose a number between 1 and {len(current_playlist["playlist"])}')
        return

    current_playlist['currently_playing'] = track_index
    skipping = True
    
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
    await wait_until_done(voice_client)
    await play_song(ctx)
    logger.info(f"Switched to track #{track_number}")

@bot.command(name='skip', help='Skip forward n songs (default 1)')
async def skip(ctx, num_to_skip: int = 1):
    global current_playlist
    target_index = current_playlist['currently_playing'] + num_to_skip
    
    if target_index >= len(current_playlist['playlist']):
        await ctx.send("Cannot skip beyond playlist end.")
        return await ctx.invoke(bot.get_command('stop'))
        
    await ctx.invoke(bot.get_command('track'), target_index + 1)

@bot.command(name='back', help='Go back n songs (default 1)')
async def back(ctx, num_to_back: int = 1):
    global current_playlist
    target_index = current_playlist['currently_playing'] - num_to_back
    
    if target_index < 0:
        await ctx.send("Cannot go back before playlist start.")
        target_index = 0
        
    await ctx.invoke(bot.get_command('track'), target_index + 1)

@bot.command(name='restart', help='Restart the current song')
async def restart(ctx):
    voice_client = ctx.guild.voice_client
    status = check_status(ctx)
    if STATUS.NOT_PLAYING.value in status and STATUS.PAUSED.value not in status:
        await ctx.send("No song is currently playing.")
    else:
        voice_client.stop()
        await wait_until_done(voice_client)
        await play_song(ctx)
        logger.info("Restarted current song.")

@bot.command(name='repeat', help='Set repeat mode: off, song, or list')
async def repeat_command(ctx, mode: str):
    global repeat
    mode = mode.upper()
    
    status = check_status(ctx)
    if STATUS.NOT_CONNECTED.value in status:
        await ctx.send(STATUS.NOT_CONNECTED.value)
        return
    if STATUS.NOT_PLAYING.value in status and STATUS.PAUSED.value not in status:
        await ctx.send(STATUS.NOT_PLAYING.value)
        return

    if mode == MODE.OFF.value:
        repeat = MODE.OFF.value
        await ctx.send("Repeat is now off")
    elif mode == MODE.SONG.value:
        repeat = MODE.SONG.value
        await ctx.send("Repeating current song")
    elif mode == MODE.LIST.value:
        repeat = MODE.LIST.value
        await ctx.send("Repeating playlist")
    else:
        await ctx.send("Invalid mode. Use: off, song, or list")
        return
    
    await ctx.send(f"Current repeat mode: {repeat}")
    logger.info(f"Repeat mode set to: {repeat}")

@bot.command(name='volume', help='Change Volume of song')
async def volume(ctx, vol: int):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not voice:
        await ctx.send('Bot is not connected to a voice channel.')
        return
    if not 0 <= vol <= 100:
        return await ctx.send('Volume must be between 0 and 100.')
    
    voice.source.volume = vol / 100
    await ctx.send(f'Volume set to {vol}%.')
    logger.info(f"Volume set to {vol}%")

@bot.command(name='mute', help='Mute the bot')
async def mute(ctx):
    global previous_volume
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice:
        previous_volume = voice.source.volume
        voice.source.volume = 0.0
        await ctx.send('Muted.')
        logger.info("Bot muted.")
    else:
        await ctx.send('Bot is not connected to a voice channel.')

@bot.command(name='unmute', help='Unmute the bot')
async def unmute(ctx):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice:
        voice.source.volume = previous_volume
        await ctx.send('Unmuted.')
        logger.info("Bot unmuted.")
    else:
        await ctx.send('Bot is not connected to a voice channel.')

@bot.command(name='save', help='Save the current playlist to a file with the specified name')
async def save(ctx, playlist_name):
    ext = get_extension(current_playlist['playlist_type'])
    filename = f"{playlist_name}.{ext}"
    playlist_path = os.path.join(PLAYLIST_DIR, filename)
    with open(playlist_path, 'w') as f:
        for song in current_playlist['playlist']:
            f.write(f"{song}\n")
    await ctx.send(f'Saved the current playlist to {filename}.')
    logger.info(f"Saved playlist to {filename}")

@bot.command(name='status', help='Check bot connection status')
async def status(ctx):
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("Not connected to a voice channel.")
        logger.info("Status: Not connected")
    else:
        await ctx.send(f"Connected to {voice_client.channel.name}")
        logger.info(f"Status: Connected to {voice_client.channel.name}")
        logger.info(f"Playing: {voice_client.is_playing()}")
        logger.info(f"Paused: {voice_client.is_paused()}")

def sort_key(filename):
    match = re.match(r'(\d+)', filename)
    return int(match.group(1)) if match else float('inf')

@bot.command(name='man', help='Provide an in-depth overview of a specific topic')
async def man(ctx, command=None, number=None):
    global access_dir
    if command is None:
        with open(os.path.join(MAN_DIR, '.quickstart.md'), 'r') as f:
            await ctx.send(f.read())
    elif command == 'index':
        dirs = [name for name in os.listdir(MAN_DIR) if os.path.isdir(os.path.join(MAN_DIR, name)) and not name.startswith('.')]
        await ctx.send('**Top Headings:**\n' + '\n'.join(f'{i+1}. {d}' for i, d in enumerate(sorted(dirs, key=sort_key))))
    elif command == 'access' and number is not None:
        dirs = [name for name in os.listdir(MAN_DIR) if os.path.isdir(os.path.join(MAN_DIR, name)) and not name.startswith('.')]
        try:
            access_dir = sorted(dirs, key=sort_key)[int(number) - 1]
            with open(os.path.join(MAN_DIR, access_dir, '.introduction.md'), 'r') as f:
                await ctx.send(f.read())
            topics = [f[:-3] for f in os.listdir(os.path.join(MAN_DIR, access_dir)) if f.endswith('.md') and not f.startswith('.')]
            await ctx.send('**Available topics:**\n' + '\n'.join(f'{i+1}. {t}' for i, t in enumerate(sorted(topics, key=sort_key))))
        except IndexError:
            await ctx.send(f'Invalid directory number: {number}')
        except FileNotFoundError:
            await ctx.send(f'No .introduction.md file found in directory: {access_dir}')
    elif command == 'topics' and access_dir is not None:
        topics = [f[:-3] for f in os.listdir(os.path.join(MAN_DIR, access_dir)) if f.endswith('.md') and not f.startswith('.')]
        await ctx.send('**Available topics:**\n' + '\n'.join(f'{i+1}. {t}' for i, t in enumerate(sorted(topics, key=sort_key))))
    elif command == 'topic' and number is not None and access_dir is not None:
        topics = [f for f in os.listdir(os.path.join(MAN_DIR, access_dir)) if f.endswith('.md') and not f.startswith('.')]
        try:
            with open(os.path.join(MAN_DIR, access_dir, sorted(topics, key=sort_key)[int(number) - 1]), 'r') as f:
                await ctx.send(f.read())
        except IndexError:
            await ctx.send(f'Invalid topic number: {number}')
    else:
        await ctx.send('Invalid command or missing number/directory.')

bot.run(TOKEN)