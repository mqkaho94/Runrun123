import telebot
import random
import time
import threading
import sqlite3
import os
from datetime import date

# ⚠️ 安全提醒：公開程式碼時請記得隱藏或更換你的 Token
TOKEN = "7742431712:AAHBx-YjOKHNK6Pq_bDkj7nOOnxEejE_Xo8"
BOT_USERNAME = "@Run1234567bot"
bot = telebot.TeleBot(TOKEN)

# 🏇 8 隻馬匹名單
HORSES = [
    "⚡1.閃電", "🌪2.黑旋風", "⭐3.幸運星", "🔥4.火麒麟", 
    "💨5.疾風", "🏅6.黃金戰馬", "🌊7.海嘯", "🦅8.傲空"
]

DB_FILE = 'race.db'

# ================== 資料庫最佳化 (Context Manager) ==================
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            chips INTEGER DEFAULT 1000,
            last_daily TEXT
        );
        ''')
        conn.commit()

def get_chips(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT chips FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO users (user_id, chips) VALUES (?, 1000)", (user_id,))
            conn.commit()
            return 1000
        return row[0]

def update_chips(user_id, amount):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (amount, user_id))
        conn.commit()

init_db()

# ================== 賽事全域變數 ==================
current_race = None
race_id = None
race_bets = {}   
race_odds = {}  # 儲存當期馬匹的隨機獨贏賠率

# ================== 機器人指令處理 ==================
@bot.message_handler(commands=['start'])
def start(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, 
        f"🏇 **{BOT_USERNAME} 虛擬賽馬** 🏇\n\n"
        f"💰 你的籌碼：**{chips}** chips\n\n"
        f"輸入 /help 查看所有指令", 
        parse_mode='Markdown')

@bot.message_handler(commands=['daily'])
def daily(message):
    user_id = message.from_user.id
    today = date.today().isoformat()
    
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
        last = c.fetchone()
        if last and last[0] == today:
            bot.reply_to(message, "❌ 你今天已經領過每日獎勵！")
            return
        
        c.execute("UPDATE users SET last_daily=? WHERE user_id=?", (today, user_id))
        conn.commit()
        
    update_chips(user_id, 3000)
    bot.reply_to(message, "✅ **每日簽到成功！** +3000chips 💰")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = f"""🏇 **{BOT_USERNAME} 指令列表**

/startrace - 開始新賽事 (自動刷新隨機賠率)
/balance   - 查詢目前籌碼

【投注方式】
/bet <號碼> <金額>     → 獨贏 (只中第1名，得獨贏賠率)
/place <號碼> <金額>   → 位置 (中前3名，得獨贏的一半賠率)
/lin <號碼1> <號碼2> <金額> → 連贏 (前兩名，不限順序，兩馬獨贏賠率相乘)

💡 <b>下注福利：</b>金額少於 100 chips 時，實際扣除 0 金幣 (免費免單)，中獎一樣照常派發全額彩金！
💡 支援百分比投注，例如：/bet 1 10%
"""
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['startrace'])
def startrace(message):
    global current_race, race_id, race_odds
    if current_race:
        bot.reply_to(message, "⚠️ 已有賽事進行中！")
        return

    current_race = True
    race_id = f"R{int(time.time())}"
    race_bets[race_id] = {}
    race_odds = {}

    # 🎲 隨機生成 8 隻馬的獨贏賠率 (2.5 - 15.0倍)
    text = f"🏇 **第 {race_id} 場賽事開始！** 60秒後開跑 🏁\n\n"
    text += "【本局獨贏 / 位置 賠率公示】\n"
    for h in HORSES:
        win_odds = round(random.uniform(2.5, 15.0), 1)
        place_odds = round(win_odds / 2, 1)
        race_odds[h] = win_odds  
        text += f"{h}  ➡️  獨贏: *{win_odds}x* | 位置: *{place_odds}x*\n"
        
    text += "\n💡 連贏賠率為前兩名馬匹的獨贏賠率相乘！\n"
    text += "\n💰 下注範例：\n/bet 1 500\n/place 3 300\n/lin 1 2 200"
    
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(60, lambda: run_race(message.chat.id)).start()

# ================== 核心：動態模擬賽馬（10秒 - 2分鐘隨機完賽） ==================
def run_race(chat_id):
    global current_race, race_id, race_odds
    
    race_msg = bot.send_message(chat_id, "🏁 **鳴槍開跑！馬匹正在激烈交鋒中...** 🏁", parse_mode='Markdown')
    
    TOTAL_DISTANCE = 100.0  # 邏輯總長度設為 100
    DISPLAY_LENGTH = 15     # 畫面上顯示的格子數（保持畫面的整齊美觀）
    
    # ⏱️ 關鍵核心：隨機為每隻馬產生 10秒 到 120秒 之間的完賽時間
    target_times = {h: random.uniform(10.0, 120.0) for h in HORSES}
    
    # 根據目標完賽時間，計算每隻馬「每秒該跑的格數」
    speeds = {h: TOTAL_DISTANCE / target_times[h] for h in HORSES}
    
    # 初始化狀態
    current_distance = {h: 0.0 for h in HORSES}
    finished_horses = []
    
    start_time = time.time()
    last_refresh_time = start_time
    
    # 🐎 動態跑馬核心主迴圈
    while len(finished_horses) < len(HORSES):
        time.sleep(0.1)  # 後台高頻率計算位置
        now = time.time()
        elapsed = now - start_time
        
        # 根據流逝的時間，精準更新每隻馬前進的距離
        for h in HORSES:
            if current_distance[h] < TOTAL_DISTANCE:
                # 基礎位置 = 當前時間 * 每秒速度
                current_distance[h] = elapsed * speeds[h]
                
                # 加上一點微小的隨機顛簸（增加賽事的超車隨機性）
                current_distance[h] += random.uniform(-0.5, 0.5)
                if current_distance[h] < 0: current_distance[h] = 0
                
                # 判定是否衝線
                if current_distance[h] >= TOTAL_DISTANCE:
                    current_distance[h] = TOTAL_DISTANCE
                    if h not in finished_horses:
                        finished_horses.append(h)
                        
        # 🛡️ 防刷屏限制：每 2.0 秒才更新一次 Telegram 畫面
        if now - last_refresh_time >= 2.0 or len(finished_horses) == len(HORSES):
            last_refresh_time = now
            
            dynamic_text = f"🏇 **第 {race_id} 場賽事 現場直播** 🏁\n"
            dynamic_text += "‾" * 25 + "\n"
            
            for h in HORSES:
                # 將邏輯的 100 進度等比例換算成畫面的 15 格
                progress_ratio = current_distance[h] / TOTAL_DISTANCE
                passed_display = int(progress_ratio * DISPLAY_LENGTH)
                if passed_display > DISPLAY_LENGTH: passed_display = DISPLAY_LENGTH
                remaining_display = DISPLAY_LENGTH - passed_display
                
                # 💡 由右向左跑邏輯：左邊終點 🏁，右邊起點
                track_str = "🏁 " + "🟩" * remaining_to_goal_display + "🐎" + "🟩" * passed_display
                # 修正上方變數：由總長度減去已走格數
                remaining_to_goal_display = DISPLAY_LENGTH - passed_display
                track_str = "🏁 " + "🟩" * remaining_to_goal_display + "🐎" + "🟩" * passed_display
                
                status_flag = " ✨衝線！" if current_distance[h] == TOTAL_DISTANCE else ""
                dynamic_text += f"{h}{status_flag}\n{track_str}\n\n"
                
            dynamic_text += "—" * 25 + f"\n💨 賽事已進行：{int(elapsed)} 秒\n💨 馬匹正在全力衝刺中..."
            
            try:
                bot.edit_message_text(dynamic_text, chat_id, race_msg.message_id, parse_mode='Markdown')
            except:
                pass
                
    # 🏁 定格最終名次
    winner = finished_horses[0]
    second = finished_horses[1]
    
    result = "🏆 **最終賽果名次** 🏆\n\n"
    for i, h in enumerate(finished_horses, 1):
        result += f"第 {i} 名：{h} (獨贏 {race_odds[h]}x)\n"
    
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    # 💰 派彩系統
    if race_id in race_bets:
        payout_message = "🎉 **派彩結果** 🎉\n\n"
        has_winner = False
        
        for uid, bets in race_bets[race_id].items():
            win_amount = 0
            for bet_type, horses, amt in bets:
                if bet_type == "bet" and horses == winner:
                    win_amount += int(amt * race_odds[winner])
                elif bet_type == "place" and horses in finished_horses[:3]:
                    win_amount += int(amt * (race_odds[horses] / 2))
                elif bet_type == "lin":
                    if isinstance(horses, list) and set(horses) == set([winner, second]):
                        lin_odds = race_odds[winner] * race_odds[second]
                        win_amount += int(amt * lin_odds)
            
            if win_amount > 0:
                update_chips(uid, win_amount)
                payout_message += f"✅ 玩家 <a href='tg://user?id={uid}'>{uid}</a> 贏得 <b>{win_amount}</b> chips\n"
                has_winner = True
        
        if has_winner:
            bot.send_message(chat_id, payout_message, parse_mode='HTML')
        else:
            bot.send_message(chat_id, "壓注全空！本局沒有人中獎 💸")
    
    # 重設當局狀態
    current_race = None
    race_odds = {}
    if race_id in race_bets:
        del race_bets[race_id]

# ================== 核心：投注邏輯處理 ==================
@bot.message_handler(commands=['bet', 'place', 'lin'])
def place_bet(message):
    global current_race, race_id, race_odds
    if not current_race:
        bot.reply_to(message, "❌ 目前沒有賽事，請輸入 /startrace 開賽")
        return

    try:
        cmd = message.text.split()
        bet_type = cmd[0][1:]
        user_id = message.from_user.id
        chips = get_chips(user_id)

        if bet_type in ["bet", "place"]:
            if len(cmd) < 3: raise ValueError
            horse_num = int(cmd[1])
            amount_str = cmd[2]
            if horse_num < 1 or horse_num > len(HORSES):
                bot.reply_to(message, "❌ 馬匹號碼錯誤！請輸入 1-8")
                return
            horses = HORSES[horse_num-1]
            
        elif bet_type == "lin":
            if len(cmd) < 4: raise ValueError
            horse1 = int(cmd[1])
            horse2 = int(cmd[2])
            amount_str = cmd[3]
            if horse1 == horse2 or min(horse1, horse2) < 1 or max(horse1, horse2) > len(HORSES):
                bot.reply_to(message, "❌ 馬匹號碼錯誤或重複！請輸入 1-8 且兩號碼不能相同")
                return
            horses = [HORSES[horse1-1], HORSES[horse2-1]]

        if "%" in amount_str:
            percent = int(amount_str.replace("%", ""))
            if percent <= 0 or percent > 100:
                bot.reply_to(message, "❌ 百分比必須在 1% - 100% 之間！")
                return
            bet_amount = int(chips * percent / 100)
        else:
            bet_amount = int(amount_str)

        if bet_amount <= 0:
            bot.reply_to(message, "❌ 下注金額必須大於 0！")
            return

        credit = 100
        if bet_amount <= credit:
            actual_deduct = 0
            used_credit = bet_amount
        else:
            actual_deduct = bet_amount - credit
            used_credit = credit

        if actual_deduct > chips:
            bot.reply_to(message, "❌ 籌碼不足！")
            return

        update_chips(user_id, -actual_deduct)

        if user_id not in race_bets[race_id]:
            race_bets[race_id][user_id] = []
        
        race_bets[race_id][user_id].append((bet_type, horses, bet_amount))

        bet_name = "獨贏" if bet_type=="bet" else "位置" if bet_type=="place" else "連贏"
        show_horse = f"{horses[0]} + {horses[1]}" if isinstance(horses, list) else horses
        
        if bet_type == "bet":
            current_odds = race_odds[horses]
        elif bet_type == "place":
            current_odds = round(race_odds[horses] / 2, 1)
        elif bet_type == "lin":
            current_odds = round(race_odds[horses[0]] * race_odds[horses[1]], 1)
            
        possible_win = int(bet_amount * current_odds)

        reply_text = (
            f"✅ **{bet_name}投注成功！** {show_horse}\n"
            f"投注額：{bet_amount} 金幣\n"
            f"實際扣除：{actual_deduct} 金幣 (已享 {used_credit} 信用)\n"
            f"{bet_name}賠率：{current_odds}倍\n"
            f"💰 若勝出可贏：{possible_win} 金幣"
        )
        
        bot.reply_to(message, reply_text, parse_mode='Markdown')

    except Exception as e:
        bot.reply_to(message, "❌ 格式錯誤！\n範例：\n/bet 1 500\n/place 3 300\n/lin 1 2 200")

@bot.message_handler(commands=['balance'])
def balance(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"💰 你的籌碼：**{chips}** chips", parse_mode='Markdown')

# ================== 啟動服務 ==================
print(f"🏇 {BOT_USERNAME} 已經完全升級成功並啟動監聽...")
bot.infinity_polling()
