import subprocess
import time
import os
import json
from threading import Thread
from flask import Flask, send_from_directory, render_template_string
from datetime import datetime
import pytz

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
STATE_FILE = "state.json"
TIMEZONE = pytz.timezone("Asia/Kolkata")

SCHEDULE = {
    "09:00": "pokemon.txt",
    "10:45": "chhota.txt",
    "12:00": "doraemon.txt",
    "12:00": "ps11.txt",
    "15:00": "chhota.txt",
    "18:00": "shinchan.txt",
}

os.makedirs(HLS_DIR, exist_ok=True)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_current_show():
    now = datetime.now(TIMEZONE)
    current_minutes = now.hour * 60 + now.minute
    sorted_times = sorted(SCHEDULE.items())

    for i, (time_str, show_file) in enumerate(sorted_times):
        start = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
        end_index = (i + 1) % len(sorted_times)
        end = int(sorted_times[end_index][0].split(":")[0]) * 60 + int(sorted_times[end_index][0].split(":")[1])
        if end <= start:
            end += 24 * 60
        if start <= current_minutes < end:
            return show_file
    return None

def get_video_duration(url):
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", url
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Cannot get video duration: {e}")
        return 0

def get_next_episode(state):
    show_file = get_current_show()
    if not show_file:
        return None, None, 0

    state.setdefault(show_file, {"index": 0, "offset": 0})
    playlist = open(show_file).read().strip().splitlines()

    index = state[show_file]["index"]
    offset = state[show_file]["offset"]

    if index >= len(playlist):
        index = 0
        offset = 0

    return show_file, playlist[index], offset

def start_ffmpeg_stream():
    state = load_state()

    while True:
        show_file, video_url, start_offset = get_next_episode(state)
        if not show_file or not video_url:
            print("[INFO] No show scheduled.")
            time.sleep(10)
            continue

        now = datetime.now(TIMEZONE)
        current_minutes = now.hour * 60 + now.minute
        sorted_times = sorted(SCHEDULE.items())
        show_start = int([k for k, v in sorted_times if v == show_file][0].split(":")[0]) * 60 + int([k for k, v in sorted_times if v == show_file][0].split(":")[1])
        next_index = (list(SCHEDULE.values()).index(show_file) + 1) % len(sorted_times)
        show_end = int(sorted_times[next_index][0].split(":")[0]) * 60 + int(sorted_times[next_index][0].split(":")[1])
        if show_end <= show_start:
            show_end += 24 * 60
        remaining_time = (show_end - current_minutes) * 60

        video_duration = get_video_duration(video_url)
        play_time = video_duration - start_offset
        actual_duration = min(play_time, remaining_time)

        print(f"[INFO] Now Playing: {video_url} ({actual_duration:.1f}s from {start_offset:.1f}s)")

        show_name = show_file.replace(".txt", "")
        show_logo = f"{show_name}.jpg"
        channel_logo = "logo.png"

        inputs = ["ffmpeg", "-ss", str(start_offset), "-i", video_url]
        filter_cmds = []
        input_index = 1

        if os.path.exists(show_logo):
            inputs += ["-i", show_logo]
            filter_cmds.append(f"[{input_index}:v]scale=120:45[showlogo]")
            input_index += 1
        if os.path.exists(channel_logo):
            inputs += ["-i", channel_logo]
            filter_cmds.append(f"[{input_index}:v]scale=150:60[channellogo]")
            input_index += 1

        overlay_chain = "[0:v]"
        if os.path.exists(show_logo):
            overlay_chain += "[showlogo]overlay=10:10[tmp1];"
        else:
            overlay_chain += "null[tmp1];"
        if os.path.exists(channel_logo):
            overlay_chain += "[tmp1][channellogo]overlay=W-w-10:10[out]"
        else:
            overlay_chain = overlay_chain.replace("[tmp1];", "[out]")

        filter_complex = ";".join(filter_cmds) + ";" + overlay_chain

        cmd = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[out]", "-map", "0:a?",
            "-c:v", "libx264", "-c:a", "aac",
            "-f", "hls",
            "-hls_time", "5",
            "-hls_list_size", "10",
            "-hls_flags", "delete_segments+omit_endlist",
            os.path.join(HLS_DIR, "stream.m3u8")
        ]

        process = subprocess.Popen(cmd)
        process.wait()

        # update playback position
        if start_offset + actual_duration >= video_duration:
            state[show_file]["index"] += 1
            state[show_file]["offset"] = 0
        else:
            state[show_file]["offset"] += actual_duration

        save_state(state)

@app.route("/")
def index():
    return render_template_string("""
    <html>
    <head><title>Streamify TV</title></head>
    <body style="background:black; color:white; text-align:center;">
        <h1>📺 Streamify TV</h1>
        <video width="640" height="360" controls autoplay>
            <source src="/stream.m3u8" type="application/vnd.apple.mpegurl">
        </video>
    </body>
    </html>
    """)

@app.route("/<path:path>")
def serve_file(path):
    return send_from_directory(HLS_DIR, path)

if __name__ == "__main__":
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
