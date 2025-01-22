import os
import asyncio
import pyrogram
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserAlreadyParticipant, InviteHashExpired, UsernameNotOccupied
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import API_ID, API_HASH, ERROR_MESSAGE
from database.db import db
from TechVJ.strings import HELP_TXT

class BatchProcessor:
    def __init__(self):
        self.active_batches = {}
        self.batch_messages = {}
        
    def start_batch(self, user_id, total_messages):
        self.active_batches[user_id] = {
            'total': total_messages,
            'completed': 0,
            'cancelled': False
        }
        
    def cancel_batch(self, user_id):
        if user_id in self.active_batches:
            self.active_batches[user_id]['cancelled'] = True
            
    def update_progress(self, user_id):
        if user_id in self.active_batches:
            self.active_batches[user_id]['completed'] += 1
            
    def is_batch_active(self, user_id):
        return user_id in self.active_batches and not self.active_batches[user_id]['cancelled']

batch_processor = BatchProcessor()

async def handle_download_status(client, message, file_id, progress):
    status_file = f'download_{file_id}.txt'
    try:
        while os.path.exists(status_file):
            with open(status_file, 'r') as f:
                percentage = f.read().strip()
            await message.edit_text(f"Downloading: {percentage}%")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"Download status error: {e}")
    finally:
        if os.path.exists(status_file):
            os.remove(status_file)

async def handle_upload_status(client, message, file_id, progress):
    status_file = f'upload_{file_id}.txt'
    try:
        while os.path.exists(status_file):
            with open(status_file, 'r') as f:
                percentage = f.read().strip()
            await message.edit_text(f"Uploading: {percentage}%")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"Upload status error: {e}")
    finally:
        if os.path.exists(status_file):
            os.remove(status_file)

def write_progress(current, total, file_id, type_):
    status_file = f'{type_}_{file_id}.txt'
    try:
        percentage = current * 100 / total
        with open(status_file, 'w') as f:
            f.write(f"{percentage:.1f}")
    except Exception as e:
        print(f"Progress write error: {e}")

@Client.on_message(filters.command(["start"]))
async def start_command(client, message):
    try:
        if not await db.is_user_exist(message.from_user.id):
            await db.add_user(message.from_user.id, message.from_user.first_name)
            
        buttons = [[
            InlineKeyboardButton("Support", url="https://support.example.com")
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await message.reply_text(
            text=f"👋 Hi {message.from_user.mention}\nI can help you download restricted content. Use /help for instructions.",
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Start command error: {e}")

@Client.on_message(filters.command(["help"]))
async def help_command(client, message):
    try:
        await message.reply_text(HELP_TXT)
    except Exception as e:
        print(f"Help command error: {e}")

@Client.on_message(filters.command(["cancel"]))
async def cancel_command(client, message):
    try:
        batch_processor.cancel_batch(message.from_user.id)
        await message.reply_text("Batch process cancelled.")
    except Exception as e:
        print(f"Cancel command error: {e}")

@Client.on_message(filters.private & filters.text)
async def handle_message(client, message):
    try:
        if "https://t.me/" not in message.text:
            return
            
        if batch_processor.is_batch_active(message.from_user.id):
            await message.reply_text("A batch process is already running. Use /cancel to stop it.")
            return
            
        link_data = parse_telegram_link(message.text)
        if not link_data:
            await message.reply_text("Invalid link format.")
            return
            
        chat_id, message_ids = link_data
        batch_processor.start_batch(message.from_user.id, len(message_ids))
        
        status_message = await message.reply_text("Processing started...")
        
        for msg_id in message_ids:
            if not batch_processor.is_batch_active(message.from_user.id):
                break
                
            try:
                await process_message(client, message, chat_id, msg_id, status_message)
                batch_processor.update_progress(message.from_user.id)
                await update_status_message(status_message, batch_processor.active_batches[message.from_user.id])
            except Exception as e:
                print(f"Message processing error: {e}")
                
            await asyncio.sleep(2)
            
        await status_message.edit_text("Batch processing completed!")
        batch_processor.active_batches.pop(message.from_user.id, None)
        
    except Exception as e:
        print(f"Message handler error: {e}")
        await message.reply_text("An error occurred while processing your request.")

async def process_message(client, message, chat_id, message_id, status_message):
    try:
        msg = await client.get_messages(chat_id, message_id)
        if msg.empty:
            return
            
        msg_type = get_message_type(msg)
        if not msg_type:
            return
            
        download_msg = await message.reply_text("Downloading...")
        file_path = await download_media(client, msg, message_id, download_msg)
        
        if not file_path:
            await download_msg.delete()
            return
            
        await upload_media(client, message, msg, file_path, msg_type, download_msg)
        
    except Exception as e:
        print(f"Message processing error: {e}")
        raise

async def download_media(client, message, message_id, status_message):
    try:
        file_path = await client.download_media(
            message,
            progress=write_progress,
            progress_args=(message_id, "download")
        )
        return file_path
    except Exception as e:
        print(f"Download error: {e}")
        return None
    finally:
        await status_message.delete()

async def upload_media(client, original_message, downloaded_message, file_path, msg_type, status_message):
    try:
        if msg_type == "Document":
            await client.send_document(
                original_message.chat.id,
                file_path,
                caption=downloaded_message.caption,
                progress=write_progress,
                progress_args=(downloaded_message.id, "upload")
            )
        elif msg_type == "Video":
            await client.send_video(
                original_message.chat.id,
                file_path,
                caption=downloaded_message.caption,
                duration=downloaded_message.video.duration,
                width=downloaded_message.video.width,
                height=downloaded_message.video.height,
                progress=write_progress,
                progress_args=(downloaded_message.id, "upload")
            )
        # Add other media types as needed
        
    except Exception as e:
        print(f"Upload error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        await status_message.delete()

def get_message_type(message):
    if message.document:
        return "Document"
    elif message.video:
        return "Video"
    elif message.audio:
        return "Audio"
    elif message.photo:
        return "Photo"
    elif message.voice:
        return "Voice"
    elif message.sticker:
        return "Sticker"
    elif message.animation:
        return "Animation"
    elif message.text:
        return "Text"
    return None

def parse_telegram_link(link):
    try:
        parts = link.split('/')
        if 't.me/c/' in link:
            chat_id = int('-100' + parts[4])
            message_ids = parse_message_range(parts[-1])
        else:
            chat_id = parts[3]
            message_ids = parse_message_range(parts[-1])
        return chat_id, message_ids
    except:
        return None

def parse_message_range(range_str):
    try:
        if '-' in range_str:
            start, end = map(int, range_str.split('-'))
            return range(start, end + 1)
        else:
            msg_id = int(range_str)
            return [msg_id]
    except:
        return []

# Main bot initialization
if __name__ == "__main__":
    app = Client(
        "save_restricted_bot",
        api_id=API_ID,
        api_hash=API_HASH
    )
    
    print("Bot started!")
    app.run()
