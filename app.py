import subprocess, time, os, shutil, urllib.parse
from threading import Thread
from flask import Flask, send_from_directory

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE = "logo.png"           # Top-right logo
NOW_POSTER = "now.jpg"           # Bottom-left (current episode)
SHOW_POSTER = "show.jpg"         # Bottom-right (series poster)
VIDEO_LIST_FILE = "videos.txt"
POSTERS_DIR = "posters"          # Folder with episode posters (optional)

def get_video_duration(url):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Duration check failed: {e}")
        return 0

def get_video_playlist():
    playlist = []
    if not os.path.exists(VIDEO_LIST_FILE):
        print("[ERROR] videos.txt not found!")
        return playlist
    with open(VIDEO_LIST_FILE, "r") as f:
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
    return playlist[0]["url"], 0  # fallback

def update_now_poster(url):
    # Try to match a poster to the current episode
    episode_name = os.path.basename(urllib.parse.unquote(url))
    poster_path = os.path.join(POSTERS_DIR, episode_name.replace(".mp4", ".jpg"))
    if os.path.exists(poster_path):
        shutil.copyfile(poster_path, NOW_POSTER)
        print(f"[INFO] Now poster updated: {poster_path}")
    elif os.path.exists("default.jpg"):
        shutil.copyfile("default.jpg", NOW_POSTER)
        print("[INFO] Using default poster for now.jpg")
    else:
        shutil.copyfile(SHOW_POSTER, NOW_POSTER)
        print("[INFO] Using show poster as now.jpg")

def start_ffmpeg_stream():
    shutil.rmtree(HLS_DIR, ignore_errors=True)
    os.makedirs(HLS_DIR, exist_ok=True)

    while True:
        playlist = get_video_playlist()
        if not playlist:
            print("[WAITING] videos.txt is empty or invalid...")
            time.sleep(10)
            continue

        url, seek_time = get_current_video_info(playlist)
        print(f"\n🎬 Now Playing: {os.path.basename(url)} (seek {seek_time}s)")

        update_now_poster(url)

        # Overlay: logo top-right, now.jpg bottom-left, show.jpg bottom-right
        filters = (
            "[1:v]scale=100:100[logo];"
            "[2:v]scale=200:300[now];"
            "[3:v]scale=200:300[show];"
            "[0:v][logo]overlay=W-w-20:20[tmp1];"
            "[tmp1][now]overlay=20:H-h-20[tmp2];"
            "[tmp2][show]overlay=W-w-20:H-h-20"
        )

        cmd = [
            "ffmpeg",
            "-ss", str(seek_time),
            "-re",
            "-i", url,          # Input video
            "-i", LOGO_FILE,    # Logo
            "-i", NOW_POSTER,   # Now playing poster
            "-i", SHOW_POSTER,  # Show poster
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
def index():
    return "<h1>🎥 Cartoon Live TV</h1><p><a href='/stream.m3u8'>📺 Watch Now</a></p>"

@app.route('/stream.m3u8')
def serve_m3u8():
    return send_from_directory(HLS_DIR, "stream.m3u8")

@app.route('/<path:filename>')
def serve_ts(filename):
    return send_from_directory(HLS_DIR, filename)

if __name__ == "__main__":
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
