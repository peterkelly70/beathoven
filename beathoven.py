#!/usr/bin/env python3
import discord
import os
import traceback
import yt_dlp
import ffmpeg
import time
import asyncio
import dotenv
import enum
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord.ext.commands import BadArgument
from dotenv import load_dotenv
from enum import Enum
from urllib.parse import urlparse


class REPEAT(Enum):
    OFF = "OFF"
    SONG = "SONG"
    LIST = "LIST"

class PLAYLIST_TYPE(Enum):
    LOCAL = "local"
    RADIO = "radio"
    YOUTUBE = "youtube"


load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
PLAYLIST_DIR = os.getenv('PLAYLIST_DIR')
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

current_type = PLAYLIST_TYPE.LOCAL.value
repeat = REPEAT.OFF
should_stop = False # Global flag to control playback
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
    ext=get_extension(playlist_type)
    playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}{ext}")
    global current_playlist
    current_playlist['name']=playlist_name
    current_playlist['playlist_type']=playlist_type
    current_playlist['currently_playing']=0
    current_playlist['duration']=0
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
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!help for commands"))
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
    stream_elapsed_time = time.time() - stream_start_time
    seek_time = convert_to_ffmpeg_time_format(stream_elapsed_time)

    audio_source = FFmpegPCMAudio(source_url, before_options=f'-ss {seek_time}')
    voice_client.play(audio_source, after=lambda e: handle_stream_end(e))
    stream_start_time = time.time()  # Reset the start time

# handle play_back errors
async def handle_playback_error(ctx, voice_client, source_url, exception):
    print(f'Error when playing {source_url}. Reason: {exception}')
    await restart_stream(voice_client, source_url)
    bot.loop.create_task(play_song(ctx, voice_client))

# Bot commands

@bot.command(name='join', help='Tells the bot to join the voice channel')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send(f"{ctx.author.name} is not connected to a voice channel")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        return await ctx.voice_client.move_to(channel)
    await channel.connect()

@bot.command(name='leave', help='Tells the bot to leave the voice channel')
async def leave(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client:
        await voice_client.disconnect()


@bot.command(name='code', help='Where do I get this awesome code?')
async def code(ctx):
    voice_client = ctx.guild.voice_client
    await ctx.send("https://github.com/peterkelly70/beathoven")

# Play Songs

async def play_song(ctx, voice_client):
    try:
        global should_stop
        global current_playlist
        global repeat
        index = current_playlist['currently_playing']
        playlist_type = current_playlist['playlist_type']
        
        if should_stop:
            should_stop = False
            return

        song = current_playlist['playlist'][index]
        song_title = ""
        if playlist_type == PLAYLIST_TYPE.YOUTUBE.value :
        # Handle YouTube URLs
            await wait_until_done(voice_client)
            stream_info, stream_url = stream_audio_from_youtube(song)
            audio_source = play_audio_with_ffmpeg(stream_info, stream_url)
            song_title = stream_info['title']
            current_playlist['duration'] = stream_info['duration']
            stream_start_time = time.time()
            # voice_client.play(audio_source,after=lambda e: bot.loop.create_task(advance_song(ctx, voice_client)))
            voice_client.play(audio_source, after=lambda e: bot.loop.create_task(handle_playback_error(ctx, voice_client, stream_url, e)) if e else bot.loop.create_task(advance_song(ctx, voice_client)))
        elif playlist_type == PLAYLIST_TYPE.RADIO.value :
                # Handle radio URLs
                song_title = song  # We'll use URL as title here
                voice_client.play(discord.FFmpegPCMAudio(source=song),after=lambda e: bot.loop.create_task(advance_song(ctx, voice_client)))
        else:  # We assume song_url is a local filepath
            await wait_until_done(voice_client)
            voice_client.play(discord.FFmpegPCMAudio(source=song),after=lambda e: bot.loop.create_task(advance_song(ctx, voice_client)))
            song_title = strip_basepath(song)
        await ctx.send('**Now playing:** {}'.format(song_title))
    except Exception as e:
        print(f'Error in play_song function: {str(e)}')  # Replace with your desired error message
        print("Type of Exception:", type(e))
        print("Exception Arguments:", e.args)
        print("Traceback:", traceback.format_exc())
        await ctx.send(f"Error playing song #{index + 1}: {str(e)}")

async def advance_song(ctx, voice_client):
    try:
        global should_stop
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

        if repeat == REPEAT.SONG :
            current_playlist['currently_playing']=current_playlist['currently_playing']
        elif repeat == REPEAT.LIST :
            current_playlist["currently_playing"] = (current_playlist["currently_playing"] + 1) % len(current_playlist["playlist"])
        else : # advance the song, if we are at the last item in the playlist stop
            current_playlist['currently_playing'] = current_playlist['currently_playing'] + 1
            if current_playlist['currently_playing'] > len(current_playlist['playlist']) :
                await ctx.send("Playlist is over.")

        # After the song index has been advanced, call play_song.
        await play_song(ctx, voice_client)
    except Exception as e:
        await ctx.send(f"Error advancing song: {str(e)}")
        
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
    # create a sinlge playlist
    current_playlist['queue'] ="Youtube"
    await add_to_playlist(ctx,url)
    current_playlist['currently_playing'] = 0
    current_playlist['playlist_type'] = PLAYLIST_TYPE.YOUTUBE.value
    await play_song(ctx, voice_client)

        
@bot.command(name='add', help='Add a single url to the current playlist')
async def add_to_playlist(ctx, url): 
    current_playlist['playlist'].append(url)
    await ctx.send(f'Added {url} to the playlist.')    

@bot.command(name='list', help='Show available playlists')
async def playlists(ctx, playlist_type=PLAYLIST_TYPE.LOCAL.value):
    # Check if type is a valid playlist type
    ext=get_extension(playlist_type)
    global current_type 
    current_type = playlist_type
    playlists = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith(ext)]
    playlists = [pl.replace(ext, '') for pl in playlists]
    response = "\n".join(f"{i+1}. {pl}" for i, pl in enumerate(playlists))
    await ctx.send(f"Available {playlist_type} playlists:\n{response}")

@bot.command(name='play', help='Play songs from a playlist')
async def play_playlist(ctx,*,args):
   
    global current_playlist
    split_args = args.split(" ")
    # Case "!play 2"
    if len(split_args) == 1:
        playlist_type = current_type
        playlist_number = int(split_args[0])
    # Case: "!play radio 2"
    elif len(split_args) == 2:
        playlist_type = split_args[0]
        playlist_number = int(split_args[1])
    # Unrecognized command
    else:
        return await ctx.send(f"Unrecognized command: {args}")

    if playlist_number < 1:
        await ctx.send("Invalid playlist number!")
        return
  
    
    # Determine the extension based on the playlist type
    ext=get_extension(playlist_type)
    
    playlists = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith(ext)]
    
    if playlist_number > len(playlists):
        await ctx.send("Invalid playlist number!")
        return

    playlist_name = playlists[playlist_number - 1].replace(ext, '')
    load_playlist(playlist_name,current_type)
    
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("Bot must be in a voice channel to play music.")
        return

    playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}{ext}")
    
    if not os.path.exists(playlist_path):
        await ctx.send(f"No playlist found named: {playlist_name}")
        return
    
    # Print the playlist
    await ctx.send('Songs in the playlist:')
    song_list = ""
    for i, path in enumerate(current_playlist['playlist']):
        song_name = os.path.basename(path)  # This removes the path detail and leaves only the song's name
        song_list += f'{i+1}. {song_name}\n'  # Append each song to the list
    await ctx.send(song_list)  # Send the complete list to chat
    await play_song(ctx, voice_client)


# Track controls
# Stop command
@bot.command(name='stop', help='stop playing')
async def stop(ctx):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    global should_stop
    if voice.is_playing():
        voice.stop()
        should_stop = True
        await ctx.send('Stopping playback.')
    else:
        await ctx.send('Nothing is playing right now.')

# Pause command
@bot.command(name='pause', help='Pause song')
async def pause(ctx):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice.is_playing():
        voice.pause()
        await ctx.send('Playback paused.')
    else:
        await ctx.send('Nothing is playing right now.')

# Resume command
@bot.command(name='resume', help='Resumes a song.')
async def resume(ctx):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice.is_paused():
        voice.resume()
        await ctx.send('Playback resumed.')
    else:
        await ctx.send('No song is paused right now.')

# Skip track
@bot.command(name='skip', help='Skip song')
async def skip(ctx, num_to_skip: int = 1):
    # Check if a playlist is currently playing
    if not current_playlist:
        await ctx.send("Nothing is currently playing.")
        return
    
    voice_client = ctx.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.send("No song is currently playing.")
        return

    next_song_index = max(0, current_playlist['currently_playing']+ num_to_skip)
    voice_client.stop()
    await wait_until_done(voice_client)
    bot.loop.create_task(play_song(ctx, voice_client))

# Back, ideally this should be a wrapper.
@bot.command(name='back', help='Go back one or more songs')
async def back(ctx, num_to_go_back: int = 1):
    voice_client = ctx.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.send("No song is currently playing.")
        return

    next_song_index = max(0, current_playlist['currently_playing']- num_to_go_back)
    voice_client.stop()
    await wait_until_done(voice_client)
    bot.loop.create_task(play_song(ctx, voice_client))

@bot.command(name='restart', help='Restart the current song')
async def restart(ctx):
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("No song is currently playing.")
        return
    voice_client.stop()
    bot.loop.create_task(play_song(ctx, voice_client))

@bot.command(name='repeat', help='Tells the bot to repeat the song/list or not')
async def repeat(ctx, state):
    global repeat
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("No song is currently playing.")
        return
    if state.upper() == 'OFF':
        repeat = REPEAT.OFF
        await ctx.send("repeat is off")
    elif state.upper() == 'SONG':
        repeat = REPEAT.SONG
        await ctx.send("repeating song")
    elif state.upper() == 'LIST':
        repeat = REPEAT.LIST
        await ctx.send("repeating list")
    else:
        repeat = REPEAT.OFF
        await ctx.send("repeat is off")

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

    
bot.run(TOKEN)