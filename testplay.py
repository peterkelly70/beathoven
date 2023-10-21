#!/usr/bin/env python3
import yt_dlp as youtube_dl
import ffmpeg

def stream_audio_from_youtube(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        stream_url = info['url']

    return stream_url

def play_audio_with_ffmpeg(stream_url):
    input_audio = ffmpeg.input(stream_url)
    out_audio = ffmpeg.output(input_audio, 'default', format='alsa')
    ffmpeg.run(out_audio)

if __name__ == "__main__":
    youtube_url = "https://www.youtube.com/watch?v=Rz_1tNB5o2Y"  # Replace with your hardcoded URL
    audio_stream_url = stream_audio_from_youtube(youtube_url)
    play_audio_with_ffmpeg(audio_stream_url)
