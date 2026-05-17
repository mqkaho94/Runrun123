import telebot
import random
import time
import threading
import sqlite3
from datetime import date

TOKEN = "7742431712:AAHBx-YjOKHNK6Pq_bDkj7nOOnxEejE_Xo8"
BOT_USERNAME = "Run1234567bot"

bot = telebot.TeleBot(TOKEN)
DB_NAME = 'race_tycoon.db'

# 馬匹購買價格級距 (依擁有數量決定)
BUY_PRICES = [500, 50000, 5000000, 500000000, 5000000000]

# 隨機隱藏狀態與其對應的勝率加權倍數
STATUSES = [
    {"text": "💊 食錯藥，反應不穩", "weight": 0.6},
    {"text": "🎭 雙重人格，時快時慢", "weight": 0.8},
    {"text": "🦷 牙痛影響發揮", "weight": 0.5},
    {"text": "🤧 感冒未清，狀態一般", "weight": 0.7},
    {"text": "🔥 狀態大勇，步履輕盈", "weight": 1.5},
    {"text": "🌟 鬥志高昂，全神貫注", "weight": 1.3}
]

# ================== 資料庫初始化 ==================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 用戶表
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        chips INTEGER DEFAULT 1000,
        last_daily TEXT
    );''')
    # 馬匹表
    c.execute('''
    CREATE TABLE IF NOT EXISTS horses (
        horse_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        horse_name TEXT,
        buy_price INTEGER
    );''')
    conn.commit()
    conn.close()

def get_chips(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT chips FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, chips) VALUES (?, 1000)", (user_id,))
        conn.commit()
        chips = 1000
    else:
        chips = row[0]
    conn.close()
    return chips

def update_chips(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

init_db()

# 賽事全域變數
current_race = None
race_id = None
race_bets = {}   
race_horses = [] # 本場出賽馬匹完整資訊

# ================== 系統指令 ==================
@bot.message_handler(commands=['start'])
def start(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, 
        f"🏇 **@{BOT_USERNAME} 馬場大亨** 🏇\n\n"
        f"💰 你的餘額：**{chips}** 金幣\n\n"
        f"輸入 /help 查看所有指令！", parse_mode='Markdown')

@bot.message_handler(commands=['balance'])
def balance(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"💰 你的餘額：**{chips}** 金幣", parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = f"""🏇 **@{BOT_USERNAME} 指令列表**

/startrace - 開始新賽事
/balance   - 查看金幣餘額
/buy       - 購買新馬匹 💰
/myhorses  - 查看我的馬匹列表

【投注方式】
/bet <號碼> <金額>     → 獨贏 (第1名，3倍)
/place <號碼> <金額>   → 位置 (前3名，2倍)
/lin <號碼1> <號碼2> <金額> → 連贏 (前兩名不分順序，5倍)
"""
    bot.reply_to(message, text, parse_mode='Markdown')

# ================== 馬匹養成與購買機制 ==================
@bot.message_handler(commands=['myhorses'])
def my_horses(message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT horse_name, buy_price FROM horses WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "🐴 你目前名下沒有任何愛駒，輸入 /buy 購買一隻吧！")
        return
        
    text = "🐴 **你的馬匹列表** **\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}. {row[0]} (購入價: {row[1]:,})\n"
    text += "\n💡 /rename <編號> <新名> 可以幫馬匹改名"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['buy'])
def buy_horse(message):
    user_id = message.from_user.id
    chips = get_chips(user_id)
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM horses WHERE user_id=?", (user_id,))
    owned_count = c.fetchone()[0]
    conn.close()
    
    if owned_count >= len(BUY_PRICES):
        bot.reply_to(message, "❌ 你的馬廄已經滿了，無法再購買更多馬匹！")
        return
        
    cost = BUY_PRICES[owned_count]
    if chips < cost:
        bot.reply_to(message, f"❌ 餘額不足！購買第 {owned_count+1} 隻馬需要 **{cost:,}** 金幣。")
        return
        
    # 扣除金幣
    update_chips(user_id, -cost)
    
    msg = bot.reply_to(message, f"✅ 已扣除 {cost:,} 金幣！\n請輸入馬匹名稱 (最多 4 字)：")
    # 註冊下一步處理函數：等待用戶輸入名字
    bot.register_next_step_handler(msg, save_new_horse, user_id, cost)

def save_new_horse(message, user_id, cost):
    name = message.text.strip()
    if len(name) == 0 or len(name) > 4:
        # 如果名字不合規，把錢退給人家
        update_chips(user_id, cost)
        bot.reply_to(message, "❌ 命名失敗！名字必須在 1 到 4 個字之間，已退回金幣。")
        return
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO horses (user_id, horse_name, buy_price) VALUES (?, ?, ?)", (user_id, name, cost))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"🎉 成功購買第 🐴 愛駒「**{name}**」！快去 /startrace 看看牠會不會出賽吧！", parse_mode='Markdown')

# ================== 賽事與隱藏狀態邏輯 ==================
@bot.message_handler(commands=['startrace'])
def startrace(message):
    global current_race, race_id, race_horses
    if current_race:
        bot.reply_to(message, "⚠️ 已有賽事進行中！")
        return

    current_race = True
    race_id = f"R{int(time.time())}"
    race_bets[race_id] = {}
    race_horses = []

    # 1. 抽選出賽馬匹（先從資料庫抽玩家的馬，不夠就補野生馬）
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT horse_name FROM horses ORDER BY RANDOM() LIMIT 6")
    db_horses = [row[0] for row in c.fetchall()]
    conn.close()
    
    # 野生預備馬匹名字
    wild_horses = ["閃電", "黑旋風", "幸運星", "火麒麟", "疾風", "黃金戰馬", "假架啲奶", "自摸奶奶"]
    random.shuffle(wild_horses)
    
    # 湊滿 6 匹馬
    chosen_names = db_horses[:]
    for wh in wild_horses:
        if len(chosen_names) >= 6: break
        if wh not in chosen_names:
            chosen_names.append(wh)
            
    # 2. 為這 6 匹馬附加上隨機隱藏狀態與計算勝率加權
    icons = ["⚡", "🌪", "⭐", "🔥", "💨", "🏅"]
    text = f"🏇 **第 {race_id} 場賽事開始！** 60秒後開跑 🏁\n\n"
    
    for i, name in enumerate(chosen_names):
        status = random.choice(STATUSES)
        full_name = f"{icons[i]}{i+1}.{name}"
        race_horses.append({
            "id_num": i+1,
            "full_name": full_name,
            "name": name,
            "status_text": status["text"],
            "weight": status["weight"]
        })
        text += f"🐴 你的愛駒「{name}」出戰！\n🔍 隱藏狀態：{status['text']}\n\n" if name in db_horses else f"{full_name}\n🔍 隱藏狀態：{status['text']}\n\n"

    text += "💰 下注範例：\n/bet 1 500\n/place 3 300\n/lin 1 2 200"
    bot.reply_to(message, text, parse_mode='Markdown')
    
    threading.Timer(60, lambda: run_race(message.chat.id, race_id)).start()

def run_race(chat_id, target_race_id):
    global current_race, race_horses
    bot.send_message(chat_id, "🏁 閘門打開，賽馬開跑！模擬中...")
    time.sleep(4.0)
    
    # 依據狀態權重進行加權隨機洗牌，計算出最終名次
    # 原理：權重越高的馬，越容易被排在前面
    pool = race_horses[:]
    finish = []
    while pool:
        total_weight = sum(h["weight"] for h in pool)
        r = random.uniform(0, total_weight)
        current = 0
        for h in pool:
            current += h["weight"]
            if r <= current:
                finish.append(h)
                pool.remove(h)
                break
                
    winner = finish[0]["full_name"]
    second = finish[1]["full_name"]
    
    result = "🏆 **最終賽果** 🏆\n\n"
    for i, h in enumerate(finish, 1):
        result += f"{i}名：{h['full_name']}\n"
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    # 派彩處理
    if target_race_id in race_bets:
        payout_message = "🎉 **派彩結果** 🎉\n\n"
        has_winner = False
        
        for uid, bets in race_bets[target_race_id].items():
            win_amount = 0
            for bet_type, horses, amt in bets:
                if bet_type == "bet" and horses == winner:
                    win_amount += amt * 3
                elif bet_type == "place" and horses in [f["full_name"] for f in finish[:3]]:
                    win_amount += amt * 2
                elif bet_type == "lin":
                    if isinstance(horses, list) and set(horses) == set([winner, second]):
                        win_amount += amt * 5
            
            if win_amount > 0:
                update_chips(uid, win_amount)
                payout_message += f"✅ 玩家 (ID: `{uid}`) 贏得 **{win_amount:,}** 金幣\n"
                has_winner = True
                
        if has_winner:
            bot.send_message(chat_id, payout_message, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "💸 本場賽事大家都摃龜啦！")
            
        del race_bets[target_race_id]
        
    current_race = None

# ================== 投注判定 (支援當前場次動態馬名) ==================
@bot.message_handler(commands=['bet', 'place', 'lin'])
def place_bet(message):
    global current_race, race_id, race_horses
    if not current_race:
        bot.reply_to(message, "❌ 目前沒有賽事進行中，請輸入 /startrace 開賽")
        return

    try:
        cmd = message.text.split()
        raw_cmd = cmd[0][1:]
        bet_type = raw_cmd.split('@')[0]
        user_id = message.from_user.id
        chips = get_chips(user_id)

        # 根據動態生成的馬匹清單比對號碼
        if bet_type in ["bet", "place"]:
            horse_num = int(cmd[1])
            amount_str = cmd[2]
            if horse_num < 1 or horse_num > 6: raise ValueError
            horses = race_horses[horse_num-1]["full_name"]
        elif bet_type == "lin":
            horse1 = int(cmd[1])
            horse2 = int(cmd[2])
            amount_str = cmd[3]
            if horse1 == horse2 or not (1 <= horse1 <= 6) or not (1 <= horse2 <= 6): raise ValueError
            horses = [race_horses[horse1-1]["full_name"], race_horses[horse2-1]["full_name"]]
        else:
            return

        if "%" in amount_str:
            percent = int(amount_str.replace("%", ""))
            if percent <= 0 or percent > 100: raise ValueError
            amount = int(chips * percent / 100)
        else:
            amount = int(amount_str)

        if amount < 100:
            bot.reply_to(message, "❌ 最低下注金額為 100 金幣")
            return
        if amount > chips:
            bot.reply_to(message, "❌ 餘額不足！")
            return

        update_chips(user_id, -amount)

        if user_id not in race_bets[race_id]:
            race_bets[race_id][user_id] = []
        race_bets[race_id][user_id].append((bet_type, horses, amount))

        bet_name = "獨贏" if bet_type=="bet" else "位置" if bet_type=="place" else "連贏"
        show_horses = f"{horses[0]} + {horses[1]}" if isinstance(horses, list) else horses
            
        bot.reply_to(message, f"✅ **{bet_name} 下注成功！**\n馬匹：**{show_horses}**\n金額：**{amount:,}** 金幣", parse_mode='Markdown')

    except Exception:
        bot.reply_to(message, "❌ 格式錯誤或輸入無效號碼！\n範例：\n/bet 1 500\n/place 3 10%\n/lin 1 2 200")

print(f"專屬養成版 🏇 @{BOT_USERNAME} 啟動成功！")
bot.infinity_polling()
