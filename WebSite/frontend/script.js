document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    document.getElementById('theme-toggle').checked = savedTheme === 'dark';

    document.getElementById('theme-toggle').addEventListener('change', (e) => {
        const theme = e.target.checked ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    });

    const savedLang = localStorage.getItem('lang') || 'uk';
    document.documentElement.setAttribute('data-lang', savedLang);
    document.getElementById('lang-toggle').checked = savedLang === 'en';
    updatePageLanguage(savedLang);

    document.getElementById('lang-toggle').addEventListener('change', (e) => {
        const lang = e.target.checked ? 'en' : 'uk';
        document.documentElement.setAttribute('data-lang', lang);
        localStorage.setItem('lang', lang);
        updatePageLanguage(lang);
    });

    const deviceToggle = document.getElementById('device-toggle');
    const savedDevice = localStorage.getItem('device') || 'pc';
    const showcaseGrid = document.querySelector('.showcase-grid');
    
    deviceToggle.checked = savedDevice === 'mobile';
    updateVideoSources(savedDevice);

    deviceToggle.addEventListener('change', (e) => {
        const device = e.target.checked ? 'mobile' : 'pc';
        localStorage.setItem('device', device);
        updateVideoSources(device);
    });
});

const API_URL = 'http://localhost:8000/api';

const URL_PATTERNS = {
    youtube: /^(https?:\/\/)?(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[\w-]+/,
    instagram: /https?:\/\/(?:www\.)?instagram\.com\/(?:p|reel|share)\/[\w-]+\/?/,
    tiktok: /https?:\/\/(?:www\.|vm\.)?tiktok\.com\//
};

const translations = {
    uk: {
        title: 'Відео Завантажувач',
        telegramText: 'Спробуйте також наш',
        telegramBot: 'Telegram бот',
        urlPlaceholder: 'Вставте YouTube, Instagram, або Tiktok URL',
        videoOption: 'MP4 (Відео)',
        audioOption: 'MP3 (Аудіо)',
        downloadButton: 'Завантажити',
        preparing: 'Підготовка до завантаження...',
        downloading: 'Завантаження...',
        completed: 'Завантаження завершено!',
        error: 'Помилка:'
    },
    en: {
        title: 'Video Downloader',
        telegramText: 'Also try our',
        telegramBot: 'Telegram bot',
        urlPlaceholder: 'Paste YouTube, Instagram, or TikTok URL',
        videoOption: 'MP4 (Video)',
        audioOption: 'MP3 (Audio)',
        downloadButton: 'Download',
        preparing: 'Preparing to download...',
        downloading: 'Downloading...',
        completed: 'Download completed!',
        error: 'Error:'
    }
};

function updatePageLanguage(lang) {
    const t = translations[lang];
    
    document.title = t.title;
    
    document.querySelector('h1').textContent = t.title;
    document.querySelector('.telegram-banner').innerHTML = 
        `${t.telegramText} <a href="https://t.me/zcollage_bot" target="_blank">${t.telegramBot}</a> 🤖`;
    document.querySelector('#url').placeholder = t.urlPlaceholder;
    document.querySelector('select option[value="mp4"]').textContent = t.videoOption + ' 🎞️';
    document.querySelector('select option[value="mp3"]').textContent = t.audioOption + ' 🔈';
    document.querySelector('#downloadBtn').textContent = t.downloadButton;

    const statusDiv = document.getElementById('status');
    if (statusDiv.textContent) {
        Object.entries(translations.uk).forEach(([key, value]) => {
            if (statusDiv.textContent.includes(value)) {
                statusDiv.textContent = statusDiv.textContent.replace(
                    value,
                    translations[lang][key]
                );
            }
        });
    }

    const device = localStorage.getItem('device') || 'pc';
    updateVideoSources(device);
}

async function startDownload() {
    const urlInput = document.getElementById('url');
    const formatSelect = document.getElementById('format');
    const statusDiv = document.getElementById('status');
    const downloadBtn = document.getElementById('downloadBtn');
    const progressBar = document.getElementById('progress');
    const progressFill = progressBar.querySelector('.progress-fill');
    const lang = document.documentElement.getAttribute('data-lang') || 'uk';
    const t = translations[lang];

    try {
        const url = urlInput.value.trim();
        let isValidUrl = false;
        let platform = '';

        if (URL_PATTERNS.youtube.test(url)) {
            isValidUrl = true;
            platform = 'YouTube';
        } else if (URL_PATTERNS.instagram.test(url)) {
            isValidUrl = true;
            platform = 'Instagram';
        } else if (URL_PATTERNS.tiktok.test(url)) {
            isValidUrl = true;
            platform = 'TikTok';
        }

        if (!isValidUrl) {
            throw new Error('Невірне посилання. Підтримуються тільки YouTube, Instagram та TikTok');
        }

        statusDiv.className = 'status info';  
        downloadBtn.disabled = true;
        progressBar.style.display = 'block';
        progressFill.style.width = '0%';
        statusDiv.textContent = t.preparing;

        const response = await fetch(`${API_URL}/download`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: urlInput.value,
                format: formatSelect.value
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\n').filter(line => line.trim());
            
            for (const line of lines) {
                try {
                    const data = JSON.parse(line);
                    if (data.error) {
                        throw new Error(data.error);
                    }
                    if (data.progress !== undefined) {
                        progressFill.style.width = `${data.progress}%`;
                        statusDiv.textContent = `${data.status} (${data.progress}%)`;
                    }
                    if (data.download_id) {
                        const downloadUrl = `${API_URL}/download/${data.download_id}`;
                        const downloadResponse = await fetch(downloadUrl);
                        if (!downloadResponse.ok) throw new Error('Download failed');
                        const blob = await downloadResponse.blob();

                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = data.filename;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                        a.remove();

                        statusDiv.textContent = t.completed;
                        statusDiv.className = 'status success';
                        urlInput.classList.add('unhook-animation');
                        setTimeout(() => {
                            urlInput.classList.add('fade-out');
                            setTimeout(() => {
                                urlInput.value = '';
                                urlInput.classList.remove('unhook-animation', 'fade-out');
                            }, 300);
                        }, 500);
                    }
                } catch (e) {
                    console.error('Error parsing progress:', e);
                }
            }
        }

    } catch (error) {
        statusDiv.textContent = `${t.error} ${error.message}`;
        statusDiv.className = 'status error';
        progressBar.style.display = 'none';
    } finally {
        downloadBtn.disabled = false;
        setTimeout(() => {
            progressBar.style.display = 'none';
            progressFill.style.width = '0%';
        }, 1000);
    }
}

function updateVideoSources(device) {
    const videos = document.querySelectorAll('.showcase-grid video');
    const lang = document.documentElement.getAttribute('data-lang') || 'uk';
    const videoLang = lang === 'uk' ? 'ua' : 'en';
    
    videos.forEach(video => {
        const currentTime = video.currentTime;
        const wasPlaying = !video.paused;
        
        let source = `addition/${video.closest('.platform-showcase').className.split(' ')[1]} ${device} ${videoLang}.MP4`;
        video.querySelector('source').setAttribute('src', source);
        
        video.load();
        video.currentTime = currentTime;
        if (wasPlaying) video.play();
    });
}

document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !document.getElementById('downloadBtn').disabled) {
        startDownload();
    }
});

document.getElementById('url').addEventListener('paste', function(e) {
    this.classList.remove('unhook-animation', 'fade-out');
});
