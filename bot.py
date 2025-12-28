import telebot
import requests
import sqlite3
import time
import threading
import os
from datetime import datetime
from telebot import types
from flask import Flask
from threading import Thread

# --- CẤU HÌNH ---
# Render sẽ lấy Token từ phần Environment Variables để bảo mật
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE') 
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- KHỞI TẠO DATABASE ---
def init_db():
    conn = sqlite3.connect('checkuid_pro.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tracking 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, 
                  uid TEXT, status TEXT, note TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

# --- HÀM KIỂM TRA TRẠNG THÁI FB ---
def check_fb_status(uid):
    try:
        url = f"https://graph.facebook.com/{uid}/picture?type=normal"
        res = requests.get(url, timeout=15, allow_redirects=True)
        # Nếu chuyển hướng về ảnh mặc định là Die/Checkpoint
        if "static.xx.fbcdn.net" in res.url or "default-black" in res.url:
            return "DIE 🔴"
        return "LIVE 🟢"
    except:
        return "ERROR ⚠️"

# --- THIẾT LẬP MENU LỆNH (COMMANDS) ---
def set_bot_commands():
    commands = [
        types.BotCommand("start", "Khởi động & Hướng dẫn"),
        types.BotCommand("add", "Lên kèo: /add UID | Ghi chú"),
        types.BotCommand("list", "Danh sách kèo đang chạy"),
        types.BotCommand("stats", "Thống kê tổng quan")
    ]
    bot.set_my_commands(commands)

# --- XỬ LÝ LỆNH /START & /HELP ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "🚀 **Hệ Thống Check UID Tự Động 24/7**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **Cách lên kèo nhanh:**\n"
        "Gõ: `/add UID | Ghi chú` \n"
        "*(Ví dụ: /add 1000123456 | Nick Kháng)*\n\n"
        "✨ **Lệnh khác:**\n"
        "📜 `/list` : Xem các kèo đang chạy\n"
        "📊 `/stats` : Thống kê số lượng\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ *Bot tự động báo 'Hoàn Thành' và Xóa UID khi trạng thái thay đổi.*"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# --- XỬ LÝ LỆNH /ADD ---
@bot.message_handler(commands=['add'])
def cmd_add(message):
    try:
        input_data = message.text.replace('/add', '').strip()
        if '|' not in input_data:
            bot.reply_to(message, "❌ Cú pháp sai! Hãy nhập: `/add UID | Ghi chú`", parse_mode="Markdown")
            return
            
        uid, note = [i.strip() for i in input_data.split('|')]
        if not uid.isdigit():
            bot.reply_to(message, "❌ UID phải là dãy số.")
            return

        start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = check_fb_status(uid)
        
        conn = sqlite3.connect('checkuid_pro.db')
        c = conn.cursor()
        c.execute("INSERT INTO tracking (chat_id, uid, status, note, created_at) VALUES (?, ?, ?, ?, ?)", 
                  (message.chat.id, uid, status, note, start_time_str))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ **Đã lên kèo giám sát!**\n🆔 UID: `{uid}`\n📝 Ghi chú: {note}\n📊 Trạng thái: {status}", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ Lỗi hệ thống khi thêm UID.")

# --- XỬ LÝ LỆNH /LIST ---
@bot.message_handler(commands=['list'])
def cmd_list(message):
    conn = sqlite3.connect('checkuid_pro.db')
    c = conn.cursor()
    c.execute("SELECT uid, status, note FROM tracking WHERE chat_id=?", (message.chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📭 Hiện không có kèo nào đang chạy.")
        return
    res = "📋 **DANH SÁCH KÈO ĐANG CHẠY:**\n\n"
    for r in rows:
        res += f"• `{r[0]}` | {r[1]} | {r[2]}\n"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

# --- XỬ LÝ LỆNH /STATS ---
@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    conn = sqlite3.connect('checkuid_pro.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tracking WHERE chat_id=?", (message.chat.id,))
    count = c.fetchone()[0]
    conn.close()
    bot.send_message(message.chat.id, f"📊 Bạn đang giám sát `{count}` kèo.", parse_mode="Markdown")

# --- LUỒNG QUÉT TỰ ĐỘNG (30S/LẦN) ---
def auto_scan():
    while True:
        try:
            conn = sqlite3.connect('checkuid_pro.db')
            c = conn.cursor()
            c.execute("SELECT id, chat_id, uid, status, note, created_at FROM tracking")
            items = c.fetchall()
            
            for db_id, chat_id, uid, old_status, note, created_at in items:
                new_status = check_fb_status(uid)
                if new_status != old_status:
                    now = datetime.now()
                    try:
                        start_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                        duration = str(now - start_time).split('.')[0]
                    except:
                        duration = "N/A"
                    
                    msg = (
                        f"✅ **BÁO CÁO HOÀN THÀNH KÈO**\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📝 **Ghi chú:** {note}\n"
                        f"🆔 **UID:** `{uid}`\n"
                        f"🔄 **Kết quả:** {old_status} ➔ {new_status}\n"
                        f"⏱ **Thời gian chạy:** `{duration}`\n"
                        f"📅 **Lúc:** `{now.strftime('%H:%M:%S %d/%m/%Y')}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🗑 *Hệ thống đã tự động gỡ UID khỏi danh sách.*"
                    )
                    bot.send_message(chat_id, msg, parse_mode="Markdown")
                    c.execute("DELETE FROM tracking WHERE id=?", (db_id,))
                    conn.commit()
            conn.close()
        except Exception as e:
            print(f"Lỗi Scan: {e}")
        time.sleep(30)

# --- GIỮ BOT LUÔN SỐNG (KEEP ALIVE) ---
@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    init_db()
    set_bot_commands()
    # Chạy Web Server ảo để tránh Render tắt bot
    Thread(target=run_flask).start()
    # Chạy quét UID ngầm
    Thread(target=auto_scan, daemon=True).start()
    print("Bot is running...")
    bot.infinity_polling()
