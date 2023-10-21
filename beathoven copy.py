#!/usr/bin/env python3
import discord
from discord.ext import commands
import os
import youtube_dl
import asyncio
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
PLAYLIST_DIR = os.getenv('PLAYLIST_DIR')
PREFIX = '!'
intents = discord.Intents().all()

bot = commands.Bot(command_prefix='!', intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
currently_playing = {"playlist": None, "index": 0}

async def play_next_song(ctx, voice_client, playlist, index):
    try:
        if index < len(playlist):
            song_url = playlist[index]
            if song_url.startswith('http'):  # Check if song_url is a URL
                ytdl_format_options = {}  # Set your options here
                with youtube_dl.YoutubeDL(ytdl_format_options) as ydl:
                    info = ydl.extract_info(song_url, download=False)
                    url2 = info['formats'][0]['url']
                    voice_client.play(discord.FFmpegPCMAudio(executable="/usr/bin/ffmpeg", source=url2), 
                                      after=lambda e: bot.loop.create_task(play_next_song(ctx, voice_client, playlist, index + 1)))
                    await ctx.send(f'**Now playing:** {info["title"]}')
            else:  # We assume song_url is a local filepath
                voice_client.play(discord.FFmpegPCMAudio(executable="/usr/bin/ffmpeg", source=song_url), 
                                  after=lambda e: bot.loop.create_task(play_next_song(ctx, voice_client, playlist, index + 1)))
                await ctx.send(f'**Now playing:** {song_url}')
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
    await channel.connect()

@bot.command(name='leave', help='Tells the bot to leave the voice channel')
async def leave(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client:
        await voice_client.disconnect()


@bot.command(name='playyt', help='Play a youtube url')
async def play(ctx, url):
    voice_channel = ctx.message.author.voice.channel
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice and voice.is_connected():
        await voice.move_to(voice_channel)
    else:
        voice = await voice_channel.connect()

    with youtube_dl.YoutubeDL(ytdl_format_options) as ydl:
        info = ydl.extract_info(url, download=False)
        url2 = info['formats'][0]['url']
        voice.play(discord.FFmpegPCMAudio(executable="/usr/bin/ffmpeg", source=url2))

    await ctx.send('**Now playing:** {}'.format(info['title']))


@bot.command(name='playlists', help='Show available local playlists')
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

    playlists = os.listdir(PLAYLIST_DIR)
    playlists = [pl for pl in playlists if pl.endswith('.bpl')]
    
    if playlist_number > len(playlists):
        await ctx.send("Invalid playlist number!")
        return

    playlist_name = playlists[playlist_number - 1].replace('.bpl', '')

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
    for i, path in enumerate(playlist):
        song_name = os.path.basename(path)  # This removes the path detail and leaves only the song's name
        await ctx.send(f'{i+1}. {song_name}')

    await play_next_song(ctx, voice_client, playlist, 0)

# Stop command
@bot.command()
async def stop(ctx):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice.is_playing():
        voice.stop()
        await ctx.send('Playback stopped.')
    else:
        await ctx.send('Nothing is playing right now.')

# Pause command
@bot.command()
async def pause(ctx):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice.is_playing():
        voice.pause()
        await ctx.send('Playback paused.')
    else:
        await ctx.send('Nothing is playing right now.')

# Volume command
@bot.command()
async def volume(ctx, vol: int):
    # Ensure volume is within 0-100
    if not 0 <= vol <= 100:
        return await ctx.send('Volume must be between 0 and 100.')

    # NOTE: discord.FFmpegPCMAudio provides a volume argument when creating the audio source. 
    # You'll need to create a new audio source with this value and update your player to use this.
    audio_source = discord.FFmpegPCMAudio(song_url, volume=vol/100)  # volume should be a float between 0 and 1

    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    voice.source = audio_source  # Update the audio source with new volume

    await ctx.send(f'Volume has been set to {vol}.')


@bot.command(name='skip', help='Skip the current song')
async def skip(ctx):
    voice_client = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("No song is currently playing.")
        return

    if currently_playing["playlist"]:
        currently_playing["index"] += 1
        playlist_path = os.path.join(PLAYLIST_DIR, currently_playing["playlist"])
        
        with open(playlist_path, 'r') as f:
            lines = f.readlines()

        if currently_playing["index"] < len(lines):
            song_url = lines[currently_playing["index"]].strip()

            with youtube_dl.YoutubeDL(ytdl_format_options) as ydl:
                info = ydl.extract_info(song_url, download=False)
                url2 = info['formats'][0]['url']
                voice_client.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=url2))
                await ctx.send(f'**Now playing:** {info["title"]}')
        else:
            await ctx.send("Reached end of the playlist.")
            currently_playing["playlist"] = None
            currently_playing["index"] = 0
    else:
        voice_client.stop()
        await ctx.send("Song skipped.")

bot.run(TOKEN)