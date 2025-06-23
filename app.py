import subprocess
import time
import os
import shutil
import json
from threading import Thread
from flask import Flask, send_from_directory, render_template_string
from datetime import datetime
import pytz

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE = "logo.png"
TIMEZONE = pytz.timezone("Asia/Kolkata")
STATE_FILE = "state.json"

SCHEDULE = {
    "09:00": "pokemon.txt",
    "10:45": "chhota.txt",
    "12:00": "doraemon.txt",
    "15:00": "chhota.txt",
    "18:00": "shinchan.txt",
}

os.makedirs(HLS_DIR, exist_ok=True)

# Safely load saved state
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[WARN] state.json was empty or corrupted. Resetting.")
            return {}
    return {}

# Save playback state
def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# Get current show and time block
def get_current_show():
    now = datetime.now(TIMEZONE)
    current_minutes = now.hour * 60 + now.minute
    sorted_times = sorted(SCHEDULE.items())

    current_show = None
    for i, (time_str, file) in enumerate(sorted_times):
        start_minutes = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
        end_minutes = int(sorted_times[(i + 1) % len(sorted_times)][0].split(":")[0]) * 60 + int(sorted_times[(i + 1) % len(sorted_times)][0].split(":")[1])
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60
        if start_minutes <= current_minutes < end_minutes:
            current_show = file
            break
    return current_show

# Get video duration using ffprobe
def get_video_duration(path_or_url):
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path_or_url
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Failed to get video duration: {e}")
        return 0

# Get current playlist, episode index, and start time offset
def get_next_episode(state):
    current_show = get_current_show()
    if not current_show:
        return None, None, 0

    state.setdefault(current_show, {"index": 0, "offset": 0})
    playlist = open(current_show).read().strip().splitlines()

    index = state[current_show]["index"]
    offset = state[current_show]["offset"]

    if index >= len(playlist):
        index = 0
        offset = 0

    return current_show, playlist[index], offset

# FFmpeg streaming thread
def start_ffmpeg_stream():
    state = load_state()
    while True:
        show, video_url, start_offset = get_next_episode(state)
        if not show or not video_url:
            print("[INFO] No show scheduled.")
            time.sleep(10)
            continue

        now = datetime.now(TIMEZONE)
        current_minutes = now.hour * 60 + now.minute

        sorted_times = sorted(SCHEDULE.items())
        show_start_minutes = int([k for k, v in sorted_times if v == show][0].split(":")[0]) * 60 + int([k for k, v in sorted_times if v == show][0].split(":")[1])
        next_index = (list(SCHEDULE.values()).index(show) + 1) % len(sorted_times)
        show_end_minutes = int(sorted_times[next_index][0].split(":")[0]) * 60 + int(sorted_times[next_index][0].split(":")[1])
        if show_end_minutes <= show_start_minutes:
            show_end_minutes += 24 * 60
        remaining_time = (show_end_minutes - current_minutes) * 60

        video_duration = get_video_duration(video_url)
        play_time = video_duration - start_offset

        actual_duration = min(remaining_time, play_time)

        print(f"[INFO] Now playing: {video_url} from {start_offset:.2f}s for {actual_duration:.2f}s")

        cmd = [
            "ffmpeg",
            "-ss", str(start_offset),
            "-i", video_url,
            "-t", str(actual_duration),
            "-vf", f"drawtext=text='Now Playing':fontcolor=white:fontsize=24:x=10:y=10",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-f", "hls",
            "-hls_time", "5",
            "-hls_list_size", "10",
            "-hls_flags", "delete_segments+omit_endlist",
            os.path.join(HLS_DIR, "stream.m3u8")
        ]

        process = subprocess.Popen(cmd)
        process.wait()

        # Update state after playing
        if actual_duration + start_offset >= video_duration:
            state[show]["index"] += 1
            state[show]["offset"] = 0
        else:
            state[show]["offset"] += actual_duration

        save_state(state)

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Streamify TV</title>
    </head>
    <body style="background:black; color:white; text-align:center;">
        <h1>📺 Streamify TV</h1>
        <video controls autoplay width="640" height="360">
            <source src="/stream.m3u8" type="application/vnd.apple.mpegurl">
        </video>
    </body>
    </html>
    """)

@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(HLS_DIR, path)

if __name__ == "__main__":
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
