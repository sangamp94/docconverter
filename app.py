import subprocess, time, os, shutil
from threading import Thread
from flask import Flask, send_from_directory
from datetime import datetime
import pytz

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE = "logo.png"
TIMEZONE = pytz.timezone("Asia/Kolkata")

# Schedule: time → playlist file (all in root folder)
SCHEDULE = {
    "09:00": "pokemon.txt",
    "12:00": "doraemon.txt",
    "15:00": "chhota.txt",
    "18:00": "shinchan.txt"
}

def get_current_playlist_file():
    now = datetime.now(TIMEZONE)
    current_minutes = now.hour * 60 + now.minute
    latest_time = None
    selected_file = None
    for time_str, file in SCHEDULE.items():
        h, m = map(int, time_str.split(":"))
        start_minutes = h * 60 + m
        if current_minutes >= start_minutes:
            if latest_time is None or start_minutes > latest_time:
                latest_time = start_minutes
                selected_file = file
    return selected_file if selected_file and os.path.exists(selected_file) else None

def get_video_duration(url):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Duration check failed: {e}")
        return 0

def get_video_playlist(playlist_file):
    playlist = []
    with open(playlist_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
        for url in urls:
            duration = get_video_duration(url)
            if duration > 0:
                playlist.append({"url": url, "duration": duration})
    return playlist

def get_current_video_info(playlist):
    total_duration = sum(v["duration"] for v in playlist)
    if total_duration == 0:
        return playlist[0]["url"], 0
    seconds_now = int(time.time()) % int(total_duration)
    for v in playlist:
        if seconds_now < v["duration"]:
            return v["url"], int(seconds_now)
        seconds_now -= int(v["duration"])
    return playlist[0]["url"], 0

def start_ffmpeg_stream():
    shutil.rmtree(HLS_DIR, ignore_errors=True)
    os.makedirs(HLS_DIR, exist_ok=True)

    while True:
        playlist_file = get_current_playlist_file()
        if not playlist_file:
            print("[ERROR] No valid playlist file found.")
            time.sleep(30)
            continue

        show_name = os.path.splitext(os.path.basename(playlist_file))[0]
        show_poster = f"{show_name}.jpg"
        if not os.path.exists(show_poster):
            print(f"[WARN] Poster for {show_name} not found. Using default.")
            show_poster = "default.jpg"

        playlist = get_video_playlist(playlist_file)
        if not playlist:
            print("[ERROR] Playlist is empty.")
            time.sleep(30)
            continue

        url, seek_time = get_current_video_info(playlist)
        print(f"\n🎬 Streaming: {os.path.basename(url)} from {playlist_file}")

        filters = (
            "[1:v]scale=100:100[logo];"
            "[2:v]scale=200:300[show];"
            "[0:v][logo]overlay=W-w-20:20[tmp1];"
            "[tmp1][show]overlay=W-w-20:H-h-20"
        )

        cmd = [
            "ffmpeg",
            "-ss", str(seek_time),
            "-re",
            "-i", url,
            "-i", LOGO_FILE,
            "-i", show_poster,
            "-filter_complex", filters,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "hls",
            "-hls_time", "10",
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments",
            "-hls_start_number_source", "epoch",
            f"{HLS_DIR}/stream.m3u8"
        ]

        try:
            process = subprocess.Popen(cmd)
            process.wait()
        except Exception as e:
            print(f"[ERROR] FFmpeg crashed: {e}")
        time.sleep(1)

@app.route('/')
def home():
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    playlist_file = get_current_playlist_file()
    show_name = os.path.basename(playlist_file).replace(".txt", "") if playlist_file else "Unknown"
    return f"<h1>📺 Cartoon Live TV</h1><p>🕒 {now} | 🎬 Now Showing: {show_name}</p><a href='/stream.m3u8'>▶️ Watch Stream</a>"

@app.route('/stream.m3u8')
def m3u8():
    return send_from_directory(HLS_DIR, "stream.m3u8")

@app.route('/<path:filename>')
def ts_files(filename):
    return send_from_directory(HLS_DIR, filename)

if __name__ == "__main__":
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
