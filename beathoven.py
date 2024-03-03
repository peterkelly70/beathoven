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
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord.ext.commands import BadArgument
from dotenv import load_dotenv
from enum import Enum
from urllib.parse import urlparse
from pytube import YouTube

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
    "name": None,           # name of the playlist
    "playlist": [],         # holds the playlist, uri's
    "currently_playing": 0, # index of current track
    "duration": 0,          # duration of current track in seconds
    "playlist_type": None   # Local, Radio or Youtube
}
access_dir = None
current_type = PLAYLIST_TYPE.LOCAL.value
repeat = MODE.OFF.value
print(f"repeat: {repeat}")
should_stop = False # Global flag to control playback
skipping = False # Global flag to control skipping
keep_alive_interval = 1.0 # in seconds
stream_start_time = 0 # tracks stream start for stream restart
bot = commands.Bot(command_prefix='!', intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best[ext=m4a]',  # This should give the highest quality audio
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',  # This sets the output file path and naming convention
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # Binding to this can help bypass some ISP restrictions
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',  # Extract audio with ffmpeg
        'preferredcodec': 'm4a',  # Prefer m4a codec
        'preferredquality': '192',  # Set audio quality
    }],
    'prefer_ffmpeg': True,  # Prefer ffmpeg over avconv for audio extraction
    'keepvideo': False
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)



# helper

def count_playlists(playlist_type):
    ext=get_extension(playlist_type)
    playlists_number = len(glob.glob(f'{PLAYLIST_DIR}*.{ext}'))
    print(f"Playlist Directory: {PLAYLIST_DIR}")
    print(f"Number of {playlist_type} playlists: {playlists_number}")
    return playlists_number

def get_playlist():
    # Print the playlist
    global current_playlist
    song_list = ""
    for i, url in enumerate(current_playlist['playlist']):
        if current_playlist['playlist_type'] == PLAYLIST_TYPE.YOUTUBE.value:
            youtube = YouTube(url)
            song_name = youtube.title
        else:
            song_name = os.path.basename(url)  # This removes the path detail and leaves only the song's name

        # Check if the current song is the one that's playing
        if i == current_playlist['currently_playing']:
            song_list += f'{i+1}. **{song_name}**\n'  # Make the currently playing song bold
        else:
            song_list += f'{i+1}. {song_name}\n'  # Append each song to the list

    return song_list
    
def convert_to_ffmpeg_time_format(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

def stream_audio_from_youtube(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
    }
    global ytdl_format_options
    with yt_dlp.YoutubeDL(ytdl_format_options) as ydl:
        info = ydl.extract_info(url, download=False)
        stream_url = info['url']
    
    return info, stream_url

def play_audio_with_ffmpeg(stream_info, stream_url):
    return discord.FFmpegPCMAudio(executable="ffmpeg", source=stream_url)

# determin playlist extension based on playlist type
def get_extension(playlist_type):
    ext=""
    if playlist_type == PLAYLIST_TYPE.LOCAL.value :
        ext= "blp"
    elif playlist_type == PLAYLIST_TYPE.RADIO.value :
        ext= "brp"
    elif playlist_type == PLAYLIST_TYPE.YOUTUBE.value :
        ext= "byp"
    else :
        raise BadArgument(f"{type} is not a valid playlist type")
    return ext
    
    
# function to load a playlist into current_playlist
def load_playlist(playlist_name,playlist_type):
    playlist_type = playlist_type.lower()
    ext=get_extension(playlist_type)
    playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}{ext}")
    global current_playlist
    current_playlist['playlist'] = []
    current_playlist['name']=playlist_name
    current_playlist['playlist_type']=playlist_type
    current_playlist['currently_playing']=0
    current_playlist['duration']=0
    # Load the new playlist
    with open(playlist_path, 'r') as f:
        current_playlist['playlist'] = [line.rstrip() for line in f]

async def wait_until_done(voice_client):
    while voice_client.is_playing() or voice_client.is_paused():
        await asyncio.sleep(1)  # check every second

def strip_basepath(url):
    parsed_url = urlparse(url)
    return os.path.basename(parsed_url.path)

async def send_keep_alive():
    while True:
        # Code to send the keep-alive signal
        global keep_alive_interval
        await asyncio.sleep(keep_alive_interval)  # Pause for the interval duration


# Bot Events

# on join event
@bot.event
async def on_ready():
    print(f'Bot {bot.user.name} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!join to get started."))
    bot.loop.create_task(send_keep_alive())

# bad argument handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.BadArgument):
        await ctx.send(f"Bad argument: {error}\nUse *help* command to see the correct usage.")
    else:
        await ctx.send(f"An error occurred: {error}")

# restart stream
async def restart_stream(voice_client, source_url):
    global stream_start_time
    stream_elapsed_time = t.time()  # Reset the start time

# handle play_back errorshttps://www.youtube.com/watch?v=MrxQ4eOh-yM
    playlist_type = playlist_type.lower()
    if playlist_type == 'yt':
        playlist_type = 'youtube'
    if playlist_type not in [PLAYLIST_TYPE.LOCAL.value, PLAYLIST_TYPE.RADIO.value, PLAYLIST_TYPE.YOUTUBE.value]:
        await ctx.send(f"{playlist_type} is not a valid playlist type.")
        return  
    current_playlist['playlist_type'] = playlist_type
    current_type=playlist_type
    # Clear the current playlist
    current_playlist['playlist'] = []
    await ctx.send(f'Created a new {playlist_type} playlist.')
    await ctx.send(f'Start by !add <url>.')
    await ctx.send(f'When you are ready to play, type !play. ')
    await ctx.send(f'You can also !save <playlistname>.')

@bot.command(name='save', help='Save the current playlist to a file with the specified name')
async def save(ctx, playlist_name):
    # Get the file extension based on the playlist type
    ext = get_extension(current_playlist['playlist_type'])
    # Save the current playlist to a file
    filename=playlist_name+"."+ext
    playlist_path = os.path.join(PLAYLIST_DIR, f"{filename}")
    with open(playlist_path, 'w') as f:
        for song in current_playlist['playlist']:
            f.write(f"{song}\n")
    await ctx.send(f'Saved the current playlist to {filename}.')

@bot.command(name='join', help='Tells the bot to join the voice channel')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send(f"{ctx.author.name} is not connected to a voice channel")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        return await ctx.voice_client.move_to(channel)
    await channel.connect()
    # Send a message to the text channel
    await ctx.send(f"I'm Beathoven, I've joined {channel} and I'm ready to play some music!\nType !help for commands.")
    
@bot.command(name='leave', help='Tells the bot to leave the voice channel')
async def leave(ctx):
    global should_stop
    voice_client = ctx.guild.voice_client
    if voice_client:
        should_stop=True
        await ctx.invoke(bot.get_command('stop'))
        await voice_client.disconnect()


@bot.command(name='code', help='Where do I get this awesome code?')
async def code(ctx):
    voice_client = ctx.guild.voice_client
    await ctx.send("https://github.com/peterkelly70/beathoven")


# Play Songs

async def play_song(ctx):
    try:
        global should_stop
        global current_playlist
        global repeat
        global skipping
        voice_client = ctx.guild.voice_client
        index = current_playlist['currently_playing']
        playlist_type = current_playlist['playlist_type']
        
        if should_stop:
            should_stop = False
            return
        
        if skipping:
            skipping=False
            current_playlist['currently_playing'] = current_playlist['currently_playing']
            return  
        
        if not ctx.voice_client:
            await ctx.send("I'm not connected to a voice channel.")
            return
        if index < 0 or index >= len(current_playlist['playlist']):
            await ctx.invoke(bot.get_command('stop'))
        else:
            song = current_playlist['playlist'][index]
        song_title = ""
        if playlist_type == PLAYLIST_TYPE.YOUTUBE.value :
        # Handle YouTube URLs
            await wait_until_done(voice_client)
            stream_info, stream_url = stream_audio_from_youtube(song)
            audio_source = play_audio_with_ffmpeg(stream_info, stream_url)
            song_title = stream_info['title']
            current_playlist['duration'] = stream_info['duration']
            # stream_start_time = time.time()
            voice_client.play(audio_source, after=lambda e: bot.loop.create_task(handle_playback_error(ctx, voice_client, stream_url, e)) if e else bot.loop.create_task(advance_song(ctx)))
        elif playlist_type == PLAYLIST_TYPE.RADIO.value :
                # Handle radio URLs
                song_title = song  # We'll use URL as title here
                voice_client.play(discord.FFmpegPCMAudio(source=song),after=lambda e: bot.loop.create_task(advance_song(ctx)))
        else:  # We assume song_url is a local filepath
            await wait_until_done(voice_client)
            voice_client.play(discord.FFmpegPCMAudio(source=song),after=lambda e: bot.loop.create_task(advance_song(ctx)))
            song_title = strip_basepath(song)
        await ctx.send('**Now playing:** {}'.format(song_title))
    except Exception as e:
        print(f'Error in play_song function: {str(e)}')  # Replace with your desired error message
        print("Type of Exception:", type(e))
        print("Exception Arguments:", e.args)
        print("Traceback:", traceback.format_exc())
        await ctx.send(f"Error playing song #{index + 1}: {str(e)}")

async def advance_song(ctx):
    try:
        global should_stop
        global skipping
        global current_playlist
        global repeat
        global stream_start_time
    
        # If playlist is empty, just return
        if not current_playlist["playlist"]:
            return
        
        #If we should stop, then let's not advance song.
        if should_stop:
            should_stop = False
            return

        if repeat == MODE.SONG.value :
            current_playlist['currently_playing']=current_playlist['currently_playing']
            await ctx.send("Repeating song: "+tr(current_playlist['currently_playing']+1))
        elif repeat == MODE.LIST.value :
            current_playlist["currently_playing"] = (current_playlist["currently_playing"] + 1) % len(current_playlist["playlist"])
            await ctx.send("Repeating list: "+str(current_playlist['currently_playing']))
        elif skipping:
            current_playlist['currently_playing'] = current_playlist['currently_playing']
            skipping=False
        else : # advance the song, if we are at the last item in the playlist stop
            current_playlist['currently_playing'] = current_playlist['currently_playing'] + 1
            if current_playlist['currently_playing'] >= len(current_playlist['playlist']):
                await ctx.send("Playlist is over.")
                current_playlist['currently_playing'] = 0  # Set to the last valid inde
                await ctx.invoke(bot.get_command('stop'))

        # After the song index has been set, call play_song.
        await play_song(ctx)
    except Exception as e:
        await ctx.send(f"Error advancing song: {str(e)}")


@bot.command(name='new', help='Start a new yuotube playlist')
async def new(ctx, playlist_type: str):
    global current_playlist  # Use the global current_playlist

    # Clear the current playlist
    current_playlist['playlist'] = []

    # Set the playlist type
    current_playlist['playlist_type'] = PLAYLIST_TYPE.YOUTUBE.value

    await ctx.send(f'Started a new youtube playlist.')

        
@bot.command(name='yt', help='Play a youtube url')
async def play_yt(ctx, url): 
    global should_stop
    title=""
    if should_stop:
        should_stop = False
        return title
    
    voice_channel = ctx.message.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_connected():
        await voice_client.move_to(voice_channel)
    else:
        voice_client = await voice_channel.connect()

    # Start a new playlist with youtube url
    print("Starting a new playlist with youtube url")
    await ctx.invoke(bot.get_command('new'), PLAYLIST_TYPE.YOUTUBE.value)
    
    # Add the new URL to the playlist
    print(f"Adding {url} to the playlist")
    await ctx.invoke(bot.get_command('add'), url)
    
    # Start playing the playlist
    print("Starting to play the playlist")
    await play_song(ctx)

        
@bot.command(name='add', help='Add a single url to the current playlist')
async def add_to_playlist(ctx, url): 
    global current_playlist
    
    # Check if url is valid
    if not url:
        await ctx.send("No URL provided.")
        return
    if current_playlist['playlist_type'] != PLAYLIST_TYPE.YOUTUBE.value:
        await ctx.send("Current playlist is not a youtube playlist.")
        return
       
    try:
        result = urlparse(url)
        if all([result.scheme, result.netloc, result.path]):
            # If this is the first URL, clear the current playlist and set the type to YouTube
            if len(current_playlist['playlist']) == 0:
                current_playlist['playlist'] = []
                current_playlist['playlist_type'] = PLAYLIST_TYPE.YOUTUBE.value
                current_playlist['currently_playing'] = 0
                current_type = PLAYLIST_TYPE.YOUTUBE.value
                
            current_playlist['playlist'].append(url)
            youtube = YouTube(url)
            song_name = youtube.title
            await ctx.send(f'Added {song_name} to the playlist.')
        else:
            await ctx.send(f'Invalid URL: {url}')
    except Exception as e:
        print(f'An error occurred while adding {url} to the playlist: {e}')             

@bot.command(name='remove', help='Remove a track from the playlist by its number')
async def remove(ctx, track_number: int):
    global current_playlist  # Use the global current_playlist

    # Subtract 1 from the track number because list indices start at 0
    track_index = track_number - 1

    # Check if the track number is valid
    if track_index < 0 or track_index >= len(current_playlist['playlist']):
        await ctx.send('Invalid track number.')
        return

    # Remove the track from the playlist
    removed_track = current_playlist['playlist'].pop(track_index)
    song_title=YouTube(removed_track).title
    await ctx.send(f'Removed track {track_number}: {song_title}')

    # If the removed track was the last one in the playlist, reset the currently playing track
    if track_index == current_playlist['currently_playing']:
        current_playlist['currently_playing'] = 0

@bot.command(name='list', help='Show available playlists[local,radio,youtube/yt]')
async def playlists(ctx, playlist_type=PLAYLIST_TYPE.LOCAL.value):
    # Check if type is a valid playlist type
    global current_type 
    playlist_type = playlist_type.lower()
    if playlist_type == 'yt':
        playlist_type = 'youtube'
    ext=get_extension(playlist_type)
    current_type = playlist_type
    playlists = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith(ext)]
    playlists = [pl.replace(ext, '') for pl in playlists]
    response = "\n".join(f"{i+1}. {pl}" for i, pl in enumerate(playlists))
    await ctx.send(f"Available {playlist_type} playlists:\n{response}")

@bot.command(name='play', help='Play songs from a playlist [local,radio,youtube/yt] [playlist number]')
async def play_playlist(ctx,*,args=None):
    """
    Play songs from a playlist.

    Args:
        ctx: The context object representing the invocation context.
        args: Optional argument containing the playlist type and number.

    Returns:
        None
    """
   
    global current_playlist
    global current_type
    if args:
        split_args = args.split(" ") 
    else:
        split_args = []
        
    # Case "!play"
    if len(split_args) == 0 :
        playlist_type = current_type
        playlist_number = 0
    # Case "!play 2"
    elif len(split_args) == 1:
        playlist_type = current_type
        playlist_number = int(split_args[0])
    # Case: "!play radio 2"
    elif len(split_args) == 2:
        playlist_type = split_args[0].lower()
        if playlist_type == 'yt':
            playlist_type = 'youtube'
        playlist_number = int(split_args[1])
    # Unrecognized command
    else:
        return await ctx.send(f"Unrecognized command: {args}")

    if playlist_number < 0 or playlist_number > count_playlists(playlist_type):
        await ctx.send("Invalid playlist number!")
        return
  
    # Determine the extension based on the playlist type
    ext=get_extension(playlist_type)
    current_playlist['playlist_type'] = playlist_type
    current_type=playlist_type
    print(f"Playlist type: {playlist_type}")
    print(f"Playlist number: {playlist_number}")
    print(f"Extension: {ext}")
    
    playlists = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith(ext)]
    
    if playlist_number < 0 or playlist_number > count_playlists(playlist_type):
        await ctx.send("Invalid playlist number!!")
        return
    status=check_status(ctx)
    if STATUS.PLAYING.value in status:
        await ctx.invoke(bot.get_command('stop'))
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("Bot must be in a voice channel to play music.")
        return

    if playlist_number != 0:
        playlist_name = playlists[playlist_number - 1].replace(ext, '')
        await ctx.invoke(bot.get_command('stop'))
        current_playlist['playlist'] = []
        load_playlist(playlist_name,current_type)

        playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}{ext}")
        print(f"Playlist path: {playlist_path}")
        
        if not os.path.exists(playlist_path):
            await ctx.send(f"No playlist found named: {playlist_name}")
            return
    
    if current_playlist['playlist']:  
        await ctx.send('Songs in the playlist:')
        song_list=get_playlist()
        print(song_list)
        await ctx.send(song_list)  # Send the complete list to chat    
        await ctx.send("Repeat mode: "+str(repeat))
        await play_song(ctx)
    else:
        await ctx.send('No songs in the playlist')

@bot.command()
async def clear(ctx):
    # Stop the current song
    voice_client = ctx.guild.voice_client
    status=check_status(ctx)
    if STATUS.PLAYING.value in status:
        voice_client.stop()

    # Clear the playlist
    global current_playlist
    current_playlist['playlist'] = []

    await ctx.send("The playlist has been cleared and the current song has been stopped.")

@bot.command(name='show', help='Show the current playlist')
async def show_playlist(ctx):
    global repeat
    if len(current_playlist['playlist']) == 0:
        await ctx.send('The playlist is currently empty.')
    else:
        await ctx.send('Songs in the playlist:')
        song_list=get_playlist()
        await ctx.send(song_list)
        await ctx.send("Repeat mode: "+str(repeat))
    

def check_status(ctx):
    status = []
    voice_client = ctx.guild.voice_client

    # Check if a playlist is currently playing
    if not voice_client.is_playing():
        status.append(STATUS.NOT_PLAYING.value)
    
    if not voice_client:
        status.append(STATUS.NOT_CONNECTED.value)
     
    if voice_client.is_playing():
        status.append(STATUS.PLAYING.value)
   
    if voice_client.is_paused():
        status.append(STATUS.PAUSED.value)
    
    if voice_client:
        status.append(STATUS.CONNECTED.value)  
        
    if not status:
        status.append(STATUS.NOSTATUS.value)

    return status

# Track controls
# Stop command
@bot.command(name='stop', help='stop playing')
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    global should_stop
    global repeat
    status=check_status(ctx)
    if STATUS.PLAYING.value in status:
        voice_client.stop()
        should_stop = True
        repeat = MODE.OFF.value
        await ctx.send('Repeat is off.')
        await ctx.send('Stopping playback.')
        
# Pause command
@bot.command(name='pause', help='Pause song')
async def pause(ctx):
    voice_client = ctx.guild.voice_client
    global should_stop
    status=check_status(ctx)
    if STATUS.PLAYING.value in status:
        voice_client.pause()
        should_stop = True
        await ctx.send('Playback paused.')
    else:
        await ctx.send('Nothing is playing right now.')

# Resume command
@bot.command(name='resume', help='Resumes a song.')
async def resume(ctx):
    voice_client = ctx.guild.voice_client
    status=check_status(ctx)
    if STATUS.PAUSED.value in status:
        voice_client.resume()
        await ctx.send('Playback resumed.')
    else:
        await ctx.send('No song is paused right now.')

# Move to track
@bot.command(name='track', help='Play a specific track')
async def track(ctx, track_number: int):
    global current_playlist  # Use the global current_playlist
    global skipping
    print(f"Destination Track number: {track_number}")

    # Subtract 1 from the track number because list indices start at 0
    track_index = track_number - 2

    # Check if the track number is valid
    if track_index < -1 or track_index >= len(current_playlist['playlist'])-1:
        await ctx.send('Invalid track number.')
        return

    # Update the currently playing track
    current_playlist['currently_playing'] = track_index
    skipping = True 

    # Stop the current song and play the new one
    ctx.voice_client.stop()
    await wait_until_done(ctx.voice_client)
    await play_song(ctx)

# Skip track
@bot.command(name='skip', help='Skip song')
async def skip(ctx, num_to_skip: int = 1):
    global skipping
    track_index = current_playlist['currently_playing'] + num_to_skip
    await ctx.invoke(bot.get_command('track'), track_index+1)

# Back, call skip with a negative number    
@bot.command(name='back', help='Go back to a previous song')
async def back(ctx, num_to_back: int = 1):
    track_index = current_playlist['currently_playing'] - num_to_back 
    await ctx.invoke(bot.get_command('track'),track_index+1)

@bot.command(name='restart', help='Restart the current song')
async def restart(ctx):
    voice_client = ctx.guild.voice_client
    status=check_status(ctx)
    if STATUS.NOT_PLAYING in status:
        await ctx.send("No song is currently playing.")
    else:
        voice_client.stop()
        await wait_until_done(voice_client)
        bot.loop.create_task(play_song(ctx))
    
@bot.command(name='repeat', help='Tells the bot to repeat the song/list or not')
async def repeat(ctx, mode):
    global repeat
    mode = mode.upper()
    status=check_status(ctx)
    if STATUS.NOT_CONNECTED.value in status:
        await ctx.send(STATUS.NOT_CONNECTED.value)
    elif STATUS.NOT_PLAYING.value in status:
        await ctx.send(STATUS.NOT_PLAYING.value)
    elif MODE.OFF.value in mode: 
        repeat = MODE.OFF.value
    elif MODE.SONG.value in mode:
        repeat = MODE.SONG.value
    elif MODE.LIST.value in mode:
        repeat = MODE.LIST.value
    else:
        await ctx.send("no such mode for Repeat [off,song,list]")
    await ctx.send("Playback mode set: "+repeat)
                       
# Volume controls
@bot.command(name='volume', help='Change Volume of song')
async def volume(ctx, vol: int):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    # Ensure volume is within 0-100
    if not 0 <= vol <= 100:
        return await ctx.send('Volume must be between 0 and 100.')
    else:
        previous_volume = voice.source.volume  # store previous volume
        voice.source.volume =  vol/100   # set volume

    # NOTE: discord.FFmpegPCMAudio provides a volume argument when creating the audio source. 
    # You'll need to create a new audio source with this value and update your player to use this.
    # audio_source = discord.FFmpegPCMAudio(song_url, volume=vol/100)  # volume should be a float between 0 and 1

    #voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    #voice.source = audio_source  # Update the audio source with new volume

    await ctx.send(f'Volume has been set to {vol}.')
    await ctx.send(f'Restart Song for new Volume.')

@bot.command(name='mute', help='Mute the bot')
async def mute(ctx):
    global previous_volume
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice:
        previous_volume = voice.source.volume  # store previous volume
        voice.source.volume = 0.0  # mute
        await ctx.send('Muted.')
    else:
        await ctx.send('Bot is not connected to a voice channel.')


@bot.command(name='unmute', help='Unmute the bot')
async def unmute(ctx):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice:
        voice.source.volume = previous_volume  # restore volume
        await ctx.send('Unmuted.')
    else:
        await ctx.send('Bot is not connected to a voice channel.')




def sort_key(filename):
    # Extract the first number in the filename and use it as the sorting key
    match = re.match(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    else:
        return float('inf')  # If no number is found, put the file at the end

@bot.command(name='man', help='Provide an in-depth overview of a specific topic')
async def man(ctx, command=None, number=None):
    global access_dir
    if command is None:
        # If no command is provided, show the .quickstart.md
        with open(os.path.join(MAN_DIR, '.quickstart.md'), 'r') as f:
            await ctx.send(f.read())
    elif command == 'index':
        # If the command is 'index', show the top headings (directories), excluding hidden ones
        dirs = [name for name in os.listdir(MAN_DIR) if os.path.isdir(os.path.join(MAN_DIR, name)) and not name.startswith('.')]
        await ctx.send('**Top Headings:**\n' + '\n'.join(f'{i+1}. {d}' for i, d in enumerate(sorted(dirs, key=sort_key))))
    elif command == 'access' and number is not None:
        # If the command is 'access' and a number is provided, store the directory to access
        dirs = [name for name in os.listdir(MAN_DIR) if os.path.isdir(os.path.join(MAN_DIR, name)) and not name.startswith('.')]
        try:
            access_dir = sorted(dirs, key=sort_key)[int(number) - 1]
            # Show the .introduction.md file in the accessed directory
            with open(os.path.join(MAN_DIR, access_dir, '.introduction.md'), 'r') as f:
                await ctx.send(f.read())
            # Show the list of topic files in the accessed directory, excluding hidden ones
            topics = [f[:-3] for f in os.listdir(os.path.join(MAN_DIR, access_dir)) if f.endswith('.md') and not f.startswith('.')]
            await ctx.send('**Available topics:**\n' + '\n'.join(f'{i+1}. {t}' for i, t in enumerate(sorted(topics, key=sort_key))))
        except IndexError:
            await ctx.send(f'Invalid directory number: {number}')
        except FileNotFoundError:
            await ctx.send(f'No .introduction.md file found in directory: {access_dir}')
    elif command == 'topics' and access_dir is not None:
        # If the command is 'topics', show the list of topics in numerical order in the accessed directory
        topics = [f[:-3] for f in os.listdir(os.path.join(MAN_DIR, access_dir)) if f.endswith('.md') and not f.startswith('.')]
        await ctx.send('**Available topics:**\n' + '\n'.join(f'{i+1}. {t}' for i, t in enumerate(sorted(topics, key=sort_key))))
    elif command == 'topic' and number is not None and access_dir is not None:
        # If the command is 'topic' and a number is provided, show the corresponding file in the accessed directory
        topics = [f for f in os.listdir(os.path.join(MAN_DIR, access_dir)) if f.endswith('.md') and not f.startswith('.')]
        try:
            with open(os.path.join(MAN_DIR, access_dir, sorted(topics, key=sort_key)[int(number) - 1]), 'r') as f:
                await ctx.send(f.read())
        except IndexError:
            await ctx.send(f'Invalid topic number: {number}')
    else:
        await ctx.send('Invalid command or missing number/directory.')

bot.run(TOKEN)