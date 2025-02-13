# app.py
from datetime import datetime
import json
import time
from flask import Flask, request, redirect, url_for, render_template, send_file, session
from flask_httpauth import HTTPBasicAuth
import hashlib
import moviepy.editor as mp
import whisper
import os
from werkzeug.utils import secure_filename
import yt_dlp
import threading

progress = {"step": 0}  # Track processing steps
progress_lock = threading.Lock()

HISTORY_FILE = "history.json"

def load_history():
    """Load previous transcripts from file, ensuring it doesn't break on empty JSON."""
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:  # Create an empty JSON list if file doesn't exist
            f.write("[]")

    try:
        with open(HISTORY_FILE, "r") as f:
            data = f.read().strip()  # Read and remove any accidental spaces or newlines
            
            if not data:  # If the file is empty, return an empty list
                return []
            
            return json.loads(data)  # Convert JSON to Python list safely
    except json.JSONDecodeError:
        print("⚠️ WARNING: history.json is corrupted. Resetting history.")
        with open(HISTORY_FILE, "w") as f:
            f.write("[]")  # Reset to an empty JSON list
        return []


def save_to_history(video_url, video_filename, transcript_filename):
    """Save new transcript to history."""
    history = load_history()
    history_entry = {
        "video_url": video_url,
        "video_filename": video_filename,
        "transcript_filename": transcript_filename,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    history.append(history_entry)
    
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)


app = Flask(__name__)
auth = HTTPBasicAuth()

# Configure user credentials
users = {"user": "pass"}

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None

app.config['UPLOAD_FOLDER'] = 'uploads'  # Folder to store uploaded videos
app.config['TRANSCRIPTS_FOLDER'] = 'transcripts'  # Folder to store transcripts

# Ensure the upload and transcript folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TRANSCRIPTS_FOLDER'], exist_ok=True)

# Load Whisper model globally to avoid loading it every time
model = whisper.load_model("base")

def get_unique_filename(url):
    """Generate a unique filename based on the URL."""
    return hashlib.md5(url.encode()).hexdigest()  # Creates a unique hash for each video URL


def download_video(url, output_path_base):
    unique_filename = get_unique_filename(url)
    output_path_base = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

    ydl_opts = {
        'outtmpl': output_path_base + '.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'quiet': False,
        'noplaylist': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(result)
            
            # Use a default placeholder if thumbnail is missing
            thumbnail_url = result.get("thumbnail", "/static/default-thumbnail.jpg")  

            return {
                "path": video_path if os.path.exists(video_path) else None,
                "title": result.get("title", "Unknown"),
                "thumbnail": thumbnail_url,
                "uploader": result.get("uploader", "Unknown")
            }
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None

def extract_audio_and_transcribe(video_path, output_audio_path, output_transcript_path):
    video = mp.VideoFileClip(video_path)
    duration = video.duration  # Get video length in seconds
    audio = video.audio
    audio.write_audiofile(output_audio_path)

    with progress_lock:
        progress["step"] = 70  # Midway update

    start_time = time.time()
    result = model.transcribe(output_audio_path)

    with progress_lock:
        progress["step"] = 85  # Near completion update

    # Save transcript
    with open(output_transcript_path, "w") as f:
        f.write(result["text"])

    elapsed_time = time.time() - start_time
    estimated_total = (elapsed_time / (70 - 40)) * 100  # Extrapolate ETA
    final_progress = min(100, 85 + (100 - 85) * (elapsed_time / estimated_total))

    with progress_lock:
        progress["step"] = final_progress



@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def upload_file():
    global progress
    if request.method == 'POST':
        with progress_lock:
            progress["step"] = 10  # Start progress

        video_info = None
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            filename = secure_filename(file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(video_path)
        elif 'url' in request.form and request.form['url']:
            video_url = request.form['url']
            filename = secure_filename("downloaded_video")
            output_path_base = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            with progress_lock:
                progress["step"] = 20  # Download started

            video_info = download_video(video_url, output_path_base)

            if video_info is None or video_info["path"] is None:
                return 'Failed to download video', 400

            video_path = video_info["path"]  # Extract the correct video path

        if not os.path.exists(video_path):
            return 'Video file could not be found', 400

        with progress_lock:
            progress["step"] = 40  # Video downloaded

        # Define paths for audio and transcript
        audio_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}.wav"
        output_audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        transcript_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}_transcript.txt"
        output_transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], transcript_filename)

        with progress_lock:
            progress["step"] = 60  # Audio extraction started

        extract_audio_and_transcribe(video_path, output_audio_path, output_transcript_path)

        with progress_lock:
            progress["step"] = 100  # Done

        save_to_history(video_info.get("title", "Unknown"), os.path.basename(video_path), transcript_filename)

        return redirect(url_for('view_transcript', filename=transcript_filename, title=video_info.get("title", "Unknown"), thumbnail=video_info.get("thumbnail", ""), uploader=video_info.get("uploader", "Unknown")))

    return render_template('upload.html')


@app.route('/history')
@auth.login_required
def history():
    history_data = load_history()
    return render_template('history.html', history_data=history_data)


@app.route('/progress')
def get_progress():
    with progress_lock:
        return {"progress": progress["step"]}


@app.route('/transcript/<filename>')
@auth.login_required
def view_transcript(filename):
    transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename)

    if not os.path.exists(transcript_path):
        return 'Transcript not found', 404

    with open(transcript_path, 'r') as file:
        transcript_text = file.read()

    # Retrieve metadata from query parameters
    title = request.args.get("title", "Unknown Title")
    thumbnail = request.args.get("thumbnail", "")
    uploader = request.args.get("uploader", "Unknown Uploader")

    return render_template('transcript.html', transcript_text=transcript_text, filename=filename, title=title, thumbnail=thumbnail, uploader=uploader)


@app.route('/downloads/<filename>')
@auth.login_required
def download_transcript(filename):
    transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename)
    
    if not os.path.exists(transcript_path):
        return 'Transcript not found', 404

    return send_file(
        transcript_path,
        as_attachment=True,
        download_name=filename,
        mimetype='text/plain'
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
