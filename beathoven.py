"""Main entry point for Beathoven"""
import os
import sys
import logging
import asyncio
import dotenv
from discord_bot import MusicBot
from web_ui import WebUI
from playlist_manager import PlaylistManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('beathoven.log')
    ]
)
logger = logging.getLogger(__name__)

# Reduce werkzeug logging
logging.getLogger('werkzeug').setLevel(logging.WARNING)

async def main():
    """Main entry point"""
    try:
        # Load environment variables
        dotenv.load_dotenv()
        
        # Ensure required environment variables are set
        required_vars = ['DISCORD_TOKEN', 'PLAYLIST_DIR']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            sys.exit(1)
        
        # Set up playlist manager
        playlist_manager = PlaylistManager()
        
        # Set up web UI
        web_ui = WebUI(playlist_manager)
        
        # Set up Discord bot
        bot = MusicBot(playlist_manager)
        
        # Start web UI in a separate thread
        import threading
        web_thread = threading.Thread(target=web_ui.run)
        web_thread.daemon = True
        web_thread.start()
        
        # Start Discord bot
        await bot.start(os.getenv('DISCORD_TOKEN'))
        
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())