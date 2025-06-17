import os
import logging
import json
import tempfile
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
import yt_dlp
from urllib.parse import urlparse, parse_qs
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def is_valid_youtube_url(url):
    """Validate if the URL is a valid YouTube URL"""
    youtube_regex = re.compile(
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    return youtube_regex.match(url) is not None

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    youtube_regex = re.compile(
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    match = youtube_regex.match(url)
    if match:
        return match.group(6)
    return None

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    """Get video information from YouTube URL"""
    try:
        url = request.form.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'Please enter a YouTube URL'}), 400
        
        if not is_valid_youtube_url(url):
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400
        
        # Configure yt-dlp options
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
             'cookies': 'cookies.txt',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract video information
            info = ydl.extract_info(url, download=False)
            
            # Get available formats
            formats = []
            seen_qualities = set()
            
            if 'formats' in info:
                for fmt in info['formats']:
                    if fmt.get('vcodec') != 'none' and fmt.get('height'):
                        quality = f"{fmt['height']}p"
                        if quality not in seen_qualities:
                            formats.append({
                                'format_id': fmt['format_id'],
                                'quality': quality,
                                'ext': fmt.get('ext', 'mp4'),
                                'filesize': fmt.get('filesize'),
                                'fps': fmt.get('fps')
                            })
                            seen_qualities.add(quality)
            
            # Sort formats by quality (descending)
            formats.sort(key=lambda x: int(x['quality'].replace('p', '')), reverse=True)
            
            # Add audio-only option
            formats.append({
                'format_id': 'bestaudio',
                'quality': 'Audio Only (MP3)',
                'ext': 'mp3',
                'filesize': None,
                'fps': None
            })
            
            video_info = {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': formats[:10]  # Limit to top 10 formats
            }
            
            return jsonify(video_info)
            
    except yt_dlp.DownloadError as e:
        app.logger.error(f"yt-dlp error: {str(e)}")
        return jsonify({'error': 'Failed to fetch video information. Please check the URL and try again.'}), 400
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/download', methods=['POST'])
def download_video():
    """Download video with specified quality"""
    try:
        url = request.form.get('url', '').strip()
        format_id = request.form.get('format_id', 'best')
        
        if not url or not is_valid_youtube_url(url):
            flash('Invalid YouTube URL', 'error')
            return redirect(url_for('index'))
        
        # Create temporary directory for download
        temp_dir = tempfile.mkdtemp()
        
        # Configure yt-dlp options
        if format_id == 'bestaudio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'cookies': '/etc/secrets/cookies.txt',

            }
        else:
            ydl_opts = {
                'format': format_id,
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                  'cookies': '/etc/secrets/cookies.txt',
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Get video info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
            
            # Download the video
            ydl.download([url])
            
            # Find the downloaded file
            downloaded_files = os.listdir(temp_dir)
            if not downloaded_files:
                flash('Download failed. No file was created.', 'error')
                return redirect(url_for('index'))
            
            file_path = os.path.join(temp_dir, downloaded_files[0])
            
            # Send file to user
            return send_file(
                file_path,
                as_attachment=True,
                download_name=downloaded_files[0]
            )
            
    except yt_dlp.DownloadError as e:
        app.logger.error(f"Download error: {str(e)}")
        flash('Download failed. Please try again with a different quality option.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"Unexpected download error: {str(e)}")
        flash('An unexpected error occurred during download.', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
