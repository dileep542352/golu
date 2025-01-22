import os
import asyncio
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWait
from pyrogram import Client as PyroClient, filters, enums
from pyrogram.errors import UsernameNotOccupied
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import API_ID, API_HASH, ERROR_MESSAGE
from database.db import db
from TechVJ.strings import HELP_TXT

# Initialize the Pyrogram client
pyro_client = PyroClient("my_bot", api_id=API_ID, api_hash=API_HASH)
# Initialize the Telethon client
aman = TelegramClient('session_name', API_ID, API_HASH)

# Global variables for batch processing
ids = []
batch = []

class batch_temp:
    IS_BATCH = {}

async def downstatus(client, statusfile, message, chat):
    while True:
        if os.path.exists(statusfile):
            break
        await asyncio.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as downread:
            txt = downread.read()
        try:
            await client.edit_message_text(chat, message.id, f"**Downloaded:** **{txt}**")
            await asyncio.sleep(10)
        except:
            await asyncio.sleep(5)

async def upstatus(client, statusfile, message, chat):
    while True:
        if os.path.exists(statusfile):
            break
        await asyncio.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as upread:
            txt = upread.read()
        try:
            await client.edit_message_text(chat, message.id, f"**Uploaded:** **{txt}**")
            await asyncio.sleep(10)
        except:
            await asyncio.sleep(5)

def progress(current, total, message, type):
    with open(f'{message.id}{type}status.txt', "w") as fileup:
        fileup.write(f"{current * 100 / total:.1f}%")

@pyro_client.on_message(filters.command(["start"]))
async def send_start(client: PyroClient, message: Message):
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
    buttons = [[
        InlineKeyboardButton("❣️ Developer", url="https://t.me/kingvj01")
    ], [
        InlineKeyboardButton('🔍 sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ', url='https://t.me/vj_bot_disscussion'),
        InlineKeyboardButton('🤖 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ', url='https://t.me/vj_botz')
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)
    await client.send_message(
        chat_id=message.chat.id,
        text=f"<b>👋 Hi {message.from_user.mention}, I am Save Restricted Content Bot, I can send you restricted content by its post link.\n\nFor downloading restricted content /login first.\n\nKnow how to use bot by - /help</b>",
        reply_markup=reply_markup,
        reply_to_message_id=message.id
    )

@pyro_client.on_message(filters.command(["help"]))
async def send_help(client: PyroClient, message: Message):
    await client.send_message(
        chat_id=message.chat.id,
        text=f"{HELP_TXT}"
    )

@pyro_client.on_message(filters.command(["cancel"]))
async def send_cancel(client: PyroClient, message: Message):
    batch_temp.IS_BATCH[message.from_user.id] = True
    await client.send_message(
        chat_id=message.chat.id,
        text="**Batch Successfully Cancelled.**"
    )

@pyro_client.on_message(filters.text & filters.private)
async def save(client: PyroClient, message: Message):
    if "https://t.me/" in message.text:
        if batch_temp.IS_BATCH.get(message.from_user.id) == False:
            return await message.reply_text("**One Task Is Already Processing. Wait For Complete It. If You Want To Cancel This Task Then Use - /cancel**")
        datas = message.text.split("/")
        temp = datas[-1].replace("?single", "").split("-")
        fromID = int(temp[0].strip())
        try:
            toID = int(temp[1].strip())
        except:
            toID = fromID
        batch_temp.IS_BATCH[message.from_user.id] = False
        for msgid in range(fromID, toID + 1):
            if batch_temp.IS_BATCH.get(message.from_user.id): break
            user_data = await db.get_session(message.from_user.id)
            if user_data is None:
                await message.reply("**For Downloading Restricted Content You Have To /login First.**")
                batch_temp.IS_BATCH[message.from_user.id] = True
                return
            try:
                acc = PyroClient("saverestricted", session_string=user_data, api_hash=API_HASH, api_id=API_ID)
                await acc.connect()
            except:
                batch_temp.IS_BATCH[message.from_user.id] = True
                return await message.reply("**Your Login Session Expired. So /logout First Then Login Again By - /login**")

            # Handle different types of message links
            if "https://t.me/c/" in message.text:
                chatid = int("-100" + datas[4])
                try:
                    await handle_private(client, acc, message, chatid, msgid)
                except Exception as e:
                    if ERROR_MESSAGE:
                        await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)

            elif "https://t.me/b/" in message.text:
                username = datas[4]
                try:
                    await handle_private(client, acc, message, username, msgid)
                except Exception as e:
                    if ERROR_MESSAGE:
                        await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)

            else:
                username = datas[3]
                try:
                    msg = await client.get_messages(username, msgid)
                except UsernameNotOccupied:
                    await client.send_message(message.chat.id, "The username is not occupied by anyone", reply_to_message_id=message.id)
                    return
                try:
                    await client.copy_message(message.chat.id, msg.chat.id, msg.id, reply_to_message_id=message.id)
                except:
                    try:
                        await handle_private(client, acc, message, username, msgid)
                    except Exception as e:
                        if ERROR_MESSAGE:
                            await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)

            await asyncio.sleep(3)
        batch_temp.IS_BATCH[message.from_user.id] = True

async def handle_private(client: PyroClient, acc, message: Message, chatid: int, msgid: int):
    msg: Message = await acc.get_messages(chatid, msgid)
    if msg.empty: return
    msg_type = get_message_type(msg)
    if not msg_type: return
    chat = message.chat.id
    if batch_temp.IS_BATCH.get(message.from_user.id): return
    if "Text" == msg_type:
        try:
            await client.send_message(chat, msg.text, entities=msg.entities, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
            return
        except Exception as e:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
            return

    smsg = await client.send_message(message.chat.id, '**Downloading**', reply_to_message_id=message.id)
    asyncio.create_task(downstatus(client, f'{message.id}downstatus.txt', smsg, chat))
    try:
        file = await acc.download_media(msg, progress=progress, progress_args=[message, "down"])
        os.remove(f'{message.id}downstatus.txt')
    except Exception as e:
        if ERROR_MESSAGE:
            await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        return await smsg.delete()
    if batch_temp.IS_BATCH.get(message.from_user.id): return
    asyncio.create_task(upstatus(client, f'{message.id}upstatus.txt', smsg, chat))

    caption = msg.caption if msg.caption else None
    if batch_temp.IS_BATCH.get(message.from_user.id): return

    if "Document" == msg_type:
        try:
            ph_path = await acc.download_media(msg.document.thumbs[0].file_id)
        except:
            ph_path = None
        try:
            await client.send_document(chat, file, thumb=ph_path, caption=caption, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML, progress=progress, progress_args=[message, "up"])
        except Exception as e:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        if ph_path is not None: os.remove(ph_path)

    elif "Video" == msg_type:
        try:
            ph_path = await acc.download_media(msg.video.thumbs[0].file_id)
        except:
            ph_path = None
        try:
            await client.send_video(chat, file, duration=msg.video.duration, width=msg.video.width, height=msg.video.height, thumb=ph_path, caption=caption, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML, progress=progress, progress_args=[message, "up"])
        except Exception as e:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        if ph_path is not None: os.remove(ph_path)

    elif "Animation" == msg_type:
        try:
            await client.send_animation(chat, file, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    elif "Sticker" == msg_type:
        try:
            await client.send_sticker(chat, file, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    elif "Voice" == msg_type:
        try:
            await client.send_voice(chat, file, caption=caption, caption_entities=msg.caption_entities, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML, progress=progress, progress_args=[message, "up"])
        except Exception as e:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    elif "Audio" == msg_type:
        try:
            ph_path = await acc.download_media(msg.audio.thumbs[0].file_id)
        except:
            ph_path = None
        try:
            await client.send_audio(chat, file, thumb=ph_path, caption=caption, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML, progress=progress, progress_args=[message, "up"])
        except Exception as e:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        if ph_path is not None: os.remove(ph_path)

    elif "Photo" == msg_type:
        try:
            await client.send_photo(chat, file, caption=caption, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        except:
            if ERROR_MESSAGE:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    if os.path.exists(f'{message.id}upstatus.txt'):
        os.remove(f'{message.id}upstatus.txt')
        os.remove(file)
    await client.delete_messages(message.chat.id, [smsg.id])

def get_message_type(msg: Message):
    try:
        msg.document.file_id
        return "Document"
    except:
        pass
    try:
        msg.video.file_id
        return "Video"
    except:
        pass
    try:
        msg.animation.file_id
        return "Animation"
    except:
        pass
    try:
        msg.sticker.file_id
        return "Sticker"
    except:
        pass
    try:
        msg.voice.file_id
        return "Voice"
    except:
        pass
    try:
        msg.audio.file_id
        return "Audio"
    except:
        pass
    try:
        msg.photo.file_id
        return "Photo"
    except:
        pass
    try:
        msg.text
        return "Text"
    except:
        pass

@aman.on(events.NewMessage(incoming=True, pattern='/batch'))
async def _batch(event):
    s = False
    if f'{event.sender_id}' in batch:
        return await event.reply("You've already started one batch, wait for it to complete you dumbfuck owner!")
    async with aman.conversation(event.chat_id) as conv:
        if not s:
            await conv.send_message("Send me the message link you want to start saving from, as a reply to this message.", buttons=Button.force_reply())
            try:
                link = await conv.get_reply()
                try:
                    _link = get_link(link.text)
                except Exception:
                    await conv.send_message("No link found.")
            except Exception as e:
                return await conv.send_message("Cannot wait more longer for your response!")
            await conv.send_message("Send me the number of files/range you want to save from the given message, as a reply to this message.", buttons=Button.force_reply())
            try:
                _range = await conv.get_reply()
            except Exception as e:
                return await conv.send_message("Cannot wait more longer for your response!")
            try:
                value = int(_range.text)
                if value > 1000000:
                    return await conv.send_message("You can only get up to 100000 files in a single batch.")
            except ValueError:
                return await conv.send_message("Range must be an integer!")
            for i in range(value):
                ids.append(i)
            s, r = await check(aman, _link)
            if s != True:
                await conv.send_message(r)
                return
            batch.append(f'{event.sender_id}')
            cd = await conv.send_message("**Batch process ongoing...**\n\nProcess completed: ",
                                         buttons=[[Button.url("Join Channel", url="http://t.me/LegendBotzs")]])
            co = await run_batch(aman, event.sender_id, cd, _link)
            try:
                if co == -2:
                    await aman.send_message(event.sender_id, "Batch successfully completed!")
                    await cd.edit(f"**Batch process ongoing.**\n\nProcess completed: {value} \n\n Batch successfully completed! ")
            except:
                await aman.send_message(event.sender_id, "ERROR!\n\n maybe last msg didn't exist yet")
            conv.cancel()
            ids.clear()
            batch.clear()

@aman.on(events.callbackquery.CallbackQuery(data="cancel"))
async def cancel(event):
    ids.clear()
    batch.clear()

async def run_batch(userbot, sender, countdown, link):
    for i in range(len(ids)):
        timer = 6
        if i < 250:
            timer = 2
        elif i < 1000:
            timer = 3
        elif i < 10000:
            timer = 4
        elif i < 50000:
            timer = 5
        elif i < 100000:
            timer = 6
        elif i < 200000:
            timer = 8
        elif i < 1000000:
            timer = 10

        if 't.me/c/' not in link:
            timer = 1 if i < 500 else 2
        try:
            count_down = f"**Batch process ongoing.**\n\nProcess completed: {i + 1}"
            msg_id = int(link.split("/")[-1]) + int(ids[i])
            await get_bulk_msg(userbot, sender, link, msg_id)

            protection = await userbot.send_message(sender, f"Sleeping for `{timer}` seconds to avoid Floodwaits and Protect account!")
            await countdown.edit(count_down, buttons=[[Button.url("Join Channel", url="https://t.me/LegendBotzs")]])
            await asyncio.sleep(timer)
            await protection.delete()

        except IndexError:
            await userbot.send_message(sender, f"Batch ended completed!")
            await countdown.delete()
            break

        except FloodWait as fw:
            if int(fw.value) > 300:
                await userbot.send_message(sender, f'You have floodwaits of {fw.value} seconds, cancelling batch')
                ids.clear()
                break
            else:
                fw_alert = await userbot.send_message(sender, f'Sleeping for {fw.value + 5} second(s) due to telegram floodwait.')
                await asyncio.sleep(fw.value + 5)
                await fw_alert.delete()

        except Exception as e:
            await userbot.send_message(sender, f"An error occurred during cloning, batch will continue.\n\n**Error:** {str(e)}")

        n = i + 1
        if n == len(ids):
            return -2

C = "/cancel"
START_PIC = "https://telegra.ph/file/c37f3eaf3e59e7e64fde7.png"
TEXT = "👋 Hi, This is 'Paid Restricted Content Saver' bot Made with ❤️ by __**Legend Union**__."

@aman.on(events.NewMessage(pattern=f"^{C}"))
async def start_command(event):
    buttons = [
        [Button.inline("Cancel", data="cancel"),
         Button.inline("Cancel", data="cancel")],
        [Button.url("Join Channel", url="https://telegram.dog/LegendBotzs")]
    ]

    await aman.send_file(
        event.chat_id,
        file=START_PIC,
        caption=TEXT,
        buttons=buttons
    )
