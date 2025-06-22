import os, subprocess, time, shutil
from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory
from threading import Thread
from datetime import datetime
import pytz

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

HLS_DIR = "/tmp/hls"
LOGO_FILE = os.path.join(app.config['UPLOAD_FOLDER'], "logo.png")
TIMEZONE = pytz.timezone("Asia/Kolkata")

# Time-based schedule: "HH:MM" → file
SCHEDULE = {
    "09:00": "pokemon.txt",
    "12:00": "doraemon.txt",
    "15:00": "chhota.txt",
    "18:00": "shinchan.txt"
}

def get_current_playlist_file():
    now = datetime.now(TIMEZONE)
    current_minutes = now.hour * 60 + now.minute
    selected_file = None
    latest_time = -1
    for time_str, file in SCHEDULE.items():
        h, m = map(int, time_str.split(":"))
        minutes = h * 60 + m
        if current_minutes >= minutes > latest_time:
            latest_time = minutes
            selected_file = file
    path = os.path.join(app.config['UPLOAD_FOLDER'], selected_file)
    return path if selected_file and os.path.exists(path) else None

def get_video_duration(url):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15
        )
        return float(result.stdout.strip())
    except:
        return 0

def get_video_playlist(playlist_file):
    playlist = []
    with open(playlist_file, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                duration = get_video_duration(url)
                if duration > 0:
                    playlist.append({"url": url, "duration": duration})
    return playlist

def get_current_video_info(playlist):
    total_duration = sum(v["duration"] for v in playlist)
    if total_duration == 0: return playlist[0]["url"], 0
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
        poster_file = os.path.join(app.config['UPLOAD_FOLDER'], f"{show_name}.jpg")
        if not os.path.exists(poster_file):
            poster_file = os.path.join(app.config['UPLOAD_FOLDER'], "default.jpg")

        playlist = get_video_playlist(playlist_file)
        if not playlist:
            print("[ERROR] Playlist is empty.")
            time.sleep(30)
            continue
        url, seek_time = get_current_video_info(playlist)

        filters = (
            "[1:v]scale=100:100[logo];"
            "[2:v]scale=160:120[poster];"
            "[0:v][logo]overlay=W-w-20:20[tmp1];"
            "[tmp1][poster]overlay=20:20"
        )

        cmd = [
            "ffmpeg",
            "-ss", str(seek_time),
            "-re",
            "-i", url,
            "-i", LOGO_FILE,
            "-i", poster_file,
            "-filter_complex", filters,
            "-c:v", "libx264", "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "hls", "-hls_time", "10",
            "-hls_list_size", "5", "-hls_flags", "delete_segments",
            f"{HLS_DIR}/stream.m3u8"
        ]
        print(f"▶️ Playing: {url}")
        try:
            subprocess.run(cmd)
        except Exception as e:
            print(f"[ERROR] FFmpeg crash: {e}")
        time.sleep(1)

@app.route("/")
def home():
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    playlist_file = get_current_playlist_file()
    show = os.path.basename(playlist_file) if playlist_file else "N/A"
    return f"<h1>🖥 Live Cartoon TV</h1><p>⏰ {now} | 📺 {show}</p><a href='/stream.m3u8'>▶️ Watch Live</a><br><a href='/admin'>⚙️ Admin Panel</a>"

@app.route("/admin", methods=["GET", "POST"])
def admin():
    msg = ""
    if request.method == "POST":
        file = request.files.get("file")
        if file:
            fname = file.filename
            if fname.endswith((".txt", ".jpg", ".png")):
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                file.save(save_path)
                msg = f"✅ Uploaded {fname}"
            else:
                msg = "❌ Only .txt, .jpg, .png allowed."
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    html = """
    <h2>⚙️ Admin Panel</h2>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file><input type=submit value=Upload>
    </form>
    <p>{{msg}}</p>
    <h3>📂 Uploaded Files:</h3>
    <ul>
      {% for f in files %}
        <li><a href='/uploads/{{f}}' target='_blank'>{{f}}</a></li>
      {% endfor %}
    </ul>
    <a href='/'>⬅️ Back</a>
    """
    return render_template_string(html, msg=msg, files=files)

@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/stream.m3u8")
def stream():
    return send_from_directory(HLS_DIR, "stream.m3u8")

@app.route("/<path:filename>")
def stream_files(filename):
    return send_from_directory(HLS_DIR, filename)

if __name__ == "__main__":
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
