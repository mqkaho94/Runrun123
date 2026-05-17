import telebot
import random
import time
import threading
import sqlite3
import os
from datetime import date

TOKEN = "7742431712:AAHBx-YjOKHNK6Pq_bDkj7nOOnxEejE_Xo8"

bot = telebot.TeleBot(TOKEN)

HORSES = [
    "⚡1.閃電", "🌪2.黑旋風", "⭐3.幸運星", 
    "🔥4.火麒麟", "💨5.疾風", "🏅6.黃金戰馬"
]

# 資料庫
conn = sqlite3.connect('race.db', check_same_thread=False)
c = conn.cursor()
c.executescript('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    chips INTEGER DEFAULT 1000,
    last_daily TEXT
);
''')
conn.commit()

def get_chips(user_id):
    c.execute("SELECT chips FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, chips) VALUES (?, 1000)", (user_id,))
        conn.commit()
        return 1000
    return row[0]

def update_chips(user_id, amount):
    c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

current_race = None
race_id = None
race_bets = {}   # race_id: {user_id: [(bet_type, horses, amount)]}

# ================== 指令 ==================
@bot.message_handler(commands=['start'])
def start(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"🏇 **虛擬賽馬 Bot** 🏇\n💰 你的籌碼：**{chips}** chips", parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = """🏇 **投注指令**

/startrace - 開始新賽事

【投注方式】
/bet <號碼> <金額>     → 獨贏 (只中第1名)
/place <號碼> <金額>   → 位置 (中前3名)
/lin <號碼1> <號碼2> <金額> → 連贏 (前兩名順序不限)

💡 支援數字或百分比： /bet 1 500   或   /bet 1 10%
"""
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['startrace'])
def startrace(message):
    global current_race, race_id
    if current_race:
        bot.reply_to(message, "⚠️ 已有賽事進行中！")
        return

    current_race = True
    race_id = f"R{int(time.time())}"
    race_bets[race_id] = {}

    text = f"🏇 **第 {race_id} 場賽事開始！** 30秒後開跑\n\n"
    for h in HORSES:
        text += f"{h}\n"
    text += "\n💰 下注範例：\n/bet 1 500\n/place 3 300\n/lin 1 2 200"
    
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(30, lambda: run_race(message.chat.id)).start()
