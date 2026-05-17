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

# 🏇 基礎 7 隻固定馬匹名單（保留第 8 個位置給抽中的專屬馬）
BASE_HORSES = [
    "⚡1.閃電", "🌪2.黑旋風", "⭐3.幸運星", "🔥4.火麒麟", 
    "💨5.疾風", "🏅6.黃金戰馬", "🌊7.海嘯"
]
DEFAULT_HORSE_8 = "🦅8.傲空" # 若當局無馬主下注，則預設的 8 號馬

# 🔢 名次對應的數字 Emoji 對照表（完賽定格用）
RANK_EMOJIS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
    5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"
}

DB_FILE = 'race.db'
HORSE_PRICE = 3000  # 購買馬匹所需籌碼為 3000 chips

# ================== 資料庫升級 ==================
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            chips INTEGER DEFAULT 1000,
            last_daily TEXT,
            has_horse INTEGER DEFAULT 0,
            horse_name TEXT DEFAULT NULL
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

# 獲取玩家的馬匹資訊
def get_user_horse(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT has_horse, horse_name FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if row:
            return {"has_horse": row[0], "horse_name": row[1]}
        return {"has_horse": 0, "horse_name": None}

# 根據馬匹名字反查馬主的 user_id
def get_owner_by_horse_name(horse_name):
    clean_name = horse_name.replace("👑8.", "")
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE horse_name=?", (clean_name,))
        row = c.fetchone()
        return row[0] if row else None

# 獲取全伺服器所有擁有專屬馬的馬主 user_id 清單
def get_all_horse_owners():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE has_horse=1")
        rows = c.fetchall()
        return [row[0] for row in rows]

# 🎰 核心隨機抽獎機制：不論多少位馬主下注，用抽籤形式隨機挑選一位上場
def get_active_custom_horse(active_user_ids):
    if not active_user_ids:
        return DEFAULT_HORSE_8
    
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # 從這局有下注的人當中，撈出「同時也是馬主」的玩家名單
        placeholders = ','.join('?' for _ in active_user_ids)
        c.execute(f"SELECT horse_name FROM users WHERE has_horse=1 AND horse_name IS NOT NULL AND user_id IN ({placeholders})", list(active_user_ids))
        rows = c.fetchall()
        
        # 如果有馬主參與下注（不論幾個人），隨機抽籤一隻馬名代表 8 號上場
        if rows:
            chosen_name = random.choice(rows)[0]
            return f"👑8.{chosen_name}" 
    return DEFAULT_HORSE_8

init_db()

# ================== 賽事全域變數 ==================
current_race = None    
race_id = None
race_bets = {}   
race_odds = {}  
current_horses = []   

# 🔄 限制機制全域變數
user_bet_count = {}     
user_refund_count = {}  
user_actual_deduct = {} 

# ================== 🤖 私訊專屬功能 🤖 ==================
@bot.message_handler(commands=['buy'])
def buy_horse(message):
    if message.chat.type != "private":
        bot.reply_to(message, f"❌ 為了防洗版，此功能限私訊使用！請點擊此處私訊我： {BOT_USERNAME}")
        return

    user_id = message.from_user.id
    chips = get_chips(user_id)
    horse_info = get_user_horse(user_id)

    if horse_info["has_horse"] == 1:
        bot.reply_to(message, f"🐴 您已經擁有一匹愛駒了！目前名字為：**{horse_info['horse_name']}**\n若想修改名字請輸入：\n`/rename 新的馬名`", parse_mode='Markdown')
        return

    cmd = message.text.split(maxsplit=1)
    
    if len(cmd) < 2:
        bot.reply_to(message, 
            f"🛒 **【專屬馬匹拍賣所】**\n\n"
            f"擁有專屬馬後，只要你在群組參與下注，你的愛駒就有機會代替 8 號馬登場參賽！\n"
            f"💰 售價：**{HORSE_PRICE}** chips\n"
            f"💰 你的餘額：**{chips}** chips\n\n"
            f"👉 **購買請輸入**：\n`/buy 你的馬名` (最多4個字，例如：`/buy 天馬行空`)", 
            parse_mode='Markdown')
        return

    horse_name = cmd[1].strip()

    if len(horse_name) < 1 or len(horse_name) > 4:
        bot.reply_to(message, "❌ 名字字數不符合規定！請設定在 **1 到 4 個字** 之間。")
        return

    if chips < HORSE_PRICE:
        bot.reply_to(message, f"❌ 你的籌碼不足！購買專屬馬需要 **{HORSE_PRICE}** chips，你目前只有 {chips}。")
        return

    update_chips(user_id, -HORSE_PRICE)
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET has_horse=1, horse_name=? WHERE user_id=?", (horse_name, user_id))
        conn.commit()

    bot.reply_to(message, f"🎉 **恭喜購馬成功！**\n籌碼已扣除 {HORSE_PRICE}。\n您的愛駒 **「{horse_name}」** 已成功登記！今後只要你在群組下注，牠就有機會代表 8 號馬出賽參戰！")

@bot.message_handler(commands=['rename'])
def rename_horse(message):
    if message.chat.type != "private":
        bot.reply_to(message, f"❌ 為了防洗版，此功能限私訊使用！請點擊此處私訊我： {BOT_USERNAME}")
        return

    user_id = message.from_user.id
    horse_info = get_user_horse(user_id)

    if horse_info["has_horse"] == 0:
        bot.reply_to(message, "❌ 您目前還沒有馬匹，無法使用改名功能！請先輸入 `/buy 馬名` 購買一匹。", parse_mode='Markdown')
        return

    cmd = message.text.split(maxsplit=1)
    
    if len(cmd) < 2:
        bot.reply_to(message, 
            f"🐴 **【愛駒改名所】**\n\n"
            f"目前愛駒名字：**{horse_info['horse_name']}**\n\n"
            f"👉 **改名請輸入**：\n`/rename 新的馬名` (最多4個字，例如：`/rename 閃電俠`)", 
            parse_mode='Markdown')
        return

    new_horse_name = cmd[1].strip()

    if len(new_horse_name) < 1 or len(new_horse_name) > 4:
        bot.reply_to(message, "❌ 名字字數不符合規定！請設定在 **1 到 4 個字** 之間。")
        return

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET horse_name=? WHERE user_id=?", (new_horse_name, user_id))
        conn.commit()

    bot.reply_to(message, f"✨ **改名成功！**\n您的愛駒已成功更名為：**「{new_horse_name}」** 🏇")

@bot.message_handler(commands=['start'])
def start(message):
    chips = get_chips(message.from_user.id)
    text = (
        f"🏇 **{BOT_USERNAME} 虛擬賽馬** 🏇\n\n"
        f"💰 你的籌碼：**{chips}** chips\n\n"
        f"💡 **【私訊專屬功能】**\n"
        f"輸入 `/buy 馬名` 可以用 {HORSE_PRICE} 籌碼購買專屬賽馬！\n"
        f"輸入 `/rename 新馬名` 可以幫現有的愛駒改名！\n\n"
        f"輸入 /help 查看所有指令"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

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
/refund    - 開賽前退款當局投注（每場限一次）
/buy       - <b>【私訊限定】</b>購買專屬馬匹 (3000 chips)
/rename    - <b>【私訊限定】</b>自訂愛駒修改名字 (限4字)

【投注方式】（每場限投注一次）
/bet <號碼> <金額>     → 獨贏
/place <號碼> <金額>   → 位置
/lin <號碼1> <號碼2> <金額> → 連贏

💡 <b>下注福利：</b>金額少於 100 chips 時，實際扣除 0 金幣 (免費免單)，中獎一樣照常派發全額彩金！
"""
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['startrace'])
def startrace(message):
    global current_race, race_id, race_odds, user_bet_count, user_refund_count, user_actual_deduct, current_horses
    if current_race:
        bot.reply_to(message, "⚠️ 已有賽事進行中！")
        return

    current_race = "betting"  
    race_id = f"R{int(time.time())}"
    race_bets[race_id] = {}
    race_odds = {}
    user_bet_count = {}
    user_refund_count = {}
    user_actual_deduct = {}
    
    current_horses = BASE_HORSES.copy() + [DEFAULT_HORSE_8]

    text = f"🏇 **第 {race_id} 場賽事開始！** 60秒後開跑 🏁\n\n"
    text += "【本局獨贏 / 位置 賠率公示】\n"
    for h in current_horses:
        win_odds = round(random.uniform(2.5, 15.0), 1)
        place_odds = round(win_odds / 2, 1)
        race_odds[h] = win_odds  
        text += f"{h}  ➡️  獨贏: *{win_odds}x* | 位置: *{place_odds}x*\n"

    text += "\n" + "—" * 20 + "\n"
    text += "💰 **【下注範例】**\n"
    text += "👉 獨贏：`/bet 1 100` (下注 1 號馬 100)\n"
    text += "👉 位置：`/place 3 100` (下注 3 號馬前三名 100)\n"
    text += "👉 連贏：`/lin 1 2 100` (下注 1 號與 2 號包辦前兩名 100)\n"
    text += "—" * 20 + "\n"
    
    text += f"\n💡 每人每場限投一次！私訊我 `/buy` 可擁有自訂排位馬。開跑前買錯可輸入 `/refund` 退款重填。\n"
    
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(60, lambda: run_race(message.chat.id)).start()

# ================== 核心：動態模擬賽馬 ==================
def run_race(chat_id):
    global current_race, race_id, race_odds, race_bets, current_horses
    
    if current_race != "betting":
        return

    active_users = race_bets.get(race_id, {}).keys()
    
    # 🎰 呼叫隨機抽獎函數：從本局下注的馬主中，用隨機抽獎形式挑選 1 人上場
    chosen_custom_horse = get_active_custom_horse(active_users)
    
    old_8_horse = current_horses[7]
    if chosen_custom_horse != old_8_horse:
        current_horses[7] = chosen_custom_horse
        race_odds[chosen_custom_horse] = race_odds[old_8_horse]
        del race_odds[old_8_horse]
        
        for uid, bets in race_bets[race_id].items():
            for idx, bet in enumerate(bets):
                b_type, h_target, b_amt = bet
                if b_type in ["bet", "place"] and h_target == old_8_horse:
                    bets[idx] = (b_type, chosen_custom_horse, b_amt)
                elif b_type == "lin" and isinstance(h_target, list):
                    if old_8_horse in h_target:
                        new_target = [chosen_custom_horse if h == old_8_horse else h for h in h_target]
                        bets[idx] = (b_type, new_target, b_amt)

    current_race = "running" 
    race_msg = bot.send_message(chat_id, "🏁 **鳴槍開跑！馬匹正在激烈交鋒中...** 🏁", parse_mode='Markdown')
    
    TOTAL_DISTANCE = 100.0  
    DISPLAY_LENGTH = 15     
    
    target_times = {h: random.uniform(10.0, 120.0) for h in current_horses}
    speeds = {h: TOTAL_DISTANCE / target_times[h] for h in current_horses}
    
    current_distance = {h: 0.0 for h in current_horses}
    finished_horses = []  
    
    start_time = time.time()
    last_refresh_time = start_time
    
    while len(finished_horses) < 3:
        time.sleep(0.1)  
        now = time.time()
        elapsed = now - start_time
        
        for h in current_horses:
            if current_distance[h] < TOTAL_DISTANCE:
                current_distance[h] = elapsed * speeds[h]
                current_distance[h] += random.uniform(-0.2, 0.2)
                if current_distance[h] < 0: current_distance[h] = 0
                
                if current_distance[h] >= TOTAL_DISTANCE:
                    current_distance[h] = TOTAL_DISTANCE
                    if h not in finished_horses:
                        finished_horses.append(h)
                        
        if now - last_refresh_time >= 2.0 or len(finished_horses) >= 3:
            last_refresh_time = now
            
            dynamic_text = f"🏇 **第 {race_id} 場賽事 現場直播** 🏁\n"
            dynamic_text += "‾" * 25 + "\n"
            
            for h in current_horses:
                progress_ratio = current_distance[h] / TOTAL_DISTANCE
                passed_display = int(progress_ratio * DISPLAY_LENGTH)
                if passed_display > DISPLAY_LENGTH: passed_display = DISPLAY_LENGTH
                remaining_to_goal_display = DISPLAY_LENGTH - passed_display
                
                track_str = "🏁 " + "_" * remaining_to_goal_display + "🐎" + "_" * passed_display
                
                status_flag = ""
                if h in finished_horses:
                    rank = finished_horses.index(h) + 1
                    if rank == 1: status_flag = " 🥇【冠軍】"
                    elif rank == 2: status_flag = " 🥈【亞軍】"
                    elif rank == 3: status_flag = " 🥉【季軍】"
                
                dynamic_text += f"{h}{status_flag}\n`{track_str}`\n\n"
                
            dynamic_text += "—" * 25 + f"\n💨 賽事已進行：{int(elapsed)} 秒\n💨 頭馬正在全力衝刺中..."
            
            try:
                bot.edit_message_text(dynamic_text, chat_id, race_msg.message_id, parse_mode='Markdown')
            except:
                pass

    remaining_horses = [h for h in current_horses if h not in finished_horses]
    remaining_horses.sort(key=lambda h: current_distance[h], reverse=True)
    all_ranks = finished_horses + remaining_horses
    
    final_track_text = f"🏇 **第 {race_id} 場賽事 直播結束（定格名次）** 🏁\n"
    final_track_text += "‾" * 25 + "\n"
    
    for h in current_horses:
        final_rank = all_ranks.index(h) + 1
        rank_emoji = RANK_EMOJIS.get(final_rank, "🐎") 
        
        progress_ratio = current_distance[h] / TOTAL_DISTANCE
        passed_display = int(progress_ratio * DISPLAY_LENGTH)
        if passed_display > DISPLAY_LENGTH: passed_display = DISPLAY_LENGTH
        remaining_to_goal_display = DISPLAY_LENGTH - passed_display
        
        track_str = "🏁 " + "_" * remaining_to_goal_display + rank_emoji + "_" * passed_display
        
        status_flag = ""
        if final_rank == 1: status_flag = " 🥇【冠軍】"
        elif final_rank == 2: status_flag = " 🥈【亞軍】"
        elif final_rank == 3: status_flag = " 🥉【季軍】"
        
        final_track_text += f"{h}{status_flag}\n`{track_str}`\n\n"
        
    final_track_text += "—" * 25 + f"\n🏁 賽事在 {int(time.time() - start_time)} 秒時完美結算！"
    
    try:
        bot.edit_message_text(final_track_text, chat_id, race_msg.message_id, parse_mode='Markdown')
    except:
        pass
                
    winner = all_ranks[0]
    second = all_ranks[1]
    
    result = "🏆 **最終賽果名次結果** 🏆\n\n"
    for i, h in enumerate(all_ranks, 1):
        if i == 1: medal = "🥇"
        elif i == 2: medal = "🥈"
        elif i == 3: medal = "🥉"
        else: medal = "🏁"
        result += f"{medal} 第 {i} 名：{h} (獨贏 {race_odds[h]}x)\n"
    
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    # 💰 1. 玩家投注常規派彩系統
    if race_id in race_bets:
        payout_message = "🎉 **派彩結果** 🎉\n\n"
        has_winner = False
        
        for uid, bets in race_bets[race_id].items():
            win_amount = 0
            for bet_type, horses, amt in bets:
                if bet_type == "bet" and horses == winner:
                    win_amount += int(amt * race_odds[winner])
                elif bet_type == "place" and horses in all_ranks[:3]:
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

    # 👑 2. 馬主額外分紅系統（包含大獎與安慰獎）
    owner_payout_text = "✨ <b>【本局馬主專利分紅】</b> ✨\n"
    big_winners = [] 
    has_owner_bonus = False
    
    # (A) 先結算前三名大獎
    for rank_idx in range(3):
        target_horse = all_ranks[rank_idx]
        if "👑8." in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id:
                rank_num = rank_idx + 1
                if rank_num == 1:
                    bonus_chips = random.randint(200000, 300000)
                    title = "🥇 冠軍"
                elif rank_num == 2:
                    bonus_chips = random.randint(50000, 100000)
                    title = "🥈 亞軍"
                else:
                    bonus_chips = random.randint(10000, 30000)
                    title = "🥉 季軍"
                
                update_chips(owner_id, bonus_chips)
                big_winners.append(owner_id)
                owner_payout_text += f"恭喜專屬馬 <b>{target_horse}</b> 榮獲{title}！\n馬主 <a href='tg://user?id={owner_id}'>{owner_id}</a> 額外獲得隨機大獎 <b>+{bonus_chips}</b> chips 💰\n"
                has_owner_bonus = True

    # (B) 若有專屬馬進前三名，則對「其餘所有馬主」發放隨機安慰獎
    if has_owner_bonus:
        all_owners = get_all_horse_owners()
        consolation_owners = [oid for oid in all_owners if oid not in big_winners]
        
        if consolation_owners:
            lucky_comfort_bonus = random.randint(3000, 5000)
            for c_owner in consolation_owners:
                update_chips(c_owner, lucky_comfort_bonus)
                
            owner_payout_text += f"\n🎁 <b>【馬主同慶安慰獎】</b>\n其餘 <b>{len(consolation_owners)}</b> 位沒進前三名的馬主，人人皆獲得 <b>+{lucky_comfort_bonus}</b> chips 安慰獎！\n"

    if has_owner_bonus:
        bot.send_message(chat_id, owner_payout_text, parse_mode='HTML')
    
    current_race = None
    race_odds = {}
    if race_id in race_bets:
        del race_bets[race_id]

# ================== 核心：投注邏輯處理 ==================
@bot.message_handler(commands=['bet', 'place', 'lin'])
def place_bet(message):
    global current_race, race_id, race_odds, user_bet_count, user_actual_deduct, current_horses
    if current_race != "betting":
        bot.reply_to(message, "❌ 目前非投注時間！")
        return

    user_id = message.from_user.id
    
    if user_bet_count.get(user_id, 0) >= 1:
        bot.reply_to(message, "❌ 您本場已投注過！若想更改，請在開賽前輸入 /refund 退款後重新買一次。")
        return

    try:
        cmd = message.text.split()
        bet_type = cmd[0][1:]
        chips = get_chips(user_id)

        if bet_type in ["bet", "place"]:
            if len(cmd) < 3: raise ValueError
            horse_num = int(cmd[1])
            amount_str = cmd[2]
            if horse_num < 1 or horse_num > len(current_horses):
                bot.reply_to(message, f"❌ 馬匹號碼錯誤！請輸入 1-{len(current_horses)}")
                return
            horses = current_horses[horse_num-1]
            
        elif bet_type == "lin":
            if len(cmd) < 4: raise ValueError
            horse1 = int(cmd[1])
            horse2 = int(cmd[2])
            amount_str = cmd[3]
            if horse1 == horse2 or min(horse1, horse2) < 1 or max(horse1, horse2) > len(current_horses):
                bot.reply_to(message, f"❌ 馬匹號碼錯誤或重複！請輸入 1-{len(current_horses)} 且兩號碼不能相同")
                return
            horses = [current_horses[horse1-1], current_horses[horse2-1]]

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
        user_actual_deduct[user_id] = actual_deduct 

        if user_id not in race_bets[race_id]:
            race_bets[race_id][user_id] = []
        
        race_bets[race_id][user_id].append((bet_type, horses, bet_amount))
        user_bet_count[user_id] = 1

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

# ================== 核心：退款重投邏輯 ==================
@bot.message_handler(commands=['refund'])
def refund_bet(message):
    global current_race, race_id, race_bets, user_bet_count, user_refund_count, user_actual_deduct
    
    if current_race != "betting":
        bot.reply_to(message, "❌ 只能在比賽開跑前（倒數 60 秒內）申請退款！")
        return

    user_id = message.from_user.id

    if user_bet_count.get(user_id, 0) == 0:
        bot.reply_to(message, "❌ 您本局根本還沒有投注，無法退款！")
        return

    if user_refund_count.get(user_id, 0) >= 1:
        bot.reply_to(message, "❌ 抱歉，每場比賽每人最多隻能退款重新購買「一次」！")
        return

    refund_amount = user_actual_deduct.get(user_id, 0)
    update_chips(user_id, refund_amount) 

    if race_id in race_bets and user_id in race_bets[race_id]:
        del race_bets[race_id][user_id]
    
    user_bet_count[user_id] = 0
    user_refund_count[user_id] = 1
    if user_id in user_actual_deduct:
        del user_actual_deduct[user_id]

    bot.reply_to(message, f"✅ **退款成功！** 已歸還 {refund_amount} 金幣。\n您現在可以重新進行投注。", parse_mode='Markdown')

@bot.message_handler(commands=['balance'])
def balance(message):
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"💰 你的籌碼：**{chips}** chips", parse_mode='Markdown')

# ================== 啟動服務 ==================
print(f"🏇 {BOT_USERNAME} 已經完全升級成功並啟動監聽...")
bot.infinity_polling()
