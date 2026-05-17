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

# 🏇 基礎 1 至 8 號 NPC 固定馬匹名單（只有在無人買馬時作為備用）
BASE_NPC_HORSES = [
    "⚡1.閃電", "🌪2.黑旋風", "⭐3.幸運星", "🔥4.火麒麟", 
    "💨5.疾風", "🏅6.黃金戰馬", "🌊7.海嘯", "🦅8.傲空"
]

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
    if "." in horse_name:
        clean_name = horse_name.split(".", 1)[1]
    else:
        clean_name = horse_name
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE horse_name=?", (clean_name,))
        row = c.fetchone()
        return row[0] if row else None

# 獲取全伺服器所有「已經購買專屬馬」的馬主資料清單 [(user_id, horse_name), ...]
def get_all_registered_horses():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, horse_name FROM users WHERE has_horse=1 AND horse_name IS NOT NULL")
        return c.fetchall()

# 獲取全伺服器所有擁有專屬馬的馬主 user_id 清單 (用於分紅發放)
def get_all_horse_owners():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE has_horse=1")
        rows = c.fetchall()
        return [row[0] for row in rows]

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
            f"擁有專屬馬後，你不需要投注，愛駒每局都會自動獲得隨機抽籤上場的資格！\n"
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

    bot.reply_to(message, f"🎉 **恭喜購馬成功！**\n籌碼已扣除 {HORSE_PRICE}。\n您的愛駒 **「{horse_name}」** 已成功登記！今後每局賽事牠都會自動在後台參與抽籤補位！")

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

/startrace - 開始新賽事 (全體擁有馬匹之馬主全自動隨機抽籤補位上場)
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

# ================== 🎰 核心：開局全自動抽籤補位機制 ==================
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
    
    # 🎲 1. 獲取全伺服器所有已註冊的馬匹
    all_registered = get_all_registered_horses() # 格式: [(uid, '馬名'), ...]
    
    chosen_horses_pool = []
    
    if len(all_registered) == 0:
        # 備用方案：若全伺服器都還沒有玩家買馬，則完全使用原本的 NPC 名單
        chosen_horses_pool = BASE_NPC_HORSES.copy()
    else:
        # 如果有玩家馬匹，隨機打亂
        random.shuffle(all_registered)
        
        # 抽取最多 8 匹玩家馬
        selected_players = all_registered[:8]
        
        # 組裝成帶皇冠的馬名
        for idx, (uid, h_name) in enumerate(selected_players):
            chosen_horses_pool.append(f"👑{idx + 1}.{h_name}")
            
        # 如果玩家買的馬不足 8 匹，剩下的位置用基礎 NPC 填補
        if len(chosen_horses_pool) < 8:
            shortage = 8 - len(chosen_horses_pool)
            npc_backup = BASE_NPC_HORSES[len(chosen_horses_pool):8]
            for idx, npc_horse in enumerate(npc_backup):
                # 重新校正號碼前綴
                actual_lane = len(chosen_horses_pool) + 1
                clean_npc_name = npc_horse.split('.', 1)[1] if '.' in npc_horse else npc_horse
                # 保持原 NPC 的特殊符號
                icon = npc_horse[0] if not npc_horse[0].isdigit() else "🐎"
                chosen_horses_pool.append(f"{icon}{actual_lane}.{clean_npc_name}")

    # 寫入全域變數
    current_horses = chosen_horses_pool

    # 🎲 2. 產生隨機賠率並建立排位公示
    text = f"🏇 **第 {race_id} 場賽事開始！** 60秒後開跑 🏁\n\n"
    text += "【本局參賽馬匹 ＆ 賠率公示】\n"
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
    
    text += f"\n💡 馬主免投注！每局開局自動從全服抽籤挑選最多 8 匹直接排位上場！\n"
    
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(60, lambda: run_race(message.chat.id)).start()

# ================== 核心：動態模擬賽馬 ==================
def run_race(chat_id):
    global current_race, race_id, race_odds, race_bets, current_horses
    
    if current_race != "betting":
        return

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
        if "👑" in target_horse: # 只要名稱帶皇冠的馬進前三，即代表有專屬馬得獎
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

# ================== 💸 核心功能：玩家轉帳轉讓系統 💸 ==================
@bot.message_handler(commands=['pay'])
def pay_chips(message):
    # 1. 檢查是否為回覆訊息
    if not message.reply_to_message:
        bot.reply_to(message, "❌ **轉帳失敗！**\n請**回覆（Reply）**你想轉讓籌碼的那位玩家的訊息，並輸入 `/pay 金額`", parse_mode='Markdown')
        return

    from_user_id = message.from_user.id
    to_user_id = message.reply_to_message.from_user.id
    
    # 2. 安全檢查：防止轉帳給自己
    if from_user_id == to_user_id:
        bot.reply_to(message, "❌ 喂！不能把籌碼轉讓給自己啦！")
        return

    # 3. 安全檢查：防止轉帳給機器人
    if message.reply_to_message.from_user.is_bot:
        bot.reply_to(message, "❌ 系統無法接收您的個人籌碼轉讓喔！")
        return

    # 4. 解析輸入金額
    cmd = message.text.split()
    if len(cmd) < 2:
        bot.reply_to(message, "❌ 請輸入你想轉讓的金額！\n例如回覆別人：`/pay 500`", parse_mode='Markdown')
        return

    try:
        pay_amount = int(cmd[1])
        if pay_amount <= 0:
            bot.reply_to(message, "❌ 轉讓金額必須大於 0！")
            return
    except ValueError:
        bot.reply_to(message, "❌ 金額格式不正確，請輸入整數數字！\n例如：`/pay 1000`")
        return

    # 5. 餘額檢查：檢查轉出方籌碼是否足夠
    from_user_chips = get_chips(from_user_id) # 呼叫你原本的 get_chips 函數
    if from_user_chips < pay_amount:
        bot.reply_to(message, f"❌ 您的籌碼不足！您目前只有 **{from_user_chips}** chips，無法轉出 {pay_amount}。")
        return

    # 6. 確保接收方在資料庫中存在（若無則 get_chips 會自動初始化）
    get_chips(to_user_id)

    # 7. 執行資料庫變更（呼叫你原本的 update_chips 函數）
    update_chips(from_user_id, -pay_amount) # 扣錢
    update_chips(to_user_id, pay_amount)   # 加錢

    # 8. 獲取雙方暱稱並發送成功公告
    from_username = message.from_user.first_name
    to_username = message.reply_to_message.from_user.first_name

    success_text = (
        f"💸 **【籌碼轉讓成功】** 💸\n"
        f"🤝 轉出人：<a href='tg://user?id={from_user_id}'>{from_username}</a>\n"
        f"🎁 接收人：<a href='tg://user?id={to_user_id}'>{to_username}</a>\n"
        f"💰 轉讓金額：<b>{pay_amount}</b> chips\n\n"
        f"祝兩位合作愉快，繼續在賽馬場大發利市！ 🏇"
    )
    bot.send_message(message.chat.id, success_text, parse_mode='HTML')

# ================== 啟動服務 ==================
print(f"🏇 {BOT_USERNAME} 已經完全升級成功並啟動監聽...")
bot.infinity_polling()
