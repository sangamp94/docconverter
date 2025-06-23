import subprocess
import time
import os
from threading import Thread
from flask import Flask, send_from_directory, render_template_string
from datetime import datetime
import pytz
import signal

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
TIMEZONE = pytz.timezone("Asia/Kolkata")

SCHEDULE = {
    "09:00": "pokemon.txt",
    "10:45": "chhota.txt",
    "12:00": "doraemon.txt",
    "13:00": "ps11.txt",
    "15:00": "chhota.txt",
    "18:00": "shinchan.txt",
}

os.makedirs(HLS_DIR, exist_ok=True)

def get_current_show():
    now = datetime.now(TIMEZONE)
    current_minutes = now.hour * 60 + now.minute
    sorted_schedule = sorted(SCHEDULE.items())

    for i, (time_str, show_file) in enumerate(sorted_schedule):
        start = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
        end_index = (i + 1) % len(sorted_schedule)
        end = int(sorted_schedule[end_index][0].split(":")[0]) * 60 + int(sorted_schedule[end_index][0].split(":")[1])
        if end <= start:
            end += 24 * 60
        if start <= current_minutes < end:
            return show_file
    return None

def run_ffmpeg_with_logos(video_url, show_name):
    # Clean previous HLS files
    for f in os.listdir(HLS_DIR):
        try:
            os.remove(os.path.join(HLS_DIR, f))
        except:
            pass

    logo_file = "logo.png"
    show_logo_file = f"{show_name}.jpg"

    inputs = ["ffmpeg", "-re", "-i", video_url]
    filters = []
    input_idx = 1

    if os.path.exists(show_logo_file):
        inputs += ["-i", show_logo_file]
        filters.append(f"[{input_idx}:v]scale=200:105[showlogo]")
        input_idx += 1

    if os.path.exists(logo_file):
        inputs += ["-i", logo_file]
        filters.append(f"[{input_idx}:v]scale=200:105[channellogo]")
        input_idx += 1

    # overlay chain
    overlay = "[0:v]"
    if os.path.exists(show_logo_file):
        overlay += "[showlogo]overlay=10:10[tmp1];"
    else:
        overlay += "null[tmp1];"

    if os.path.exists(logo_file):
        overlay += "[tmp1][channellogo]overlay=W-w-10:10[out]"
    else:
        overlay = overlay.replace("[tmp1];", "[out]")

    filter_complex = ";".join(filters) + ";" + overlay if filters else overlay

    cmd = inputs + [
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "ultrafast",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments+omit_endlist+independent_segments+program_date_time",
        os.path.join(HLS_DIR, "stream.m3u8")
    ]

    return subprocess.Popen(cmd)

def streaming_loop():
    current_process = None
    current_show = None
    playlist = []
    episode_index = 0

    while True:
        show_file = get_current_show()

        if show_file != current_show:
            if current_process:
                current_process.send_signal(signal.SIGINT)
                current_process.wait()
                current_process = None

            current_show = show_file
            episode_index = 0

            if current_show:
                try:
                    with open(current_show, "r") as f:
                        playlist = [line.strip() for line in f if line.strip()]
                except:
                    playlist = []
            else:
                playlist = []

        if current_show and playlist:
            if episode_index >= len(playlist):
                print(f"[INFO] Finished all episodes for {current_show}, waiting for next show")
                time.sleep(10)
                continue

            video_url = playlist[episode_index]
            show_name = current_show.replace(".txt", "")
            current_process = run_ffmpeg_with_logos(video_url, show_name)
            print(f"[INFO] Streaming {video_url} for {show_name}")
            current_process.wait()
            episode_index += 1
        else:
            print("[INFO] No valid show or playlist. Sleeping.")
            time.sleep(30)

@app.route("/")
def index():
    return render_template_string("""
    <html>
    <head><title>Streamify TV</title></head>
    <body style="background:black; color:white; text-align:center;">
        <h1>📺 Streamify TV</h1>
        <video width="640" height="360" controls autoplay muted playsinline>
            <source src="/stream.m3u8" type="application/vnd.apple.mpegurl">
        </video>
    </body>
    </html>
    """)

@app.route("/<path:path>")
def serve_file(path):
    return send_from_directory(HLS_DIR, path)

if __name__ == "__main__":
    Thread(target=streaming_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
