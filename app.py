import subprocess, time, os, json, shutil
from threading import Thread
from flask import Flask, send_from_directory
from datetime import datetime, time as dt_time
import pytz

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
SCHEDULE_LOG = "schedule_log.json"
os.makedirs(HLS_DIR, exist_ok=True)

IST = pytz.timezone("Asia/Kolkata")

SCHEDULE = [
    ("pokemon",  dt_time(7, 0),  dt_time(12, 0)),
    ("doraemon", dt_time(12, 0), dt_time(13, 0)),
    ("pokemon",  dt_time(13, 0), dt_time(15, 0)),
    ("chhota",   dt_time(15, 0), dt_time(18, 0)),
    ("shinchan", dt_time(18, 0), dt_time(20, 0)),
    ("ramayan",  dt_time(20, 0), dt_time(23, 59, 59)),
]

def get_current_show():
    if not os.path.exists("show.txt"):
        return None
    with open("show.txt", "r") as f:
        return f.read().strip().lower()

def set_current_show(show):
    with open("show.txt", "w") as f:
        f.write(show)

def get_show_for_now():
    now = datetime.now(IST).time()
    for show, start, end in SCHEDULE:
        if start <= now < end:
            return show, start.strftime("%H:%M")
    return None, None

def scheduler_thread():
    current_show = None
    while True:
        show_now, _ = get_show_for_now()
        if show_now != current_show and show_now is not None:
            print(f"[SCHEDULER] Switching to: {show_now}")
            set_current_show(show_now)
            current_show = show_now
        time.sleep(10)

def get_video_duration(url):
    print(f"[DEBUG] Checking duration for: {url}")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Duration fetch failed: {e}")
        return 0

def get_video_playlist(file):
    print(f"[DEBUG] Reading playlist: {file}")
    playlist = []
    if not os.path.exists(file):
        print(f"[ERROR] Playlist file missing: {file}")
        return playlist
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                duration = get_video_duration(url)
                if duration > 0:
                    playlist.append({"url": url, "duration": duration})
    return playlist

def clear_hls_stream():
    print("[DEBUG] Clearing old HLS stream")
    for f in os.listdir(HLS_DIR):
        path = os.path.join(HLS_DIR, f)
        if os.path.isfile(path):
            os.remove(path)

def play_videos_in_order():
    current_show = None
    ffmpeg_process = None

    while True:
        show = get_current_show()
        if not show:
            print("[INFO] No current show found.")
            time.sleep(5)
            continue

        if show != current_show:
            if ffmpeg_process:
                print(f"[SWITCH] Killing FFmpeg for previous show: {current_show}")
                ffmpeg_process.kill()
                ffmpeg_process = None
            clear_hls_stream()
            current_show = show

        playlist_file = f"{show}.txt"
        playlist = get_video_playlist(playlist_file)
        if not playlist:
            print(f"[ERROR] Playlist empty for show: {show}")
            time.sleep(5)
            continue

        index = 0
        offset = 0

        while index < len(playlist):
            if get_current_show() != show:
                print(f"[INTERRUPT] Show changed during playback: {get_current_show()}")
                break

            video = playlist[index]
            url = video["url"]
            duration = int(video["duration"])

            now = datetime.now(IST)
            time_left = 600  # fallback default
            for s_name, start, end in SCHEDULE:
                if s_name == show:
                    end_dt = datetime.combine(now.date(), end, tzinfo=IST)
                    time_left = int((end_dt - now).total_seconds())
                    break

            remaining = duration - offset
            play_time = min(remaining, time_left)

            print(f"[DEBUG] Duration={duration}, Offset={offset}, Remaining={remaining}, TimeLeft={time_left}, PlayTime={play_time}")

            if play_time <= 0 or remaining <= 0 or time_left <= 0:
                print("[WARN] Skipping due to invalid time values.")
                index += 1
                offset = 0
                continue

            print(f"[PLAYING] {show.upper()} - Episode {index+1} from {offset}s for {play_time}s")

            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", str(offset),
                "-re",
                "-t", str(play_time),
                "-i", url,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-c:a", "aac",
                "-b:a", "128k",
                "-f", "hls",
                "-hls_time", "4",
                "-hls_list_size", "3",
                "-hls_flags", "delete_segments",
                "-hls_allow_cache", "0",
                f"{HLS_DIR}/stream.m3u8"
            ]

            try:
                ffmpeg_process = subprocess.Popen(cmd)
                start_time = time.time()
                while time.time() - start_time < play_time:
                    if get_current_show() != show:
                        print(f"[FORCE STOP] New show: {get_current_show()}")
                        ffmpeg_process.kill()
                        clear_hls_stream()
                        break
                    if ffmpeg_process.poll() is not None:
                        break
                    time.sleep(1)
                offset += int(time.time() - start_time)
                if offset >= duration:
                    index += 1
                    offset = 0
            except Exception as e:
                print(f"[ERROR] FFmpeg failed: {e}")
                time.sleep(5)
                break

@app.route('/')
def home():
    show = get_current_show()
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    return f"<h1>📺 Cartoon Live TV</h1><p>🕒 {now}<br>🎬 Now Showing: <b>{show.upper() if show else 'None'}</b></p><a href='/stream.m3u8'>▶️ Watch</a>"

@app.route('/stream.m3u8')
def serve_m3u8():
    return send_from_directory(HLS_DIR, "stream.m3u8")

@app.route('/<path:filename>')
def serve_file(filename):
    return send_from_directory(HLS_DIR, filename)

if __name__ == "__main__":
    Thread(target=scheduler_thread, daemon=True).start()
    Thread(target=play_videos_in_order, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
