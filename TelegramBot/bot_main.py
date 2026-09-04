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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


WAITING_FOR_INSTAGRAM_LINK, WAITING_FOR_TIKTOK_LINK = range(2)

TEMP_FOLDER = "temp_downloads"
os.makedirs(TEMP_FOLDER, exist_ok=True)

active_downloads = {}
MAX_VIDEO_SIZE_BYTES = 200 * 1024 * 1024
VIDEO_SEND_TIMEOUT_SECONDS = 5 * 60


class VideoTooLargeError(Exception):
    pass


def validate_video_size(info):
    formats = info.get('requested_formats') or [info]
    known_size = sum(
        item.get('filesize') or item.get('filesize_approx') or 0
        for item in formats
    )
    if known_size > MAX_VIDEO_SIZE_BYTES:
        raise VideoTooLargeError("Відео більше 200 МБ. Завантаження скасовано.")


def stop_oversized_download(status):
    if status.get('status') == 'downloading' and status.get('downloaded_bytes', 0) > MAX_VIDEO_SIZE_BYTES:
        raise VideoTooLargeError("Відео більше 200 МБ. Завантаження скасовано.")

def cleanup_temp_files(user_id):
    user_folder = os.path.join(TEMP_FOLDER, str(user_id))
    if os.path.exists(user_folder):
        try:
            shutil.rmtree(user_folder)
            logger.info(f"Очищено тимчасові файли користувача {user_id}")
        except Exception as e:
            logger.error(f"Помилка очищення тимчасових файлів: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_keyboard = [[KeyboardButton("🔄 Головне меню")]] 
    start_markup = ReplyKeyboardMarkup(
        start_keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    inline_keyboard = [
        [InlineKeyboardButton("📸 Instagram", callback_data="instagram")],
        [InlineKeyboardButton("🎵 TikTok", callback_data="tiktok")]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)

    await update.message.reply_text(
        "Привіт! Я допоможу вам завантажити відео з Instagram та TikTok.",
        reply_markup=start_markup
    )
    await update.message.reply_text(
        "Оберіть платформу для завантаження:",
        reply_markup=inline_markup
    )
    return ConversationHandler.END

async def instagram_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Будь ласка, надішліть посилання на відео з Instagram:")
    return WAITING_FOR_INSTAGRAM_LINK

async def tiktok_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Будь ласка, надішліть посилання на TikTok відео:")
    return WAITING_FOR_TIKTOK_LINK
    
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
            'format': '(mp4)[width>=0][height>=0]',  
            'outtmpl': os.path.join(output_folder, 'instagram_video.%(ext)s'),
            'max_filesize': MAX_VIDEO_SIZE_BYTES,
            'progress_hooks': [stop_oversized_download],
            'quiet': False,
            'no_warnings': False,
            'merge_output_format': 'mp4', 
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
                validate_video_size(ydl.extract_info(instagram_link, download=False))
                ydl.download([instagram_link])
        except VideoTooLargeError:
            raise
        except Exception as e:
            logger.error(f"First attempt failed: {str(e)}")
            ydl_opts['format'] = 'best[ext=mp4]/best'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                validate_video_size(ydl.extract_info(instagram_link, download=False))
                ydl.download([instagram_link])

        if not os.path.exists(video_path):
            mp4_files = [f for f in os.listdir(output_folder) if f.endswith('.mp4')]
            if mp4_files:
                video_path = os.path.join(output_folder, mp4_files[0])
            else:
                raise Exception("Не вдалося знайти завантажене відео")

        file_size = os.path.getsize(video_path) / (1024 * 1024)
        if file_size == 0:
            raise Exception("Завантажений файл порожній")
        if os.path.getsize(video_path) > MAX_VIDEO_SIZE_BYTES:
            raise VideoTooLargeError("Відео більше 200 МБ. Завантаження скасовано.")

        await message.edit_text("Надсилання відео в чат...")
        
        with open(video_path, 'rb') as video_file:
            await asyncio.wait_for(
                context.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    caption="Ось ваше відео з Instagram!",
                    supports_streaming=True
                ),
                timeout=VIDEO_SEND_TIMEOUT_SECONDS
            )

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

    except asyncio.TimeoutError:
        error_message = "Помилка: не вдалося надіслати відео протягом 5 хвилин. Файл видалено."
        logger.error(error_message)
        await context.bot.send_message(chat_id=chat_id, text=error_message)
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

async def process_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tiktok_link = update.message.text.strip()
    
    if not re.match(r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/', tiktok_link):
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
            'max_filesize': MAX_VIDEO_SIZE_BYTES,
            'progress_hooks': [stop_oversized_download],
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
            validate_video_size(info)
            
            ydl.download([tiktok_link])

        if not os.path.exists(video_path):
            mp4_files = [f for f in os.listdir(output_folder) if f.endswith('.mp4')]
            if mp4_files:
                video_path = os.path.join(output_folder, mp4_files[0])
            else:
                raise Exception("Не вдалося знайти завантажене відео")

        if os.path.getsize(video_path) > MAX_VIDEO_SIZE_BYTES:
            raise VideoTooLargeError("Відео більше 200 МБ. Завантаження скасовано.")

        await message.edit_text("Надсилання відео в чат...")
        
        with open(video_path, 'rb') as video_file:
            await asyncio.wait_for(
                context.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    caption="Ось ваше відео з TikTok!",
                    supports_streaming=True
                ),
                timeout=VIDEO_SEND_TIMEOUT_SECONDS
            )

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

    except asyncio.TimeoutError:
        error_message = "Помилка: не вдалося надіслати відео протягом 5 хвилин. Файл видалено."
        logger.error(error_message)
        await context.bot.send_message(chat_id=chat_id, text=error_message)
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

def calculate_optimal_bitrate(duration, target_size_mb=45):
    target_size_bytes = target_size_mb * 1024 * 1024
    audio_bitrate_bytes = 192 * 1024 / 8  
    
    available_bytes = target_size_bytes - (duration * audio_bitrate_bytes)
    video_bitrate_bps = (available_bytes * 8) / duration
    
    min_bitrate = 800 * 1024   
    max_bitrate = 4000 * 1024  
    
    video_bitrate_bps = max(min_bitrate, min(video_bitrate_bps, max_bitrate))
    return int(video_bitrate_bps)

def get_optimal_resolution(original_width, original_height, target_bitrate):
    return original_width, original_height

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Операцію скасовано.')
    return ConversationHandler.END

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")
    application = Application.builder().token(token).build()
    
    application.add_handler(MessageHandler(
        filters.Regex("^🔄 Головне меню$"),
        start,
        block=False
    ))
    
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
    
    application.add_handler(CallbackQueryHandler(instagram_button, pattern="^instagram$"))
    application.add_handler(CallbackQueryHandler(tiktok_button, pattern="^tiktok$"))
    
    application.run_polling()

if __name__ == "__main__":
    main()



