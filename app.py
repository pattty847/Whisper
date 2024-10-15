# app.py
from flask import Flask, request, redirect, url_for, render_template, send_file
import moviepy.editor as mp
import whisper
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'  # Folder to store uploaded videos
app.config['TRANSCRIPTS_FOLDER'] = 'transcripts'  # Folder to store transcripts

# Ensure the upload and transcript folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TRANSCRIPTS_FOLDER'], exist_ok=True)

# Load Whisper model globally to avoid loading it every time
model = whisper.load_model("base")

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
def upload_file():
    if request.method == 'POST':
        # Check if a file is included in the POST request
        if 'file' not in request.files:
            return 'No file part in the request', 400
        file = request.files['file']
        # If the user does not select a file
        if file.filename == '':
            return 'No selected file', 400
        if file:
            filename = secure_filename(file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(video_path)

            # Define paths for audio and transcript
            audio_filename = f"{os.path.splitext(filename)[0]}.wav"
            output_audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
            transcript_filename = f"{os.path.splitext(filename)[0]}_transcript.txt"
            output_transcript_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], transcript_filename)

            # Process the video file
            extract_audio_and_transcribe(video_path, output_audio_path, output_transcript_path)

            # Provide the transcript for download
            return redirect(url_for('download_transcript', filename=transcript_filename))
    return render_template('upload.html')

@app.route('/downloads/<filename>')
def download_transcript(filename):
    return send_file(os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
