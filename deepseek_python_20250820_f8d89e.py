import logging
import sqlite3
import asyncio
from typing import List, Dict, Tuple
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    InputMediaPhoto
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    ContextTypes, 
    filters
)
from telegram.error import BadRequest
import aiohttp
import io
from PIL import Image, ImageDraw, ImageFont
import random
import string

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "YOUR_BOT_TOKEN"
DOMAIN = "https://yourdomain.com"
ADMIN_IDS = [123456789]  # Replace with your admin user IDs
VERIFICATION_CODE = "AB12CD"  # Fixed verification code for all users

# Database setup
def init_db():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        verified INTEGER DEFAULT 0,
        code_sent INTEGER DEFAULT 0,
        upi_sent INTEGER DEFAULT 0
    )
    ''')
    
    # Channels table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        channel_id INTEGER PRIMARY KEY,
        username TEXT,
        title TEXT,
        invite_link TEXT,
        is_private INTEGER DEFAULT 0,
        required INTEGER DEFAULT 1,
        sequence INTEGER
    )
    ''')
    
    # Payments table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payments (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        upi_id TEXT,
        amount REAL,
        status TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

# Database functions
def get_db_connection():
    return sqlite3.connect('bot.db')

# Channel management functions
def get_channels():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels ORDER BY sequence")
    channels = cursor.fetchall()
    conn.close()
    return channels

def add_channel(channel_id, username, title, invite_link, is_private):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get the next sequence number
    cursor.execute("SELECT MAX(sequence) FROM channels")
    max_seq = cursor.fetchone()[0]
    sequence = max_seq + 1 if max_seq is not None else 1
    
    cursor.execute(
        "INSERT INTO channels (channel_id, username, title, invite_link, is_private, sequence) VALUES (?, ?, ?, ?, ?, ?)",
        (channel_id, username, title, invite_link, is_private, sequence)
    )
    conn.commit()
    conn.close()

def delete_channel(channel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def update_channel_sequence(channel_id, new_sequence):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE channels SET sequence = ? WHERE channel_id = ?", (new_sequence, channel_id))
    conn.commit()
    conn.close()

# User management functions
def add_user(user_id, username, first_name, last_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, last_name)
    )
    conn.commit()
    conn.close()

def update_user_verification(user_id, verified):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET verified = ? WHERE user_id = ?", (verified, user_id))
    conn.commit()
    conn.close()

def update_user_code_sent(user_id, code_sent):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET code_sent = ? WHERE user_id = ?", (code_sent, user_id))
    conn.commit()
    conn.close()

def update_user_upi_sent(user_id, upi_sent):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET upi_sent = ? WHERE user_id = ?", (upi_sent, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# Payment functions
def add_payment(user_id, upi_id, amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payments (user_id, upi_id, amount, status) VALUES (?, ?, ?, ?)",
        (user_id, upi_id, amount, 'pending')
    )
    conn.commit()
    conn.close()

# Image generation function (for demo purposes)
async def generate_image_with_text(image_url, text):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    image = Image.open(io.BytesIO(image_data))
                    
                    # Add text to image
                    draw = ImageDraw.Draw(image)
                    # You might need to adjust font path based on your system
                    try:
                        font = ImageFont.truetype("arial.ttf", 30)
                    except:
                        font = ImageFont.load_default()
                    
                    # Position the text
                    text_position = (50, image.height - 100)
                    draw.text(text_position, text, fill=(255, 255, 255), font=font)
                    
                    # Save to bytes
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    return img_byte_arr
    except Exception as e:
        logger.error(f"Error generating image: {e}")
        return None

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name, user.last_name)
    
    # Send first image with channel list
    channels = get_channels()
    keyboard = []
    
    for channel in channels:
        channel_id, username, title, invite_link, is_private, required, sequence = channel
        keyboard.append([InlineKeyboardButton(title, url=invite_link)])
    
    keyboard.append([InlineKeyboardButton("✅ I've Joined All", callback_data="verify_join")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Generate or fetch the image
    image_url = f"{DOMAIN}/images/welcome.jpg"
    caption = "Welcome! Please join all the channels below to continue:"
    
    # Try to generate image with text, fallback to sending URL if fails
    image_bytes = await generate_image_with_text(image_url, "Welcome!")
    
    if image_bytes:
        await update.message.reply_photo(
            photo=image_bytes,
            caption=caption,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_photo(
            photo=image_url,
            caption=caption,
            reply_markup=reply_markup
        )

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    channels = get_channels()
    
    # Check if user is member of all channels
    not_joined = []
    for channel in channels:
        channel_id, username, title, invite_link, is_private, required, sequence = channel
        
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(title)
        except BadRequest:
            not_joined.append(title)
        except Exception as e:
            logger.error(f"Error checking membership: {e}")
            not_joined.append(title)
    
    if not_joined:
        await query.edit_message_caption(
            caption=f"You haven't joined these channels: {', '.join(not_joined)}. Please join all and try again."
        )
        return
    
    # User has joined all channels
    update_user_verification(user_id, 1)
    
    # Send second image with verification code
    image_url = f"{DOMAIN}/images/verification.jpg"
    caption = f"Thank you for joining! Your verification code is: {VERIFICATION_CODE}\n\nPlease send this code to continue."
    
    # Generate or fetch the image
    image_bytes = await generate_image_with_text(image_url, f"Code: {VERIFICATION_CODE}")
    
    if image_bytes:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=image_bytes,
            caption=caption
        )
    else:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=image_url,
            caption=caption
        )
    
    update_user_code_sent(user_id, 1)

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_code = update.message.text.strip()
    
    # Check if user has been sent the code
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code_sent FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        await update.message.reply_text("Please start the verification process with /start first.")
        return
    
    if user_code == VERIFICATION_CODE:
        await update.message.reply_text("Code verified! Please send your UPI ID to make the payment of ₹10.")
        update_user_upi_sent(user_id, 1)
    else:
        await update.message.reply_text("Invalid code. Please try again.")

async def handle_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upi_id = update.message.text.strip()
    
    # Check if user has been asked for UPI
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT upi_sent FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        await update.message.reply_text("Please complete the previous steps first.")
        return
    
    # Validate UPI ID (basic validation)
    if not upi_id.lower().endswith('@upi'):
        await update.message.reply_text("Please enter a valid UPI ID (e.g., name@upi).")
        return
    
    # Add payment record
    add_payment(user_id, upi_id, 10.0)
    
    # Send payment instructions
    payment_text = f"Please send ₹10 to the following UPI ID: {upi_id}\n\nAfter payment, you will be granted access."
    await update.message.reply_text(payment_text)
    
    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"New payment request:\nUser: {update.effective_user.mention_markdown()}\nUPI: {upi_id}\nAmount: ₹10"
            )
        except Exception as e:
            logger.error(f"Error notifying admin: {e}")

# Admin commands
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    keyboard = [
        [InlineKeyboardButton("Manage Channels", callback_data="admin_channels")],
        [InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("Stats", callback_data="admin_stats")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Admin Panel:", reply_markup=reply_markup)

async def admin_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("You are not authorized to use this feature.")
        return
    
    channels = get_channels()
    keyboard = []
    
    for channel in channels:
        channel_id, username, title, invite_link, is_private, required, sequence = channel
        keyboard.append([
            InlineKeyboardButton(f"❌ {title}", callback_data=f"delete_channel_{channel_id}"),
            InlineKeyboardButton("⬆️", callback_data=f"move_up_{channel_id}"),
            InlineKeyboardButton("⬇️", callback_data=f"move_down_{channel_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Channel Management:\nClick ❌ to delete a channel\nUse ⬆️ ⬇️ to change order",
        reply_markup=reply_markup
    )

async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("You are not authorized to use this feature.")
        return
    
    await query.edit_message_text(
        "To add a channel, forward a message from the channel or send the channel username (@username)."
    )
    # Set state to wait for channel info
    context.user_data['awaiting_channel'] = True

async def handle_channel_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not context.user_data.get('awaiting_channel'):
        return
    
    if update.message.forward_from_chat and update.message.forward_from_chat.type in ['channel', 'supergroup']:
        chat = update.message.forward_from_chat
        channel_id = chat.id
        username = chat.username
        title = chat.title
        
        # Check if bot is admin in the channel
        try:
            bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
            if bot_member.status not in ['administrator', 'creator']:
                await update.message.reply_text(
                    f"I need to be an admin in {title} to verify members. Please make me admin and try again."
                )
                return
        except Exception as e:
            logger.error(f"Error checking bot admin status: {e}")
            await update.message.reply_text(
                f"Error checking my admin status in {title}. Please make sure I'm added as admin."
            )
            return
        
        # Generate invite link
        try:
            invite_link = await context.bot.create_chat_invite_link(channel_id, creates_join_request=False)
            invite_link = invite_link.invite_link
        except:
            invite_link = f"https://t.me/{username}" if username else "No invite link available"
        
        # Add channel to database
        add_channel(channel_id, username, title, invite_link, 0 if username else 1)
        
        await update.message.reply_text(f"Channel {title} added successfully!")
        context.user_data['awaiting_channel'] = False
        
        # Return to admin panel
        await admin_channels_callback(update, context)
    else:
        await update.message.reply_text("Please forward a message from the channel you want to add.")

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("You are not authorized to use this feature.")
        return
    
    await query.edit_message_text(
        "Send the message you want to broadcast. You can include text, photos, or documents."
    )
    context.user_data['awaiting_broadcast'] = True

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not context.user_data.get('awaiting_broadcast'):
        return
    
    users = get_all_users()
    success = 0
    failed = 0
    
    # Send to all users
    for user_id in users:
        try:
            # Forward the message
            await update.message.forward(user_id)
            success += 1
        except Exception as e:
            logger.error(f"Error broadcasting to {user_id}: {e}")
            failed += 1
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    # Send broadcast report
    report = f"Broadcast completed!\nSuccess: {success}\nFailed: {failed}"
    await update.message.reply_text(report)
    
    context.user_data['awaiting_broadcast'] = False

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("You are not authorized to use this feature.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user stats
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE verified = 1")
    verified_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'completed'")
    completed_payments = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'completed'")
    total_revenue = cursor.fetchone()[0] or 0
    
    conn.close()
    
    stats_text = f"""
📊 Bot Statistics:
    
👥 Total Users: {total_users}
✅ Verified Users: {verified_users}
💳 Completed Payments: {completed_payments}
💰 Total Revenue: ₹{total_revenue}
    """
    
    await query.edit_message_text(stats_text)

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("You are not authorized to use this feature.")
        return
    
    data = query.data
    
    if data.startswith("delete_channel_"):
        channel_id = int(data.split("_")[2])
        delete_channel(channel_id)
        await query.edit_message_text("Channel deleted successfully!")
        await admin_channels_callback(update, context)
    
    elif data.startswith("move_up_") or data.startswith("move_down_"):
        channel_id = int(data.split("_")[2])
        channels = get_channels()
        
        # Find current sequence
        current_seq = None
        for channel in channels:
            if channel[0] == channel_id:
                current_seq = channel[6]
                break
        
        if current_seq is None:
            await query.answer("Channel not found!")
            return
        
        # Determine new sequence
        if data.startswith("move_up_"):
            new_seq = max(1, current_seq - 1)
        else:
            new_seq = current_seq + 1
        
        # Swap sequences
        for channel in channels:
            if channel[6] == new_seq:
                update_channel_sequence(channel[0], current_seq)
                break
        
        update_channel_sequence(channel_id, new_seq)
        await query.answer("Channel order updated!")
        await admin_channels_callback(update, context)
    
    elif data == "admin_back":
        await query.edit_message_text("Returning to main admin menu...")
        await admin(update, context)

def main():
    # Initialize database
    init_db()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    
    application.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    application.add_handler(CallbackQueryHandler(admin_channels_callback, pattern="^admin_channels$"))
    application.add_handler(CallbackQueryHandler(add_channel_callback, pattern="^add_channel$"))
    application.add_handler(CallbackQueryHandler(admin_broadcast_callback, pattern="^admin_broadcast$"))
    application.add_handler(CallbackQueryHandler(admin_stats_callback, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(handle_admin_actions))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_upi))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_channel_forward))
    application.add_handler(MessageHandler(filters.ALL, handle_broadcast_message))
    
    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()