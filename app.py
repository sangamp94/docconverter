import subprocess, time, os
from threading import Thread
from flask import Flask, send_from_directory

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
LOGO_FILE = "logo.png"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

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
    except:
        return 0

def get_video_playlist():
    playlist = []
    with open("videos.txt", "r") as f:
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
    return playlist[0]["url"], 0

def start_ffmpeg_stream():
    os.makedirs(HLS_DIR, exist_ok=True)
    while True:
        playlist = get_video_playlist()
        if not playlist:
            print("Playlist empty.")
            time.sleep(10)
            continue

        url, seek_time = get_current_video_info(playlist)
        title = url.split("/")[-1][:30]

        filters = (
            "[1:v]scale=100:100[logo];"
            "[0:v][logo]overlay=W-w-20:20[video];"
            f"[video]drawtext=fontfile={FONT_PATH}:"
            f"text='Now Playing: {title}':"
            "fontcolor=white:fontsize=20:x=10:y=H-th-30:box=1:boxcolor=black@0.5,"
            f"drawtext=fontfile={FONT_PATH}:"
            "text='%{localtime\\:%H\\\\:%M}':"
            "fontcolor=white:fontsize=20:x=W-tw-20:y=10:box=1:boxcolor=black@0.4"
        )

        cmd = [
            "ffmpeg",
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
            "-hls_flags", "delete_segments",
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
    return f"<h1>✅ Streamify Live TV</h1><p><a href='/stream.m3u8'>Watch Live</a></p>"

@app.route('/stream.m3u8')
def serve_m3u8():
    return send_from_directory(HLS_DIR, "stream.m3u8")

@app.route('/<path:filename>')
def serve_segments(filename):
    return send_from_directory(HLS_DIR, filename)

if __name__ == "__main__":
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
