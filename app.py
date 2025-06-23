import subprocess
import time
import os
from threading import Thread
from flask import Flask, send_from_directory, render_template_string
from datetime import datetime
import pytz

app = Flask(__name__)
HLS_DIR = "/tmp/hls"
TIMEZONE = pytz.timezone("Asia/Kolkata")

# Schedule: time (HH:MM) → playlist file
SCHEDULE = {
    "09:00": "pokemon.txt",
    "10:45": "chhota.txt",
    "12:00": "doraemon.txt",
    "13:00": "ps11.txt",
    "15:00": "chhota.txt",
    "18:00": "shinchan.txt",
    "19:00": "ram.txt",
    "20:00": "ps11.txt"
    
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
            return show_file, (current_minutes - start) * 60, (end - current_minutes) * 60
    return None, 0, 0

def get_video_duration(url):
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", url
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] Cannot get video duration: {e}")
        return 0

def start_ffmpeg_stream():
    while True:
        show_file, elapsed_time, remaining_time = get_current_show()
        if not show_file:
            print("[INFO] No show scheduled.")
            time.sleep(10)
            continue

        try:
            playlist = open(show_file).read().strip().splitlines()
        except:
            print(f"[ERROR] Cannot read {show_file}")
            time.sleep(10)
            continue

        cumulative = 0
        selected = None
        for video in playlist:
            duration = get_video_duration(video)
            if cumulative + duration > elapsed_time:
                offset = elapsed_time - cumulative
                selected = (video, offset)
                break
            cumulative += duration

        if not selected:
            print("[INFO] No episode fits the current time slot.")
            time.sleep(10)
            continue

        video_url, start_offset = selected
        video_duration = get_video_duration(video_url)
        play_time = video_duration - start_offset
        actual_duration = min(play_time, remaining_time)

        if actual_duration <= 0:
            print("[INFO] Skipping — no time left.")
            time.sleep(5)
            continue

        print(f"[PLAY] {video_url} (start: {start_offset:.1f}s, play: {actual_duration:.1f}s)")

        show_name = show_file.replace(".txt", "")
        show_logo = f"{show_name}.jpg"
        channel_logo = "logo.png"

        inputs = ["ffmpeg", "-re", "-ss", str(start_offset), "-i", video_url]
        filter_cmds = []
        input_index = 1

        if os.path.exists(show_logo):
            inputs += ["-i", show_logo]
            filter_cmds.append(f"[{input_index}:v]scale=200:105[showlogo]")
            input_index += 1
        if os.path.exists(channel_logo):
            inputs += ["-i", channel_logo]
            filter_cmds.append(f"[{input_index}:v]scale=200:100[channellogo]")
            input_index += 1

        overlay_chain = "[0:v]"
        if os.path.exists(show_logo):
            overlay_chain += "[showlogo]overlay=10:10[tmp1];"
        else:
            overlay_chain += "null[tmp1];"
        if os.path.exists(channel_logo):
            overlay_chain += "[tmp1][channellogo]overlay=W-w-10:10[out]"
        else:
            overlay_chain = overlay_chain.replace("[tmp1];", "[out]")

        filter_complex = ";".join(filter_cmds) + ";" + overlay_chain

        cmd = inputs + [
            "-t", str(actual_duration),
            "-filter_complex", filter_complex,
            "-map", "[out]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            "-f", "hls", "-hls_time", "5", "-hls_list_size", "10",
            "-hls_flags", "delete_segments+omit_endlist",
            os.path.join(HLS_DIR, "stream.m3u8")
        ]

        try:
            process = subprocess.Popen(cmd)
            process.wait()
        except Exception as e:
            print(f"[ERROR] FFmpeg crashed: {e}")
            time.sleep(5)

@app.route("/")
def index():
    return render_template_string("""
    <html>
    <head><title>📺 Streamify Live</title></head>
    <body style="background:black; color:white; text-align:center;">
        <h1>📺 Streamify Live TV</h1>
        <video width="640" height="360" controls autoplay>
            <source src="/stream.m3u8" type="application/vnd.apple.mpegurl">
        </video>
    </body>
    </html>
    """)

@app.route("/<path:path>")
def serve_file(path):
    return send_from_directory(HLS_DIR, path)

if __name__ == "__main__":
    Thread(target=start_ffmpeg_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
