import subprocess, time, os
from threading import Thread
from flask import Flask, send_from_directory

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE_RIGHT = "logo.png"  # Fixed top-right logo

os.makedirs(HLS_DIR, exist_ok=True)

def get_current_show():
    if not os.path.exists("show.txt"):
        return None
    with open("show.txt", "r") as f:
        return f.read().strip().lower()

def get_video_duration(url):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Duration fetch failed: {e}")
        return 0

def get_video_playlist(playlist_file):
    playlist = []
    if not os.path.exists(playlist_file):
        return playlist
    with open(playlist_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
        for url in urls:
            duration = get_video_duration(url)
            if duration > 0:
                playlist.append({"url": url, "duration": duration})
    return playlist

def play_videos_in_order():
    while True:
        show = get_current_show()
        if not show:
            print("[INFO] No show specified in show.txt. Waiting...")
            time.sleep(10)
            continue

        playlist_file = f"{show}.txt"
        logo_file_left = f"{show}.jpg"

        playlist = get_video_playlist(playlist_file)
        if not playlist:
            print(f"[INFO] Playlist file {playlist_file} empty or missing. Waiting...")
            time.sleep(10)
            continue

        for video in playlist:
            url = video["url"]
            duration = int(video["duration"])
            print(f"[INFO] Playing {show.upper()}: {url} ({duration}s)")

            filters = (
                "[1:v]scale=80:80[rightlogo];"
                "[2:v]scale=80:80[leftlogo];"
                "[0:v][rightlogo]overlay=W-w-10:10[tmp1];"
                "[tmp1][leftlogo]overlay=10:10"
            )

            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-re",
                "-i", url,
                "-i", LOGO_FILE_RIGHT,
                "-i", logo_file_left,
                "-filter_complex", filters,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-c:a", "aac",
                "-b:a", "128k",
                "-f", "hls",
                "-hls_time", "10",
                "-hls_list_size", "5",
                "-hls_flags", "delete_segments+omit_endlist",
                f"{HLS_DIR}/stream.m3u8"
            ]

            try:
                process = subprocess.Popen(cmd)
                time.sleep(duration)
                process.kill()
                time.sleep(1)
            except Exception as e:
                print(f"[ERROR] FFmpeg crashed: {e}")
                time.sleep(5)

@app.route('/')
def root():
    return "<h1>✅ Streamify Live TV</h1><p><a href='/stream.m3u8'>📺 Watch Live</a></p>"

@app.route('/stream.m3u8')
def serve_m3u8():
    return send_from_directory(HLS_DIR, "stream.m3u8")

@app.route('/<path:filename>')
def serve_segments(filename):
    return send_from_directory(HLS_DIR, filename)

if __name__ == "__main__":
    Thread(target=play_videos_in_order, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
