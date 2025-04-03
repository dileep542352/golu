import motor.motor_asyncio
from config import DB_NAME, DB_URI

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users

    def new_user(self, id, name):
        return dict(
            id=id,
            name=name,
            session=None,
        )
    
    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.insert_one(user)
    
    async def is_user_exist(self, id):
        user = await self.col.find_one({'id': int(id)})
        return bool(user)
    
    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def set_session(self, id, session):
        await self.col.update_one({'id': int(id)}, {'$set': {'session': session}})

    async def get_session(self, id):
        user = await self.col.find_one({'id': int(id)})
        return user.get('session')

    async def save_batch_progress(self, user_id, link, last_processed, total_value):
        """
        Save the progress of a batch process for a user.
        """
        await self.col.update_one(
            {'id': int(user_id)},
            {'$set': {'paused_batch': {'link': link, 'last_processed': last_processed, 'total_value': total_value}}},
            upsert=True
        )

    async def get_paused_batch(self, user_id):
        """
        Retrieve the paused batch data for a user.
        """
        user = await self.col.find_one({'id': int(user_id)})
        return user.get('paused_batch') if user else None

    async def clear_batch_progress(self, user_id):
        """
        Clear the paused batch data for a user.
        """
        await self.col.update_one(
            {'id': int(user_id)},
            {'$unset': {'paused_batch': ''}}
        )

# Initialize the database
db = Database(DB_URI, DB_NAME)
