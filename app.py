import subprocess, time, os
from threading import Thread
from flask import Flask, send_from_directory

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE = "logo.png"  # Your own logo (goes on opposite side of channel logo)

# Create required directory
os.makedirs(HLS_DIR, exist_ok=True)

def get_video_duration(url):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Could not get duration for {url}: {e}")
        return 0

def get_video_playlist():
    playlist = []
    if not os.path.exists("videos.txt"):
        return playlist

    with open("videos.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
        for url in urls:
            duration = get_video_duration(url)
            if duration > 0:
                playlist.append({"url": url, "duration": duration})
    return playlist

def get_current_video_info(playlist):
    total_duration = sum(v["duration"] for v in playlist)
    seconds_now = int(time.time()) % int(total_duration)

    for v in playlist:
        if seconds_now < v["duration"]:
            return v["url"], int(seconds_now)
        seconds_now -= int(v["duration"])

    return playlist[0]["url"], 0 if playlist else ("", 0)

def start_ffmpeg_stream():
    while True:
        playlist = get_video_playlist()
        if not playlist:
            print("[INFO] Playlist is empty, waiting...")
            time.sleep(10)
            continue

        url, seek_time = get_current_video_info(playlist)
        print(f"[INFO] Starting stream: {url} (seek {seek_time}s)")

        # Filter: add logo overlay to **top-left**
        filters = (
            "[1:v]scale=80:80[logo];"
            "[0:v][logo]overlay=10:10"  # Logo on top-left (opposite side of channel logo)
        )

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(seek_time),
            "-re",
            "-i", url,
            "-i", LOGO_FILE,
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
            process.wait()
        except Exception as e:
            print(f"[ERROR] FFmpeg crashed: {e}")
        time.sleep(1)

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
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
