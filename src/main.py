import logging
import json
from time import time
from decouple import config
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from firebase_admin import credentials as firebase_credentials, db as firebase_db, initialize_app as initialize_firebase
from pymongo import MongoClient

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

initialize_firebase(
    firebase_credentials.Certificate(json.loads(config('FIREBASE_CONFIG'))),
    {'databaseURL': config('FIREBASE_DATABASE')}
)

mongo_client = MongoClient(f"mongodb+srv://{config('MONGODB_USER')}:{config('MONGODB_PASSWORD')}@{config('MONGODB_CLUSTER')}/?retryWrites=true&w=majority")
subscriptions = mongo_client['telegram']['subscriptions']

async def list_devices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    devices = firebase_db.reference().get(shallow=True).keys()
    await update.message.reply_text(', '.join(devices))

async def list_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    devices = [subscription['device'] for subscription in subscriptions.find() if subscriptions['user_id'] == update.message.chat_id]
    await update.message.reply_text(', '.join(devices))

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text('Select a device to subscribe.')
        return
    device = context.args[0]
    user_devices = firebase_db.reference().get(shallow=True).keys()
    if device not in user_devices:
        await update.message.reply_text('This device does not exist.')
        return
    user_subscription = subscriptions.find_one({'user_id': update.message.chat_id, 'device': device})
    if user_subscription:
        await update.message.reply_text(f'You are already subscribed to the {device} device.')
    else:
        subscriptions.insert_one({'user_id': update.message.chat_id, 'device': device, 'timestamp': int(time())})
        await update.message.reply_text(f'You are now subscribed to the {device} device.')

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text('Select a device to unsubscribe.')
        return
    device = context.args[0]
    user_subscription = subscriptions.find_one({'user_id': update.message.chat_id, 'device': device})
    if user_subscription:
        subscriptions.delete_one({'_id': user_subscription['_id']})
        await update.message.reply_text(f'You are now unsubscribed from the {device} device.')
    else:
        await update.message.reply_text(f'You are not subscribed to the {device} device.')

async def status_update(context: ContextTypes.DEFAULT_TYPE):
    for subscription in subscriptions.find():
        user_id, device, user_timestamp = subscription['user_id'], subscription['device'], subscription['timestamp']
        _, last_update = firebase_db.reference(f'{device}').order_by_key().limit_to_last(1).get().popitem()
        timestamp, moisture = last_update['timestamp'], last_update['moisture']
        if timestamp > user_timestamp:
            subscriptions.update_one({'_id': subscription['_id']}, {'$set': {'timestamp': timestamp}})
            await context.bot.send_message(user_id, f'Moisture {moisture}')

if __name__ == '__main__':
    application = ApplicationBuilder().token(config('TELEGRAM_API')).build()
    application.add_handler(CommandHandler('devices', list_devices))
    application.add_handler(CommandHandler('subscriptions', list_subscriptions))
    application.add_handler(CommandHandler('subscribe', subscribe))
    application.add_handler(CommandHandler('unsubscribe', unsubscribe))
    application.job_queue.run_repeating(status_update, interval=60)
    application.run_polling()
