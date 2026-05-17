import telebot
import random
import time
import threading
import sqlite3
import os
from datetime import date
TOKEN = "7742431712:AAHBx-YjOKHNK6Pq_bDkj7nOOnxEejE_Xo8"

BOT_USERNAME = "@Run1234567bot"

bot = telebot.TeleBot(TOKEN)

HORSES = [
    "⚡1.閃電", "🌪2.黑旋風", "⭐3.幸運星", 
    "🔥4.火麒麟", "💨5.疾風", "🏅6.黃金戰馬"
]

# ================== 資料庫 ==================
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
race_bets = {}   

# ================== 指令 ==================
@bot.message_handler(commands=['start'])
def start(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, 
        f"🏇 **@Run1234567bot 虛擬賽馬** 🏇\n\n"
        f"💰 你的籌碼：**{chips}** chips\n\n"
        f"輸入 /help 查看所有指令", 
        parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = f"""🏇 **{BOT_USERNAME} 指令列表**

/startrace - 開始新賽事

【投注方式】
/bet <號碼> <金額>     → 獨贏 (只中第1名)
/place <號碼> <金額>   → 位置 (中前3名)
/lin <號碼1> <號碼2> <金額> → 連贏 (前兩名)

💡 支援百分比投注，例如：/bet 1 10%
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

    text = f"🏇 **第 {race_id} 場賽事開始！** 30秒後開跑 🏁\n\n"
    for h in HORSES:
        text += f"{h}\n"
    text += "\n💰 下注範例：\n/bet 1 500\n/place 3 300\n/lin 1 2 200"
    
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(30, lambda: run_race(message.chat.id)).start()

def run_race(chat_id):
    global current_race
    bot.send_message(chat_id, "🏁 賽馬開跑！模擬中...")
    time.sleep(3.5)
    
    finish = HORSES[:]
    random.shuffle(finish)
    winner = finish[0]
    second = finish[1]
    
    result = "🏆 **最終賽果** 🏆\n\n"
    for i, h in enumerate(finish, 1):
        result += f"{i}名：{h}\n"
    
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    # 派彩處理
    if race_id in race_bets:
        payout_message = "🎉 **派彩結果** 🎉\n"
        for uid, bets in race_bets[race_id].items():
            win_amount = 0
            for bet_type, horses, amt in bets:
                if bet_type == "bet" and horses == winner:
                    win_amount += amt * 3
                elif bet_type == "place" and horses in finish[:3]:
                    win_amount += amt * 2
                elif bet_type == "lin":
                    if isinstance(horses, list) and set([h.split('.')[1] for h in horses]) == set([winner.split('.')[1], second.split('.')[1]]):
                        win_amount += amt * 5
            
            if win_amount > 0:
                update_chips(uid, win_amount)
                payout_message += f"✅ 玩家贏得 **{win_amount}** chips\n"
        
        if "玩家贏得" in payout_message:
            bot.send_message(chat_id, payout_message, parse_mode='HTML')
    
    current_race = None
    if race_id in race_bets:
        del race_bets[race_id]

# 投注處理
@bot.message_handler(commands=['bet', 'place', 'lin'])
def place_bet(message):
    global current_race
    if not current_race:
        bot.reply_to(message, "❌ 目前沒有賽事，請輸入 /startrace 開賽")
        return

    try:
        cmd = message.text.split()
        bet_type = message.text.split()[0][1:]
        user_id = message.from_user.id
        chips = get_chips(user_id)

        if bet_type in ["bet", "place"]:
            horse_num = int(cmd[1])
            amount_str = cmd[2]
            horses = HORSES[horse_num-1]
        elif bet_type == "lin":
            horse1 = int(cmd[1])
            horse2 = int(cmd[2])
            amount_str = cmd[3]
            horses = [HORSES[horse1-1], HORSES[horse2-1]]

        # 百分比處理
        if "%" in amount_str:
            percent = int(amount_str.replace("%", ""))
            amount = int(chips * percent / 100)
        else:
            amount = int(amount_str)

        if amount < 100:
            bot.reply_to(message, "❌ 最低下注金額為 100 chips")
            return
        if amount > chips:
            bot.reply_to(message, "❌ 籌碼不足！")
            return

        update_chips(user_id, -amount)

        if user_id not in race_bets[race_id]:
            race_bets[race_id][user_id] = []
        race_bets[race_id][user_id].append((bet_type, horses, amount))

        bet_name = "獨贏" if bet_type=="bet" else "位置" if bet_type=="place" else "連贏"
        bot.reply_to(message, f"✅ **{bet_name} 下注成功！**\n馬匹：**{horses}**\n金額：**{amount}** chips", parse_mode='Markdown')

    except:
        bot.reply_to(message, "❌ 格式錯誤！\n範例：\n/bet 1 500\n/place 3 300\n/lin 1 2 200")

@bot.message_handler(commands=['balance'])
def balance(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"💰 你的籌碼：**{chips}** chips", parse_mode='Markdown')

print(f"🏇 {BOT_USERNAME} 已成功啟動")
bot.infinity_polling()
