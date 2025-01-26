import os
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import (
    UsernameNotOccupied,
    ChannelInvalid,
    FloodWait,
    MessageIdInvalid,
    UserNotParticipant
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import API_ID, API_HASH, ERROR_MESSAGE
from database.db import db
from TechVJ.strings import HELP_TXT

class BatchStatus:
    IS_BATCH = {}

async def update_status(client, statusfile, message, chat, prefix):
    while not os.path.exists(statusfile):
        await asyncio.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as file:
            progress = file.read()
        try:
            await client.edit_message_text(chat, message.id, f"**{prefix}:** **{progress}**")
            await asyncio.sleep(10)
        except:
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
    await client.send_message(chat_id=message.chat.id, text=f"{HELP_TXT}")

@Client.on_message(filters.command(["cancel"]))
async def send_cancel(client: Client, message: Message):
    BatchStatus.IS_BATCH[message.from_user.id] = True
    await client.send_message(chat_id=message.chat.id, text="**Batch Successfully Cancelled.**")

@Client.on_message(filters.text & filters.private)
async def save(client: Client, message: Message):
    if "https://t.me/" not in message.text:
        return

    if BatchStatus.IS_BATCH.get(message.from_user.id) == False:
        return await message.reply_text("**One task is already in progress. Use /cancel to stop it.**")

    try:
        datas = message.text.split("/")
        temp = datas[-1].replace("?single", "").split("-")
        if len(temp) == 2:
            from_id, to_id = map(int, temp)
        else:
            from_id = to_id = int(temp[0])
    except Exception:
        return await message.reply("Invalid format. Use: https://t.me/username/123-456")

    BatchStatus.IS_BATCH[message.from_user.id] = False

    user_data = await db.get_session(message.from_user.id)
    if user_data is None:
        await message.reply("**Please /login first.**")
        BatchStatus.IS_BATCH[message.from_user.id] = True
        return

    async with Client("saverestricted", session_string=user_data, api_hash=API_HASH, api_id=API_ID) as acc:
        for msg_id in range(from_id, to_id + 1):
            if BatchStatus.IS_BATCH.get(message.from_user.id):
                break
            try:
                await process_message(client, acc, message, datas, msg_id)
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                if ERROR_MESSAGE:
                    await message.reply(f"Error processing message {msg_id}: {str(e)}")
            await asyncio.sleep(2)

    BatchStatus.IS_BATCH[message.from_user.id] = True

async def process_message(client, acc, message, datas, msg_id):
    try:
        if "https://t.me/c/" in message.text:
            chat_id = int("-100" + datas[4])
            await handle_private(client, acc, message, chat_id, msg_id)
        elif "https://t.me/b/" in message.text:
            username = datas[4]
            await handle_private(client, acc, message, username, msg_id)
        else:
            username = datas[3]
            try:
                # First try to get chat info
                try:
                    chat = await acc.get_chat(username)
                except Exception:
                    try:
                        await acc.join_chat(username)
                        await asyncio.sleep(1)
                        chat = await acc.get_chat(username)
                    except Exception as e:
                        raise Exception(f"Failed to access chat: {str(e)}")

                # Get message
                try:
                    msg = await acc.get_messages(chat.id, msg_id)
                    if not msg or msg.empty:
                        raise MessageIdInvalid
                except MessageIdInvalid:
                    raise Exception(f"Message {msg_id} not found")

                # Try direct copy first
                try:
                    await client.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=chat.id,
                        message_id=msg_id,
                        reply_to_message_id=message.id
                    )
                except Exception:
                    # If direct copy fails, try downloading and sending
                    if msg.text:
                        await client.send_message(
                            message.chat.id,
                            text=msg.text,
                            entities=msg.entities,
                            reply_to_message_id=message.id
                        )
                    else:
                        file = await acc.download_media(msg)
                        if file:
                            caption = msg.caption or None
                            await send_media(client, acc, msg, message.chat.id, file, caption, message.id)
                            if os.path.exists(file):
                                os.remove(file)

            except Exception as e:
                error_text = str(e)
                if "CHANNEL_INVALID" in error_text:
                    error_text = "Unable to access this channel/group. Please make sure the bot is a member of the group."
                elif "MESSAGE_ID_INVALID" in error_text:
                    error_text = f"Message {msg_id} not found."
                elif "FLOOD_WAIT" in error_text:
                    wait_time = int(''.join(filter(str.isdigit, error_text)))
                    error_text = f"Please wait {wait_time} seconds before trying again."
                
                if ERROR_MESSAGE:
                    await client.send_message(
                        message.chat.id,
                        f"Error: {error_text}",
                        reply_to_message_id=message.id
                    )

    except UsernameNotOccupied:
        if ERROR_MESSAGE:
            await client.send_message(
                message.chat.id,
                "This username is not occupied by any channel or group.",
                reply_to_message_id=message.id
            )
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        if ERROR_MESSAGE:
            await client.send_message(
                message.chat.id,
                f"An error occurred: {str(e)}",
                reply_to_message_id=message.id
            )

async def handle_private(client: Client, acc, message: Message, chat_id, msg_id: int):
    try:
        msg = await acc.get_messages(chat_id, msg_id)
        if not msg or msg.empty:
            return

        if msg.text:
            await client.send_message(
                message.chat.id,
                text=msg.text,
                entities=msg.entities,
                reply_to_message_id=message.id
            )
            return

        msg_type = get_message_type(msg)
        if not msg_type:
            return

        chat = message.chat.id
        smsg = await client.send_message(chat, '**Downloading...**', reply_to_message_id=message.id)
        
        try:
            file = await acc.download_media(
                msg,
                progress=progress,
                progress_args=[message, "down"]
            )
            
            if file:
                caption = msg.caption or None
                await send_media(client, acc, msg, chat, file, caption, message.id)
                if os.path.exists(file):
                    os.remove(file)
        except Exception:
            try:
                await client.copy_message(
                    chat_id=chat,
                    from_chat_id=msg.chat.id,
                    message_id=msg.id,
                    reply_to_message_id=message.id
                )
            except Exception as e:
                if ERROR_MESSAGE:
                    await client.send_message(
                        chat,
                        f"Error: {str(e)}",
                        reply_to_message_id=message.id
                    )
        finally:
            await smsg.delete()

    except Exception as e:
        if ERROR_MESSAGE:
            await client.send_message(
                message.chat.id,
                f"Error processing message {msg_id}: {str(e)}",
                reply_to_message_id=message.id
            )

async def send_media(client, acc, msg, chat, file, caption, reply_to_message_id):
    msg_type = get_message_type(msg)
    thumb = await download_thumb(acc, msg)

    try:
        if msg_type == "Document":
            await client.send_document(chat, file, thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id)
        elif msg_type == "Video":
            await client.send_video(chat, file, duration=msg.video.duration, width=msg.video.width, height=msg.video.height,
                                    thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id)
        elif msg_type == "Animation":
            await client.send_animation(chat, file, reply_to_message_id=reply_to_message_id)
        elif msg_type == "Sticker":
            await client.send_sticker(chat, file, reply_to_message_id=reply_to_message_id)
        elif msg_type == "Voice":
            await client.send_voice(chat, file, caption=caption, reply_to_message_id=reply_to_message_id)
        elif msg_type == "Audio":
            await client.send_audio(chat, file, thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id)
        elif msg_type == "Photo":
            await client.send_photo(chat, file, caption=caption, reply_to_message_id=reply_to_message_id)
        elif msg_type == "Text":
            await client.send_message(chat, msg.text, entities=msg.entities, reply_to_message_id=reply_to_message_id)
    finally:
        if thumb and os.path.exists(thumb):
            os.remove(thumb)

async def download_thumb(acc, msg):
    try:
        if msg.document and msg.document.thumbs:
            return await acc.download_media(msg.document.thumbs[0].file_id)
        elif msg.video and msg.video.thumbs:
            return await acc.download_media(msg.video.thumbs[0].file_id)
    except:
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
