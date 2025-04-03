import os
import asyncio
import logging
import time
import random
from pyrogram import Client, filters
from pyrogram.errors import UsernameNotOccupied, FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import API_ID, API_HASH, ERROR_MESSAGE
from database.db import db
from TechVJ.strings import HELP_TXT

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dictionary to store active client instances for users
active_clients = {}

class BatchStatus:
    IS_BATCH = {}

# List to store batch process IDs
batch_ids = []

async def update_status(client, statusfile, message, chat, prefix):
    while not os.path.exists(statusfile):
        await asyncio.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as file:
            progress = file.read()
        try:
            await client.edit_message_text(chat, message.id, f"**{prefix}:** **{progress}**")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            await asyncio.sleep(5)

def progress(current, total, message, type):
    with open(f'{message.id}{type}status.txt', "w") as file:
        file.write(f"{current * 100 / total:.1f}%")

@Client.on_message(filters.command(["start"]))
async def send_start(client: Client, message: Message):
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
    buttons = [
        [InlineKeyboardButton("❣️ Developer", url="https://t.me/kingvj01")],
        [InlineKeyboardButton('🔍 Support Group', url='https://t.me/vj_bot_disscussion'),
         InlineKeyboardButton('🤖 Update Channel', url='https://t.me/vj_botz')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await client.send_message(
        chat_id=message.chat.id,
        text=f"<b>👋 Hi {message.from_user.mention}, I am Save Restricted Content Bot. "
             f"Use /login to access restricted content and /help to know more.</b>",
        reply_markup=reply_markup,
        reply_to_message_id=message.id
    )

@Client.on_message(filters.command(["help"]))
async def send_help(client: Client, message: Message):
    help_text = f"{HELP_TXT}\n\n" \
                "**Additional Info:**\n" \
                "- Batch processing is limited to 500 messages at a time to avoid rate limits.\n" \
                "- If a batch is paused due to floodwaits, use /resume to continue from where you left off."
    await client.send_message(chat_id=message.chat.id, text=help_text)

@Client.on_message(filters.command(["cancel"]))
async def send_cancel(client: Client, message: Message):
    user_id = message.from_user.id
    BatchStatus.IS_BATCH[user_id] = True
    if str(user_id) in batch_ids:
        batch_ids.remove(str(user_id))
    await client.send_message(chat_id=message.chat.id, text="**Batch Successfully Cancelled.**")

@Client.on_message(filters.command(["batch"]))
async def batch_handler(client: Client, message: Message):
    """
    Enhanced batch handler with better throttling, progress tracking, and pause/resume functionality
    """
    user_id = message.from_user.id
    
    if str(user_id) in batch_ids:
        return await message.reply("**You've already started one batch, wait for it to complete!**")
    
    user_data = await db.get_session(user_id)
    if user_data is None:
        await message.reply("**Please /login first.**")
        return
    
    # Reuse existing client instance if available
    if user_id in active_clients:
        acc = active_clients[user_id]
    else:
        logger.info(f"Creating new Client instance for user {user_id}")
        acc = Client("saverestricted", session_string=user_data, api_hash=API_HASH, api_id=API_ID)
        await acc.start()
        logger.info(f"Client instance created and started for user {user_id}")
        active_clients[user_id] = acc
    
    link_msg = await client.ask(
        chat_id=message.chat.id,
        text="**Send me the message link you want to start saving from.**",
        filters=filters.text
    )
    
    if not link_msg.text:
        return await message.reply("**Cancelled due to no response.**")
    
    link = link_msg.text.strip()
    if "https://t.me/" not in link:
        return await message.reply("**Invalid link format. Please send a valid Telegram message link.**")
    
    range_msg = await client.ask(
        chat_id=message.chat.id,
        text="**Send me the number of files/range you want to save from the given message.**",
        filters=filters.text
    )
    
    if not range_msg.text:
        return await message.reply("**Cancelled due to no response.**")
    
    try:
        value = int(range_msg.text.strip())
        if value > 500:  # Reduced batch size limit
            return await message.reply("**You can only process up to 500 messages in a single batch. Split your range into smaller chunks.**")
    except ValueError:
        return await message.reply("**Range must be an integer!**")
    
    batch_ids.append(str(user_id))
    BatchStatus.IS_BATCH[user_id] = False
    
    progress_msg = await message.reply(
        "**Batch process ongoing.**\n\n"
        "Process completed: 0"
    )
    
    try:
        msg_id = 0
        try:
            msg_id = int(link.split("/")[-1])
        except ValueError:
            if '?single' in link:
                link_ = link.split("?single")[0]
                msg_id = int(link_.split("/")[-1])
            else:
                await progress_msg.edit("**Invalid Link!**")
                BatchStatus.IS_BATCH[user_id] = True
                batch_ids.remove(str(user_id))
                return
        
        # Check for paused batch
        paused_data = await db.get_paused_batch(user_id)
        if paused_data:
            last_processed = paused_data.get("last_processed", msg_id)
            msg_id = last_processed + 1
            await client.send_message(user_id, f"**Resuming batch from message ID {msg_id}...**")
        
        for i in range(value):
            if BatchStatus.IS_BATCH.get(user_id, True):
                break
            
            # More conservative throttling
            timer = 3
            if i >= 100:
                timer = 5
            if i >= 500:
                timer = 7
            if i >= 1000:
                timer = 10
            if i >= 5000:
                timer = 15
            if i >= 10000:
                timer = 20
            
            if 't.me/c/' not in link:
                timer = 2 if i < 500 else 5
            
            random_delay = random.uniform(0.5, 1.5)
            total_delay = timer + random_delay
            
            try:
                await progress_msg.edit(
                    f"**Batch process ongoing.**\n\n"
                    f"Process completed: {i+1}/{value}"
                )
                
                msg_to_fetch = msg_id + i
                await process_message(client, acc, message, link, msg_to_fetch)
                
                # Save progress in case of interruption
                await db.save_batch_progress(user_id, link, msg_to_fetch, value)
                
                await client.send_message(
                    user_id, 
                    f"**Sleeping for {total_delay:.2f} seconds to avoid Floodwaits and protect account!**"
                )
                await asyncio.sleep(total_delay)
                
            except FloodWait as fw:
                if fw.value > 300:  # Pause batch if wait time is too long
                    await db.save_batch_progress(user_id, link, msg_to_fetch, value)
                    await client.send_message(
                        user_id,
                        f"**Paused batch due to floodwait of {fw.value} seconds. "
                        f"Last processed message ID: {msg_to_fetch}. "
                        f"Use /resume to continue later.**"
                    )
                    break
                else:
                    fw_alert = await client.send_message(
                        user_id,
                        f"**Sleeping for {fw.value + 5} seconds due to telegram floodwait.**"
                    )
                    await asyncio.sleep(fw.value + 5)
                    await fw_alert.delete()
            except Exception as e:
                logger.error(f"Error processing message {msg_to_fetch}: {e}")
                await client.send_message(
                    user_id,
                    f"**An error occurred during cloning, batch will continue.**\n\n**Error:** {str(e)}"
                )
        
        if not BatchStatus.IS_BATCH.get(user_id, True):
            await progress_msg.edit(
                f"**Batch process completed.**\n\n"
                f"Successfully processed: {min(i+1, value)}/{value}"
            )
            await client.send_message(user_id, "**Batch successfully completed!**")
            # Clear paused batch data on successful completion
            await db.clear_batch_progress(user_id)
        
    except Exception as e:
        logger.error(f"Batch process error: {e}")
        await progress_msg.edit(f"**Batch process failed.**\n\n**Error:** {str(e)}")
    finally:
        BatchStatus.IS_BATCH[user_id] = True
        if str(user_id) in batch_ids:
            batch_ids.remove(str(user_id))

@Client.on_message(filters.command(["resume"]))
async def resume_batch(client: Client, message: Message):
    user_id = message.from_user.id
    paused_data = await db.get_paused_batch(user_id)
    
    if not paused_data:
        await message.reply("**No paused batch found. Start a new batch with /batch.**")
        return
    
    link = paused_data["link"]
    last_processed = paused_data["last_processed"]
    total_value = paused_data["total_value"]
    
    # Calculate remaining messages to process
    start_msg_id = int(link.split("/")[-1])
    remaining_value = total_value - (last_processed - start_msg_id)
    
    await message.reply(f"**Resuming batch from message ID {last_processed + 1}...**")
    
    # Simulate a new batch with the remaining range
    class FakeMessage:
        def __init__(self, user_id, text):
            self.from_user = type('User', (), {'id': user_id})
            self.text = text
            self.chat = type('Chat', (), {'id': user_id})
            self.id = 0
    
    fake_message = FakeMessage(user_id, str(remaining_value))
    fake_link_message = FakeMessage(user_id, link)
    
    # Call batch_handler with the fake message to resume
    await batch_handler(client, fake_message, link_msg=fake_link_message)

async def process_message(client, acc, message, link, msg_id):
    """Process a single message from the batch"""
    try:
        if "https://t.me/c/" in link:
            chat_id = int("-100" + link.split("/")[4])
            await handle_private(client, acc, message, chat_id, msg_id)
        elif "https://t.me/b/" in link:
            username = link.split("/")[4]
            await handle_private(client, acc, message, username, msg_id)
        else:
            username = link.split("/")[3]
            try:
                msg = await client.get_messages(username, msg_id)
            except Exception:
                msg = await acc.get_messages(username, msg_id)
            
            if msg:
                if msg.text:
                    await client.send_message(
                        message.from_user.id,
                        text=msg.text,
                        entities=msg.entities,
                        reply_markup=msg.reply_markup
                    )
                else:
                    await msg.copy(message.from_user.id, reply_markup=msg.reply_markup)
    except Exception as e:
        logger.error(f"Error in process_message: {e}")
        if ERROR_MESSAGE:
            await client.send_message(
                message.from_user.id,
                f"Error: {str(e)}"
            )

@Client.on_message(filters.text & filters.private)
async def save(client: Client, message: Message):
    if "https://t.me/" not in message.text:
        return

    if BatchStatus.IS_BATCH.get(message.from_user.id) == False:
        return await message.reply_text("**One task is already in progress. Use /cancel to stop it.**")

    cleaned_text = message.text.replace(" ", "")
    datas = cleaned_text.split("/")
    
    try:
        msg_range = datas[-1].replace("?single", "")
        if "-" in msg_range:
            from_id, to_id = map(int, msg_range.split("-"))
        else:
            from_id = to_id = int(msg_range)
    except Exception as e:
        logger.error(f"Invalid message link format: {e}")
        return await message.reply_text("**Invalid message link format.**")

    BatchStatus.IS_BATCH[message.from_user.id] = False

    user_data = await db.get_session(message.from_user.id)
    if user_data is None:
        await message.reply("**Please /login first.**")
        BatchStatus.IS_BATCH[message.from_user.id] = True
        return

    # Reuse existing client instance if available
    if message.from_user.id in active_clients:
        acc = active_clients[message.from_user.id]
    else:
        logger.info(f"Creating new Client instance for user {message.from_user.id}")
        acc = Client("saverestricted", session_string=user_data, api_hash=API_HASH, api_id=API_ID)
        await acc.start()
        logger.info(f"Client instance created and started for user {message.from_user.id}")
        active_clients[message.from_user.id] = acc

    for msg_id in range(from_id, to_id + 1):
        if BatchStatus.IS_BATCH.get(message.from_user.id):
            break

        await process_message(client, acc, message, cleaned_text, msg_id)
        await asyncio.sleep(1)  # Add a delay to avoid rate limiting

    BatchStatus.IS_BATCH[message.from_user.id] = True

async def handle_private(client: Client, acc, message: Message, chat_id, msg_id: int):
    try:
        try:
            msg = await acc.get_messages(chat_id, msg_id)
        except Exception as e:
            logger.error(f"Error getting message {msg_id} from {chat_id}: {e}")
            msg = await client.get_messages(chat_id, msg_id)
            
        if not msg:
            logger.warning(f"Message {msg_id} not found in {chat_id}")
            return

        chat = message.from_user.id

        if msg.text:
            await client.send_message(
                chat,
                text=msg.text,
                entities=msg.entities,
                reply_markup=msg.reply_markup
            )
            return

        msg_type = get_message_type(msg)
        if not msg_type:
            logger.warning(f"Unsupported message type for message {msg_id} in {chat_id}")
            return

        smsg = await client.send_message(chat, '**Downloading...**')
        
        try:
            status_file = f'{message.id}downstatus.txt'
            asyncio.create_task(update_status(client, status_file, smsg, chat, "Downloaded"))
            
            file = await acc.download_media(
                msg,
                progress=progress,
                progress_args=[message, "down"]
            )
            
            if os.path.exists(status_file):
                os.remove(status_file)

            if not file:
                await smsg.edit("Download failed!")
                return

            up_status_file = f'{message.id}upstatus.txt'
            asyncio.create_task(update_status(client, up_status_file, smsg, chat, "Uploaded"))
            
            caption = msg.caption or None
            await send_media(client, acc, msg, chat, file, caption, message.id, reply_markup=msg.reply_markup)

            if os.path.exists(up_status_file):
                os.remove(up_status_file)
            
            if os.path.exists(file):
                os.remove(file)

        except Exception as e:
            logger.error(f"Error handling message {msg_id}: {e}")
            await smsg.edit(f"Error: {str(e)}")
            return
        finally:
            await smsg.delete()

    except Exception as e:
        logger.error(f"Error in handle_private for message {msg_id}: {e}")
        await client.send_message(
            message.from_user.id,
            f"Error: {str(e)}"
        )

async def send_media(client, acc, msg, chat, file, caption, reply_to_message_id, reply_markup=None):
    msg_type = get_message_type(msg)
    thumb = await download_thumb(acc, msg)

    try:
        if msg_type == "Document":
            await client.send_document(
                chat, file, thumb=thumb, caption=caption, 
                reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
        elif msg_type == "Video":
            await client.send_video(
                chat, file, duration=msg.video.duration, width=msg.video.width, height=msg.video.height,
                thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
        elif msg_type == "Animation":
            await client.send_animation(
                chat, file, reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
        elif msg_type == "Sticker":
            await client.send_sticker(
                chat, file, reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
        elif msg_type == "Voice":
            await client.send_voice(
                chat, file, caption=caption, reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
        elif msg_type == "Audio":
            await client.send_audio(
                chat, file, thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
        elif msg_type == "Photo":
            await client.send_photo(
                chat, file, caption=caption, reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
        elif msg_type == "Text":
            await client.send_message(
                chat, msg.text, entities=msg.entities, reply_to_message_id=reply_to_message_id, reply_markup=reply_markup
            )
    finally:
        if thumb:
            try:
                os.remove(thumb)
            except:
                pass

async def download_thumb(acc, msg):
    try:
        if msg.document and msg.document.thumbs:
            return await acc.download_media(msg.document.thumbs[0].file_id)
        elif msg.video and msg.video.thumbs:
            return await acc.download_media(msg.video.thumbs[0].file_id)
    except Exception as e:
        logger.error(f"Error downloading thumbnail: {e}")
        return None

def get_message_type(msg: Message):
    if msg.document:
        return "Document"
    if msg.video:
        return "Video"
    if msg.animation:
        return "Animation"
    if msg.sticker:
        return "Sticker"
    if msg.voice:
        return "Voice"
    if msg.audio:
        return "Audio"
    if msg.photo:
        return "Photo"
    if msg.text:
        return "Text"
    return None
