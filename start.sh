#!/bin/bash

# Start the Flask app in the background
python3 app.py &

# Start ngrok and bind it to port 5000 (same as Flask)
ngrok http 5000
