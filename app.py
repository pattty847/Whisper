# app.py
import os
import json
import time
import uuid
import hashlib
import threading
import logging
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template, send_file
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename

import moviepy.editor as mp
import torch
import whisper
import yt_dlp

# Set up logging
logging.basicConfig(level=logging.INFO)

HISTORY_FILE = "history.json"

def load_history():
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            f.write("[]")
    try:
        with open(HISTORY_FILE, "r") as f:
            data = f.read().strip()
            if not data:
                return []
            return json.loads(data)
    except json.JSONDecodeError:
        logging.warning("history.json is corrupted. Resetting history.")
        with open(HISTORY_FILE, "w") as f:
            f.write("[]")
        return []

def save_to_history(video_url, video_filename, transcript_filename):
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
users = {"user": "pass"}

@auth.get_password
def get_pw(username):
    return users.get(username)

# Folders
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TRANSCRIPTS_FOLDER'] = 'transcripts'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TRANSCRIPTS_FOLDER'], exist_ok=True)

# Load Whisper model (optionally add your model selection logic)
device = "cuda" if torch.cuda.is_available() else "cpu"
model = whisper.load_model("base", device=device)
logging.info("✅ Loaded Whisper model: base")

# --- JOB MANAGEMENT (replacing global progress) ---
# Each job (keyed by a unique job_id) will have its own progress and results.
jobs = {}       # { job_id: { "progress": 0, "error": None, "transcript": None, ... } }
jobs_lock = threading.Lock()

def get_unique_filename(url):
    return hashlib.md5(url.encode()).hexdigest()

def download_video(url, output_path_base):
    unique_filename = get_unique_filename(url)
    output_path_base = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    ydl_opts = {
        'outtmpl': output_path_base + '.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'quiet': True,
        'noplaylist': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(result)
            thumbnail_url = result.get("thumbnail", "/static/default-thumbnail.png")
            return {
                "path": video_path if os.path.exists(video_path) else None,
                "title": result.get("title", "Unknown"),
                "thumbnail": thumbnail_url,
                "uploader": result.get("uploader", "Unknown")
            }
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        return None

def extract_audio_and_transcribe(video_path, output_audio_path, output_transcript_path, job_id):
    # Step 1: Extract audio
    try:
        video = mp.VideoFileClip(video_path)
        video.audio.write_audiofile(output_audio_path, logger=None)
    except Exception as e:
        logging.error(f"Audio extraction failed: {e}")
        with jobs_lock:
            jobs[job_id]["error"] = "Audio extraction failed."
        return

    with jobs_lock:
        jobs[job_id]["progress"] = 60

    # Step 2: Transcribe audio
    try:
        transcription_result = model.transcribe(output_audio_path)
        transcript_text = transcription_result["text"]
    except Exception as e:
        logging.error(f"Transcription failed: {e}")
        with jobs_lock:
            jobs[job_id]["error"] = "Transcription failed."
        return

    # Save transcript to file
    try:
        with open(output_transcript_path, "w") as f:
            f.write(transcript_text)
    except Exception as e:
        logging.error(f"Saving transcript failed: {e}")
        with jobs_lock:
            jobs[job_id]["error"] = "Saving transcript failed."
        return

    with jobs_lock:
        jobs[job_id]["progress"] = 100
        jobs[job_id]["transcript_filename"] = os.path.basename(output_transcript_path)
        jobs[job_id]["video_title"] = os.path.basename(video_path).rsplit(".", 1)[0]
    # Optionally remove temporary audio file:
    try:
        os.remove(output_audio_path)
    except Exception:
        pass

def process_video(job_id, form_data):
    with jobs_lock:
        jobs[job_id]["progress"] = 10

    video_title = "Unknown"
    video_thumbnail = "/static/default-thumbnail.png"
    video_uploader = "Unknown"

    # Use the pre-saved file if available
    if "file_path" in form_data:
        video_path = form_data["file_path"]
        video_title = os.path.splitext(os.path.basename(video_path))[0]
    elif "url" in form_data and form_data["url"]:
        video_url = form_data["url"]
        with jobs_lock:
            jobs[job_id]["progress"] = 20
        video_info = download_video(video_url, os.path.join(app.config['UPLOAD_FOLDER'], "downloaded_video"))
        if video_info is None or video_info["path"] is None:
            with jobs_lock:
                jobs[job_id]["error"] = "Failed to download video."
            return
        video_path = video_info["path"]
        video_title = video_info.get("title", "Unknown")
        video_thumbnail = video_info.get("thumbnail", video_thumbnail)
        video_uploader = video_info.get("uploader", "Unknown")
    else:
        with jobs_lock:
            jobs[job_id]["error"] = "No file or URL provided."
        return

    if not os.path.exists(video_path):
        with jobs_lock:
            jobs[job_id]["error"] = "Video file could not be found."
        return

    with jobs_lock:
        jobs[job_id]["progress"] = 40

    # Define paths for audio and transcript
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    audio_filename = f"{base_name}.wav"
    transcript_filename = f"{base_name}_transcript.txt"
    output_audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
    output_transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], transcript_filename)

    with jobs_lock:
        jobs[job_id]["progress"] = 50

    extract_audio_and_transcribe(video_path, output_audio_path, output_transcript_path, job_id)

    with jobs_lock:
        if not jobs[job_id].get("error"):
            save_to_history(video_title, os.path.basename(video_path), transcript_filename)
            jobs[job_id]["video_thumbnail"] = video_thumbnail
            jobs[job_id]["video_uploader"] = video_uploader
            jobs[job_id]["video_url"] = form_data.get("url", "Uploaded File")


@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def upload_file():
    if request.method == 'POST':
        # Create a new job and start a background thread
        job_id = str(uuid.uuid4())
        with jobs_lock:
            jobs[job_id] = {"progress": 0, "error": None}

        form_data = {}
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            filename = secure_filename(file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # Save the file in the main thread
            file.save(video_path)
            form_data["file_path"] = video_path
        elif 'url' in request.form and request.form['url']:
            form_data["url"] = request.form['url']

        # Start the processing thread
        thread = threading.Thread(target=process_video, args=(job_id, form_data))
        thread.start()

        # Redirect to a processing page that polls the job progress.
        return redirect(url_for('job_status', job_id=job_id))
    return render_template('upload.html')


@app.route('/job/<job_id>')
@auth.login_required
def job_status(job_id):
    # This page shows a progress bar and will redirect when job is done.
    return render_template('processing.html', job_id=job_id)

@app.route('/progress/<job_id>')
def get_progress(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return {"progress": 0, "error": "Job not found"}
        return {
            "progress": job["progress"],
            "error": job["error"],
            "transcript_filename": job.get("transcript_filename"),
            "video_title": job.get("video_title"),
            "video_thumbnail": job.get("video_thumbnail"),
            "video_uploader": job.get("video_uploader")
        }

@app.route('/transcript/<filename>')
@auth.login_required
def view_transcript(filename):
    transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename)
    if not os.path.exists(transcript_path):
        return 'Transcript not found', 404
    with open(transcript_path, 'r') as file:
        transcript_text = file.read()
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

@app.route('/history')
@auth.login_required
def history():
    history_data = load_history()
    return render_template('history.html', history_data=history_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
