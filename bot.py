import telebot
import random
import time
import threading
import sqlite3
import os
from datetime import date

# ================== TOKEN 已填入 ==================
TOKEN = "7742431712:AAHBx-YjOKHNK6Pq_bDkj7nOOnxEejE_Xo8"

bot = telebot.TeleBot(TOKEN)

HORSES = ["⚡閃電", "🌪黑旋風", "⭐幸運星", "🔥火麒麟", "💨疾風", "🏅黃金戰馬"]

# 資料庫
conn = sqlite3.connect('race.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                chips INTEGER DEFAULT 1000,
                last_daily TEXT)''')
conn.commit()

def get_user(user_id, username):
    c.execute("SELECT chips FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, username, chips) VALUES (?, ?, 1000)", (user_id, username))
        conn.commit()
        return 1000
    return row[0]

def update_chips(user_id, amount):
    c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def get_leaderboard():
    c.execute("SELECT username, chips FROM users ORDER BY chips DESC LIMIT 10")
    return c.fetchall()

current_race = None
race_bets = {}

@bot.message_handler(commands=['start'])
def start(message):
    chips = get_user(message.from_user.id, message.from_user.first_name)
    bot.reply_to(message, 
        f"🏇 **@Run1234567bot 虛擬賽馬場** 🏇\n\n"
        f"💰 你的籌碼：**{chips}** chips\n\n"
        f"🎮 指令：\n"
        f"/race - 開新賽事\n"
        f"/daily - 每日簽到 (+500)\n"
        f"/balance - 查看籌碼\n"
        f"/leaderboard - 排行榜", 
        parse_mode='Markdown')

@bot.message_handler(commands=['daily'])
def daily(message):
    user_id = message.from_user.id
    today = date.today().isoformat()
    c.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
    last = c.fetchone()
    if last and last[0] == today:
        bot.reply_to(message, "❌ 你今天已經領過每日獎勵！")
        return
    update_chips(user_id, 500)
    c.execute("UPDATE users SET last_daily=? WHERE user_id=?", (today, user_id))
    conn.commit()
    bot.reply_to(message, "✅ **每日簽到成功！** +500 chips 💰")

@bot.message_handler(commands=['balance'])
def balance(message):
    chips = get_user(message.from_user.id, message.from_user.first_name)
    bot.reply_to(message, f"💰 你的籌碼：**{chips}** chips", parse_mode='Markdown')

@bot.message_handler(commands=['leaderboard'])
def leaderboard(message):
    board = get_leaderboard()
    text = "🏆 **賽馬富豪排行榜** 🏆\n\n"
    for i, (name, chips) in enumerate(board, 1):
        text += f"{i}. {name} — **{chips}** chips\n"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['race'])
def start_race(message):
    global current_race
    if current_race:
        bot.reply_to(message, "⚠️ 已有賽事進行中...")
        return
    current_race = time.time()
    race_bets.clear()
    text = "🏇 **新賽事開始！** 30秒後開跑 🏁\n\n**參賽馬匹：**\n" + "\n".join([f"• {h}" for h in HORSES])
    text += "\n\n💸 下注指令： `/bet 馬名 金額`"
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(30, run_race, [message.chat.id]).start()

def run_race(chat_id):
    global current_race
    bot.send_message(chat_id, "🏁 賽馬開跑！模擬中...")
    time.sleep(3.5)
    finish = HORSES[:]
    random.shuffle(finish)
    winner = finish[0]
    result = "🏆 **最終賽果** 🏆\n\n" + "\n".join([f"{i}. {h}" for i, h in enumerate(finish, 1)])
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    if current_race in race_bets:
        for uid, (horse, amt) in race_bets[current_race].items():
            if horse == winner:
                win = amt * 3
                update_chips(uid, win)
                bot.send_message(chat_id, f"🎉 <a href='tg://user?id={uid}'>玩家</a> 贏得 **{win}** chips！", parse_mode='HTML')
    current_race = None

@bot.message_handler(commands=['bet'])
def bet(message):
    global current_race
    if not current_race:
        bot.reply_to(message, "❌ 請先輸入 /race 開新賽事")
        return
    try:
        _, horse, amt_str = message.text.split()
        amount = int(amt_str)
        if horse not in HORSES:
            bot.reply_to(message, "❌ 馬名錯誤！請確認馬名")
            return
        chips = get_user(message.from_user.id, message.from_user.first_name)
        if chips < amount:
            bot.reply_to(message, "❌ 籌碼不足！")
            return
        update_chips(message.from_user.id, -amount)
        if current_race not in race_bets:
            race_bets[current_race] = {}
        race_bets[current_race][message.from_user.id] = (horse, amount)
        bot.reply_to(message, f"✅ 下注成功！\n🐎 馬匹：**{horse}**\n💰 金額：**{amount}** chips", parse_mode='Markdown')
    except:
        bot.reply_to(message, "❌ 格式錯誤！\n正確用法：`/bet 馬名 金額`\n範例：`/bet 閃電 200`")

print("🏇 @Run1234567bot 已啟動...")
bot.infinity_polling()
