# 🎬 VideoDW: Asynchronous Media Processing Service

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)
![Telegram API](https://img.shields.io/badge/Telegram_Bot-API-blue.svg?logo=telegram)
![FFmpeg](https://img.shields.io/badge/FFmpeg-processing-green.svg)

VideoDW is a robust, asynchronous Python-based backend service designed to extract, process, and download media from major social platforms (YouTube, Instagram, TikTok). It provides two distinct client interfaces: a **Telegram Bot** and a **Web UI**, both utilizing the same core processing logic.

The project demonstrates advanced backend capabilities, including real-time progress streaming (Server-Sent Events), dynamic video compression via FFmpeg, and asynchronous task management.

## ✨ Core Features

*   **Multi-Platform Support:** Seamlessly handles YouTube, Instagram (Reels/Posts), and TikTok URLs (including watermark bypassing).
*   **Format Extraction:** Supports both raw high-quality `MP4` video and `MP3` audio extraction.
*   **Dual Interfaces:**
    *   🤖 **Telegram Bot Interface:** Asynchronous bot using `python-telegram-bot` (v20+), featuring conversation handlers, dynamic inline keyboards, and automated file size optimization to bypass API limits.
    *   🌐 **Web Service Interface:** Built with `FastAPI`, featuring a responsive Vanilla JS/CSS frontend with Dark/Light modes, i18n (EN/UK), and real-time progress bars via `StreamingResponse`.
*   **Advanced Media Processing:** 
    *   Dynamic bitrate calculation to keep files under specific size limits (e.g., Telegram's 50MB limit).
    *   Post-processing and multiplexing using FFmpeg.
*   **Resource Management:** Automated cleanup of temporary files using FastAPI's `BackgroundTasks` and Python's `shutil` to prevent server storage bloat.

## 🛠️ Technical Stack

*   **Backend Framework:** FastAPI, Python `asyncio`
*   **Bot Framework:** python-telegram-bot
*   **Media Processing:** yt-dlp, FFmpeg-python
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript
*   **API Architecture:** RESTful endpoints, Server-Sent Events (SSE) for real-time progress updates.

## 🏗️ Project Structure

```text
videodw/
├── Telegram Bot/
│   ├── bot.py             # Main asynchronous Telegram bot logic
│   └── temp_downloads/    # Temporary storage (auto-cleaned)
├── WebSite/
│   ├── app.py             # FastAPI backend server
│   ├── index.html         # Frontend interface
│   ├── script.js          # Client-side logic & SSE parsing
│   └── styles.css         # Responsive UI styling
├── requirements.txt       # Python dependencies
└── README.md
```

## 🚀 Getting Started

### Prerequisites
*   Python 3.9 or higher
*   **FFmpeg** installed and added to your system's PATH.

### Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Denius88/videodw.git](https://github.com/Denius88/videodw.git)
   cd videodw
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Setup:**
   Create an environment variable for the Telegram Bot token:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   ```

### Running the Services

**To run the Web Service (FastAPI):**
```bash
cd WebSite
uvicorn app:app --host 0.0.0.0 --port 8000
```
*The web interface will be available at `http://localhost:8000`. Keep `index.html` running in your browser to interact with the API.*

**To run the Telegram Bot:**
```bash
cd "Telegram Bot"
python bot.py
```

## 🎯 Architecture Highlights for Developers
*   **Real-time Progress:** The FastAPI backend utilizes generator functions and `StreamingResponse` to push JSON progress chunks to the frontend.
*   **Error Handling:** Implements comprehensive `try/except/finally` blocks ensuring that failed downloads still trigger directory cleanup, preventing memory leaks.
*   **Format Selection Logic:** Employs advanced `yt-dlp` format sorting (preferring `h264`, `mp4`, and `aac`) to ensure maximum compatibility across iOS, Android, and desktop devices.

## ⚠️ Disclaimer
This project is built for educational and portfolio demonstration purposes. Users are responsible for adhering to the terms of service of the respective media platforms and respecting copyright laws.
