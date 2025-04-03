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

class BatchStatus:
    IS_BATCH = {}
    CURRENT_PROCESS = {}  # Track current process status

# List to store batch process IDs
batch_ids = []

# Dict to store FloodWait history for adaptive timing
flood_history = {}

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

# New function for retry with exponential backoff
async def retry_with_backoff(func, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            return await func()
        except FloodWait as fw:
            logger.warning(f"FloodWait encountered: {fw.value} seconds")
            wait_time = fw.value + 5  # Add a small buffer
            await asyncio.sleep(wait_time)
        except Exception as e:
            wait_time = 2 ** retries  # Exponential backoff
            retries += 1
            if retries >= max_retries:
                raise e
            logger.info(f"Retry {retries}/{max_retries} after {wait_time}s due to: {str(e)}")
            await asyncio.sleep(wait_time)
    raise Exception("Maximum retries exceeded")

# Calculate adaptive delay based on recent FloodWait history
def calculate_adaptive_delay(user_id, msg_count):
    base_delay = 2  # Base delay in seconds
    
    # Adjust base delay based on message count
    if msg_count >= 100:
        base_delay = 3
    if msg_count >= 500:
        base_delay = 4
    if msg_count >= 1000:
        base_delay = 5
    
    # Increase delay if user has recent FloodWait history
    if user_id in flood_history:
        recent_floods = flood_history[user_id]
        if recent_floods['count'] > 0:
            # Calculate dynamic increase based on frequency and severity
            severity_factor = min(recent_floods['total_time'] / max(1, recent_floods['count']), 10)
            frequency_factor = min(recent_floods['count'], 5)
            
            # Apply the factors to increase delay
            base_delay += severity_factor * 0.5 + frequency_factor
            
            # Add small random variation to prevent pattern detection
            jitter = random.uniform(0, 1)
            base_delay += jitter
    
    return min(round(base_delay, 1), 15)  # Cap at 15 seconds

# Record a FloodWait occurrence for a user
def record_floodwait(user_id, wait_time):
    if user_id not in flood_history:
        flood_history[user_id] = {
            'count': 0,
            'total_time': 0,
            'last_time': 0
        }
    
    flood_history[user_id]['count'] += 1
    flood_history[user_id]['total_time'] += wait_time
    flood_history[user_id]['last_time'] = time.time()
    
    # Reset flood history after 1 hour to allow recovery
    asyncio.create_task(reset_flood_history(user_id))

async def reset_flood_history(user_id):
    await asyncio.sleep(3600)  # 1 hour
    if user_id in flood_history:
        flood_history[user_id]['count'] = max(0, flood_history[user_id]['count'] - 1)
        if flood_history[user_id]['count'] == 0:
            del flood_history[user_id]

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
    await client.send_message(chat_id=message.chat.id, text=f"{HELP_TXT}")

@Client.on_message(filters.command(["cancel"]))
async def send_cancel(client: Client, message: Message):
    BatchStatus.IS_BATCH[message.from_user.id] = True
    # Clear any batch IDs for this user
    if str(message.from_user.id) in batch_ids:
        batch_ids.remove(str(message.from_user.id))
    # Clear current process info
    if message.from_user.id in BatchStatus.CURRENT_PROCESS:
        del BatchStatus.CURRENT_PROCESS[message.from_user.id]
    await client.send_message(chat_id=message.chat.id, text="**Batch Successfully Cancelled.**")

@Client.on_message(filters.command(["batch"]))
async def batch_handler(client: Client, message: Message):
    """
    Enhanced batch handler that supports better throttling and progress tracking
    """
    user_id = message.from_user.id
    
    # Check if user already has a batch running
    if str(user_id) in batch_ids:
        return await message.reply("**You've already started one batch, wait for it to complete!**")
    
    # Check if user has logged in
    user_data = await db.get_session(user_id)
    if user_data is None:
        await message.reply("**Please /login first.**")
        return
    
    # Get the message link from user
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
    
    # Get the number of messages to process
    range_msg = await client.ask(
        chat_id=message.chat.id,
        text="**Send me the number of files/range you want to save from the given message.**\n\n"
             "**Tip:** For large batches, consider splitting into smaller chunks of 50-100 messages to avoid FloodWait errors.",
        filters=filters.text
    )
    
    if not range_msg.text:
        return await message.reply("**Cancelled due to no response.**")
    
    try:
        value = int(range_msg.text.strip())
        if value > 100000:
            return await message.reply("**You can only get up to 100000 files in a single batch.**")
    except ValueError:
        return await message.reply("**Range must be an integer!**")
    
    # Get custom delay if user wants (new feature)
    delay_msg = await client.ask(
        chat_id=message.chat.id,
        text="**Set a custom delay between messages (2-15 seconds)**\n\n"
             "**Higher values reduce FloodWait errors but make the process slower.**\n"
             "**Type '0' for automatic delay adjustment.**",
        filters=filters.text
    )
    
    custom_delay = 0
    try:
        custom_delay = float(delay_msg.text.strip())
        if custom_delay > 0:
            custom_delay = max(2, min(custom_delay, 15))  # Limit between 2-15 seconds
    except ValueError:
        custom_delay = 0  # Use adaptive delay
    
    # Add user to batch process
    batch_ids.append(str(user_id))
    BatchStatus.IS_BATCH[user_id] = False
    
    # Create progress info
    BatchStatus.CURRENT_PROCESS[user_id] = {
        'total': value,
        'completed': 0,
        'errors': 0,
        'floodwait_time': 0
    }
    
    # Send initial progress message
    progress_msg = await message.reply(
        "**Batch process ongoing.**\n\n"
        "Process completed: 0"
    )
    
    # Start batch processing
    try:
        msg_id = 0
        try:
            msg_id = int(link.split("/")[-1])
        except ValueError:
            if '?single' in link:
                link_ = link.split("?single")[0]
                msg_id = int(link_.split("/")[-1])
            elif '-' in link.split("/")[-1]:
                range_values = link.split("/")[-1].split("-")
                if len(range_values) == 2:
                    try:
                        msg_id = int(range_values[0])
                        to_msg_id = int(range_values[1])
                        value = to_msg_id - msg_id + 1  # Adjust value based on range
                        BatchStatus.CURRENT_PROCESS[user_id]['total'] = value
                    except ValueError:
                        await progress_msg.edit("**Invalid Link! Could not parse message range.**")
                        BatchStatus.IS_BATCH[user_id] = True
                        batch_ids.remove(str(user_id))
                        return
            else:
                await progress_msg.edit("**Invalid Link!**")
                BatchStatus.IS_BATCH[user_id] = True
                batch_ids.remove(str(user_id))
                return
                
        # Process the batch of messages
        async with Client("saverestricted", session_string=user_data, api_hash=API_HASH, api_id=API_ID) as acc:
            consecutive_errors = 0
            
            for i in range(value):
                if BatchStatus.IS_BATCH.get(user_id, True):  # If cancelled
                    break
                
                # Update process info
                proc_info = BatchStatus.CURRENT_PROCESS[user_id]
                
                # Determine appropriate delay
                if custom_delay > 0:
                    timer = custom_delay
                else:
                    timer = calculate_adaptive_delay(user_id, i)
                
                # Reduce timer for public channels slightly
                if 't.me/c/' not in link and custom_delay == 0:
                    timer = max(1, timer - 1)
                
                try:
                    # Calculate time remaining estimate
                    time_remaining = "calculating..."
                    if i > 0:
                        avg_time_per_msg = proc_info.get('avg_time', timer)
                        est_time = avg_time_per_msg * (value - i)
                        # Format time remaining
                        if est_time > 3600:
                            time_remaining = f"~{est_time/3600:.1f} hours"
                        elif est_time > 60:
                            time_remaining = f"~{est_time/60:.1f} minutes"
                        else:
                            time_remaining = f"~{est_time:.0f} seconds"
                    
                    # Update progress message with enhanced information
                    await progress_msg.edit(
                        f"**Batch process ongoing.**\n\n"
                        f"• Progress: {i+1}/{value} ({((i+1)/value*100):.1f}%)\n"
                        f"• Current Delay: {timer}s\n"
                        f"• Errors: {proc_info['errors']}\n"
                        f"• FloodWait Time: {proc_info['floodwait_time']}s\n"
                        f"• Estimated Time Left: {time_remaining}"
                    )
                    
                    # Calculate message ID to fetch
                    msg_to_fetch = msg_id + i
                    
                    # Record start time to calculate average processing time
                    start_time = time.time()
                    
                    # Process the message with retry mechanism
                    await process_message_with_retry(client, acc, message, link, msg_to_fetch)
                    
                    # Calculate and update average processing time
                    proc_time = time.time() - start_time
                    if 'avg_time' not in proc_info:
                        proc_info['avg_time'] = proc_time
                    else:
                        # Weighted average (more weight to recent times)
                        proc_info['avg_time'] = 0.7 * proc_info['avg_time'] + 0.3 * proc_time
                    
                    # Update completion count
                    proc_info['completed'] = i + 1
                    
                    # Reset consecutive errors
                    consecutive_errors = 0
                    
                    # Sleep to avoid rate limiting
                    status_msg = await client.send_message(
                        user_id, 
                        f"**Sleeping for {timer} seconds to avoid Floodwaits and protect account!**"
                    )
                    await asyncio.sleep(timer)
                    await status_msg.delete()
                    
                    # Add extra cooldown period every 20 messages
                    if (i + 1) % 20 == 0 and custom_delay == 0:
                        cooldown = random.uniform(5, 10)
                        cooldown_msg = await client.send_message(
                            user_id,
                            f"**Adding a cooldown period of {cooldown:.1f} seconds to avoid rate limits...**"
                        )
                        await asyncio.sleep(cooldown)
                        await cooldown_msg.delete()
                    
                except FloodWait as fw:
                    # Enhanced FloodWait handling
                    proc_info['floodwait_time'] += fw.value
                    record_floodwait(user_id, fw.value)
                    
                    if fw.value > 300:
                        fw_msg = await client.send_message(
                            user_id,
                            f"**Significant FloodWait detected ({fw.value} seconds)!**\n\n"
                            f"• Consider using smaller batches\n"
                            f"• The process will pause for {fw.value} seconds\n"
                            f"• Current progress: {i+1}/{value}"
                        )
                        await asyncio.sleep(fw.value + 5)
                        await fw_msg.delete()
                        if fw.value > 1800:  # More than 30 minutes - give option to cancel
                            await client.send_message(
                                user_id,
                                "**Very long FloodWait detected. Consider using /cancel to stop this batch and try again later with smaller chunks.**"
                            )
                    else:
                        fw_alert = await client.send_message(
                            user_id,
                            f"**FloodWait detected: Sleeping for {fw.value + 5} seconds**\n"
                            f"Progress: {i+1}/{value}"
                        )
                        await asyncio.sleep(fw.value + 5)
                        await fw_alert.delete()
                except Exception as e:
                    logger.error(f"Error processing message {msg_to_fetch}: {e}")
                    proc_info['errors'] += 1
                    consecutive_errors += 1
                    
                    # If too many consecutive errors, ask user if they want to continue
                    if consecutive_errors >= 5:
                        cont_msg = await client.send_message(
                            user_id,
                            f"**Multiple consecutive errors detected!**\n\n"
                            f"Error: {str(e)}\n\n"
                            f"Do you want to continue? Use /cancel to stop the batch or wait 30 seconds to continue."
                        )
                        try:
                            await asyncio.sleep(30)
                            await cont_msg.delete()
                            consecutive_errors = 0
                        except:
                            pass
                    else:
                        error_msg = await client.send_message(
                            user_id,
                            f"**Error occurred during cloning, batch will continue.**\n\n"
                            f"Error: {str(e)}"
                        )
                        await asyncio.sleep(5)
                        await error_msg.delete()
            
            # Batch completed
            proc_info = BatchStatus.CURRENT_PROCESS.get(user_id, {'completed': 0, 'total': value, 'errors': 0})
            completed = proc_info['completed']
            
            await progress_msg.edit(
                f"**Batch process completed.**\n\n"
                f"• Successfully processed: {completed}/{value} ({(completed/value*100):.1f}%)\n"
                f"• Errors encountered: {proc_info['errors']}\n"
                f"• Total FloodWait time: {proc_info.get('floodwait_time', 0)}s"
            )
            await client.send_message(user_id, "**Batch successfully completed!**")
            
    except Exception as e:
        logger.error(f"Batch process error: {e}")
        await progress_msg.edit(f"**Batch process failed.**\n\n**Error:** {str(e)}")
    finally:
        # Clean up
        BatchStatus.IS_BATCH[user_id] = True
        if str(user_id) in batch_ids:
            batch_ids.remove(str(user_id))
        if user_id in BatchStatus.CURRENT_PROCESS:
            del BatchStatus.CURRENT_PROCESS[user_id]

async def process_message_with_retry(client, acc, message, link, msg_id, max_retries=3):
    """Process a message with retry mechanism"""
    retries = 0
    while retries < max_retries:
        try:
            await process_message(client, acc, message, link, msg_id)
            return
        except FloodWait as fw:
            # Let the main handler deal with FloodWait
            raise
        except Exception as e:
            retries += 1
            if retries >= max_retries:
                raise
            await asyncio.sleep(2 ** retries)  # Exponential backoff
    raise Exception(f"Failed to process message after {max_retries} retries")

async def process_message(client, acc, message, link, msg_id):
    """Process a single message from the batch"""
    try:
        # Determine if it's a private channel or public
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
        raise

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
            # Limit range size to reduce FloodWait risk
            if to_id - from_id > 100:
                await message.reply_text(
                    "**The requested range is too large and may cause FloodWait errors.**\n\n"
                    "Consider using smaller ranges (less than 100 messages) or use the /batch command "
                    "which has better handling for large ranges."
                )
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

    # Show progress message
    progress_msg = await message.reply("**Starting to save messages...**")

    try:
        async with Client("saverestricted", session_string=user_data, api_hash=API_HASH, api_id=API_ID) as acc:
            total_msgs = to_id - from_id + 1
            for idx, msg_id in enumerate(range(from_id, to_id + 1)):
                if BatchStatus.IS_BATCH.get(message.from_user.id):
                    break

                # Update progress periodically
                if idx % 5 == 0 or idx == total_msgs - 1:
                    await progress_msg.edit(f"**Saving messages: {idx+1}/{total_msgs}**")

                try:
                    await process_message(client, acc, message, cleaned_text, msg_id)
                    
                    # Smart delay based on channel type
                    if "https://t.me/c/" in cleaned_text:  # Private channel
                        delay = random.uniform(2, 3.5)
                    else:  # Public channel
                        delay = random.uniform(1, 2)
                        
                    await asyncio.sleep(delay)
                except FloodWait as fw:
                    await progress_msg.edit(
                        f"**FloodWait detected!**\n\n"
                        f"Waiting for {fw.value} seconds as required by Telegram.\n"
                        f"Progress: {idx+1}/{total_msgs}"
                    )
                    await asyncio.sleep(fw.value + 5)
                except Exception as e:
                    logger.error(f"Error saving message {msg_id}: {e}")
                    error_msg = await client.send_message(
                        message.from_user.id,
                        f"**Error saving message {msg_id}:**\n{str(e)}\n\nContinuing with next message..."
                    )
                    await asyncio.sleep(3)
                    await error_msg.delete()
            
            await progress_msg.edit(f"**Successfully saved {total_msgs} messages!**")
    except Exception as e:
        await progress_msg.edit(f"**Error during saving process:**\n{str(e)}")
    finally:
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
