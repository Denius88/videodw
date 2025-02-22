from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
import yt_dlp
import os
import shutil
import logging
from typing import Optional
import uuid
import asyncio
from urllib.parse import unquote
import re
import urllib.parse
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the absolute path of the backend directory
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_FOLDER = os.path.join(BACKEND_DIR, "downloads")
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Add URL validation patterns
URL_PATTERNS = {
    'youtube': re.compile(r'^(https?:\/\/)?(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[\w-]+'),
    'instagram': re.compile(r'https?:\/\/(?:www\.)?instagram\.com\/(?:p|reel|share)\/[\w-]+\/?'),
    'tiktok': re.compile(r'https?:\/\/(?:www\.|vm\.)?tiktok\.com\/')
}

class DownloadRequest(BaseModel):
    url: str
    format: str

    @validator('url')
    def validate_url(cls, v):
        v = v.strip()
        for platform, pattern in URL_PATTERNS.items():
            if pattern.match(v):
                return v
        raise ValueError('Invalid URL. Only YouTube, Instagram and TikTok URLs are supported')

def sanitize_filename(title: str) -> str:
    # First, replace any non-ASCII characters with their closest ASCII equivalents
    import unicodedata
    title = unicodedata.normalize('NFKD', title).encode('ASCII', 'ignore').decode('ASCII')
    # Then keep only alphanumeric characters and some special chars
    return "".join([c for c in title if c.isalnum() or c in ' .-_']).strip()

class ProgressCallback:
    def __init__(self):
        self.current = 0
        self.total = 0
        self.status = ""

    def __call__(self, d):
        if d['status'] == 'downloading':
            self.total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            self.current = d.get('downloaded_bytes', 0)
            if self.total:
                progress = int(self.current * 100 / self.total)
                return json.dumps({
                    "progress": progress,
                    "status": f"Завантаження: {d.get('filename', '')}"
                }) + "\n"
        elif d['status'] == 'finished':
            return json.dumps({
                "progress": 100,
                "status": "Обробка завершена"
            }) + "\n"

def download_media(url: str, format: str, download_id: str) -> tuple[str, str]:
    output_folder = os.path.join(TEMP_FOLDER, download_id)
    os.makedirs(output_folder, exist_ok=True)

    # Common headers and options
    common_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    base_opts = {
        'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'extract_flat': False,
        'http_headers': common_headers,
    }

    # For MP3 conversion, always download best quality first then convert
    if format == 'mp3':
        base_opts.update({
            'format': 'best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
        })

    if 'instagram.com' in url:
        url = url.split('?')[0]
        url = url.replace('/reels/', '/reel/')
        base_opts.update({
            'format': 'best' if format == 'mp3' else 'best[ext=mp4]',
            'extract_flat': False,
            'add_header': [
                ('User-Agent', 'Instagram 219.0.0.12.117 Android'),
                ('Origin', 'https://www.instagram.com'),
            ],
        })
    elif 'tiktok.com' in url:
        base_opts.update({
            'format': 'best' if format == 'mp3' else '(mp4)[width>=0]',
            'nocheckcertificate': True,
        })
    else:  # YouTube
        if format == 'mp3':
            base_opts.update({
                'format': 'bestaudio/best',
            })
        else:
            base_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
            })

    progress_callback = ProgressCallback()
    base_opts.update({
        'progress_hooks': [progress_callback],
        'quiet': False
    })

    try:
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            print(json.dumps({
                "progress": 0,
                "status": "Початок завантаження"
            }))
            
            info = ydl.extract_info(url, download=True)
            
            print(json.dumps({
                "progress": 95,
                "status": "Фінальна обробка"
            }))

            # Find downloaded file
            import glob
            pattern = '*.mp3' if format == 'mp3' else '*.mp4'
            files = glob.glob(os.path.join(output_folder, pattern))
            
            if not files and format == 'mp3':
                # If MP3 not found, look for any audio file
                files = glob.glob(os.path.join(output_folder, '*.[mM][pP]3'))
                if not files:
                    # Look for the downloaded video file that should be converted
                    video_files = glob.glob(os.path.join(output_folder, '*.[mM][pP]4'))
                    if (video_files):
                        # Convert video to mp3 manually if needed
                        video_path = video_files[0]
                        audio_path = os.path.splitext(video_path)[0] + '.mp3'
                        os.system(f'ffmpeg -i "{video_path}" -q:a 0 -map a "{audio_path}" -y')
                        files = [audio_path] if os.path.exists(audio_path) else []

            if not files:
                raise Exception("File not found after download")
                
            filepath = files[0]
            filename = os.path.basename(filepath)
            
            if os.path.getsize(filepath) == 0:
                raise Exception("Downloaded file is empty")

            return filename, filepath

    except Exception as e:
        # Cleanup on error
        shutil.rmtree(output_folder, ignore_errors=True)
        logger.error(f"Download error: {str(e)}")
        raise Exception(f"Помилка завантаження: {str(e)}")

@app.post("/api/download")
async def create_download(request: DownloadRequest):
    try:
        download_id = str(uuid.uuid4())
        
        async def download_generator():
            try:
                filename, filepath = download_media(request.url, request.format, download_id)
                yield json.dumps({
                    "success": True,
                    "download_id": download_id,
                    "filename": filename,
                    "progress": 100,
                    "status": "Завантаження завершено"
                })
            except Exception as e:
                yield json.dumps({
                    "error": str(e),
                    "progress": 0,
                    "status": "Помилка завантаження"
                })

        return StreamingResponse(
            download_generator(), 
            media_type="text/event-stream"
        )
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/download/{download_id}")
async def get_file(download_id: str, background_tasks: BackgroundTasks):
    try:
        # Ensure the download_id is valid UUID
        try:
            uuid.UUID(download_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid download ID")

        download_dir = os.path.join(TEMP_FOLDER, download_id)
        if not os.path.exists(download_dir):
            raise HTTPException(status_code=404, detail="File not found")
            
        # Get the first file in the directory
        files = os.listdir(download_dir)
        if not files:
            raise HTTPException(status_code=404, detail="No files found")
            
        filepath = os.path.join(download_dir, files[0])
        filename = files[0]

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File not found")

        # Check if file is empty
        if os.path.getsize(filepath) == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        async def cleanup_folder(path: str):
            try:
                await asyncio.sleep(5)  # Wait a bit before cleanup
                if os.path.exists(path):
                    shutil.rmtree(path)
                    logger.info(f"Cleaned up folder: {path}")
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}")

        # Encode the filename for HTTP header
        encoded_filename = urllib.parse.quote(filename)
        
        headers = {
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }

        # Add cleanup task to background tasks
        background_tasks.add_task(cleanup_folder, download_dir)

        return FileResponse(
            filepath,
            headers=headers,
            media_type='application/octet-stream',
            filename=filename
        )

    except Exception as e:
        # Cleanup on error
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir)
        logger.error(f"Error serving file: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# Add cleanup endpoint for failed downloads
@app.delete("/api/cleanup/{download_id}")
async def cleanup_download(download_id: str):
    try:
        download_dir = os.path.join(TEMP_FOLDER, download_id)
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
