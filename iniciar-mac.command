#!/bin/bash
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "Falta FFmpeg. Instálalo con:  brew install ffmpeg"; read; exit 1; }
python3 servidor.py
