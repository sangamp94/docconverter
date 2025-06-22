from flask import Flask, request, send_file, render_template_string
from app.py.editor import VideoFileClip, ImageClip, CompositeVideoClip
import os

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
STATIC_FOLDER = 'static'

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Simple upload form
HTML_FORM = '''
<!doctype html>
<title>Upload Episode</title>
<h2>Upload an Episode</h2>
<form method=post enctype=multipart/form-data>
  <input type=file name=video><br><br>
  <input type=submit value=Upload>
</form>
{% if download_url %}
  <br><a href="{{ download_url }}">Download Processed Video</a>
{% endif %}
'''

@app.route('/', methods=['GET', 'POST'])
def upload_video():
    if request.method == 'POST':
        video_file = request.files['video']
        if video_file:
            video_path = os.path.join(UPLOAD_FOLDER, 'episode1.mp4')
            output_path = os.path.join(OUTPUT_FOLDER, 'output.mp4')

            # Save uploaded file
            video_file.save(video_path)

            # Process video with logos
            process_video(video_path, output_path)

            return render_template_string(HTML_FORM, download_url='/download')
    
    return render_template_string(HTML_FORM)

@app.route('/download')
def download_video():
    return send_file(os.path.join(OUTPUT_FOLDER, 'output.mp4'), as_attachment=True)

def process_video(video_path, output_path):
    video = VideoFileClip(video_path)

    # Load logos
    left_logo = ImageClip(os.path.join(STATIC_FOLDER, 'pokemon_logo.png')).set_duration(video.duration)
    right_logo = ImageClip(os.path.join(STATIC_FOLDER, 'channel_logo.png')).set_duration(video.duration)

    # Resize both logos to same height
    left_logo = left_logo.resize(height=60).set_position(("left", "top")).margin(left=10, top=10)
    right_logo = right_logo.resize(height=60).set_position(("right", "top")).margin(right=10, top=10)

    # Overlay logos
    final = CompositeVideoClip([video, left_logo, right_logo])

    # Export
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")

if __name__ == '__main__':
    app.run(debug=True)
