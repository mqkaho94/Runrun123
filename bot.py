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

# 🏇 基礎 NPC 固定馬匹名單（前綴符號保留，用於無玩家買馬時的備用）
BASE_NPC_HORSES = [
    "⚡1.閃電", "🌪2.黑旋風", "⭐3.幸運星", "🔥4.火麒麟", 
    "💨5.疾風", "🏅6.黃金戰馬", "🌊7.海嘯", "🦅8.傲空"
]

# 🔢 名次對應的數字 Emoji 對照表（完賽定格用）
RANK_EMOJIS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
    5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"
}

# 💾 資料庫持久化路徑設定（建議在 VPS 上改為絕對路徑如 '/var/lib/tgbot/race.db'）
DB_FILE = 'race.db'
HORSE_PRICE = 3000  # 購買專屬馬匹所需籌碼

# ================== 💾 資料庫核心管理 ==================
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

def get_user_horse(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT has_horse, horse_name FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if row:
            return {"has_horse": row[0], "horse_name": row[1]}
        return {"has_horse": 0, "horse_name": None}

def get_owner_by_horse_name(horse_name):
    # 🌟 核心修復：精準剔除名字前方隨機產生的賽道號碼與裝飾符號
    clean_name = horse_name
    if "." in clean_name:
        clean_name = clean_name.split(".", 1)[1]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE horse_name=?", (clean_name,))
        row = c.fetchone()
        return row[0] if row else None

def get_all_registered_horses():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, horse_name FROM users WHERE has_horse=1 AND horse_name IS NOT NULL")
        return c.fetchall()

def get_all_horse_owners():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE has_horse=1")
        rows = c.fetchall()
        return [row[0] for row in rows]

# 追蹤與更新玩家的最新 Username，用於 /pay @Username 轉帳功能反查
def sync_username(user_id, username):
    if not username: return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET username=? WHERE user_id=?", (username.lower(), user_id))
        conn.commit()

init_db()

# ================== 賽事全域控制變數 ==================
current_race = None    
race_id = None
race_bets = {}   
race_odds = {}  
current_horses = []   

user_bet_count = {}     
user_refund_count = {}  
user_actual_deduct = {} 

# ================== 💸 核心功能：玩家轉帳轉讓系統 (全相容終極版) ==================
@bot.message_handler(commands=['pay'])
def pay_chips(message):
    try:
        from_user_id = message.from_user.id
        # 每次發送指令時自動在資料庫同步更新自己的 username
        sync_username(from_user_id, message.from_user.username)
        
        to_user_id = None
        to_username = "神祕玩家"
        pay_amount = 0

        cmd = message.text.split()
        if len(cmd) < 2:
            bot.reply_to(message, "❌ **格式錯誤**\n👉 回覆他人訊息轉帳：`/pay 金額`\n👉 直接標記名字轉帳：`/pay @玩家標記 金額`", parse_mode='Markdown')
            return

        # ---------------- 🚀 判斷方式 B：直接使用 @Username 標記轉帳 ----------------
        if len(cmd) >= 3 and cmd[1].startswith('@'):
            target_username = cmd[1].replace('@', '').strip().lower()
            raw_amount = cmd[2].strip()
            
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, username FROM users WHERE username=?", (target_username,))
                row = c.fetchone()
                if row:
                    to_user_id = row[0]
                    to_username = row[1] if row[1] else target_username
                else:
                    bot.reply_to(message, f"❌ **轉帳失敗**：找不到玩家 `@{target_username}`。\n\n💡 *提示*：目標玩家必須在群組輸入過機器人指令（如 /balance），系統才能成功建立他的名字檔案喔！", parse_mode='Markdown')
                    return

        # ---------------- 🚀 判斷方式 A：透過 Reply 回覆訊息轉帳 ----------------
        elif message.reply_to_message:
            if message.reply_to_message.from_user:
                to_user_id = message.reply_to_message.from_user.id
                to_username = message.reply_to_message.from_user.first_name
                # 同步接收方的 username
                sync_username(to_user_id, message.reply_to_message.from_user.username)
            else:
                bot.reply_to(message, "❌ **轉帳失敗**：無法讀取該訊息發送者隱私。請改用名字標記直接轉帳：\n`/pay @玩家名字 金額`", parse_mode='Markdown')
                return
            raw_amount = cmd[1].strip()
        
        else:
            bot.reply_to(message, "❌ **轉帳失敗！**\n\n👉 **請選擇以下一種方式轉帳：**\n1. **回覆真人** 的訊息，並輸入 `/pay 金額`\n2. 直接在群組輸入：`/pay @玩家標記 金額`", parse_mode='Markdown')
            return

        # ---------------- ⚙️ 統一解析金額與安全檢查 ----------------
        if '@' in raw_amount:
            raw_amount = raw_amount.split('@')[0]

        try:
            pay_amount = int(raw_amount)
            if pay_amount <= 0:
                bot.reply_to(message, "❌ 轉讓金額必須大於 0！")
                return
        except ValueError:
            bot.reply_to(message, "❌ 金額格式不正確，請輸入整數數字！\n例如：`/pay 1000`")
            return

        if from_user_id == to_user_id:
            bot.reply_to(message, "❌ 喂！不能把籌碼轉讓給自己啦！")
            return

        if message.reply_to_message and message.reply_to_message.from_user.is_bot:
            bot.reply_to(message, "❌ 系統無法接收您的個人籌碼轉讓喔！")
            return

        # 檢查轉出方餘額
        from_user_chips = get_chips(from_user_id) 
        if from_user_chips < pay_amount:
            bot.reply_to(message, f"❌ 您的籌碼不足！您目前只有 **{from_user_chips}** chips，無法轉出 {pay_amount}。")
            return

        # 執行轉帳
        get_chips(to_user_id) 
        update_chips(from_user_id, -pay_amount) 
        update_chips(to_user_id, pay_amount)   

        from_username = message.from_user.first_name if message.from_user.first_name else "神祕玩家"

        success_text = (
            f"💸 **【籌碼轉讓成功】** 💸\n"
            f"🤝 轉出人：<a href='tg://user?id={from_user_id}'>{from_username}</a>\n"
            f"🎁 接收人：<a href='tg://user?id={to_user_id}'>{to_username}</a>\n"
            f"💰 轉讓金額：<b>{pay_amount}</b> chips\n\n"
            f"祝兩位合作愉快，繼續在賽馬場大發利市！ 🏇"
        )
        bot.send_message(message.chat.id, success_text, parse_mode='HTML')

    except Exception as e:
        print(f"⚠️ [PAY_ERROR] 原因: {str(e)}")
        bot.reply_to(message, "❌ 轉帳系統發生未知錯誤。")

# ================== 🎰 核心：開局全自動隨機號碼抽籤機制 ==================
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
    
    # 同步開賽者的名字
    sync_username(message.from_user.id, message.from_user.username)
    
    # 🎲 1. 撈出全伺服器所有已註冊的玩家馬匹
    all_registered = get_all_registered_horses()
    final_8_horses = []  # 存入格式：(user_id, 馬名, 類型前綴)
    
    if len(all_registered) == 0:
        # 備用方案：如果全服都還沒人買馬，直接拿 NPC 清單（去掉原本固定數字）
        for npc in BASE_NPC_HORSES:
            clean_npc = npc.split('.', 1)[1] if '.' in npc else npc
            final_8_horses.append((None, clean_npc, npc[0] if not npc[0].isdigit() else "🐎"))
    else:
        # 🌟 第一重打亂：隨機抽出最多 8 匹玩家專屬馬
        random.shuffle(all_registered)
        selected_players = all_registered[:8]
        
        for uid, h_name in selected_players:
            final_8_horses.append((uid, h_name, "👑"))
            
        # 如果玩家馬不足 8 匹，剩下的位置用 NPC 補足
        if len(final_8_horses) < 8:
            shortage = 8 - len(final_8_horses)
            available_npcs = BASE_NPC_HORSES.copy()
            random.shuffle(available_npcs)
            
            for i in range(shortage):
                npc_horse = available_npcs[i]
                clean_npc_name = npc_horse.split('.', 1)[1] if '.' in npc_horse else npc_horse
                icon = npc_horse[0] if not npc_horse[0].isdigit() else "🐎"
                final_8_horses.append((None, clean_npc_name, icon))

    # 🌟🌟 第二重打亂（核心）：將這最終的 8 匹馬進行全體隨機大洗牌！號碼全隨機！ 🌟🌟
    random.shuffle(final_8_horses)

    # 🎲 2. 重新編排 1 至 8 號賽道
    chosen_horses_pool = []
    for idx, (uid, h_name, icon) in enumerate(final_8_horses):
        lane_num = idx + 1
        chosen_horses_pool.append(f"{icon}{lane_num}.{h_name}")

    current_horses = chosen_horses_pool

    # 🎲 3. 產生隨機賠率並建立排位公示
    text = f"🏇 **第 {race_id} 場賽事開始！** 60秒後開跑 🏁\n\n"
    text += "【本局參賽馬匹 ＆ 隨機排位賠率】\n"
    for h in current_horses:
        win_odds = round(random.uniform(2.5, 15.0), 1)
        place_odds = round(win_odds / 2, 1)
        race_odds[h] = win_odds  
        text += f"{h}  ➡️  獨贏: *{win_odds}x* | 位置: *{place_odds}x*\n"

    text += "\n" + "—" * 20 + "\n"
    text += "💰 **【下注範例】**\n"
    text += "👉 獨贏：`/bet 1 100`\n"
    text += "👉 位置：`/place 3 100`\n"
    text += "👉 連贏：`/lin 1 2 100`\n"
    text += "—" * 20 + "\n"
    text += f"💡 **本局看點**：玩家愛駒已全隨機排位！馬主免投注自動入場抽籤分紅！\n"
    
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(60, lambda: run_race(message.chat.id)).start()

# ================== 核心：動態模擬賽馬直播 ==================
def run_race(chat_id):
    global current_race, race_id, race_odds, race_bets, current_horses
    
    if current_race != "betting": return
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
                current_distance[h] = elapsed * speeds[h] + random.uniform(-0.2, 0.2)
                if current_distance[h] < 0: current_distance[h] = 0
                if current_distance[h] >= TOTAL_DISTANCE:
                    current_distance[h] = TOTAL_DISTANCE
                    if h not in finished_horses: finished_horses.append(h)
                        
        if now - last_refresh_time >= 2.0 or len(finished_horses) >= 3:
            last_refresh_time = now
            dynamic_text = f"🏇 **第 {race_id} 場賽事 現場直播** 🏁\n" + "‾" * 25 + "\n"
            for h in current_horses:
                progress = int((current_distance[h] / TOTAL_DISTANCE) * DISPLAY_LENGTH)
                progress = min(max(progress, 0), DISPLAY_LENGTH)
                track_str = "🏁 " + "_" * (DISPLAY_LENGTH - progress) + "🐎" + "_" * progress
                status = ""
                if h in finished_horses:
                    r = finished_horses.index(h) + 1
                    status = " 🥇【冠軍】" if r==1 else " 🥈【亞軍】" if r==2 else " 🥉【季軍】"
                dynamic_text += f"{h}{status}\n`{track_str}`\n\n"
            try:
                bot.edit_message_text(dynamic_text, chat_id, race_msg.message_id, parse_mode='Markdown')
            except: pass

    remaining = [h for h in current_horses if h not in finished_horses]
    remaining.sort(key=lambda h: current_distance[h], reverse=True)
    all_ranks = finished_horses + remaining
    
    # 定格完賽畫面
    final_text = f"🏇 **第 {race_id} 場賽事 直播結束（定格名次）** 🏁\n" + "‾" * 25 + "\n"
    for h in current_horses:
        final_rank = all_ranks.index(h) + 1
        rank_emoji = RANK_EMOJIS.get(final_rank, "🐎") 
        progress = int((current_distance[h] / TOTAL_DISTANCE) * DISPLAY_LENGTH)
        progress = min(max(progress, 0), DISPLAY_LENGTH)
        track_str = "🏁 " + "_" * (DISPLAY_LENGTH - progress) + rank_emoji + "_" * progress
        status = " 🥇【冠軍】" if final_rank==1 else " 🥈【亞軍】" if final_rank==2 else " 🥉【季軍】" if final_rank==3 else ""
        final_text += f"{h}{status}\n`{track_str}`\n\n"
    try:
        bot.edit_message_text(final_text, chat_id, race_msg.message_id, parse_mode='Markdown')
    except: pass
                
    winner, second = all_ranks[0], all_ranks[1]
    result = "🏆 **最終賽果名次結果** 🏆\n\n"
    for i, h in enumerate(all_ranks, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else "🏁"
        result += f"{medal} 第 {i} 名：{h} (獨贏 {race_odds[h]}x)\n"
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    # 💰 常規投注派彩
    if race_id in race_bets:
        payout_message = "🎉 **派彩結果** 🎉\n\n"
        has_winner = False
        for uid, bets in race_bets[race_id].items():
            win_amount = 0
            for b_type, horses, amt in bets:
                if b_type == "bet" and horses == winner:
                    win_amount += int(amt * race_odds[winner])
                elif b_type == "place" and horses in all_ranks[:3]:
                    win_amount += int(amt * (race_odds[horses] / 2))
                elif b_type == "lin" and isinstance(horses, list) and set(horses) == set([winner, second]):
                    win_amount += int(amt * (race_odds[winner] * race_odds[second]))
            if win_amount > 0:
                update_chips(uid, win_amount)
                payout_message += f"✅ 玩家 <a href='tg://user?id={uid}'>{uid}</a> 贏得 <b>{win_amount}</b> chips\n"
                has_winner = True
        if has_winner: bot.send_message(chat_id, payout_message, parse_mode='HTML')
        else: bot.send_message(chat_id, "壓注全空！本局沒有人中獎 💸")

    # 👑 馬主大獎與安慰獎分紅系統
    owner_text = "✨ <b>【本局馬主專利分紅】</b> ✨\n"
    big_winners, has_owner_bonus = [], False
    for rank_idx in range(3):
        target_horse = all_ranks[rank_idx]
        if "👑" in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id:
                rank_num = rank_idx + 1
                bonus_chips = random.randint(200000, 300000) if rank_num==1 else random.randint(50000, 100000) if rank_num==2 else random.randint(10000, 30000)
                t_title = "🥇 冠軍" if rank_num==1 else "🥈 亞軍" if rank_num==2 else "🥉 季軍"
                update_chips(owner_id, bonus_chips)
                big_winners.append(owner_id)
                owner_text += f"恭喜專屬馬 <b>{target_horse}</b> 榮獲{t_title}！\n馬主 <a href='tg://user?id={owner_id}'>{owner_id}</a> 獲得隨機大獎 <b>+{bonus_chips}</b> chips 💰\n"
                has_owner_bonus = True

    if has_owner_bonus:
        all_owners = get_all_horse_owners()
        consolation_owners = [oid for oid in all_owners if oid not in big_winners]
        if consolation_owners:
            lucky_comfort_bonus = random.randint(3000, 5000)
            for c_owner in consolation_owners: update_chips(c_owner, lucky_comfort_bonus)
            owner_text += f"\n🎁 <b>【馬主同慶安慰獎】</b>\n其餘 <b>{len(consolation_owners)}</b> 位馬主獲得 <b>+{lucky_comfort_bonus}</b> chips 安慰獎！\n"
        bot.send_message(chat_id, owner_text, parse_mode='HTML')
    
    current_race, race_odds = None, {}
    if race_id in race_bets: del race_bets[race_id]

# ================== 核心：投注與退款邏輯處理 ==================
@bot.message_handler(commands=['bet', 'place', 'lin'])
def place_bet(message):
    global current_race, race_id, race_odds, user_bet_count, user_actual_deduct, current_horses
    if current_race != "betting":
        bot.reply_to(message, "❌ 目前非投注時間！")
        return

    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
    
    if user_bet_count.get(user_id, 0) >= 1:
        bot.reply_to(message, "❌ 您本場已投注過！更改請先輸入 /refund 退款。")
        return

    try:
        cmd = message.text.split()
        bet_type = cmd[0][1:]
        chips = get_chips(user_id)

        if bet_type in ["bet", "place"]:
            if len(cmd) < 3: raise ValueError
            horse_num = int(cmd[1])
            amount_str = cmd[2]
            if horse_num < 1 or horse_num > len(current_horses): return
            horses = current_horses[horse_num-1]
        elif bet_type == "lin":
            if len(cmd) < 4: raise ValueError
            h1, h2 = int(cmd[1]), int(cmd[2])
            amount_str = cmd[3]
            if h1 == h2 or min(h1, h2) < 1 or max(h1, h2) > len(current_horses): return
            horses = [current_horses[h1-1], current_horses[h2-1]]

        bet_amount = int(chips * int(amount_str.replace("%", "")) / 100) if "%" in amount_str else int(amount_str)
        if bet_amount <= 0: return

        credit = 100
        actual_deduct = max(0, bet_amount - credit) if bet_amount > credit else 0
        if actual_deduct > chips: return

        update_chips(user_id, -actual_deduct)
        user_actual_deduct[user_id] = actual_deduct 

        if user_id not in race_bets[race_id]: race_bets[race_id][user_id] = []
        race_bets[race_id][user_id].append((bet_type, horses, bet_amount))
        user_bet_count[user_id] = 1

        bot.reply_to(message, f"✅ 投注成功！")
    except: pass

@bot.message_handler(commands=['refund'])
def refund_bet(message):
    global current_race, race_id, race_bets, user_bet_count, user_refund_count, user_actual_deduct
    if current_race != "betting": return
    user_id = message.from_user.id
    if user_bet_count.get(user_id, 0) == 0 or user_refund_count.get(user_id, 0) >= 1: return
    refund_amount = user_actual_deduct.get(user_id, 0)
    update_chips(user_id, refund_amount) 
    if race_id in race_bets and user_id in race_bets[race_id]: del race_bets[race_id][user_id]
    user_bet_count[user_id] = 0
    user_refund_count[user_id] = 1
    bot.reply_to(message, f"✅ 退款成功！")

# ================== 🤖 其他玩家/私訊專屬功能指令 ==================
@bot.message_handler(commands=['buy'])
def buy_horse(message):
    if message.chat.type != "private":
        bot.reply_to(message, f"❌ 為了防洗版，此功能限私訊使用！請點擊： {BOT_USERNAME}")
        return
    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
    chips = get_chips(user_id)
    horse_info = get_user_horse(user_id)

    if horse_info["has_horse"] == 1:
        bot.reply_to(message, f"🐴 您已擁有一匹愛駒：**{horse_info['horse_name']}**\n修改名字請輸入：`/rename 新的馬名`", parse_mode='Markdown')
        return

    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2:
        bot.reply_to(message, f"🛒 **【專屬馬匹拍賣所】**\n\n💰 售價：**{HORSE_PRICE}** chips\n💰 你的餘額：**{chips}** chips\n👉 **購買請輸入**：`/buy 你的馬名` (限1-4個字)", parse_mode='Markdown')
        return

    h_name = cmd[1].strip()
    if len(h_name) < 1 or len(h_name) > 4: return
    if chips < HORSE_PRICE: return

    update_chips(user_id, -HORSE_PRICE)
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET has_horse=1, horse_name=? WHERE user_id=?", (h_name, user_id))
        conn.commit()
    bot.reply_to(message, f"🎉 專屬愛駒 **「{h_name}」** 登記成功！每局開賽自動隨機分配號碼入場！")

@bot.message_handler(commands=['rename'])
def rename_horse(message):
    if message.chat.type != "private": return
    user_id = message.from_user.id
    horse_info = get_user_horse(user_id)
    if horse_info["has_horse"] == 0: return
    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2: return
    new_name = cmd[1].strip()
    if len(new_name) < 1 or len(new_name) > 4: return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET horse_name=? WHERE user_id=?", (new_name, user_id))
        conn.commit()
    bot.reply_to(message, f"✨ 您的愛駒已成功更名為：**「{new_name}」** 🏇")

@bot.message_handler(commands=['balance'])
def balance(message):
    sync_username(message.from_user.id, message.from_user.username)
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"💰 你的籌碼：**{chips}** chips", parse_mode='Markdown')

@bot.message_handler(commands=['daily'])
def daily(message):
    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
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

@bot.message_handler(commands=['start'])
def start(message):
    sync_username(message.from_user.id, message.from_user.username)
    bot.reply_to(message, f"🏇 **虛擬賽馬 Bot 已就緒**\n輸入 /help 查看完整指令列表。")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = f"""🏇 **指令列表**
/startrace - 開始新賽事 (馬主全自動隨機號碼抽籤補位)
/balance   - 查詢目前籌碼
/refund    - 開賽前退款當局投注
/pay - <b>【回覆訊息 或 標記@Username】</b>轉讓籌碼
/buy       - <b>【私訊】</b>購買專屬馬匹 ({HORSE_PRICE} chips)
/rename    - <b>【私訊】</b>自訂愛駒修改名字

【投注方式】/bet 號碼 金額 | /place 號碼 金額 | /lin 號碼1 號碼2 金額
"""
    bot.reply_to(message, text, parse_mode='HTML')

# ================== 啟動服務 ==================
print(f"🏇 {BOT_USERNAME} 已經完全整合升級，24/7 模式準備完畢！啟動監聽中...")
bot.infinity_polling()
