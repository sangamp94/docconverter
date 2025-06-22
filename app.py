import subprocess, time, os
from threading import Thread
from flask import Flask, send_from_directory
from datetime import datetime, time as dt_time
import pytz

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE_RIGHT = "logo.png"  # fixed top-right logo
os.makedirs(HLS_DIR, exist_ok=True)

# Timezone
IST = pytz.timezone('Asia/Kolkata')

# Real-time TV schedule (24-hour format)
SCHEDULE = [
    ("pokemon",  dt_time(7, 0),  dt_time(12, 0)),
    ("doraemon", dt_time(12, 0), dt_time(15, 0)),
    ("chhota",   dt_time(15, 0), dt_time(18, 0)),
    ("shinchan", dt_time(18, 0), dt_time(20, 0)),
    ("ramayan",  dt_time(20, 0), dt_time(23, 59, 59)),
]

def get_current_show():
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
    return None

def scheduler_thread():
    current_show = None
    while True:
        show_now = get_show_for_now()
        if show_now != current_show and show_now is not None:
            print(f"[SCHEDULER] Switching show to: {show_now}")
            set_current_show(show_now)
            current_show = show_now
        time.sleep(30)

def get_video_duration(url):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15
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
            print("[INFO] No show specified. Waiting...")
            time.sleep(10)
            continue

        playlist_file = f"{show}.txt"
        logo_file_left = f"{show}.jpg"

        playlist = get_video_playlist(playlist_file)
        if not playlist:
            print(f"[INFO] Playlist {playlist_file} missing or empty.")
            time.sleep(10)
            continue

        index = 0
        while index < len(playlist):
            video = playlist[index]
            url = video["url"]
            duration = int(video["duration"])

            # Time left in current show slot
            now = datetime.now(IST)
            for s_name, start, end in SCHEDULE:
                if s_name == show:
                    end_dt = datetime.combine(now.date(), end, tzinfo=IST)
                    seconds_left = int((end_dt - now).total_seconds())
                    break
            else:
                seconds_left = duration

            play_time = min(duration, seconds_left)

            print(f"[INFO] Playing {show.upper()}: {url} for {play_time}s")

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
                "-t", str(play_time),
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
                process.wait(timeout=play_time + 5)
            except subprocess.TimeoutExpired:
                print("[INFO] Cutting video early to switch show.")
                process.kill()
            except Exception as e:
                print(f"[ERROR] FFmpeg crashed: {e}")
                time.sleep(5)

            # If schedule switched mid-loop
            if get_current_show() != show:
                print(f"[INFO] Schedule changed. Switching to {get_current_show()}...")
                break

            index += 1

@app.route('/')
def home():
    show = get_current_show() or "unknown"
    return f"<h1>📺 Cartoon Live TV</h1><p>🎬 Now Showing: {show.upper()}</p><a href='/stream.m3u8'>▶️ Watch</a>"

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
