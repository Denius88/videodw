import os
import logging
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler
import yt_dlp
import ffmpeg
import shutil
import concurrent.futures
import re
import json

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Стани в яких може перебувати розмова
WAITING_FOR_LINK, WAITING_FOR_FORMAT, WAITING_FOR_INSTAGRAM_LINK, WAITING_FOR_TIKTOK_LINK = range(4)

# Папка для тимчасових файлів
TEMP_FOLDER = "temp_downloads"
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Словник активних завантажень
active_downloads = {}

# Функція для очищення тимчасових файлів
def cleanup_temp_files(user_id):
    user_folder = os.path.join(TEMP_FOLDER, str(user_id))
    if os.path.exists(user_folder):
        try:
            shutil.rmtree(user_folder)
            logger.info(f"Очищено тимчасові файли користувача {user_id}")
        except Exception as e:
            logger.error(f"Помилка очищення тимчасових файлів: {str(e)}")

# Функція для стартового повідомлення
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Create persistent Start button with custom text
    start_keyboard = [[KeyboardButton("🔄 Головне меню")]]  # Changed button text, still sends /start
    start_markup = ReplyKeyboardMarkup(
        start_keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    # Updated button labels with emojis
    inline_keyboard = [
        [InlineKeyboardButton("▶️ YouTube", callback_data="youtube")],
        [InlineKeyboardButton("📸 Instagram", callback_data="instagram")],
        [InlineKeyboardButton("🎵 TikTok", callback_data="tiktok")]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)

    # Send message with both keyboards
    await update.message.reply_text(
        "Привіт! Я допоможу вам завантажити відео з YouTube, Instagram та TikTok.",
        reply_markup=start_markup
    )
    await update.message.reply_text(
        "Оберіть платформу для завантаження:",
        reply_markup=inline_markup
    )
    return ConversationHandler.END

# Функція для обробки кнопки YouTube
async def youtube_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Будь ласка, надішліть посилання на YouTube відео:")
    return WAITING_FOR_LINK

# Add Instagram button handler
async def instagram_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Будь ласка, надішліть посилання на відео з Instagram:")
    return WAITING_FOR_INSTAGRAM_LINK

# Add TikTok button handler
async def tiktok_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Будь ласка, надішліть посилання на TikTok відео:")
    return WAITING_FOR_TIKTOK_LINK

# Функція для обробки отриманого посилання
async def process_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    youtube_link = update.message.text
    # Зберігаємо посилання в контексті для подальшого використання
    context.user_data["youtube_link"] = youtube_link
    
    # Updated audio/video button labels with emojis
    keyboard = [
        [
            InlineKeyboardButton("🎵 MP3 (аудіо)", callback_data="mp3"),
            InlineKeyboardButton("🎬 MP4 (відео)", callback_data="mp4")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Обране відео: {youtube_link}\nВиберіть формат завантаження:",
        reply_markup=reply_markup
    )
    return WAITING_FOR_FORMAT

# Add Instagram link processing function
async def process_instagram_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    instagram_link = update.message.text.strip()
    
    if not re.match(r'https?://(?:www\.)?instagram\.com/(?:p|reel|share)/[\w-]+/?', instagram_link):
        await update.message.reply_text("Це не схоже на коректне посилання Instagram. Спробуйте ще раз.")
        return WAITING_FOR_INSTAGRAM_LINK

    message = await update.message.reply_text("Завантаження розпочато... Будь ласка, зачекайте.")
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    output_folder = os.path.join(TEMP_FOLDER, str(user_id))
    os.makedirs(output_folder, exist_ok=True)

    try:
        ydl_opts = {
            'format': '(mp4)[width>=0][height>=0]',  # Changed format specification
            'outtmpl': os.path.join(output_folder, 'instagram_video.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'merge_output_format': 'mp4',  # Added to ensure MP4 output
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'extract_flat': False,
            'nocheckcertificate': True,
            'addheader': [
                ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'),
                ('Accept-Language', 'en-US,en;q=0.5'),
            ]
        }

        video_path = os.path.join(output_folder, 'instagram_video.mp4')
        await message.edit_text("Завантаження відео...")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([instagram_link])
        except Exception as e:
            logger.error(f"First attempt failed: {str(e)}")
            # Fallback to simpler format
            ydl_opts['format'] = 'best[ext=mp4]/best'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([instagram_link])

        # Rest of the function remains the same
        if not os.path.exists(video_path):
            mp4_files = [f for f in os.listdir(output_folder) if f.endswith('.mp4')]
            if mp4_files:
                video_path = os.path.join(output_folder, mp4_files[0])
            else:
                raise Exception("Не вдалося знайти завантажене відео")

        file_size = os.path.getsize(video_path) / (1024 * 1024)
        if file_size == 0:
            raise Exception("Завантажений файл порожній")

        # The rest of your existing code...
        await message.edit_text("Надсилання відео в чат...")
        
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption="Ось ваше відео з Instagram!",
                supports_streaming=True
            )

        # Return to main menu
        keyboard = [
            [InlineKeyboardButton("▶️ YouTube", callback_data="youtube")],
            [InlineKeyboardButton("📸 Instagram", callback_data="instagram")],
            [InlineKeyboardButton("🎵 TikTok", callback_data="tiktok")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="Готово! Що бажаєте зробити далі?",
            reply_markup=reply_markup
        )

    except Exception as e:
        error_message = f"Помилка: {str(e)}"
        logger.error(error_message)
        await context.bot.send_message(chat_id=chat_id, text=error_message)

    finally:
        await asyncio.to_thread(cleanup_temp_files, user_id)
        try:
            await message.delete()
        except Exception:
            pass

    return ConversationHandler.END

# Add TikTok processing function
async def process_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tiktok_link = update.message.text.strip()
    
    if not re.match(r'https?://(?:www\.|vm\.)?tiktok\.com/', tiktok_link):
        await update.message.reply_text("Це не схоже на коректне посилання TikTok. Спробуйте ще раз.")
        return WAITING_FOR_TIKTOK_LINK

    message = await update.message.reply_text("Завантаження розпочато... Будь ласка, зачекайте.")
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    output_folder = os.path.join(TEMP_FOLDER, str(user_id))
    os.makedirs(output_folder, exist_ok=True)

    try:
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(output_folder, 'tiktok_video.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'nocheckcertificate': True,
            'addheader': [
                ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'),
            ]
        }

        video_path = os.path.join(output_folder, 'tiktok_video.mp4')
        await message.edit_text("Отримання відео без водяного знаку...")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(tiktok_link, download=False)
            if info.get('duration', 0) == 0:
                raise Exception("Це фото або GIF. Бот підтримує лише відео з TikTok.")
            
            # Download without watermark
            ydl.download([tiktok_link])

        if not os.path.exists(video_path):
            mp4_files = [f for f in os.listdir(output_folder) if f.endswith('.mp4')]
            if mp4_files:
                video_path = os.path.join(output_folder, mp4_files[0])
            else:
                raise Exception("Не вдалося знайти завантажене відео")

        await message.edit_text("Надсилання відео в чат...")
        
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption="Ось ваше відео з TikTok!",
                supports_streaming=True
            )

        # Return to main menu
        keyboard = [
            [InlineKeyboardButton("▶️ YouTube", callback_data="youtube")],
            [InlineKeyboardButton("📸 Instagram", callback_data="instagram")],
            [InlineKeyboardButton("🎵 TikTok", callback_data="tiktok")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="Готово! Що бажаєте зробити далі?",
            reply_markup=reply_markup
        )

    except Exception as e:
        error_message = f"Помилка: {str(e)}"
        logger.error(error_message)
        await context.bot.send_message(chat_id=chat_id, text=error_message)

    finally:
        await asyncio.to_thread(cleanup_temp_files, user_id)
        try:
            await message.delete()
        except Exception:
            pass

    return ConversationHandler.END

# Функція для отримання інформації про відео
def get_video_info(youtube_link):
    ydl_opts = {'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_link, download=False)
        return info

# Синхронні функції для виконання в окремому потоці
def download_video_sync(youtube_link, output_path, format_id='best'):
    ydl_opts = {
        'format': format_id,
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_link])
    return os.path.exists(output_path)

def compress_video_sync(input_file, output_file, width, height, video_bitrate, audio_bitrate='128k', crf=23, preset='medium'):
    try:
        (
            ffmpeg
            .input(input_file)
            .output(
                output_file,
                vf=f"scale={width}:{height}",
                video_bitrate=video_bitrate,
                audio_bitrate=audio_bitrate,
                crf=crf,
                preset=preset
            )
            .run(quiet=True, overwrite_output=True)
        )
        return os.path.exists(output_file)
    except Exception as e:
        logger.error(f"Помилка компресії: {str(e)}")
        return False

def download_audio_sync(youtube_link, output_folder, safe_title):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_folder, f"{safe_title}.%(ext)s"),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_link])
    
    # Пошук файлу mp3 в каталозі
    for file in os.listdir(output_folder):
        if file.endswith(".mp3"):
            return os.path.join(output_folder, file)
    return None

# Функція для визначення оптимальних параметрів відео
def calculate_optimal_bitrate(duration, target_size_mb=45):
    # Залишаємо запас у 5MB від ліміту 50MB
    target_size_bytes = target_size_mb * 1024 * 1024
    # Приблизний оверхед аудіо (192kbps)
    audio_bitrate_bytes = 192 * 1024 / 8  # bytes per second
    
    # Обчислюємо доступний бітрейт для відео
    available_bytes = target_size_bytes - (duration * audio_bitrate_bytes)
    video_bitrate_bps = (available_bytes * 8) / duration
    
    # Обмежуємо бітрейт розумними значеннями
    min_bitrate = 800 * 1024   # Increased from 500 to 800 kbps
    max_bitrate = 4000 * 1024  # Increased from 3000 to 4000 kbps
    
    video_bitrate_bps = max(min_bitrate, min(video_bitrate_bps, max_bitrate))
    return int(video_bitrate_bps)

# Функція для вибору оптимальної роздільної здатності
def get_optimal_resolution(original_width, original_height, target_bitrate):
    # Always maintain original dimensions for initial compression
    return original_width, original_height

# Функція для виконання завантаження в окремому потоці
def run_in_executor(func, *args):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        return executor.submit(func, *args).result()

# Функція для завантаження та компресії відео
async def download_and_compress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    format_type = query.data
    youtube_link = context.user_data.get("youtube_link")
    
    if not youtube_link:
        await query.edit_message_text(text="Помилка: посилання не знайдено. Почніть спочатку.")
        return ConversationHandler.END
    
    # Повідомлення про початок завантаження
    message = await query.edit_message_text(text=f"Завантаження розпочато... Будь ласка, зачекайте.")
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Створюємо новий запис для відстеження цього завантаження
    active_downloads[user_id] = {
        'chat_id': chat_id,
        'message_id': message.message_id,
        'format': format_type,
        'status': 'downloading'
    }
    
    # Запускаємо обробку у фоновому режимі
    asyncio.create_task(process_download(context, youtube_link, format_type, chat_id, user_id, message.message_id))
    
    return ConversationHandler.END

# Основна функція обробки завантаження
async def process_download(context, youtube_link, format_type, chat_id, user_id, message_id):
    try:
        # Створюємо окрему папку для цього користувача
        output_folder = os.path.join(TEMP_FOLDER, str(user_id))
        os.makedirs(output_folder, exist_ok=True)
        
        # Отримуємо інформацію про відео
        video_info = await asyncio.to_thread(get_video_info, youtube_link)
        title = video_info.get('title', 'video')
        # Приберемо заборонені символи з назви файлу
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' .-_']).strip()
        
        if format_type == "mp3":
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Завантаження аудіо..."
            )
            
            # Завантаження аудіо в окремому потоці
            output_file = await asyncio.to_thread(
                download_audio_sync,
                youtube_link,
                output_folder,
                safe_title
            )
            
            if not output_file:
                await context.bot.send_message(chat_id=chat_id, text="Помилка: аудіофайл не знайдено.")
                return
            
            # Перевірка розміру файлу
            file_size = os.path.getsize(output_file) / (1024 * 1024)  # розмір в MB
            if file_size > 50:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Файл завеликий. Виконується додаткова компресія..."
                )
                
                compressed_file = os.path.join(output_folder, f"{safe_title}_compressed.mp3")
                success = await asyncio.to_thread(
                    compress_video_sync,
                    output_file,
                    compressed_file,
                    0, 0,  # width/height не використовуються для аудіо
                    "none",  # video_bitrate не використовується для аудіо
                    "128k"  # аудіо бітрейт
                )
                
                if success and os.path.exists(compressed_file):
                    output_file = compressed_file
            
            # Надсилаємо аудіо
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Надсилання аудіо файлу..."
            )
            
            with open(output_file, 'rb') as audio_file:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=title
                )
            
        elif format_type == "mp4":
            # Отримуємо тривалість відео для розрахунку оптимального бітрейту
            duration = video_info.get('duration', 0)
            if duration == 0:
                duration = 300  # 5 хвилин за замовчуванням
            
            # Вибираємо найкращий формат і розмір
            best_format = None
            original_width, original_height = 1280, 720  # Типова HD якість
            
            # Проходимо доступні формати, щоб вибрати оптимальний
            for fmt in video_info.get('formats', []):
                if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                    width = fmt.get('width', 0)
                    height = fmt.get('height', 0)
                    if width > 0 and height > 0:
                        best_format = fmt.get('format_id')
                        original_width = width
                        original_height = height
                        break
            
            if not best_format:
                best_format = 'best'
            
            # Обчислюємо оптимальний бітрейт відео
            target_bitrate = calculate_optimal_bitrate(duration)
            bitrate_str = f"{int(target_bitrate/1024)}k"
            
            # Визначаємо оптимальну роздільну здатність
            new_width, new_height = get_optimal_resolution(original_width, original_height, target_bitrate)
            
            # Створюємо шляхи до файлів
            temp_file = os.path.join(output_folder, f"{safe_title}_temp.mp4")
            output_file = os.path.join(output_folder, f"{safe_title}.mp4")
            
            # Завантаження відео
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"Завантаження відео...\nРозмір оригіналу: {original_width}x{original_height}"
            )
            
            # Завантажуємо відео в окремому потоці
            success = await asyncio.to_thread(
                download_video_sync,
                youtube_link,
                temp_file,
                best_format
            )
            
            if not success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Помилка: не вдалося завантажити відео."
                )
                return
            
            # Компресія відео з оптимальними параметрами
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"Оптимізація відео для Telegram...\n"
                     f"Цільовий розмір < 50MB\n"
                     f"Роздільна здатність: {new_width}x{new_height}\n"
                     f"Бітрейт відео: {bitrate_str}"
            )
            
            # Компресуємо відео в окремому потоці
            success = await asyncio.to_thread(
                compress_video_sync,
                temp_file,
                output_file,
                original_width,
                original_height,
                bitrate_str,
                '128k',
                23,
                'medium'
            )
            
            if not success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Помилка: не вдалося стиснути відео."
                )
                return
            
            # Перевірка розміру файлу після компресії
            file_size = os.path.getsize(output_file) / (1024 * 1024)  # розмір в MB
            
            # Якщо після першої компресії файл досі занадто великий
            attempt = 0
            max_attempts = 3
            
            while file_size > 50 and attempt < max_attempts:
                attempt += 1
                # Зменшуємо якість більш агресивно
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"Файл все ще завеликий ({file_size:.1f} MB).\n"
                         f"Спроба {attempt}/{max_attempts} додаткової компресії..."
                )
                
                # Зменшуємо бітрейт та роздільну здатність на кожній ітерації
                target_bitrate = target_bitrate * 0.7
                new_width = int(new_width * 0.85)
                new_height = int(new_height * 0.85)
                
                # Забезпечуємо парні значення розмірів
                new_width = (new_width // 2) * 2
                new_height = (new_height // 2) * 2
                
                bitrate_str = f"{int(target_bitrate/1024)}k"
                temp_output = os.path.join(output_folder, f"{safe_title}_attempt{attempt}.mp4")
                
                success = await asyncio.to_thread(
                    compress_video_sync,
                    output_file,
                    temp_output,
                    original_width,  # Keep original width
                    original_height, # Keep original height
                    bitrate_str,
                    '96k' if attempt > 1 else '128k',
                    28 if attempt > 1 else 25,
                    'medium'
                )
                
                if success and os.path.exists(temp_output):
                    # Перевіряємо новий розмір
                    file_size = os.path.getsize(temp_output) / (1024 * 1024)
                    output_file = temp_output
                    if file_size <= 50:
                        break
            
            # Якщо після всіх спроб файл все ще завеликий
            if file_size > 50:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Відео занадто велике для відправки через Telegram навіть після компресії."
                )
                return
            
            # Надсилаємо відео
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"Надсилання відео ({file_size:.1f} MB)..."
            )
            
            with open(output_file, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    caption=title,
                    supports_streaming=True
                )
        
        # Повернення до головного меню
        keyboard = [
            [InlineKeyboardButton("▶️ YouTube", callback_data="youtube")],
            [InlineKeyboardButton("📸 Instagram", callback_data="instagram")],
            [InlineKeyboardButton("🎵 TikTok", callback_data="tiktok")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="Готово! Що бажаєте зробити далі?",
            reply_markup=reply_markup
        )
        
        # Видаляємо повідомлення про статус
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
            
    except Exception as e:
        logger.error(f"Помилка завантаження: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Виникла помилка: {str(e)}"
        )
    finally:
        # Видаляємо запис про активне завантаження
        if user_id in active_downloads:
            del active_downloads[user_id]
        # Очищаємо тимчасові файли
        await asyncio.to_thread(cleanup_temp_files, user_id)

# Функція відміни операції
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Операцію скасовано.')
    return ConversationHandler.END

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "7507497236:AAFLn5QaKCVAl0pF1Cuu6e6FnzMoE3e3lDw")
    application = Application.builder().token(token).build()
    
    # Add a separate handler for the main menu button that takes precedence over others
    application.add_handler(MessageHandler(
        filters.Regex("^🔄 Головне меню$"),
        start,
        block=False
    ))
    
    # Modify conversation handler to not include the main menu button
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(youtube_button, pattern="^youtube$"),
            CallbackQueryHandler(instagram_button, pattern="^instagram$"),
            CallbackQueryHandler(tiktok_button, pattern="^tiktok$")
        ],
        states={
            WAITING_FOR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_youtube_link)],
            WAITING_FOR_FORMAT: [CallbackQueryHandler(download_and_compress, pattern="^(mp3|mp4)$")],
            WAITING_FOR_INSTAGRAM_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_instagram_link)],
            WAITING_FOR_TIKTOK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_tiktok_link)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    
    # Add handlers for inline buttons
    application.add_handler(CallbackQueryHandler(youtube_button, pattern="^youtube$"))
    application.add_handler(CallbackQueryHandler(instagram_button, pattern="^instagram$"))
    application.add_handler(CallbackQueryHandler(tiktok_button, pattern="^tiktok$"))
    
    application.run_polling()

if __name__ == "__main__":
    main()



