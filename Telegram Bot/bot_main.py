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
WAITING_FOR_INSTAGRAM_LINK, WAITING_FOR_TIKTOK_LINK = range(2)

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

    # Remove YouTube button, keep only Instagram and TikTok
    inline_keyboard = [
        [InlineKeyboardButton("📸 Instagram", callback_data="instagram")],
        [InlineKeyboardButton("🎵 TikTok", callback_data="tiktok")]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)

    # Send message with both keyboards
    await update.message.reply_text(
        "Привіт! Я допоможу вам завантажити відео з Instagram та TikTok.",
        reply_markup=start_markup
    )
    await update.message.reply_text(
        "Оберіть платформу для завантаження:",
        reply_markup=inline_markup
    )
    return ConversationHandler.END

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

# Синхронні функції для виконання в окремому потоці
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

# Функція відміни операції
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Операцію скасовано.')
    return ConversationHandler.END

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")
    application = Application.builder().token(token).build()
    
    # Add a separate handler for the main menu button that takes precedence over others
    application.add_handler(MessageHandler(
        filters.Regex("^🔄 Головне меню$"),
        start,
        block=False
    ))
    
    # Update conversation handler to remove YouTube
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(instagram_button, pattern="^instagram$"),
            CallbackQueryHandler(tiktok_button, pattern="^tiktok$")
        ],
        states={
            WAITING_FOR_INSTAGRAM_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_instagram_link)],
            WAITING_FOR_TIKTOK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_tiktok_link)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # Update inline button handlers
    application.add_handler(CallbackQueryHandler(instagram_button, pattern="^instagram$"))
    application.add_handler(CallbackQueryHandler(tiktok_button, pattern="^tiktok$"))
    
    application.run_polling()

if __name__ == "__main__":
    main()



