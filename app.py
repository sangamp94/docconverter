import subprocess
import time
import os
from threading import Thread
from flask import Flask, send_from_directory, render_template_string
from datetime import datetime, timedelta
import pytz
import signal

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
TIMEZONE = pytz.timezone("Asia/Kolkata")

# Schedule format: "HH:MM" -> playlist filename
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

def run_ffmpeg_live_stream(video_url):
    # Clean up previous HLS files
    for f in os.listdir(HLS_DIR):
        try:
            os.remove(os.path.join(HLS_DIR, f))
        except:
            pass

    cmd = [
        "ffmpeg",
        "-re",                  # read input at native rate to simulate live
        "-i", video_url,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-c:a", "aac",
        "-f", "hls",
        "-hls_time", "4",           # 4-second segments
        "-hls_list_size", "5",      # keep last 5 segments (sliding window)
        "-hls_flags", "delete_segments+omit_endlist+independent_segments+program_date_time",
        os.path.join(HLS_DIR, "stream.m3u8"),
    ]

    print(f"[INFO] Starting ffmpeg for {video_url}")
    process = subprocess.Popen(cmd)
    return process

def streaming_loop():
    current_process = None
    current_show = None
    playlist = []
    episode_index = 0

    while True:
        show_file = get_current_show()

        if show_file != current_show:
            # Show changed, stop old ffmpeg and start new show
            if current_process:
                print(f"[INFO] Stopping ffmpeg for previous show {current_show}")
                current_process.send_signal(signal.SIGINT)
                current_process.wait()
                current_process = None

            current_show = show_file
            episode_index = 0

            if current_show:
                # Load playlist episodes
                try:
                    with open(current_show, "r") as f:
                        playlist = [line.strip() for line in f if line.strip()]
                    print(f"[INFO] Scheduled show: {current_show} with {len(playlist)} episodes")
                except Exception as e:
                    print(f"[ERROR] Cannot load playlist {current_show}: {e}")
                    playlist = []
            else:
                playlist = []

        if current_show and playlist:
            if episode_index >= len(playlist):
                print(f"[INFO] Finished all episodes in {current_show}, waiting for next schedule")
                # Wait for schedule change
                time.sleep(10)
                continue

            video_url = playlist[episode_index]
            current_process = run_ffmpeg_live_stream(video_url)
            # Wait for ffmpeg to finish streaming this episode
            retcode = current_process.wait()

            if retcode != 0:
                print(f"[ERROR] ffmpeg exited with code {retcode}, restarting stream")
            else:
                print(f"[INFO] Finished episode {episode_index + 1} of {current_show}")

            episode_index += 1
        else:
            print("[INFO] No show scheduled or empty playlist, waiting 30 seconds")
            time.sleep(30)

@app.route("/")
def index():
    return render_template_string("""
    <html>
    <head><title>Streamify TV - Live</title></head>
    <body style="background:black; color:white; text-align:center;">
        <h1>📺 Streamify TV - Live</h1>
        <video width="640" height="360" controls autoplay muted>
            <source src="/stream.m3u8" type="application/vnd.apple.mpegurl">
            Your browser does not support the video tag.
        </video>
        <p>Currently streaming live scheduled shows.</p>
    </body>
    </html>
    """)

@app.route("/<path:path>")
def serve_file(path):
    return send_from_directory(HLS_DIR, path)

if __name__ == "__main__":
    Thread(target=streaming_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
