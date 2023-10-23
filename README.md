# beathoven
A discord music playing bot v0.2

Setup
clone the repo
    git clone https://github.com/peterkelly70/beathoven.git
    cd beathoven
    touch .env
    # Create a virtual environment named botenv
    python3 -m venv botenv

    # Activate the virtual environment
    source botenv/bin/activate  # On Windows, use: .\botenv\Scripts\activate
    # Install the dependencies from the requirements.txt file
    pip install -r requirements.txt

    #run beathoven.py
    chmod +x beathoven.py
    ./beathoven.py
    
    # When done working on the project, you can deactivate the virtual environment
    deactivate  # (Optional) Run this when you're done working to exit the virtual environment

    ******* TO DO *******
     - make the bot a service

You will need the follwoing in the .env file:
    DISCORD_BOT_TOKEN='YOUR_DISCDORD_TOKEN'
    PLAYLIST_DIR='/home/musicbot/Beathoven/playlists/'

Was developed on Ubuntu 22.04 against Python 3.10.
I used a chatGPT and codeGPT to the bulk of the bolierplate and to teach me the discord.py package. It took a bit of wrangling but I think the code seems pretty straightforward and mostly works*

Beathoven Commands:
  back    Go back one or more songs
  help    Shows this message
  join    Tells the bot to join the voice channel
  leave   Tells the bot to leave the voice channel
  list    Show available local playlists
  mute    Mute the bot
  pause   Pause song
  play    Play songs from a local playlist
  repeat  Tells the bot to repeat the song/list or not
  restart Restart the current song
  resume  Resumes a song.
  skip    Skip song
  stop    Stop playing
  unmute  Unmute the bot
  volume  Change Volume of song
  yt      Play a youtube url

Type !help command for more info on a command.
You can also type !help category for more info on a category.


BUGS galore:
    youtube playback - The stream seems to get terminated, at random times
    volume  - volume works occasionaly
    mute/unbmute - related to volume issues? mute does nothing
    playlists - don't handle spaces in filenames
    repeat song not working if song is last song in list

Wishlist:
    logging is non existent at present.
    queing, let people add music to a que.
    mp3 tag information used and embedded images for Songs.
    Folder images, like cover.jpg displayed for playlists.
    Youtube thumbnails for now playing and playlists.
    Playlists by genre.
    User control of playlists, and playlists content
        - create
        - update
        - delete

Roadmap
    - MVP (minium viable product)
        - pretty much there, just need to sort out the youtube playback issues
    - add logging
    - fix volume control
    - update documentation

