import subprocess, time, os, shutil, json
from threading import Thread
from flask import Flask, send_from_directory
from datetime import datetime
import pytz

app = Flask(__name__)

HLS_DIR = "/tmp/hls"
LOGO_FILE = "logo.png"
TIMEZONE = pytz.timezone("Asia/Kolkata")
STATE_FILE = "playback_state.json"

SCHEDULE = {
    "09:00": "pokemon.txt",
    "12:00": "doraemon.txt",
    "15:00": "chhota.txt",
    "18:00": "shinchan.txt",
    "20:35": "pokemon.txt",
    "23:00": "doraemon.txt"
}

os.makedirs(HLS_DIR, exist_ok=True)


def get_current_schedule_block():
    now = datetime.now(TIMEZONE)
    current_minutes = now.hour * 60 + now.minute
    latest_time = None
    selected_file = None
    start_time = None

    for time_str, file in SCHEDULE.items():
        h, m = map(int, time_str.split(":"))
        start_minutes = h * 60 + m
        if current_minutes >= start_minutes:
            if latest_time is None or start_minutes > latest_time:
                latest_time = start_minutes
                selected_file = file
                start_time = h * 3600 + m * 60

    return selected_file, start_time


def get_next_schedule_time(current_time_sec):
    today = datetime.now(TIMEZONE)
    times = sorted(SCHEDULE.keys(), key=lambda t: int(t[:2]) * 60 + int(t[3:]))

    for t in times:
        h, m = map(int, t.split(":"))
        t_sec = h * 3600 + m * 60
        if t_sec > current_time_sec:
            return t_sec

    # If past last slot, use tomorrow's first
    first = times[0]
    h, m = map(int, first.split(":"))
    return (24 * 3600) + (h * 3600 + m * 60)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def get_video_duration(url):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Failed to get duration for {url}: {e}")
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


def start_ffmpeg_stream():
    shutil.rmtree(HLS_DIR, ignore_errors=True)
    os.makedirs(HLS_DIR, exist_ok=True)

    state = load_state()

    while True:
        playlist_file, block_start_time = get_current_schedule_block()
        now = datetime.now(TIMEZONE)
        now_sec = now.hour * 3600 + now.minute * 60 + now.second
        block_end_time = get_next_schedule_time(block_start_time)

        if not playlist_file:
            print("[ERROR] No valid playlist file found.")
            time.sleep(30)
            continue

        show_name = os.path.splitext(os.path.basename(playlist_file))[0]
        show_poster = f"{show_name}.jpg"
        if not os.path.exists(show_poster):
            show_poster = "default.jpg"

        playlist = get_video_playlist(playlist_file)
        if not playlist:
            print(f"[ERROR] Empty playlist for {show_name}")
            time.sleep(30)
            continue

        if show_name not in state:
            state[show_name] = {"index": 0, "offset": 0, "finished": True}

        while now_sec < block_end_time:
            current_index = state[show_name]["index"]
            if current_index >= len(playlist):
                print(f"✅ All episodes of {show_name} played. Waiting for next scheduled show...")
                while now_sec < block_end_time:
                    time.sleep(10)
                    now = datetime.now(TIMEZONE)
                    now_sec = now.hour * 3600 + now.minute * 60 + now.second
                break

            episode = playlist[current_index]
            url = episode["url"]
            duration = episode["duration"]
            seek_time = state[show_name]["offset"] if not state[show_name]["finished"] else 0

            print(f"\n🎬 Streaming: {os.path.basename(url)} (Seek: {seek_time}s)")

            filters = (
                "[1:v]scale=100:100[logo];"
                "[2:v]scale=160:120[show];"
                "[0:v][logo]overlay=W-w-20:20[tmp1];"
                "[tmp1][show]overlay=20:20"
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

            start_time = time.time()
            proc = subprocess.Popen(cmd)

            while proc.poll() is None:
                time.sleep(5)
                now = datetime.now(TIMEZONE)
                now_sec = now.hour * 3600 + now.minute * 60 + now.second
                elapsed = time.time() - start_time

                if now_sec >= block_end_time:
                    print("⏱ Time's up. Ending current show block.")
                    proc.terminate()
                    proc.wait()
                    if elapsed < duration:
                        state[show_name]["offset"] = int(elapsed + seek_time)
                        state[show_name]["finished"] = False
                    else:
                        state[show_name]["offset"] = 0
                        state[show_name]["index"] += 1
                        state[show_name]["finished"] = True
                    save_state(state)
                    break

            else:
                # Episode finished
                state[show_name]["index"] += 1
                state[show_name]["offset"] = 0
                state[show_name]["finished"] = True
                save_state(state)

        time.sleep(1)


@app.route('/')
def home():
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    playlist_file, _ = get_current_schedule_block()
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
