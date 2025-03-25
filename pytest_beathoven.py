import unittest
from unittest.mock import AsyncMock, MagicMock
from beathoven import play_song

class TestPlaySong(unittest.TestCase):
    def setUp(self):
        self.ctx = AsyncMock()
        self.voice_client = MagicMock()
        self.voice_client.play = MagicMock()

    async def test_play_song_youtube(self):
        global should_stop
        global current_playlist
        global repeat
        should_stop = False
        current_playlist = {'currently_playing': 0, 'playlist_type': 'YOUTUBE', 'playlist': ['song1']}
        repeat = False
        await play_song(self.ctx, self.voice_client)
        self.voice_client.play.assert_called_once()

    async def test_play_song_radio(self):
        global should_stop
        global current_playlist
        global repeat
        should_stop = False
        current_playlist = {'currently_playing': 0, 'playlist_type': 'RADIO', 'playlist': ['song1']}
        repeat = False
        await play_song(self.ctx, self.voice_client)
        self.voice_client.play.assert_called_once()

    async def test_play_song_local(self):
        global should_stop
        global current_playlist
        global repeat
        should_stop = False
        current_playlist = {'currently_playing': 0, 'playlist_type': 'LOCAL', 'playlist': ['song1']}
        repeat = False
        await play_song(self.ctx, self.voice_client)
        self.voice_client.play.assert_called_once()

    async def test_play_song_should_stop(self):
        global should_stop
        global current_playlist
        global repeat
        should_stop = True
        current_playlist = {'currently_playing': 0, 'playlist_type': 'YOUTUBE', 'playlist': ['song1']}
        repeat = False
        await play_song(self.ctx, self.voice_client)
        self.voice_client.play.assert_not_called()

    async def test_play_song_exception(self):
        global should_stop
        global current_playlist
        global repeat
        should_stop = False
        current_playlist = {'currently_playing': 0, 'playlist_type': 'YOUTUBE', 'playlist': ['song1']}
        repeat = False
        self.voice_client.play.side_effect = Exception('Test exception')
        with self.assertRaises(Exception):
            await play_song(self.ctx, self.voice_client)

if __name__ == '__main__':
    unittest.main()