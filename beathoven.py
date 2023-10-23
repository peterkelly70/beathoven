#!/usr/bin/env python3
import discord
from discord.ext import commands
import os
import yt_dlp
import ffmpeg
import asyncio
from dotenv import load_dotenv
from enum import Enum
from urllib.parse import urlparse


class REPEAT(Enum):
    OFF = "OFF"
    SONG = "SONG"
    LIST = "LIST"

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
PLAYLIST_DIR = os.getenv('PLAYLIST_DIR')
PREFIX = '!'
intents = discord.Intents().all()

# Global variables
previous_volume = 0.5
current_playlist = []
# Global repeat variable
repeat = REPEAT.OFF
should_stop = False # Global flag to control playback
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

currently_playing = {"playlist": None, "index": 0}

# helper
def stream_audio_from_youtube(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        stream_url = info['url']
    
    return info, stream_url

def play_audio_with_ffmpeg(stream_info, stream_url):
    return discord.FFmpegPCMAudio(executable="ffmpeg", source=stream_url)

# function to load a playlist into current_playlist
def load_playlist(playlist_name):
    playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.bpl")
    with open(playlist_path, 'r') as f:
        global current_playlist
        current_playlist = [line.rstrip() for line in f]

async def wait_until_done(voice_client):
    while voice_client.is_playing() or voice_client.is_paused():
        await asyncio.sleep(1)  # check every second

def strip_basepath(url):
    parsed_url = urlparse(url)
    return os.path.basename(parsed_url.path)

# Bot commands

async def play_next_song(ctx, voice_client, index):
    try:
        # If the flag is set, stop playback and reset the flag
        global should_stop
        global current_playlist
        global repeat
        if repeat == REPEAT.SONG:
            next_index=index
        else:
            next_index=index+1
        if should_stop:
            should_stop = False
            return
        if index < len(current_playlist):
            song_url = current_playlist[index]
            if song_url.startswith('http'):  # Check if song_url is a URL
                # ytdl_format_options = {}  # Set your options here
                await wait_until_done(voice_client)
                song_title = await play(ctx, song_url)
            else:  # We assume song_url is a local filepath
                await wait_until_done(voice_client)
                voice_client.play(discord.FFmpegPCMAudio(executable="/usr/bin/ffmpeg", source=song_url), 
                                  after=lambda e: bot.loop.create_task(play_next_song(ctx, voice_client, next_index)))
                song_title = strip_basepath(song_url)
            await ctx.send('**Now playing:** {}'.format(song_title))
        else:
            # Check the repeat state here
            if repeat == REPEAT.LIST:
                index = 0  # Reset index to start of playlist
                await play_next_song(ctx, voice_client, index)
            else:
                await ctx.send("Playlist is over.")
    except Exception as e:
        await ctx.send(f"Error playing song: {str(e)}")


@bot.event
async def on_ready():
    print(f'Bot {bot.user.name} has connected to Discord!')

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

@bot.command(name='yt', help='Play a youtube url')
async def play(ctx, url): 
    title = ""
    global should_stop
    if should_stop:
        should_stop = False
        return title
    
    voice_channel = ctx.message.author.voice.channel
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice and voice.is_connected():
        await voice.move_to(voice_channel)
    else:
        voice = await voice_channel.connect()
        
    stream_info, stream_url = stream_audio_from_youtube(url)
    audio_source = play_audio_with_ffmpeg(stream_info, stream_url)

    voice.play(audio_source)
    title = stream_info['title']
    return title
    # await ctx.send('**Now playing:** {}'.format(stream_info['title']))

@bot.command(name='list', help='Show available local playlists')
async def playlists(ctx):
    playlists = os.listdir(PLAYLIST_DIR)
    # Remove '.bpl' from the end of each file
    playlists = [pl.replace('.bpl', '') for pl in playlists if pl.endswith('.bpl')]
    
    response = ""
    for i, pl in enumerate(playlists, 1):
        response += f"{i}. {pl}\n"
        
    await ctx.send(f"Available playlists:\n{response}")

@bot.command(name='play', help='Play songs from a local playlist')
async def play_playlist(ctx, playlist_number: int):
    if playlist_number < 1:
        await ctx.send("Invalid playlist number!")
        return

    global current_playlist
    playlists = os.listdir(PLAYLIST_DIR)
    playlists = [pl for pl in playlists if pl.endswith('.bpl')]
    
    if playlist_number > len(playlists):
        await ctx.send("Invalid playlist number!")
        return

    playlist_name = playlists[playlist_number - 1].replace('.bpl', '')
    load_playlist(playlist_name)
    
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("Bot must be in a voice channel to play music.")
        return

    playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.bpl")
    
    if not os.path.exists(playlist_path):
        await ctx.send(f"No playlist found named: {playlist_name}")
        return

    currently_playing["playlist"] = playlist_name
    currently_playing["index"] = 0
    
    # open the playlist
    with open(playlist_path, 'r') as f:
        playlist = [line.rstrip() for line in f]
    
    # Print the playlist
    await ctx.send('Songs in the playlist:')
    song_list = ""
    for i, path in enumerate(playlist):
        song_name = os.path.basename(path)  # This removes the path detail and leaves only the song's name
        song_list += f'{i+1}. {song_name}\n'  # Append each song to the list
    await ctx.send(song_list)  # Send the complete list to chat
    
    await play_next_song(ctx, voice_client, 0)

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


# Volume command
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

    next_song_index = max(0, currently_playing["index"] + num_to_skip)
    voice_client.stop()
    await wait_until_done(voice_client)
    bot.loop.create_task(play_next_song(ctx, voice_client, next_song_index))

@bot.command(name='back', help='Go back one or more songs')
async def back(ctx, num_to_go_back: int = 1):
    voice_client = ctx.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.send("No song is currently playing.")
        return

    next_song_index = max(0, currently_playing["index"] - num_to_go_back)
    voice_client.stop()
    await wait_until_done(voice_client)
    bot.loop.create_task(play_next_song(ctx, voice_client, next_song_index))

@bot.command(name='restart', help='Restart the current song')
async def restart(ctx):
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("No song is currently playing.")
        return
    voice_client.stop()
    bot.loop.create_task(play_next_song(ctx, voice_client, currently_playing["index"]))

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
    
bot.run(TOKEN)