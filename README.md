# Video to Text Transcription Service

This project is a Flask-based web application that allows users to upload video files and receive transcriptions of the audio content. The application uses the Whisper model for transcription and MoviePy for audio extraction.

## Acknowledgments

- [Flask](https://flask.palletsprojects.com/)
- [MoviePy](https://zulko.github.io/moviepy/)
- [Whisper](https://github.com/openai/whisper)

## Features

- **Video Upload**: Users can upload video files through a web interface.
- **Audio Extraction**: The application extracts audio from the uploaded video.
- **Transcription**: The extracted audio is transcribed into text using the Whisper model.
- **Download Transcripts**: Users can download the transcribed text file.

## Prerequisites

- Python 3.7+
- Flask
- Flask-HTTPAuth
- MoviePy
- Whisper
- Werkzeug

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/video-transcription-service.git
   cd video-transcription-service
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up user credentials**:
   - Edit the `app.py` file to configure user credentials in the `users` dictionary.

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Access the application**:
   - Open your web browser and go to `http://localhost:5000`.

## Usage

1. **Upload a Video**:
   - Navigate to the home page.
   - Select a video file to upload.
   - Click "Upload" to start the transcription process.

2. **Download Transcript**:
   - After processing, you will be redirected to a page where you can download the transcript.

## File Structure

- `app.py`: Main application file containing the Flask app and routes.
- `templates/upload.html`: HTML template for the upload page.
- `uploads/`: Directory where uploaded videos are stored.
- `transcripts/`: Directory where transcribed text files are saved.

## Security

- Basic HTTP authentication is implemented to secure the upload and download routes. Ensure to set strong credentials in the `users` dictionary.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
