import os

# Bot token @Botfather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8156016933:AAGsjqZTbQ7i5Ko7j2pKt_OYXSouTCwvXEY")

# Your API ID from my.telegram.org
API_ID = int(os.environ.get("API_ID", "28098044"))

# Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", "157fd817f2ceb56fb2d7d5044b3e863a")

# Your Owner / Admin Id For Broadcast 
ADMINS = int(os.environ.get("ADMINS", "8037074956"))

# Your Mongodb Database Url
# Warning - Give Db uri in deploy server environment variable, don't give in repo.
DB_URI = os.environ.get("DB_URI", " mongodb+srv://DARKCODE:4ty3w8oB5NwK280W@cluster0.8ithn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0") # Warning - Give Db uri in deploy server environment variable, don't give in repo.
DB_NAME = os.environ.get("DB_NAME", "vjsavecontentbot")

# If You Want Error Message In Your Personal Message Then Turn It True Else If You Don't Want Then Flase
ERROR_MESSAGE = bool(os.environ.get('ERROR_MESSAGE', True))
