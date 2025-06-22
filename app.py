import subprocess, time, os
from threading import Thread
from flask import Flask, send_from_directory

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE_RIGHT = "logo.png"   # Top-right
LOGO_FILE_LEFT = "show.jpg"    # Top-left

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
        print(f"[ERROR] Duration fetch failed: {e}")
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

# 🆕 LINEAR PLAY MODE — play one by one, restarting at end
def play_videos_in_order():
    playlist = get_video_playlist()
    while True:
        if not playlist:
            print("[INFO] Playlist empty, retrying...")
            time.sleep(10)
            playlist = get_video_playlist()
            continue

        for video in playlist:
            url = video["url"]
            duration = int(video["duration"])
            print(f"[INFO] Playing: {url} (0s to {duration}s)")

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
                "-i", LOGO_FILE_LEFT,
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
