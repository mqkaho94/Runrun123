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

# 🏇 基礎 NPC 固定馬匹名單
BASE_NPC_HORSES = [
    "⚡1.奧雲狗狗", "🌪2.黑旋風", "⭐3.戰槌巨人", "🔥4.火麒麟", 
    "💨5.疾風", "🏅6.黃金戰馬", "🌊7.海嘯", "🦅8.傲空"
]

# 🔢 名次對應的數字 Emoji 對照表
RANK_EMOJIS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
    5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"
}

# 💾 資料庫持久化路徑設定 (⚠️ 指向 Railway 掛載的硬碟路徑)
DB_FILE = '/data/race.db'
HORSE_PRICE = 3000  # 購買專屬馬匹所需金幣

# ================== 💾 資料庫核心管理 ==================
def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
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

# ================== 💸 核心功能：玩家轉帳系統 ==================
@bot.message_handler(commands=['pay'])
def pay_chips(message):
    try:
        from_user_id = message.from_user.id
        sync_username(from_user_id, message.from_user.username)
        
        to_user_id = None
        to_username = "神祕玩家"
        pay_amount = 0

        text_clean = message.text
        if f"{BOT_USERNAME}" in text_clean:
            text_clean = text_clean.replace(f"{BOT_USERNAME}", "")
        elif f"@run1234567bot" in text_clean.lower():
            text_clean = text_clean.lower().replace("@run1234567bot", "")

        cmd = text_clean.split()
        if len(cmd) < 2:
            bot.reply_to(message, "❌ **格式錯誤**\n👉 回覆他人訊息轉帳：`/pay 金額`\n👉 直接標記名字轉帳：`/pay @玩家標記 金額`", parse_mode='Markdown')
            return

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

        elif message.reply_to_message:
            if message.reply_to_message.from_user:
                to_user_id = message.reply_to_message.from_user.id
                to_username = message.reply_to_message.from_user.first_name
                sync_username(to_user_id, message.reply_to_message.from_user.username)
            else:
                bot.reply_to(message, "❌ **轉帳失敗**：無法讀取該訊息發送者隱私。請改用名字標記直接轉帳：\n`/pay @玩家名字 金額`", parse_mode='Markdown')
                return
            raw_amount = cmd[1].strip()
        
        else:
            bot.reply_to(message, "❌ **轉帳失敗！**\n\n👉 **請選擇以下一種方式轉帳：**\n1. **回覆真人** 的訊息，並輸入 `/pay 金額`\n2. 直接在群組輸入：`/pay @玩家標記 金額`", parse_mode='Markdown')
            return

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
            bot.reply_to(message, "❌ 喂！不能把金幣轉讓給自己啦！")
            return

        if message.reply_to_message and message.reply_to_message.from_user.is_bot:
            bot.reply_to(message, "❌ 系統無法接收您的個人金幣轉讓喔！")
            return

        from_user_chips = get_chips(from_user_id) 
        if from_user_chips < pay_amount:
            bot.reply_to(message, f"❌ 您的金幣不足！您目前只有 **{from_user_chips:,}** 金幣，無法轉出 {pay_amount:,}。")
            return

        get_chips(to_user_id) 
        update_chips(from_user_id, -pay_amount) 
        update_chips(to_user_id, pay_amount)   

        from_username = message.from_user.first_name if message.from_user.first_name else "神祕玩家"

        success_text = (
            f"💸 **【金幣轉讓成功】** 💸\n"
            f"🤝 轉出人：<a href='tg://user?id={from_user_id}'>{from_username}</a>\n"
            f"🎁 接收人：<a href='tg://user?id={to_user_id}'>{to_username}</a>\n"
            f"💰 轉讓金額：<b>{pay_amount:,}</b> 金幣\n\n"
            f"祝兩位合作愉快，繼續在賽馬場大發利市！ 🏇"
        )
        bot.send_message(message.chat.id, success_text, parse_mode='HTML')

    except Exception as e:
        print(f"⚠️ [PAY_ERROR] 原因: {str(e)}")
        bot.reply_to(message, "❌ 轉帳系統發生未知錯誤。")

# ================== 🎰 核心：開局與排位 ==================
@bot.message_handler(commands=['startrun'])
def startrun(message):
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
    
    sync_username(message.from_user.id, message.from_user.username)
    
    all_registered = get_all_registered_horses()
    final_8_horses = []  
    
    if len(all_registered) == 0:
        for npc in BASE_NPC_HORSES:
            clean_npc = npc.split('.', 1)[1] if '.' in npc else npc
            final_8_horses.append((None, clean_npc, npc[0] if not npc[0].isdigit() else "🐎"))
    else:
        random.shuffle(all_registered)
        selected_players = all_registered[:8]
        
        for uid, h_name in selected_players:
            final_8_horses.append((uid, h_name, "👑"))
            
        if len(final_8_horses) < 8:
            shortage = 8 - len(final_8_horses)
            available_npcs = BASE_NPC_HORSES.copy()
            random.shuffle(available_npcs)
            
            for i in range(shortage):
                npc_horse = available_npcs[i]
                clean_npc_name = npc_horse.split('.', 1)[1] if '.' in npc_horse else npc_horse
                icon = npc_horse[0] if not npc_horse[0].isdigit() else "🐎"
                final_8_horses.append((None, clean_npc_name, icon))

    random.shuffle(final_8_horses)

    chosen_horses_pool = []
    for idx, (uid, h_name, icon) in enumerate(final_8_horses):
        lane_num = idx + 1
        chosen_horses_pool.append(f"{icon}{lane_num}.{h_name}")

    current_horses = chosen_horses_pool

    text = f"🏇 **第 {race_id} 場賽事開始！** 60秒後開跑 🏁\n\n"
    text += "【本局參賽馬匹 ＆ 隨機排位賠率】\n"
    for h in current_horses:
        win_odds = round(random.uniform(2.5, 15.0), 1)
        place_odds = round(win_odds / 2, 1)
        race_odds[h] = win_odds  
        text += f"{h}  ➡️  獨贏: *{win_odds}x* | 位置: *{place_odds}x*\n"

    text += "\n" + "—" * 20 + "\n"
    text += "💰 **【下注範例】**\n"
    text += "👉 獨贏：`/win 1 100`\n"
    text += "👉 位置：`/pla 3 100`\n"
    text += "👉 連贏：`/ww 1 2 100`\n"
    text += "—" * 20 + "\n"
    text += f"💡 **玩家福利**：本局下注享有 **100 金幣免自付信用額度**！下注 100 內完全不扣自己錢包！\n"
    
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
    
    if race_id in race_bets:
        payout_message = "🎉 **派彩結果** 🎉\n\n"
        has_winner = False
        for uid, bets in race_bets[race_id].items():
            win_amount = 0
            for b_type, horses, amt in bets:
                if b_type == "win" and horses == winner:
                    win_amount += int(amt * race_odds[winner])
                elif b_type == "pla" and horses in all_ranks[:3]:
                    win_amount += int(amt * (race_odds[horses] / 2))
                elif b_type == "ww" and isinstance(horses, list) and set(horses) == set([winner, second]):
                    win_amount += int(amt * (race_odds[winner] * race_odds[second]))
            if win_amount > 0:
                update_chips(uid, win_amount)
                payout_message += f"✅ 玩家 <a href='tg://user?id={uid}'>{uid}</a> 贏得 <b>{win_amount:,}</b> 金幣\n"
                has_winner = True
        if has_winner: bot.send_message(chat_id, payout_message, parse_mode='HTML')
        else: bot.send_message(chat_id, "壓注全空！本局沒有人中獎 💸")

    # ================== 🐴 馬主分紅與安慰獎邏輯 ==================
    owner_text = "✨ <b>【本局馬主專利分紅】</b> ✨\n"
    has_owner_bonus = False
    consolation_owners = [] 

    # 1. 前三名大獎分配
    for rank_idx in range(min(3, len(all_ranks))):
        target_horse = all_ranks[rank_idx]
        if "👑" in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id:
                owner_id = int(owner_id)
                rank_num = rank_idx + 1
                
                try:
                    member = bot.get_chat_member(chat_id, owner_id)
                    owner_name = member.user.first_name
                except Exception:
                    owner_name = f"馬主({owner_id})"
                
                if rank_num == 1:
                    bonus_chips = random.randint(10000, 20000)
                    t_title = "🥇 冠軍"
                elif rank_num == 2:
                    bonus_chips = random.randint(6000, 7500)
                    t_title = "🥈 亞軍"
                else:
                    bonus_chips = random.randint(1000, 2000)
                    t_title = "🥉 季軍"
                
                update_chips(owner_id, bonus_chips)
                owner_text += f"恭喜專屬馬 <b>{target_horse}</b> 榮獲{t_title}！\n馬主 <a href='tg://user?id={owner_id}'>{owner_name}</a> 獲得分紅大獎 <b>+{bonus_chips:,}</b> 金幣 💰\n"
                has_owner_bonus = True

    # 2. 搜集第 4~8 名的專屬馬主
    for rank_idx in range(3, len(all_ranks)):
        target_horse = all_ranks[rank_idx]
        if "👑" in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id:
                consolation_owners.append(int(owner_id))

    # 3. 發放 300 - 500 金幣的落敗安慰獎
    if consolation_owners:
        consolation_mentions = []
        
        for c_owner in consolation_owners:
            lucky_comfort_bonus = random.randint(300, 500)
            update_chips(c_owner, lucky_comfort_bonus)
            try:
                member = bot.get_chat_member(chat_id, c_owner)
                c_name = member.user.first_name
            except Exception:
                c_name = f"馬主({c_owner})"
            
            consolation_mentions.append(f"<a href='tg://user?id={c_owner}'>{c_name}</a> (<b>+{lucky_comfort_bonus:,}</b>)")
            
        owner_text += f"\n🎁 <b>【馬主同慶安慰獎】</b>\n本局上場遺憾落敗（第4-8名）的馬主： " + "、".join(consolation_mentions) + f" 獲得安慰分紅！\n"
        has_owner_bonus = True

    if has_owner_bonus:
        bot.send_message(chat_id, owner_text, parse_mode='HTML')
    
    current_race, race_odds = None, {}
    if race_id in race_bets: del race_bets[race_id]

# ================== 核心：投注與退款邏輯 ==================
@bot.message_handler(commands=['win', 'pla', 'ww'])
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

    error_help_text = (
        "❌ **投注格式錯誤！**\n\n"
        "💡 **請參考以下正確的下注範例：**\n"
        "👉 **獨贏** (押第一名)：`/win [馬匹編號] [金額]`\n"
        "範例：`/win 1 200`\n\n"
        "👉 **位置** (押前三名)：`/pla [馬匹編號] [金額]`\n"
        "範例：`/pla 3 500`\n\n"
        "👉 **連贏** (押前兩名，不限順序)：`/ww [馬匹A] [馬匹B] [金額]`\n"
        "範例：`/ww 1 2 300`"
    )

    try:
        text_clean = message.text
        if f"{BOT_USERNAME}" in text_clean:
            text_clean = text_clean.replace(f"{BOT_USERNAME}", "")
        elif f"@run1234567bot" in text_clean.lower():
            text_clean = text_clean.lower().replace("@run1234567bot", "")

        cmd = text_clean.split()
        bet_type = cmd[0][1:]  # 將會取得 win, pla, 或是 ww
        chips = get_chips(user_id)

        if bet_type in ["win", "pla"]:
            if len(cmd) < 3: 
                bot.reply_to(message, error_help_text, parse_mode='Markdown')
                return
            try:
                horse_num = int(cmd[1])
                amount_str = cmd[2]
            except ValueError:
                bot.reply_to(message, error_help_text, parse_mode='Markdown')
                return
                
            if horse_num < 1 or horse_num > len(current_horses): 
                bot.reply_to(message, f"❌ 投注失敗：找不到該馬匹編號！目前只有 1 到 {len(current_horses)} 號馬。", parse_mode='Markdown')
                return
            selected_horse_full = current_horses[horse_num-1]
            
        elif bet_type == "ww":
            if len(cmd) < 4: 
                bot.reply_to(message, error_help_text, parse_mode='Markdown')
                return
            try:
                h1, h2 = int(cmd[1]), int(cmd[2])
                amount_str = cmd[3]
            except ValueError:
                bot.reply_to(message, error_help_text, parse_mode='Markdown')
                return
                
            if h1 == h2:
                bot.reply_to(message, "❌ 投注失敗：連贏的兩匹馬不能是同一個編號！", parse_mode='Markdown')
                return
            if min(h1, h2) < 1 or max(h1, h2) > len(current_horses): 
                bot.reply_to(message, f"❌ 投注失敗：找不到對應的馬匹編號！目前只有 1 到 {len(current_horses)} 號馬。", parse_mode='Markdown')
                return
            selected_horse_full = [current_horses[h1-1], current_horses[h2-1]]

        try:
            bet_amount = int(chips * int(amount_str.replace("%", "")) / 100) if "%" in amount_str else int(amount_str)
        except ValueError:
            bot.reply_to(message, error_help_text, parse_mode='Markdown')
            return
            
        if bet_amount <= 0: 
            bot.reply_to(message, "❌ 投注失敗：下注金額必須大於 0 金幣！", parse_mode='Markdown')
            return

        credit = 100
        actual_deduct = max(0, bet_amount - credit) if bet_amount > credit else 0
        if actual_deduct > chips:
            bot.reply_to(message, f"❌ 餘額不足！扣除 100 信用額後，您還需要 {actual_deduct:,} 金幣，但您目前只有 {chips:,}。", parse_mode='Markdown')
            return

        update_chips(user_id, -actual_deduct)
        user_actual_deduct[user_id] = actual_deduct 
        user_bet_count[user_id] = 1

        if user_id not in race_bets[race_id]: race_bets[race_id][user_id] = []
        race_bets[race_id][user_id].append((bet_type, selected_horse_full, bet_amount))

        type_title = "獨贏" if bet_type == "win" else "位置" if bet_type == "pla" else "連贏"
        
        if bet_type == "ww":
            h1_clean = selected_horse_full[0].split('.', 1)[1] if '.' in selected_horse_full[0] else selected_horse_full[0]
            h2_clean = selected_horse_full[1].split('.', 1)[1] if '.' in selected_horse_full[1] else selected_horse_full[1]
            horse_display = f"{cmd[1]},{cmd[2]} 號 {h1_clean}&{h2_clean}"
            odds_val = round(race_odds[selected_horse_full[0]] * race_odds[selected_horse_full[1]], 1)
        else:
            horse_name_clean = selected_horse_full.split('.', 1)[1] if '.' in selected_horse_full else selected_horse_full
            horse_display = f"{horse_num} 號 {horse_name_clean}"
            odds_val = race_odds[selected_horse_full] if bet_type == "win" else round(race_odds[selected_horse_full] / 2, 1)

        potential_win = int(bet_amount * odds_val)

        success_msg = (
            f"✅ **{type_title}投注成功！{horse_display}**\n"
            f"**投注額：{bet_amount:,} 金幣**\n"
            f"**實際扣除：{actual_deduct:,} 金幣（已享 100 信用）**\n"
            f"**{type_title}賠率：{odds_val} 倍**\n"
            f"💰 **若勝出可贏：{potential_win:,} 金幣**"
        )
        bot.reply_to(message, success_msg, parse_mode='Markdown')
    except Exception as e:
        print(f"⚠️ [BET_ERROR] 原因: {str(e)}")
        bot.reply_to(message, error_help_text, parse_mode='Markdown')

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
    bot.reply_to(message, f"✅ 退款成功！實退錢包金額：`{refund_amount:,}` 金幣", parse_mode='Markdown')

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
        bot.reply_to(message, f"🛒 **【專屬馬匹拍賣所】**\n\n💰 售價：**{HORSE_PRICE:,}** 金幣\n💰 你的餘額：**{chips:,}** 金幣\n👉 **購買請輸入**：`/buy 你的馬名` (限1-4個字)", parse_mode='Markdown')
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
    bot.reply_to(message, f"💰 你的餘額：**{chips:,}** 金幣", parse_mode='Markdown')

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
    bot.reply_to(message, "✅ **每日簽到成功！** +3000 金幣 💰")

@bot.message_handler(commands=['start'])
def start(message):
    sync_username(message.from_user.id, message.from_user.username)
    bot.reply_to(message, f"🏇 **虛擬賽馬 Bot 已就緒**\n輸入 /help 查看完整指令列表。")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = f"""🏇 **指令列表**
/startrun - 開始新賽事
/balance   - 查詢目前金幣
/refund    - 開賽前退款當局投注
/pay - <b>【回覆訊息 或 標記@Username】</b>轉讓金幣
/buy       - <b>【私訊】</b>購買專屬馬匹 ({HORSE_PRICE:,} 金幣)
/rename    - <b>【私訊】</b>自訂愛駒修改名字

【投注方式】/win 號碼 金額 | /pla 號碼 金額 | /ww 號碼1 號碼2 金額
"""
    bot.reply_to(message, text, parse_mode='HTML')

# ================== 啟動服務 ==================
print(f"🏇 {BOT_USERNAME} 指令全新精簡版已啟動！")
bot.infinity_polling()
