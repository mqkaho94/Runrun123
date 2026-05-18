import telebot
from telebot import util  
import random
import time
import threading
import sqlite3
import os
from datetime import date

# ⚠️ 設定你的 Bot 憑證與用戶名
TOKEN = "7742431712:AAHBx-YjOKHNK6Pq_bDkj7nOOnxEejE_Xo8"
BOT_USERNAME = "@Run1234567bot"

# 🚀 啟用多線程 ThreadPool
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=4)

# 🔒 定義每日簽到安全鎖 (防並發連擊)
daily_lock = threading.Lock()

# 🐿️ 基礎 NPC 固定鼠隻名單
BASE_NPC_HORSES = [
    "⚡1.奧雲狗狗", "🌪2.黑旋風", "⭐3.戰槌巨人", "🔥4.火麒麟", 
    "💨5.疾風", "🏅6.黃金戰鼠", "🌊7.海嘯", "🦅8.傲空"
]

# 🔢 名次對應的數字 Emoji 對照表
RANK_EMOJIS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
    5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"
}

# 🎭 20句全新無厘頭表面搞笑狀態
FUN_SURFACE_STATUSES = [
    # 🌟 特殊幸運 Buff 句（隱藏高速機率為 60%，仍有 40% 機率跑第尾）
    "朋友最多轉圈哈姆共你🐹",
    "趕住返屋企瀨屎💩",
    "昨晚拜過黃大仙🙏獲得神祕力量加持",
    
    # 💩 趕時間/突發狀況系列 (純外觀)
    "尋晚飲咗過期維他奶🥛個肚好滾",
    "出門口踩到舊大狗屎💩霉運當頭",
    "尋晚拉咗十二次斯🚽對腳發軟",
    "倒瀉咗杯凍檸茶走甜熱辣辣🍹",
    
    # 🐹 迷因/童年回憶系列 (純外觀)
    "以為自己係比卡超⚡自帶十萬伏特",
    "突然叮噹大長篇上身🎒要拯救地球",
    "阿嬤覺得佢餓👵🏻餵到變咗個波",
    "智商突然下線🧠全憑生物本能前進",
    
    # 💫 傻強/自信心爆棚系列 (純外觀)
    "食咗誠實豆沙包💊個人好清醒",
    "氪金玩家💰全身閃爍住人民幣嘅光芒",
    "眼神充滿殺氣🔪覺得自己係黎明",
    "自帶背景音樂BGM🎵氣勢如虹",
    
    # 💀 慘不忍睹/狀況外系列 (純外觀)
    "跛咗隻腳🧑🏻‍🦽要推輪椅代步跑",
    "成晚通宵打機🎮條黑眼圈去到下巴",
    "飲咗兩啖假酒🥴左右不分亂打打",
    "失戀萬念俱灰💔打算跑完去跳海",
    "高山反應🏔️呼吸困難行得好辛苦"
]

# 💾 資料庫持久化路徑設定
DB_FILE = '/data/race.db'
HORSE_PRICE = 3000  

# ================== 💾 資料庫核心管理 ==================
def init_db():
    try: os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    except: pass
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
        if row: return {"has_horse": row[0], "horse_name": row[1]}
        return {"has_horse": 0, "horse_name": None}

def get_owner_by_horse_name(horse_name):
    clean_name = horse_name
    if "." in clean_name: clean_name = clean_name.split(".", 1)[1]
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
horse_statuses = {}  
scheduled_disasters = {}  

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
        if f"{BOT_USERNAME}" in text_clean: text_clean = text_clean.replace(f"{BOT_USERNAME}", "")
        elif f"@run1234567bot" in text_clean.lower(): text_clean = text_clean.lower().replace("@run1234567bot", "")

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
                    bot.reply_to(message, f"❌ **轉帳失敗**：找不到玩家 `@{target_username}`。", parse_mode='Markdown')
                    return
        elif message.reply_to_message:
            if message.reply_to_message.from_user:
                to_user_id = message.reply_to_message.from_user.id
                to_username = message.reply_to_message.from_user.first_name
                sync_username(to_user_id, message.reply_to_message.from_user.username)
            else:
                bot.reply_to(message, "❌ **轉帳失敗**：無法讀取該訊息發送者隱私。", parse_mode='Markdown')
                return
            raw_amount = cmd[1].strip()
        else:
            bot.reply_to(message, "❌ **轉帳失敗！**", parse_mode='Markdown')
            return

        try:
            pay_amount = int(raw_amount)
            if pay_amount <= 0: return
        except ValueError: return

        if from_user_id == to_user_id: return
        from_user_chips = get_chips(from_user_id) 
        if from_user_chips < pay_amount: return

        get_chips(to_user_id) 
        update_chips(from_user_id, -pay_amount) 
        update_chips(to_user_id, pay_amount)   

        from_username = message.from_user.first_name if message.from_user.first_name else "神祕玩家"
        success_text = f"💸 **【金幣轉讓成功】** 💸\n🤝 轉出人：{from_username}\n🎁 接收人：{to_username}\n💰 轉讓金額：<b>{pay_amount:,}</b> 金幣"
        bot.send_message(message.chat.id, success_text, parse_mode='HTML')
    except: pass

# ================== 🎰 核心：開局與排位 ==================
@bot.message_handler(commands=['startrun'])
def startrun(message):
    global current_race, race_id, race_odds, user_bet_count, user_refund_count, user_actual_deduct, current_horses, horse_statuses, scheduled_disasters
    if current_race:
        bot.reply_to(message, "⚠️ 已有賽事進行中！")
        return

    current_race = "betting"  
    race_id = f"R{int(time.time())}"
    race_bets[race_id] = {}
    race_odds = {}
    horse_statuses = {}
    scheduled_disasters = {} 
    user_bet_count = {}
    user_refund_count = {}
    user_actual_deduct = {}
    
    sync_username(message.from_user.id, message.from_user.username)
    all_registered = get_all_registered_horses()
    final_8_horses = []  
    
    if len(all_registered) == 0:
        for npc in BASE_NPC_HORSES:
            clean_npc = npc.split('.', 1)[1] if '.' in npc else npc
            final_8_horses.append((None, clean_npc, npc[0] if not npc[0].isdigit() else "🐿️"))
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
                icon = npc_horse[0] if not npc_horse[0].isdigit() else "🐿️"
                final_8_horses.append((None, clean_npc_name, icon))

    random.shuffle(final_8_horses)
    chosen_horses_pool = []
    for idx, (uid, h_name, icon) in enumerate(final_8_horses):
        lane_num = idx + 1
        chosen_horses_pool.append(f"{icon}{lane_num}.{h_name}")
    current_horses = chosen_horses_pool

    # 🛠 稀有突發歹運事件抽籤
    if random.random() < 0.04:
        disaster_count = random.choice([1, 2])
        unlucky_horses = random.sample(current_horses, disaster_count)
        for uh in unlucky_horses:
            trigger_point = random.uniform(0.0, 99.0)
            reason = random.choice(["🐱【被貓吃掉❌】", "🪤【踩到鼠夾❌】"])
            scheduled_disasters[uh] = {"trigger_at": trigger_point, "reason": reason}

    text = f"🐿️ **第 {race_id} 場賽事開始！** 60秒後開跑 🏁\n\n"
    text += "【本局參賽鼠隻 ＆ 隨機排位表】\n"
    
    for h in current_horses:
        # 🎨 隨機抽取搞笑表面狀態
        surface_txt = random.choice(FUN_SURFACE_STATUSES)

        # 🧠 核心邏輯：微調指定 3 句的隱藏 Buff 機率（60% 高速 / 40% 中慢速）
        if surface_txt in ["朋友最多轉圈哈姆共你🐹", "趕住返屋企瀨屎💩", "昨晚拜過黃大仙🙏獲得神祕力量加持"]:
            if random.random() < 0.60:
                status_score = random.choice([9, 10])  # 60% 機率：高速（大勇）
            else:
                status_score = random.randint(1, 8)   # 40% 機率：普通或落後（有可能第尾）
        else:
            status_score = random.randint(1, 10)      # 其他 17 句：維持完全均等隨機

        # 🛠️ 根據後台決定的分數給予實際的時間範圍
        if status_score >= 9:
            base_time_range = (25.0, 35.0)  
        elif status_score >= 4:
            base_time_range = (40.0, 55.0)  
        else:
            base_time_range = (60.0, 80.0)  
            
        horse_statuses[h] = {
            "surface_text": surface_txt, 
            "target_time": random.uniform(*base_time_range),
            "dead_reason": None,
            "freeze_steps": 0,       
            "freeze_reason": ""      
        }

        win_odds = round(random.uniform(2.5, 15.0), 1)
        place_odds = round(win_odds / 2, 1)
        race_odds[h] = win_odds  
        
        text += f"{h} 📢【{surface_txt}】\n   ➡️ 獨贏: *{win_odds}x* | 位置: *{place_odds}x*\n"

    text += "\n" + "—" * 20 + "\n"
    text += "💰 **【下注方式】** /win 號碼 金額 | /pla 號碼 金額 | /ww 號碼1 號碼2 金額\n"
    
    bot.reply_to(message, text, parse_mode='Markdown')
    threading.Timer(60, lambda: run_race(message.chat.id)).start()

# ================== 核心：動態模擬賽鼠直播 ==================
def run_race(chat_id):
    global current_race, race_id, race_odds, race_bets, current_horses, horse_statuses, scheduled_disasters
    
    if current_race != "betting": return
    current_race = "running" 
    
    # 賽前選手狀態通報
    status_intro = f"📋 **第 {race_id} 場賽事 - 賽前選手狀態通報** 📋\n" + "‾" * 25 + "\n"
    for h in current_horses:
        surf_txt = horse_statuses[h]["surface_text"]
        status_intro += f"{h} ➡️ **{surf_txt}**\n"
    status_intro += "\n⏱ _狀態展示中，比賽將於 5 秒後正式鳴槍！_"
    
    race_msg = bot.send_message(chat_id, status_intro, parse_mode='Markdown')
    time.sleep(5)  
    
    TOTAL_DISTANCE = 100.0  
    DISPLAY_LENGTH = 15     
    
    speeds = {h: TOTAL_DISTANCE / horse_statuses[h]["target_time"] for h in current_horses}
    current_distance = {h: 0.0 for h in current_horses}
    
    finished_horses = []   
    dead_horses = []       
    
    start_time = time.time()
    last_refresh_time = start_time
    
    while (len(finished_horses) < 3) and (len(finished_horses) + len(dead_horses) < len(current_horses)):
        time.sleep(1.0)  
        now = time.time()
        
        current_second_reports = {}
        
        for h in current_horses:
            if horse_statuses[h]["dead_reason"] is not None:
                current_second_reports[h] = f"❌ {horse_statuses[h]['dead_reason']}"
                continue

            if current_distance[h] >= TOTAL_DISTANCE:
                r = finished_horses.index(h) + 1
                current_second_reports[h] = f"🏁 已衝線 (第 {r} 名)"
                continue

            if h in scheduled_disasters and current_distance[h] >= scheduled_disasters[h]["trigger_at"]:
                disaster_reason = scheduled_disasters[h]["reason"]
                horse_statuses[h]["dead_reason"] = disaster_reason
                dead_horses.append(h)
                current_second_reports[h] = f"❌ {disaster_reason}"
                continue
            
            if horse_statuses[h]["freeze_steps"] > 0:
                reason = horse_statuses[h]["freeze_reason"]
                sec_left = horse_statuses[h]["freeze_steps"]
                current_second_reports[h] = f"⚠️ {reason} (剩餘 {sec_left} 秒) 🕒"
                horse_statuses[h]["freeze_steps"] -= 1 
                continue 
            
            if random.random() < 0.005:
                freeze_sec = random.randint(3, 5) 
                freeze_type = random.choice(["發呆停止步行 💤", "地上撿到芝士吃兩口 🧀"])
                horse_statuses[h]["freeze_steps"] = freeze_sec
                horse_statuses[h]["freeze_reason"] = freeze_type
                current_second_reports[h] = f"⚠️ {freeze_type} (剩餘 {freeze_sec} 秒) 🕒"
                horse_statuses[h]["freeze_steps"] -= 1 
                continue

            move_roll = random.randint(1, 10)
            if move_roll >= 9:
                step_modifier = 2.0
                action_text = "⚡ 快步推進"
            elif move_roll >= 4:
                step_modifier = 1.0
                action_text = "✨ 穩步向前"
            else:
                step_modifier = 0.5 
                action_text = "💤 慢步推進"
                
            current_distance[h] += (speeds[h] * 1.0) * step_modifier + random.uniform(-0.2, 0.2)
            if current_distance[h] < 0: current_distance[h] = 0
            
            if current_distance[h] >= TOTAL_DISTANCE:
                current_distance[h] = TOTAL_DISTANCE
                if h not in finished_horses: 
                    finished_horses.append(h)
                current_second_reports[h] = f"🏁 剛剛衝線了！(第 {finished_horses.index(h) + 1} 名)"
            else:
                current_second_reports[h] = action_text
                        
        if now - last_refresh_time >= 3.0 or (len(finished_horses) >= 3) or (len(finished_horses) + len(dead_horses) == len(current_horses)):
            last_refresh_time = now
            dynamic_text = f"🐿️ **第 {race_id} 場賽事 現場直播** 🏁\n" + "‾" * 25 + "\n"
            
            for h in current_horses:
                if horse_statuses[h]["dead_reason"] is not None:
                    dynamic_text += f"{h} ➡️ {horse_statuses[h]['dead_reason']}\n\n"
                else:
                    progress = int((current_distance[h] / TOTAL_DISTANCE) * DISPLAY_LENGTH)
                    progress = min(max(progress, 0), DISPLAY_LENGTH)
                    track_str = "🏁 " + "_" * (DISPLAY_LENGTH - progress) + "🐿️" + "_" * progress
                    status = ""
                    if h in finished_horses:
                        r = finished_horses.index(h) + 1
                        status = " 🥇【冠軍】" if r==1 else " 🥈【亞軍】" if r==2 else " 🥉【季軍】"
                    dynamic_text += f"{h}{status}\n`{track_str}`\n\n"
            
            action_reports = []
            for h in current_horses:
                msg_status = current_second_reports.get(h, "未知")
                if horse_statuses[h]["dead_reason"] is not None:
                    rank_str = "淘汰"
                elif h in finished_horses:
                    rank_str = f"第 {finished_horses.index(h) + 1} 名"
                else:
                    higher_count = sum(1 for competitor in current_horses if competitor != h and horse_statuses[competitor]["dead_reason"] is None and competitor not in finished_horses and current_distance[competitor] > current_distance[h])
                    current_rank = len(finished_horses) + 1 + higher_count
                    rank_str = f"第 {current_rank} 名"
                
                action_reports.append(f"🏃 [{rank_str}] {h} ➡️ `[{msg_status}]`")
            
            dynamic_text += "—" * 15 + "\n"
            dynamic_text += "📊 **【即時動態戰況提示】**\n" + "\n".join(action_reports)
            
            try: bot.edit_message_text(dynamic_text, chat_id, race_msg.message_id, parse_mode='Markdown')
            except: pass

    alive_remaining = [h for h in current_horses if h not in finished_horses and h not in dead_horses]
    alive_remaining.sort(key=lambda h: current_distance[h], reverse=True)
    all_ranks = finished_horses + alive_remaining + dead_horses
    
    final_text = f"🐿️ **第 {race_id} 場賽事 直播結束（定格名次）** 🏁\n" + "‾" * 25 + "\n"
    for h in current_horses:
        if horse_statuses[h]["dead_reason"] is not None:
            final_text += f"{h} ➡️ {horse_statuses[h]['dead_reason']} (取消資格)\n\n"
        else:
            final_rank = all_ranks.index(h) + 1
            rank_emoji = RANK_EMOJIS.get(final_rank, "🐿️") 
            progress = int((current_distance[h] / TOTAL_DISTANCE) * DISPLAY_LENGTH)
            progress = min(max(progress, 0), DISPLAY_LENGTH)
            track_str = "🏁 " + "_" * (DISPLAY_LENGTH - progress) + rank_emoji + "_" * progress
            status = " 🥇【冠軍】" if final_rank==1 else " 🥈【亞軍】" if final_rank==2 else " 🥉【季軍】" if final_rank==3 else ""
            final_text += f"{h}{status}\n`{track_str}`\n\n"
    
    final_text += "—" * 15 + "\n🏁 比賽結束！正在計算最終名次與分紅..."
    try: bot.edit_message_text(final_text, chat_id, race_msg.message_id, parse_mode='Markdown')
    except: pass
                
    winner, second = all_ranks[0] if len(finished_horses) > 0 else None, all_ranks[1] if len(finished_horses) > 1 else None
    
    result = "🏆 **最終賽果名次結果** 🏆\n\n"
    for i, h in enumerate(all_ranks, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else "🏁"
        if horse_statuses[h]["dead_reason"] is not None:
            result += f"❌ 未完賽：{h} -> {horse_statuses[h]['dead_reason']} (全輸)\n"
        else:
            result += f"{medal} 第 {i} 名：{h} (獨贏 {race_odds[h]}x)\n"
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    # 派彩邏輯
    if race_id in race_bets and len(finished_horses) > 0:
        payout_message = "🎉 **派彩結果** 🎉\n\n"
        has_winner = False
        for uid, bets in race_bets[race_id].items():
            win_amount = 0
            for b_type, horses, amt in bets:
                if b_type == "win" and winner and horses == winner:
                    win_amount += int(amt * race_odds[winner])
                elif b_type == "pla" and horses in finished_horses[:3]:
                    win_amount += int(amt * (race_odds[horses] / 2))
                elif b_type == "ww" and winner and second and isinstance(horses, list) and set(horses) == set([winner, second]):
                    win_amount += int(amt * (race_odds[winner] * race_odds[second]))
            if win_amount > 0:
                update_chips(uid, win_amount)
                try: p_name = bot.get_chat_member(chat_id, uid).user.first_name
                except: p_name = f"玩家({uid})"
                payout_message += f"✅ 玩家 <b>{p_name}</b> 贏得 <b>{win_amount:,}</b> 金幣\n"
                has_winner = True
        if has_winner: bot.send_message(chat_id, payout_message, parse_mode='HTML')
        else: bot.send_message(chat_id, "壓注全空！本局沒有人中獎 💸")
    else:
        bot.send_message(chat_id, "壓注全空！本局沒有人中獎 💸")

    # ================== 🐿️ 鼠主分紅與安慰獎 ==================
    owner_text = "✨ <b>【本局鼠主專利分紅】</b> ✨\n"
    has_owner_bonus = False
    consolation_owners = [] 

    for rank_idx in range(min(3, len(finished_horses))):
        target_horse = finished_horses[rank_idx]
        if "👑" in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id:
                owner_id = int(owner_id)
                rank_num = rank_idx + 1
                try: owner_name = bot.get_chat_member(chat_id, owner_id).user.first_name
                except: owner_name = f"鼠主({owner_id})"
                
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
                owner_text += f"恭喜專屬鼠 <b>{target_horse}</b> 榮獲{t_title}！\n鼠主 <b>{owner_name}</b> 獲得分紅大獎 <b>+{bonus_chips:,}</b> 金幣 💰\n"
                has_owner_bonus = True

    for rank_idx in range(3, len(all_ranks)):
        target_horse = all_ranks[rank_idx]
        if "👑" in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id: consolation_owners.append(int(owner_id))

    if consolation_owners:
        consolation_mentions = []
        for c_owner in consolation_owners:
            lucky_comfort_bonus = random.randint(300, 500)
            update_chips(c_owner, lucky_comfort_bonus)
            try: c_name = bot.get_chat_member(chat_id, c_owner).user.first_name
            except: c_name = f"鼠主({c_owner})"
            consolation_mentions.append(f"<b>{c_name}</b> (<b>+{lucky_comfort_bonus:,}</b>)")
        owner_text += f"\n🎁 <b>【鼠主同慶安慰獎】</b>\n本局遺憾落敗（或不幸罹難）的鼠主： " + "、".join(consolation_mentions) + f" 獲得安慰分紅！\n"
        has_owner_bonus = True

    if has_owner_bonus: bot.send_message(chat_id, owner_text, parse_mode='HTML')
    
    current_race, race_odds, horse_statuses, scheduled_disasters = None, {}, {}, {}
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

    error_help_text = "❌ **投注格式錯誤！**\n👉 獨贏：`/win [編號] [金額]`\n👉 位置：`/pla [編號] [金額]`\n👉 連贏：`/ww [A] [B] [金額]`"

    try:
        text_clean = message.text
        if f"{BOT_USERNAME}" in text_clean: text_clean = text_clean.replace(f"{BOT_USERNAME}", "")
        elif f"@run1234567bot" in text_clean.lower(): text_clean = text_clean.lower().replace("@run1234567bot", "")

        cmd = text_clean.split()
        bet_type = cmd[0][1:]  
        chips = get_chips(user_id)

        # 1. 處理不同投注種類的參數與計算
        if bet_type in ["win", "pla"]:
            if len(cmd) < 3: return
            horse_num = int(cmd[1])
            amount_str = cmd[2]
            if horse_num < 1 or horse_num > len(current_horses): return
            selected_horse_full = current_horses[horse_num-1]
            
            # 清理出純鼠名 (移除圖標與編號)
            horse_name_clean = selected_horse_full.split('.', 1)[1] if '.' in selected_horse_full else selected_horse_full
            horse_display = f"（{horse_num}號）（{horse_name_clean}）"
            
            # 計算單純賠率與預期總獎金
            odds_val = race_odds[selected_horse_full] if bet_type == "win" else round(race_odds[selected_horse_full] / 2, 1)

        elif bet_type == "ww":
            if len(cmd) < 4: return
            h1, h2 = int(cmd[1]), int(cmd[2])
            amount_str = cmd[3]
            if h1 == h2 or min(h1, h2) < 1 or max(h1, h2) > len(current_horses): return
            selected_horse_full = [current_horses[h1-1], current_horses[h2-1]]
            
            h1_clean = selected_horse_full[0].split('.', 1)[1] if '.' in selected_horse_full[0] else selected_horse_full[0]
            h2_clean = selected_horse_full[1].split('.', 1)[1] if '.' in selected_horse_full[1] else selected_horse_full[1]
            horse_display = f"（{h1},{h2}號）（{h1_clean} & {h2_clean}）"
            
            odds_val = round(race_odds[selected_horse_full[0]] * race_odds[selected_horse_full[1]], 1)

        # 2. 計算籌碼金額與福利金補貼扣款
        bet_amount = int(chips * int(amount_str.replace("%", "")) / 100) if "%" in amount_str else int(amount_str)
        if bet_amount <= 0: return

        credit = 100
        actual_deduct = max(0, bet_amount - credit)
        if actual_deduct > chips: return

        # 3. 實際執行帳戶扣款與紀錄
        update_chips(user_id, -actual_deduct)
        user_actual_deduct[user_id] = actual_deduct 
        user_bet_count[user_id] = 1

        if user_id not in race_bets[race_id]: race_bets[race_id][user_id] = []
        race_bets[race_id][user_id].append((bet_type, selected_horse_full, bet_amount))

        # 4. 翻譯投注抬頭
        type_title = "獨贏" if bet_type == "win" else "位置" if bet_type == "pla" else "連贏"
        
        # 5. 計算總共可收金額 (本金 * 賠率)
        potential_win = int(bet_amount * odds_val)

        # ✨ 嚴格遵循玩家指定的回覆格式
        success_msg = f"（{type_title}）成功 🎊 {horse_display}\n" \
                      f"投注幾錢：{bet_amount:,} 金幣\n" \
                      f"幾多倍：{odds_val} 倍\n" \
                      f"贏出總數可以收幾多：{potential_win:,} 金幣"
                      
        bot.reply_to(message, success_msg, parse_mode='Markdown')
    except:
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

# ================== 🤖 每日福利指令 (安全防點擊穿透鎖定版) ==================
@bot.message_handler(commands=['daily'])
def daily(message):
    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
    today = date.today().isoformat()  
    
    # 🔒 啟用多線程排隊安全鎖，強制讓同時到達的連按請求排隊處理
    with daily_lock:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
            last = c.fetchone()
            
            # 如果資料庫裡面的時間已經是今天，代表剛剛排在前面的連擊請求已經領過了
            if last and last[0] == today:
                bot.reply_to(message, "❌ 你今天已經領過每日獎勵！明天再來吧。")
                return
                
            # 如果今天還沒領過，立刻在鎖內部把今天日期刷進資料庫（原子性鎖定）
            c.execute("UPDATE users SET last_daily=? WHERE user_id=?", (today, user_id))
            conn.commit()
            
        # 帳目發放移入排隊保護範圍中，確保只會被執行到精確的一次
        update_chips(user_id, 3000)
        bot.reply_to(message, "✅ **每日簽到成功！** +3000 金幣 💰")

# ================== 🤖 其他功能指令 ==================
@bot.message_handler(commands=['buy'])
def buy_horse(message):
    if message.chat.type != "private":
        bot.reply_to(message, f"❌ 限私訊使用！請點擊： {BOT_USERNAME}")
        return
    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
    chips = get_chips(user_id)
    horse_info = get_user_horse(user_id)

    if horse_info["has_horse"] == 1:
        bot.reply_to(message, f"🐿️ 您已擁有一隻愛鼠：**{horse_info['horse_name']}**", parse_mode='Markdown')
        return

    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2:
        bot.reply_to(message, f"🛒 **【專屬鼠隻拍賣所】**\n💰 售價：**{HORSE_PRICE:,}** 金幣\n👉 輸入：`/buy 你的鼠名`", parse_mode='Markdown')
        return

    h_name = cmd[1].strip()
    if len(h_name) < 1 or len(h_name) > 15 or chips < HORSE_PRICE: return

    update_chips(user_id, -HORSE_PRICE)
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET has_horse=1, horse_name=? WHERE user_id=?", (h_name, user_id))
        conn.commit()
    bot.reply_to(message, f"🎉 專屬愛鼠 **「{h_name}」** 登記成功！")

@bot.message_handler(commands=['rename'])
def rename_horse(message):
    if message.chat.type != "private": return
    user_id = message.from_user.id
    horse_info = get_user_horse(user_id)
    if horse_info["has_horse"] == 0: return
    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2: return
    new_name = cmd[1].strip()
    if len(new_name) < 1 or len(new_name) > 15: return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET horse_name=? WHERE user_id=?", (new_name, user_id))
        conn.commit()
    bot.reply_to(message, f"✨ 愛鼠已更名為：**「{new_name}」** 🐿️")

@bot.message_handler(commands=['money'])
def money(message):
    sync_username(message.from_user.id, message.from_user.username)
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"💰 你的餘額：**{chips:,}** 金幣", parse_mode='Markdown')

@bot.message_handler(commands=['start'])
def start(message):
    sync_username(message.from_user.id, message.from_user.username)
    bot.reply_to(message, f"🐿️ **虛擬賽鼠 Bot 已就緒**\n輸入 /help 查看完整指令列表。")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = f"""🐿️ **指令列表**
/startrun - 開始新賽事
/money   - 查詢目前金幣
/refund    - 開賽前退款當局投注
/daily     - 領取每日福利 (+3000 金幣，每日限一次)
/pay - <b>【回覆訊息】</b>轉讓金幣
/buy       - <b>【私訊】</b>購買專屬鼠隻 ({HORSE_PRICE:,} 金幣)
/rename    - <b>【私訊】</b>自訂愛鼠修改名字

【投注方式】/win 號碼 金額 | /pla 號碼 金額 | /ww 號碼1 號碼2 金幣
"""
    bot.reply_to(message, text, parse_mode='HTML')

# ================== 啟動服務 ==================
print(f"🐿️ {BOT_USERNAME} 安全高並發防刷鎖定版已成功啟動！")
bot.infinity_polling(timeout=20, long_polling_timeout=10)
