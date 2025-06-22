import subprocess, time, os
from threading import Thread
from flask import Flask, send_from_directory
from datetime import datetime, time as dt_time, timedelta
import pytz

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE_RIGHT = "logo.png"  # fixed top-right logo

os.makedirs(HLS_DIR, exist_ok=True)

# Scheduler time zones
IST = pytz.timezone('Asia/Kolkata')

# Your schedule with start and end times (24h format) and show names
SCHEDULE = [
    ("pokemon",  dt_time(7, 0),  dt_time(12, 0)),
    ("doraemon", dt_time(12, 0), dt_time(15, 0)),
    ("chhota",   dt_time(15, 0), dt_time(18, 0)),
    ("shinchan", dt_time(18, 0), dt_time(20, 0)),
    ("ramayan",  dt_time(20, 0), dt_time(23, 59, 59, 999999)),  # until midnight
]

def get_current_show():
    # Read show.txt as before
    if not os.path.exists("show.txt"):
        return None
    with open("show.txt", "r") as f:
        return f.read().strip().lower()

def set_current_show(show):
    with open("show.txt", "w") as f:
        f.write(show)

def get_show_for_now():
    now = datetime.now(IST).time()
    for show, start, end in SCHEDULE:
        if start <= now < end:
            return show
    # If no match (after midnight before 7AM), return None or default show
    return None

def scheduler_thread():
    current_show = None
    while True:
        show_now = get_show_for_now()
        if show_now != current_show and show_now is not None:
            print(f"[SCHEDULER] Switching show to: {show_now}")
            set_current_show(show_now)
            current_show = show_now
        time.sleep(30)  # check every 30 seconds

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
    Thread(target=scheduler_thread, daemon=True).start()
    Thread(target=play_videos_in_order, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
