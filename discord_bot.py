"""
Discord bot for music playback and playlist management
"""
import os
import logging
from typing import List, Optional
import discord
from discord.ext import commands
import dotenv
from playlist_manager import PlaylistManager
from web_ui import WebUI
from models import Track
import asyncio
import concurrent.futures
import threading

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
PORT = int(os.getenv('PORT', 5000))
BASE_URL = os.getenv('BEATHOVEN_BASE_URL', 'http://localhost:5000')

class MusicBot(commands.Bot):
    def __init__(self, playlist_manager: PlaylistManager):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)
        
        self.playlist_manager = playlist_manager
        self.web_ui = None  # Will be set by main.py
        self.active_voice_clients = {}  # Renamed from voice_clients
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.bg_task = None
        
    async def setup_hook(self):
        """Set up the bot"""
        logger.info("Bot is setting up...")
        # Playlists are loaded automatically by the database now
        
        # Add command cogs
        await self.add_cog(MusicCommands(self))
        
        # Start state monitoring
        self.bg_task = self.loop.create_task(self.monitor_playback_state())
        
    async def monitor_playback_state(self):
    await self.wait_until_ready()
    last_track_url = None
    last_playing_state = False

    while not self.is_closed():
        try:
            is_playing = self.playlist_manager.is_playing
            is_paused = self.playlist_manager.is_paused
            current_track = self.playlist_manager.get_current_track()
            current_playing = is_playing and not is_paused

            logger.debug(f"[Monitor] is_playing={is_playing}, is_paused={is_paused}, current_track={current_track.title if current_track else None}")

            if current_playing != last_playing_state or (current_track and current_track.url != last_track_url):
                logger.info(f"State change - playing: {current_playing}, track: {current_track.title if current_track else 'None'}")

                if current_playing and current_track:
                    logger.info("[Monitor] Conditions met, calling _play_track()")
                    for voice_client in self.active_voice_clients.values():
                        music_commands = self.get_cog('MusicCommands')
                        if music_commands:
                            await music_commands._play_track(None, voice_client, current_track)
                            break
                else:
                    logger.info("[Monitor] Playback halted: skipping _play_track() due to stop or pause")

                if not current_playing:
                    for voice_client in self.active_voice_clients.values():
                        if voice_client.is_playing():
                            logger.info("[Monitor] Stopping voice client playback")
                            voice_client.stop()

                last_playing_state = current_playing
                last_track_url = current_track.url if current_track else None

        except Exception as e:
            logger.error(f"Error in monitor_playback_state: {e}", exc_info=True)
        await asyncio.sleep(0.1)
    
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'{self.user} has connected to Discord!')
        
    def run(self, token: str):
        """Start the bot"""
        super().run(token)

class MusicCommands(commands.Cog):
    def __init__(self, bot: MusicBot):
        self.bot = bot
        
    @commands.command(name='join', help='Join your voice channel')
    async def join(self, ctx):
        """Join a voice channel"""
        try:
            if not ctx.author.voice:
                await ctx.send("You must be in a voice channel to use this command.")
                return
                
            # Send connecting message
            connecting_msg = await ctx.send("Connecting to voice channel...")
                
            channel = ctx.author.voice.channel
            if ctx.guild.id in self.bot.active_voice_clients:
                await self.bot.active_voice_clients[ctx.guild.id].move_to(channel)
            else:
                self.bot.active_voice_clients[ctx.guild.id] = await channel.connect()
            
            # Generate web UI link with session ID
            session_id = os.urandom(16).hex()
            web_url = f"{BASE_URL}/dashboard/{session_id}"
            
            embed = discord.Embed(
                title="Beathoven Music Bot",
                description="Connected to voice channel!\nUse the web interface to manage playback:",
                color=discord.Color.blue()
            )
            embed.add_field(name="Dashboard", value=web_url)
            
            # Delete connecting message and send success
            await connecting_msg.delete()
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error joining voice channel: {e}", exc_info=True)
            await ctx.send("Failed to join voice channel. Please try again.")
            
    @commands.command(name='list', help='List available playlists')
    async def list_playlists(self, ctx, playlist_type: Optional[str] = None):
        """List available playlists"""
        try:
            playlists = self.bot.playlist_manager.get_all_playlists()
            if not playlists:
                await ctx.send("No playlists found.")
                return
                
            # Filter by type if specified
            if playlist_type:
                playlist_type = playlist_type.lower()
                if playlist_type not in ['local', 'youtube', 'radio']:
                    await ctx.send("Invalid playlist type. Must be 'local', 'youtube', or 'radio'.")
                    return
                playlists = [p for p in playlists if p.type == playlist_type]
            
            # Create embed
            embed = discord.Embed(
                title="Available Playlists",
                color=discord.Color.blue()
            )
            
            # Group playlists by type
            for ptype in ['local', 'youtube', 'radio']:
                type_playlists = [p for p in playlists if p.type == ptype]
                if type_playlists:
                    playlist_info = []
                    for p in type_playlists:
                        tracks_info = f"{len(p.tracks)} track{'s' if len(p.tracks) != 1 else ''}"
                        playlist_info.append(f"• {p.name} ({tracks_info})")
                    
                    embed.add_field(
                        name=f"{ptype.title()} Playlists",
                        value="\n".join(playlist_info) if playlist_info else "None",
                        inline=False
                    )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error listing playlists: {e}", exc_info=True)
            await ctx.send("Failed to list playlists. Please try again.")
            
    @commands.command(name='leave', help='Leave voice channel')
    async def leave(self, ctx):
        """Leave the voice channel"""
        if ctx.guild.id in self.bot.active_voice_clients:
            await self.bot.active_voice_clients[ctx.guild.id].disconnect()
            del self.bot.active_voice_clients[ctx.guild.id]
            
    @commands.command(name='play', help='Play a track or playlist')
    async def play(self, ctx, *, query: str):
        """Play a track or playlist"""
        try:
            if not ctx.author.voice:
                await ctx.send("You're not in a voice channel!")
                return
                
            # Join voice channel if not already in one
            if ctx.guild.id not in self.bot.active_voice_clients:
                await self.join(ctx)
                
            voice_client = self.bot.active_voice_clients[ctx.guild.id]
            logger.info(f"Playing query: {query}")
            
            # Check if it's a playlist name
            playlist = self.bot.playlist_manager.get_playlist(query)
            if playlist:
                logger.info(f"Found playlist: {playlist.name} with {len(playlist.tracks)} tracks")
                self.bot.playlist_manager.set_current_playlist(playlist.name)
                self.bot.playlist_manager.set_playing(True)
                current_track = self.bot.playlist_manager.get_current_track()
                
                if current_track:
                    logger.info(f"Playing track: {current_track.title} from {current_track.url}")
                    await self._play_track(ctx, voice_client, current_track)
                else:
                    logger.error("No tracks in playlist")
                    await ctx.send("No tracks in playlist")
            else:
                logger.error(f"Playlist not found: {query}")
                await ctx.send(f"Playlist '{query}' not found")
                
        except Exception as e:
            logger.error(f"Error playing track: {e}", exc_info=True)
            await ctx.send(f"Error playing track: {str(e)}")
            
    @commands.command(name='pause', help='Pause current track')
    async def pause(self, ctx):
        """Pause the current track"""
        if ctx.guild.id in self.bot.active_voice_clients:
            voice_client = self.bot.active_voice_clients[ctx.guild.id]
            if voice_client.is_playing():
                voice_client.pause()
                self.bot.playlist_manager.set_paused(True)
                
    @commands.command(name='resume', help='Resume paused track')
    async def resume(self, ctx):
        """Resume the current track"""
        if ctx.guild.id in self.bot.active_voice_clients:
            voice_client = self.bot.active_voice_clients[ctx.guild.id]
            if voice_client.is_paused():
                voice_client.resume()
                self.bot.playlist_manager.set_paused(False)
                self.bot.playlist_manager.set_playing(True)
                
    @commands.command(name='next', help='Play next track')
    async def next(self, ctx):
        """Play next track"""
        try:
            if ctx.guild.id not in self.bot.active_voice_clients:
                await ctx.send("Not connected to a voice channel.")
                return
                
            # Get next track first
            next_track = self.bot.playlist_manager.next_track()
            if next_track:
                voice_client = self.bot.active_voice_clients[ctx.guild.id]
                await self._play_track(ctx, voice_client, next_track)
            else:
                await ctx.send("No more tracks in playlist.")
        except Exception as e:
            logger.error(f"Error playing next track: {e}", exc_info=True)
            await ctx.send("Failed to play next track.")
            
    @commands.command(name='previous', help='Play previous track')
    async def previous(self, ctx):
        """Play previous track"""
        try:
            if ctx.guild.id not in self.bot.active_voice_clients:
                await ctx.send("Not connected to a voice channel.")
                return
                
            # Get previous track first
            prev_track = self.bot.playlist_manager.previous_track()
            if prev_track:
                voice_client = self.bot.active_voice_clients[ctx.guild.id]
                await self._play_track(ctx, voice_client, prev_track)
            else:
                await ctx.send("No previous tracks in playlist.")
        except Exception as e:
            logger.error(f"Error playing previous track: {e}", exc_info=True)
            await ctx.send("Failed to play previous track.")
            
    @commands.command(name='volume', help='Set volume (0-100)')
    async def volume(self, ctx, volume: int):
        """Set volume (0-100)"""
        if not 0 <= volume <= 100:
            await ctx.send("Volume must be between 0 and 100")
            return
            
        self.bot.playlist_manager.set_volume(volume)
        if ctx.guild.id in self.bot.active_voice_clients:
            voice_client = self.bot.active_voice_clients[ctx.guild.id]
            if voice_client.source:
                voice_client.source.volume = volume / 100
                
    @commands.command(name='stop', help='Stop playback')
    async def stop(self, ctx):
        """Stop playback"""
        if ctx.guild.id in self.bot.active_voice_clients:
            voice_client = self.bot.active_voice_clients[ctx.guild.id]
            voice_client.stop()
            self.bot.playlist_manager.set_playing(False)
            self.bot.playlist_manager.set_paused(False)
            
    def create_audio_source(self, url):
        try:
            # Simple FFmpeg conversion to PCM
            audio_source = discord.FFmpegPCMAudio(
                url,
                before_options='-nostdin',
                options='-vn'  # Just extract audio
            )
            return discord.PCMVolumeTransformer(audio_source, volume=0.5)
        except Exception as e:
            logger.error(f"Error in create_audio_source: {e}")
            return None

    async def _play_track(self, ctx, voice_client: discord.VoiceClient, track: Track):
        """Play a track in the voice channel"""
        try:
            # Create audio source in new thread
            logger.info(f"Creating audio source for track: {track.title} from {track.url}")
            future = self.bot.thread_pool.submit(
                self.create_audio_source,
                track.url
            )
            audio_source = await asyncio.wrap_future(future)
            
            if not audio_source:
                if ctx:
                    await ctx.send(f"Failed to create audio source for: {track.title}")
                return
                
            # Start playback or patch stream
            logger.info(f"Starting playback of {track.url}")
            if voice_client.is_playing():
                # Just patch the stream if already playing
                voice_client.source = audio_source
            else:
                # Start initial playback
                voice_client.play(
                    audio_source,
                    after=lambda e: self._on_playback_finished(e, voice_client)
                )
            
            # Update state
            self.bot.playlist_manager.set_playing(True)
            self.bot.playlist_manager.set_paused(False)
            logger.info(f"Now playing: {track.title}")
            if ctx:
                await ctx.send(f"Now playing: {track.title}")
                
        except Exception as e:
            logger.error(f"Error in _play_track: {e}", exc_info=True)
            if ctx:
                await ctx.send("Failed to play track.")

    def _on_playback_finished(self, error, voice_client):
        """Handle playback finish"""
        if error:
            logger.error(f"Player error: {error}")
        
        # Schedule next track in bot's event loop
        self.bot.loop.call_soon_threadsafe(
            lambda: self.bot.loop.create_task(self._play_next(voice_client))
        )
            
    async def _play_next(self, voice_client):
        """Play next track after current one finishes"""
        try:
            # Get next track
            next_track = self.bot.playlist_manager.next_track()
            if next_track:
                await self._play_track(None, voice_client, next_track)
            else:
                logger.info("No more tracks to play")
                self.bot.playlist_manager.set_playing(False)
        except Exception as e:
            logger.error(f"Error playing next track: {e}", exc_info=True)

if __name__ == "__main__":
    playlist_manager = PlaylistManager()
    bot = MusicBot(playlist_manager)
    bot.run(TOKEN)