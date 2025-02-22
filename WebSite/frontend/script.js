const API_URL = 'http://localhost:8000/api';

// URL validation patterns from bot
const URL_PATTERNS = {
    youtube: /^(https?:\/\/)?(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[\w-]+/,
    instagram: /https?:\/\/(?:www\.)?instagram\.com\/(?:p|reel|share)\/[\w-]+\/?/,
    tiktok: /https?:\/\/(?:www\.|vm\.)?tiktok\.com\//
};

async function startDownload() {
    const urlInput = document.getElementById('url');
    const formatSelect = document.getElementById('format');
    const statusDiv = document.getElementById('status');
    const downloadBtn = document.getElementById('downloadBtn');
    const progressBar = document.getElementById('progress');
    const progressFill = progressBar.querySelector('.progress-fill');

    try {
        // Validate URL
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

        // Reset UI
        statusDiv.className = 'status';
        downloadBtn.disabled = true;
        progressBar.style.display = 'block';
        progressFill.style.width = '30%';
        statusDiv.textContent = `Завантаження ${platform} відео...`;

        // Make API request
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

        if (!response.ok) {
            throw new Error('Помилка завантаження');
        }

        progressFill.style.width = '90%';
        const data = await response.json();

        // Update UI with success
        progressFill.style.width = '100%';
        statusDiv.textContent = 'Завантаження завершено!';
        statusDiv.className = 'status success';
        
        // Direct download using fetch
        const downloadUrl = `${API_URL}/download/${data.download_id}`;
        try {
            const response = await fetch(downloadUrl);
            if (!response.ok) throw new Error('Download failed');
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = data.filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
        } catch (error) {
            // Cleanup on error
            await fetch(`${API_URL}/cleanup/${data.download_id}`, {
                method: 'DELETE'
            }).catch(console.error);
            throw error;
        }

    } catch (error) {
        statusDiv.textContent = `Помилка: ${error.message}`;
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

// Keyboard shortcuts
document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !document.getElementById('downloadBtn').disabled) {
        startDownload();
    }
});
