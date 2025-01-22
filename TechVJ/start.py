import os
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UsernameNotOccupied
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from telethon import events, Button
from telethon.errors import FloodWait as TelethonFloodWait

from config import API_ID, API_HASH, ERROR_MESSAGE
from database.db import db
from TechVJ.strings import HELP_TXT
from main.plugins.pyroplug import check, get_bulk_msg
from main.plugins.helpers import get_link

class BatchTemp:
    IS_BATCH = {}

batch = []
ids = []

# Initialize logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)

# Progress tracking functions
async def downstatus(client, statusfile, message, chat):
    while not os.path.exists(statusfile):
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
    while not os.path.exists(statusfile):
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

@Client.on_message(filters.command(["start"]))
async def send_start(client: Client, message: Message):
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
    
    buttons = [[
        InlineKeyboardButton("❣️ Developer", url="https://t.me/infobyblackhat")
    ], [
        InlineKeyboardButton('🔍 Support Group', url='https://t.me/chalobaatenkren'),
        InlineKeyboardButton('🤖 Update Channel', url='https://t.me/updatesbyeevils')
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await client.send_message(
        chat_id=message.chat.id,
        text=f"<b>👋 Hi {message.from_user.mention}, I am Save Restricted Content Bot. Send me any public or private restricted content link to clone it to your desired channel.\n\nFor downloading restricted content /login first.\n\nKnow more about usage with /help</b>",
        reply_markup=reply_markup,
        reply_to_message_id=message.id
    )

@Client.on_message(filters.command(["help"]))
async def send_help(client: Client, message: Message):
    await client.send_message(
        chat_id=message.chat.id,
        text=HELP_TXT
    )

@Client.on_message(filters.command(["cancel"]))
async def send_cancel(client: Client, message: Message):
    BatchTemp.IS_BATCH[message.from_user.id] = True
    await client.send_message(
        chat_id=message.chat.id,
        text="**Batch Processing Cancelled.**"
    )

@Client.on_message(filters.text & filters.private)
async def handle_batch_messages(client: Client, message: Message):
    """Handle batch message processing"""
    if "https://t.me/" not in message.text:
        return

    if not await db.is_user_exist(message.from_user.id):
        return await message.reply("Please /start the bot first!")

    if BatchTemp.IS_BATCH.get(message.from_user.id) is False:
        return await message.reply_text(
            "**A task is already in progress. Wait for it to complete or use /cancel**"
        )

    # Extract the range from message
    try:
        link_parts = message.text.strip().split("/")
        if len(link_parts) < 4:
            return await message.reply("Invalid link format!")

        range_part = link_parts[-1].split("-")
        if len(range_part) != 2:
            return await message.reply("Please provide range in format: start-end")

        start_id = int(range_part[0].strip())
        end_id = int(range_part[1].strip())

        if end_id < start_id:
            return await message.reply("End ID must be greater than Start ID!")

        if end_id - start_id > 100:  # You can adjust this limit
            return await message.reply("Maximum 100 messages allowed in one batch!")

        # Set batch processing flag
        BatchTemp.IS_BATCH[message.from_user.id] = False
        
        # Get user session
        user_data = await db.get_session(message.from_user.id)
        if user_data is None:
            await message.reply("**Please /login first to download restricted content.**")
            BatchTemp.IS_BATCH[message.from_user.id] = True
            return

        # Initialize client with user session
        try:
            acc = Client(
                "saverestricted",
                session_string=user_data,
                api_hash=API_HASH,
                api_id=API_ID
            )
            await acc.connect()
        except Exception as e:
            BatchTemp.IS_BATCH[message.from_user.id] = True
            return await message.reply(
                "**Your login session has expired. Please /logout and /login again.**"
            )

        # Progress message
        progress_msg = await message.reply("**Starting batch process...**")
        
        # Process messages in range
        for msg_id in range(start_id, end_id + 1):
            if BatchTemp.IS_BATCH.get(message.from_user.id):
                break

            try:
                await progress_msg.edit_text(f"**Processing message {msg_id}...**")
                
                # Handle private channel messages
                if "https://t.me/c/" in message.text:
                    chat_id = int("-100" + link_parts[4])
                    msg = await acc.get_messages(chat_id, msg_id)
                else:
                    # Handle public channel messages
                    username = link_parts[3]
                    msg = await acc.get_messages(username, msg_id)

                if msg and not msg.empty:
                    await msg.copy(
                        message.chat.id,
                        caption=msg.caption if msg.caption else None,
                        parse_mode=enums.ParseMode.HTML
                    )
                
                await asyncio.sleep(2)  # Delay to avoid flood wait

            except FloodWait as e:
                await progress_msg.edit_text(f"**FloodWait: Sleeping for {e.value} seconds**")
                await asyncio.sleep(e.value)
                continue
            except Exception as e:
                await message.reply(f"**Error processing message {msg_id}: {str(e)}**")
                continue

        BatchTemp.IS_BATCH[message.from_user.id] = True
        await progress_msg.edit_text("**Batch processing completed!**")
        await acc.disconnect()

    except ValueError:
        await message.reply("**Please provide valid message IDs in the range!**")
    except Exception as e:
        await message.reply(f"**An error occurred: {str(e)}**")
        BatchTemp.IS_BATCH[message.from_user.id] = True

# Constants
START_PIC = "https://telegra.ph/file/c37f3eaf3e59e7e64fde7.png"
TEXT = "👋 Hi, This is 'Paid Restricted Content Saver' bot Made with ❤️ by __**Legend Union**__."

def main():
    # Initialize your bot here
    app = Client(
        "SaveRestrictedContentBot",
        api_id=API_ID,
        api_hash=API_HASH,
        # Add your bot token here
    )

    print("Bot Started!")
    app.run()

if __name__ == "__main__":
    main()
