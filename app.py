# app.py
from flask import Flask, request, redirect, url_for, render_template, send_file
from flask_httpauth import HTTPBasicAuth
import instaloader
import moviepy.editor as mp
import whisper
import os
from werkzeug.utils import secure_filename
import yt_dlp

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

def download_yt_video(url, output_path_base):
    ydl_opts = {
        'outtmpl': output_path_base + '.%(ext)s',
        'format': 'bestvideo+bestaudio/best'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.download([url])
    # Find the file with the final extension
    downloaded_files = [f for f in os.listdir(os.path.dirname(output_path_base)) if f.startswith(os.path.basename(output_path_base))]
    if downloaded_files:
        return os.path.join(os.path.dirname(output_path_base), downloaded_files[0])
    return None

def download_instagram_video(url, output_path_base):
    L = instaloader.Instaloader(download_videos=True, download_comments=False, save_metadata=False)
    try:
        post = instaloader.Post.from_shortcode(L.context, url.split('/')[-2])
        L.download_post(post, target=output_path_base)
        # Find the downloaded video file
        downloaded_files = [f for f in os.listdir(output_path_base) if f.endswith('.mp4')]
        if downloaded_files:
            return os.path.join(output_path_base, downloaded_files[0])
    except Exception as e:
        print(f"Error downloading Instagram video: {e}")
    return None

def extract_audio_and_transcribe(video_path, output_audio_path, output_transcript_path):
    # Extract audio from video
    video = mp.VideoFileClip(video_path)
    audio = video.audio
    audio.write_audiofile(output_audio_path)

    # Transcribe audio
    result = model.transcribe(output_audio_path)

    # Save transcript
    with open(output_transcript_path, "w") as f:
        f.write(result["text"])

@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def upload_file():
    if request.method == 'POST':
        video_path = ""
        
        # Check if a file is included in the POST request
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            filename = secure_filename(file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(video_path)
        elif 'url' in request.form and request.form['url'] != '':
            # Handle URL input
            video_url = request.form['url']
            filename = secure_filename(f"downloaded_video")
            output_path_base = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            if "instagram.com" in video_url:
                video_path = download_instagram_video(video_url, output_path_base)
            else:
                video_path = download_yt_video(video_url, output_path_base)
            
            if video_path is None:
                return 'Failed to download video', 400
        else:
            return 'No file or URL provided', 400

        # If no valid video path was obtained
        if not os.path.exists(video_path):
            return 'Video file could not be found', 400

        # Define paths for audio and transcript
        audio_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}.wav"
        output_audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        transcript_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}_transcript.txt"
        output_transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], transcript_filename)

        # Process the video file
        extract_audio_and_transcribe(video_path, output_audio_path, output_transcript_path)

        # Provide the transcript for download
        return redirect(url_for('view_transcript', filename=transcript_filename))
    
    return render_template('upload.html')


@app.route('/transcript/<filename>')
@auth.login_required
def view_transcript(filename):
    transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename)
    if not os.path.exists(transcript_path):
        return 'Transcript not found', 404

    with open(transcript_path, 'r') as file:
        transcript_text = file.read()

    return render_template('transcript.html', transcript_text=transcript_text, filename=filename)


@app.route('/downloads/<filename>')
@auth.login_required
def download_transcript(filename):
    return send_file(os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
