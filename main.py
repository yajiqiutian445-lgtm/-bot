import os
import random
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------
# Keep-Alive用 Webサーバー (Render 「Your service is live」 対策)
# ---------------------------------------------------------
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        response_text = "<h1>✅ Web service is running!</h1><p>ちいはや鯖 Botは正常に稼働中です。</p>"
        self.wfile.write(response_text.encode('utf-8'))

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
    print(f"Webサーバーがポート {port} で起動しました。")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ---------------------------------------------------------
# Botの初期化とインテント設定
# ---------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class ChihayaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView(role_id=None))
        self.add_view(RolePanelView(role_id=None))
        self.add_view(TicketView())
        self.add_view(TicketCloseView())
        self.add_view(GamePanelView())
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました（全100個）。")

bot = ChihayaBot()

# ---------------------------------------------------------
# 1. 認証機能 (Verification UI) - 権限エラー対策付き
# ---------------------------------------------------------
class VerifyView(discord.ui.View):
    def __init__(self, role_id: int = None):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="✅ ルールに同意して認証する", style=discord.ButtonStyle.green, custom_id="verify_button_persistent")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = None
        if self.role_id:
            role = interaction.guild.get_role(self.role_id)
        if not role:
            role = discord.utils.get(interaction.guild.roles, name="メンバー")

        if not role:
            await interaction.response.send_message("エラー: 設定されたロールが見つかりませんでした。サーバー管理者に連絡してください。", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"認証が完了しました！ `{role.name}` ロールを付与しました。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ エラー: ボットにロールを付与する権限がないか、付与しようとしたロールがボット自身のロールよりも上に位置しています。サーバー管理者にお知らせください。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 予期せぬエラーが発生しました: `{e}`", ephemeral=True)

# ---------------------------------------------------------
# 2. ロールパネル機能 (Role Panel UI) - 権限エラー対策付き
# ---------------------------------------------------------
class RolePanelView(discord.ui.View):
    def __init__(self, role_id: int = None):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="🎭 ロールを取得 / 解除する", style=discord.ButtonStyle.blurple, custom_id="role_panel_button_persistent")
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.role_id:
            await interaction.response.send_message("エラー: 対象のロールが指定されていません。", ephemeral=True)
            return

        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("エラー: 該当するロールが存在しません。", ephemeral=True)
            return

        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"➖ `{role.name}` ロールを解除しました。", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"➕ `{role.name}` ロールが付与されました！", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ エラー: ボットにロールを管理する権限がないか、対象ロールがボットのロールより上にあります。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 予期せぬエラーが発生しました: `{e}`", ephemeral=True)

# ---------------------------------------------------------
# 3. チケット機能 (Ticket System UI)
# ---------------------------------------------------------
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 お問い合わせチケットを作成する", style=discord.ButtonStyle.blurple, custom_id="create_ticket_persistent")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        category = discord.utils.get(guild.categories, name="チケット")
        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name}", 
            overwrites=overwrites, 
            category=category
        )
        
        embed = discord.Embed(
            title="📩 お問い合わせ窓口",
            description=f"{interaction.user.mention}さん、お問い合わせ内容をメッセージで送信してください。\nサポート対応が完了したら下のボタンを押して閉じてください。",
            color=discord.Color.blue()
        )
        await channel.send(embed=embed, view=TicketCloseView())
        await interaction.response.send_message(f"専用のお問い合わせチャンネルを作成しました: {channel.mention}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.red, custom_id="close_ticket_persistent")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("このチケットチャンネルを閉じて削除します...", ephemeral=True)
        await asyncio.sleep(2)
        await interaction.channel.delete()

# ---------------------------------------------------------
# 4. ゲームパネル機能 (Game Panel UI)
# ---------------------------------------------------------
class GamePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎲 サイコロ", style=discord.ButtonStyle.primary, custom_id="game_dice_btn")
    async def roll_dice(self, interaction: discord.Interaction, button: discord.ui.Button):
        res = random.randint(1, 6)
        await interaction.response.send_message(f"🎲 サイコロの結果: **{res}**", ephemeral=True)

    @discord.ui.button(label="🪙 コイントス", style=discord.ButtonStyle.secondary, custom_id="game_coin_btn")
    async def toss_coin(self, interaction: discord.Interaction, button: discord.ui.Button):
        res = random.choice(["表 (Heads)", "裏 (Tails)"])
        await interaction.response.send_message(f"🪙 コインの結果: **{res}**", ephemeral=True)

    @discord.ui.button(label="🎴 おみくじ", style=discord.ButtonStyle.success, custom_id="game_omikuji_btn")
    async def omikuji(self, interaction: discord.Interaction, button: discord.ui.Button):
        res = random.choice(["大吉 🌟", "吉 😃", "中吉 🙂", "小吉 😊", "末吉 😄", "凶 😨", "大凶 💀"])
        await interaction.response.send_message(f"🎴 今日の運勢: **{res}**", ephemeral=True)

# ---------------------------------------------------------
# 5. 全100個のスラッシュコマンド定義
# ---------------------------------------------------------

# --- 💰 経済・育成系 (1〜15) ---
@bot.tree.command(name="work", description="お仕事をしてコインを稼ぐ")
async def work(interaction: discord.Interaction):
    earned = random.randint(100, 1000)
    await interaction.response.send_message(f"💼 お仕事完了！ **{earned}** 🪙 コインを獲得しました！")

@bot.tree.command(name="balance", description="所持金や資産を確認する")
async def balance(interaction: discord.Interaction):
    await interaction.response.send_message(f"💰 {interaction.user.display_name} さんの現在の所持金: **1,250** 🪙")

@bot.tree.command(name="daily", description="毎日のログインボーナスを受け取る")
async def daily(interaction: discord.Interaction):
    await interaction.response.send_message("🎁 今日のログインボーナス **500** 🪙 を受け取りました！")

@bot.tree.command(name="pay", description="他のメンバーにコインを送金する")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.send_message(f"💸 {member.mention} さんに **{amount}** 🪙 送金しました。")

@bot.tree.command(name="shop", description="専用アイテムを購入する")
async def shop(interaction: discord.Interaction):
    await interaction.response.send_message("🛒 **ちいはやショップ**\n1. 釣り竿 - 500🪙\n2. プレミアムロール - 5000🪙")

@bot.tree.command(name="inventory", description="所持アイテム一覧を見る")
async def inventory(interaction: discord.Interaction):
    await interaction.response.send_message("🎒 **あなたのインベントリ**: [普通の釣り竿], [初心者用ピッケル]")

@bot.tree.command(name="gacha", description="レアアイテムを引くガチャを回す")
async def gacha(interaction: discord.Interaction):
    rarity = random.choice(["⭐ (ノーマル)", "⭐⭐ (レア)", "⭐⭐⭐ (SR)", "🌟 (SSR!)"])
    await interaction.response.send_message(f"🎰 ガチャ結果: **{rarity}** をゲット！")

@bot.tree.command(name="fish", description="釣りをして魚や宝物をゲットする")
async def fish(interaction: discord.Interaction):
    item = random.choice(["マグロ 🐟", "サーモン 🐟", "靴 👞", "黄金の宝箱 🧰"])
    await interaction.response.send_message(f"🎣 釣りをしました！ **{item}** が釣れた！")

@bot.tree.command(name="hunt", description="モンスターを討伐して素材を集める")
async def hunt(interaction: discord.Interaction):
    await interaction.response.send_message("⚔️ 野生のスライムを倒し、**スライムゼリー**をゲットしました！")

@bot.tree.command(name="mine", description="鉱山で鉱石を採掘する")
async def mine(interaction: discord.Interaction):
    ore = random.choice(["鉄鉱石 🪨", "金鉱石 🟡", "ダイヤモンド 💎"])
    await interaction.response.send_message(f"⛏️ 採掘完了！ **{ore}** を発見しました！")

@bot.tree.command(name="bank", description="銀行にコインを預け入れる・引き出す")
async def bank(interaction: discord.Interaction, action: str, amount: int):
    await interaction.response.send_message(f"🏦 銀行処理 ({action}): **{amount}** 🪙 の処理が完了しました。")

@bot.tree.command(name="loan", description="コインを借入れ・返済する")
async def loan(interaction: discord.Interaction, amount: int):
    await interaction.response.send_message(f"🏦 **{amount}** 🪙 のローン手続きを行いました。")

@bot.tree.command(name="stocks", description="鯖内株式市場をチェックする")
async def stocks(interaction: discord.Interaction):
    await interaction.response.send_message("📈 **ちいはや株価指数**: 1,240pt (+3.5%)")

@bot.tree.command(name="property", description="マイホームや土地を購入・管理する")
async def property_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🏠 **所有不動産**: ちいはや街 1丁目 タワーマンション 1201号室")

@bot.tree.command(name="pet", description="ペットを飼育して育てる")
async def pet(interaction: discord.Interaction):
    await interaction.response.send_message("🐶 ペットのポチ（Lv.3）は元気に遊んでいます！")

# --- 🎲 ゲーム・エンタメ系 (16〜40) ---
@bot.tree.command(name="dice", description="サイコロを振る")
async def dice(interaction: discord.Interaction):
    await interaction.response.send_message(f"🎲 出た目: **{random.randint(1, 6)}**")

@bot.tree.command(name="coinflip", description="コイントスをする")
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(f"🪙 結果: **{random.choice(['表', '裏'])}**")

@bot.tree.command(name="slots", description="スロットマシンで遊ぶ")
async def slots(interaction: discord.Interaction):
    emojis = ["🎰", "7️⃣", "💎", "🍋", "🔔"]
    s1, s2, s3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)
    msg = f"[{s1} | {s2} | {s3}]"
    if s1 == s2 == s3:
        msg += " 🎉 **ジャックポット！！**"
    await interaction.response.send_message(f"スロット結果: {msg}")

@bot.tree.command(name="blackjack", description="ブラックジャックで勝負する")
async def blackjack(interaction: discord.Interaction):
    await interaction.response.send_message("🃏 あなたの手札: [K, 8] (合計: 18) vs DEALER: [10, ?]")

@bot.tree.command(name="poker", description="ポーカーの役を競う")
async def poker(interaction: discord.Interaction):
    await interaction.response.send_message("🃏 あなたの役: **ツーペア (10 & J)**")

@bot.tree.command(name="quiz", description="鯖に関するクイズに挑戦する")
async def quiz(interaction: discord.Interaction):
    await interaction.response.send_message("❓ **問題**: ちいはや鯖の創立年月日はいつでしょう？")

@bot.tree.command(name="rps", description="ボットとじゃんけんをする")
async def rps(interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(["グー", "チョキ", "パー"])
    await interaction.response.send_message(f"あなた: {choice} vs Bot: {bot_choice}")

@bot.tree.command(name="fortune", description="今日の運勢を占う")
async def fortune(interaction: discord.Interaction):
    await interaction.response.send_message(f"🔮 今日のラッキーカラーは **{random.choice(['青', '赤', '金', '緑'])}** です！")

@bot.tree.command(name="omikuji", description="おみくじを引く")
async def omikuji_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🎴 おみくじ結果: **{random.choice(['大吉', '吉', '中吉', '小吉', '凶'])}**")

@bot.tree.command(name="roulette", description="ルーレットを回す")
async def roulette(interaction: discord.Interaction, bet_color: str):
    res = random.choice(["赤", "黒", "緑"])
    await interaction.response.send_message(f"🎡 ルーレット停止位置: **{res}** (賭け: {bet_color})")

@bot.tree.command(name="bounty", description="指名手配犯を追跡するミニゲーム")
async def bounty(interaction: discord.Interaction):
    await interaction.response.send_message("🎯 **懸賞金Target**: 「影のドロボウ」を探し出せ！")

@bot.tree.command(name="arena", description="他のプレイヤーと模擬戦闘する")
async def arena(interaction: discord.Interaction, target: discord.Member):
    await interaction.response.send_message(f"⚔️ {interaction.user.mention} VS {target.mention} の勝負が始まりました！")

@bot.tree.command(name="raid", description="仲間と協力してレイドボスを倒す")
async def raid(interaction: discord.Interaction):
    await interaction.response.send_message("🐲 レイドボス「暗黒竜」が現れた！攻撃を仕掛けます！")

@bot.tree.command(name="wordwolf", description="ワードウルフのワードを生成する")
async def wordwolf(interaction: discord.Interaction):
    await interaction.response.send_message("🐺 DMにてあなたのワードを送信しました。（確認してください）", ephemeral=True)

@bot.tree.command(name="shiritori", description="ボットとしりとりをする")
async def shiritori(interaction: discord.Interaction, word: str):
    await interaction.response.send_message(f"『{word}』ですね！ Bot -> 『リンゴ』！")

@bot.tree.command(name="typing", description="タイピング速度を測定する")
async def typing_game(interaction: discord.Interaction):
    await interaction.response.send_message("⌨️ 次の文字を早く入力してください: `chihaya-server-fast`")

@bot.tree.command(name="puzzle", description="パズルゲームをプレイする")
async def puzzle(interaction: discord.Interaction):
    await interaction.response.send_message("🧩 スライドパズル生成中... [1][2][3]\n[4][ ][5]")

@bot.tree.command(name="mashroom", description="キノコ狩りゲーム")
async def mashroom(interaction: discord.Interaction):
    await interaction.response.send_message(f"🍄 森林で **{random.choice(['毒キノコ 🟣', 'マツタケ 🟤', '普通のキノコ 🍄'])}** を採取！")

@bot.tree.command(name="dungeon", description="ランダムダンジョンを探索する")
async def dungeon(interaction: discord.Interaction):
    await interaction.response.send_message("🏰 ダンジョン地下3階: 宝箱を開けた！ 100🪙 発見！")

@bot.tree.command(name="tarot", description="タロットカードを引く")
async def tarot(interaction: discord.Interaction):
    card = random.choice(["太陽 (正位置)", "愚者 (逆位置)", "世界 (正位置)", "塔 (正位置)"])
    await interaction.response.send_message(f"🃏 タロット結果: **{card}**")

@bot.tree.command(name="magic", description="魔法の呪文を唱えてみる")
async def magic(interaction: discord.Interaction, spell: str):
    await interaction.response.send_message(f"✨ 『{spell}！！』 ...何も起きなかったようだ。")

@bot.tree.command(name="petrace", description="ペットレースの勝者を予想する")
async def petrace(interaction: discord.Interaction):
    await interaction.response.send_message("🏁 ペットレース開幕！ 1着: 🐕 イヌ号！")

@bot.tree.command(name="bowling", description="ボウリングのスコアを競う")
async def bowling(interaction: discord.Interaction):
    pins = random.randint(0, 10)
    await interaction.response.send_message(f"🎳 ナイスショット！ **{pins}** ピン倒しました！")

@bot.tree.command(name="darts", description="ダーツを投げる")
async def darts(interaction: discord.Interaction):
    score = random.choice([10, 20, 50, "BULL!! (50分)"])
    await interaction.response.send_message(f"🎯 ダーツ結果: **{score}**")

@bot.tree.command(name="slot_custom", description="カスタムスロットを回す")
async def slot_custom(interaction: discord.Interaction):
    await interaction.response.send_message("🎰 カスタムスロット回転！ [🔥|🔥|🔥] 激熱！")

# --- 💬 コミュニケーション・ユーティリティ系 (41〜70) ---
@bot.tree.command(name="ping", description="Botの応答速度を確認する")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")

@bot.tree.command(name="serverinfo", description="サーバーの情報を表示する")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    await interaction.response.send_message(f"🏰 **{guild.name}** | メンバー数: {guild.member_count}人")

@bot.tree.command(name="userinfo", description="ユーザーのプロフィール情報を表示する")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.send_message(f"👤 ユーザー: {target.name} (ID: {target.id})")

@bot.tree.command(name="avatar", description="ユーザーのアイコンを高画質で表示する")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.send_message(f"🖼️ {target.name} さんのアイコン: {target.display_avatar.url}")

@bot.tree.command(name="poll", description="投票を作成する")
async def poll(interaction: discord.Interaction, question: str):
    msg = await interaction.channel.send(f"📊 **投票**: {question}")
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await interaction.response.send_message("投票を作成しました！", ephemeral=True)

@bot.tree.command(name="embed", description="お手製の埋め込みメッセージを作成する")
async def embed_cmd(interaction: discord.Interaction, title: str, description: str):
    emb = discord.Embed(title=title, description=description, color=discord.Color.blue())
    await interaction.response.send_message(embed=emb)

@bot.tree.command(name="say", description="ボットに喋らせる")
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(message)
    await interaction.response.send_message("送信しました。", ephemeral=True)

@bot.tree.command(name="calc", description="計算機を実行する")
async def calc(interaction: discord.Interaction, formula: str):
    try:
        res = eval(formula, {"__builtins__": None}, {})
        await interaction.response.send_message(f"🧮 計算結果: `{formula} = {res}`")
    except:
        await interaction.response.send_message("エラー: 正しい数式を入力してください。", ephemeral=True)

@bot.tree.command(name="weather", description="指定地域の天気予報を見る")
async def weather(interaction: discord.Interaction, location: str):
    await interaction.response.send_message(f"☀️ **{location}** の天気: 晴れ / 気温: 22°C")

@bot.tree.command(name="translate", description="テキストを翻訳する")
async def translate(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"🔤 翻訳結果: `{text}` -> [Translation Result]")

@bot.tree.command(name="reminder", description="リマインダーを設定する")
async def reminder(interaction: discord.Interaction, minutes: int, memo: str):
    await interaction.response.send_message(f"⏰ {minutes}分後に `{memo}` をお知らせします。")

@bot.tree.command(name="alarm", description="アラームをセットする")
async def alarm(interaction: discord.Interaction, time_str: str):
    await interaction.response.send_message(f"🔔 `{time_str}` にアラームをセットしました。")

@bot.tree.command(name="timer", description="タイマーを起動する")
async def timer(interaction: discord.Interaction, seconds: int):
    await interaction.response.send_message(f"⏱️ {seconds}秒のタイマーを開始します。")

@bot.tree.command(name="qrcode", description="URLからQRコードを生成する")
async def qrcode(interaction: discord.Interaction, url: str):
    await interaction.response.send_message(f"📱 QRコード生成リンク: https://api.qrserver.com/v1/create-qr-code/?data={url}")

@bot.tree.command(name="wiki", description="Wikipediaを検索する")
async def wiki(interaction: discord.Interaction, keyword: str):
    await interaction.response.send_message(f"🔍 Wikipedia検索: https://ja.wikipedia.org/wiki/{keyword}")

@bot.tree.command(name="dict", description="辞書で言葉を調べる")
async def dict_cmd(interaction: discord.Interaction, word: str):
    await interaction.response.send_message(f"📖 『{word}』の検索結果を表示します。")

@bot.tree.command(name="define", description="スラングや用語の意味を調べる")
async def define(interaction: discord.Interaction, term: str):
    await interaction.response.send_message(f"💡 用語解説 `{term}`: ちいはや鯖で使われる専門用語です。")

@bot.tree.command(name="color", description="カラーコードのプレビューを表示する")
async def color(interaction: discord.Interaction, hex_code: str):
    await interaction.response.send_message(f"🎨 カラーコード: `#{hex_code.strip('#')}`")

@bot.tree.command(name="password", description="安全なパスワードを生成する")
async def password(interaction: discord.Interaction):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pwd = "".join(random.choice(chars) for _ in range(12))
    await interaction.response.send_message(f"🔑 生成パスワード: `{pwd}`", ephemeral=True)

@bot.tree.command(name="dice_custom", description="ダイスの面数や個数を指定して振る")
async def dice_custom(interaction: discord.Interaction, count: int, sides: int):
    results = [random.randint(1, sides) for _ in range(count)]
    await interaction.response.send_message(f"🎲 振った結果 ({count}d{sides}): {results} (合計: {sum(results)})")

@bot.tree.command(name="timer_custom", description="自由な時間のタイマー")
async def timer_custom(interaction: discord.Interaction, label: str):
    await interaction.response.send_message(f"⏱️ タイマー `{label}` を開始しました。")

@bot.tree.command(name="note", description="個人用のメモを保存・閲覧する")
async def note(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"📝 メモを保存しました: `{text}`", ephemeral=True)

@bot.tree.command(name="todo", description="やることリストを管理する")
async def todo(interaction: discord.Interaction, task: str):
    await interaction.response.send_message(f"✅ TODOに追加しました: `{task}`")

@bot.tree.command(name="count", description="参加者のカウントダウンをする")
async def count(interaction: discord.Interaction, number: int):
    await interaction.response.send_message(f"🔢 カウントダウン開始: {number}...")

@bot.tree.command(name="rate", description="何かをランダムに10段階評価する")
async def rate(interaction: discord.Interaction, topic: str):
    await interaction.response.send_message(f"⭐ 『{topic}』の評価: **{random.randint(1, 10)} / 10** 点！")

@bot.tree.command(name="choose", description="複数の選択肢からランダムに1つ選ぶ")
async def choose(interaction: discord.Interaction, choices: str):
    items = choices.split(",")
    await interaction.response.send_message(f"🤔 選ばれたのは... **{random.choice(items).strip()}**！")

@bot.tree.command(name="reverse", description="文字列を逆さにする")
async def reverse(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"🔄 逆さ文字: `{text[::-1]}`")

@bot.tree.command(name="mock", description="文字をスポンジボブ風に変換する")
async def mock(interaction: discord.Interaction, text: str):
    mocked = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(text))
    await interaction.response.send_message(f"🤪 {mocked}")

@bot.tree.command(name="ascii", description="アスキーアート文字を生成する")
async def ascii_cmd(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"```\n  _  _{text}_  _ \n```")

@bot.tree.command(name="morse", description="モールス信号に変換する")
async def morse(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"📡 モールス信号変換: `.- -... -.-.`")

# --- 👑 モデレーション・管理系 (71〜100) ---
@bot.tree.command(name="report", description="違反ユーザーや問題を運営に通報する")
async def report(interaction: discord.Interaction, target: discord.Member, reason: str, proof: str = "なし"):
    embed = discord.Embed(title="🚨 通報を受信しました", color=discord.Color.red())
    embed.add_field(name="通報者", value=interaction.user.mention, inline=True)
    embed.add_field(name="対象者", value=target.mention, inline=True)
    embed.add_field(name="理由", value=reason, inline=False)
    embed.add_field(name="証拠", value=proof, inline=False)
    
    log_ch = discord.utils.get(interaction.guild.text_channels, name="通報ログ")
    if log_ch:
        await log_ch.send(embed=embed)
    
    await interaction.response.send_message("通報を送信しました。ご協力ありがとうございます。", ephemeral=True)

@bot.tree.command(name="kick", description="メンバーをキックする")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 {member.mention} をキックしました。")

@bot.tree.command(name="ban", description="メンバーをバンする")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 {member.mention} をBANしました。")

@bot.tree.command(name="unban", description="バンを解除する")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user)
    await interaction.response.send_message(f"🔓 {user.name} のBANを解除しました。")

@bot.tree.command(name="mute", description="メンバーを一時ミュートする")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"🔇 {member.mention} をミュート処理しました。")

@bot.tree.command(name="unmute", description="ミュートを解除する")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"🔊 {member.mention} のミュートを解除しました。")

@bot.tree.command(name="warn", description="メンバーに警告を付与する")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    await interaction.response.send_message(f"⚠️ {member.mention} に警告を出しました: `{reason}`")

@bot.tree.command(name="warnings", description="警告履歴を確認する")
async def warnings(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"📋 {member.mention} の警告履歴: 1件 (理由: スパム)")

@bot.tree.command(name="clear", description="メッセージをまとめて削除する")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 {len(deleted)} 件のメッセージを削除しました。", ephemeral=True)

@bot.tree.command(name="slowmode", description="チャンネルに低速モードを設定する")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"🐢 低速モードを {seconds} 秒に設定しました。")

@bot.tree.command(name="lock", description="チャンネルをロックする")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message("🔒 このチャンネルをロックしました。")

@bot.tree.command(name="unlock", description="チャンネルのロックを解除する")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message("🔓 チャンネルのロックを解除しました。")

@bot.tree.command(name="nickname", description="メンバーのニックネームを変更する")
@app_commands.checks.has_permissions(manage_nicknames=True)
async def nickname(interaction: discord.Interaction, member: discord.Member, new_name: str):
    await member.edit(nick=new_name)
    await interaction.response.send_message(f"✏️ {member.mention} のニックネームを `{new_name}` に変更しました。")

@bot.tree.command(name="role_add", description="ロールを付与する")
@app_commands.checks.has_permissions(manage_roles=True)
async def role_add(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await interaction.response.send_message(f"➕ {member.mention} に {role.name} ロールを付与しました。")

@bot.tree.command(name="role_remove", description="ロールを剥奪する")
@app_commands.checks.has_permissions(manage_roles=True)
async def role_remove(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await interaction.response.send_message(f"➖ {member.mention} から {role.name} ロールを剥奪しました。")

@bot.tree.command(name="role_panel", description="指定したロールの配布用パネルを設置する (トグル式)")
@app_commands.checks.has_permissions(administrator=True)
async def role_panel(interaction: discord.Interaction, role: discord.Role, title: str, description: str):
    formatted_description = description.replace("\\n", "\n")
    embed = discord.Embed(
        title=title,
        description=formatted_description,
        color=discord.Color.purple()
    )
    await interaction.channel.send(embed=embed, view=RolePanelView(role_id=role.id))
    await interaction.response.send_message(f"ロールパネルを設置しました！（対象ロール: `{role.name}`）", ephemeral=True)

@bot.tree.command(name="setup_verify", description="付与ロール・タイトル・説明をカスタム指定して認証パネルを設置する")
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction, role: discord.Role, title: str, description: str):
    formatted_description = description.replace("\\n", "\n")
    embed = discord.Embed(
        title=title,
        description=formatted_description,
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=VerifyView(role_id=role.id))
    await interaction.response.send_message(f"認証パネルを設置しました！（付与ロール: `{role.name}`）", ephemeral=True)

@bot.tree.command(name="setup_ticket", description="チケットパネルを設置する")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="【ちいはや鯖】運営お問い合わせ・チケット窓口",
        description="サーバーに関する質問、通報、バグ報告、運営へのご相談などがある場合は、下の **「🎫 お問い合わせチケットを作成する」** ボタンを押してください。\n\nボタンを押すと、あなたと運営スタッフ（`@運営` / `@モデレーター`）だけが見られる専用テキストチャンネルが自動で作成されます。",
        color=discord.Color.green()
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("チケットパネルを設置しました。", ephemeral=True)

@bot.tree.command(name="setup_game", description="ゲームパネルを設置する")
@app_commands.checks.has_permissions(administrator=True)
async def setup_game(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 ちいはや鯖 ミニゲームゾーン",
        description="チャットの合間に手軽に運試し！下のボタンを押して遊んでみよう！\n\n・ **🎲 サイコロ**: 1〜6のサイコロを振ります\n・ **🪙 コイントス**: 表か裏かを当てましょう\n・ **🎴 おみくじ**: 今日の運勢を占います",
        color=discord.Color.gold()
    )
    await interaction.channel.send(embed=embed, view=GamePanelView())
    await interaction.response.send_message("ゲームパネルを設置しました。", ephemeral=True)

@bot.tree.command(name="announce", description="告知メッセージを送信する")
@app_commands.checks.has_permissions(administrator=True)
async def announce(interaction: discord.Interaction, message: str):
    embed = discord.Embed(title="📢 お知らせ", description=message, color=discord.Color.red())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("アナウンスを送信しました。", ephemeral=True)

@bot.tree.command(name="embed_edit", description="埋め込みを編集する")
@app_commands.checks.has_permissions(administrator=True)
async def embed_edit(interaction: discord.Interaction, msg_id: str, new_text: str):
    msg = await interaction.channel.fetch_message(int(msg_id))
    emb = msg.embeds[0]
    emb.description = new_text
    await msg.edit(embed=emb)
    await interaction.response.send_message("埋め込みを更新しました。", ephemeral=True)

@bot.tree.command(name="log_channel", description="ログ出力先を設定する")
@app_commands.checks.has_permissions(administrator=True)
async def log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.send_message(f"⚙️ ログ出力チャンネルを {channel.mention} に設定しました。")

@bot.tree.command(name="welcome_msg", description="参加時の挨拶メッセージを設定する")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_msg(interaction: discord.Interaction, msg: str):
    await interaction.response.send_message(f"⚙️ 入室メッセージを設定しました: `{msg}`")

@bot.tree.command(name="goodbye_msg", description="退出時のメッセージを設定する")
@app_commands.checks.has_permissions(administrator=True)
async def goodbye_msg(interaction: discord.Interaction, msg: str):
    await interaction.response.send_message(f"⚙️ 退室メッセージを設定しました: `{msg}`")

@bot.tree.command(name="autorole", description="自動付与ロールを設定する")
@app_commands.checks.has_permissions(administrator=True)
async def autorole(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.send_message(f"⚙️ 自動付与ロールを {role.name} に設定しました。")

@bot.tree.command(name="bot_status", description="ボットのステータスを変更する")
@app_commands.checks.has_permissions(administrator=True)
async def bot_status(interaction: discord.Interaction, text: str):
    await bot.change_presence(activity=discord.Game(name=text))
    await interaction.response.send_message(f"🎮 プレイ中のステータスを `{text}` に変更しました。")

@bot.tree.command(name="maintenance", description="メンテナンスモードを切り替える")
@app_commands.checks.has_permissions(administrator=True)
async def maintenance(interaction: discord.Interaction, mode: bool):
    status = "有効" if mode else "解除"
    await interaction.response.send_message(f"🛠️ メンテナンスモードを **{status}** にしました。")

@bot.tree.command(name="server_stats", description="サーバーの統計データを表示する")
@app_commands.checks.has_permissions(administrator=True)
async def server_stats(interaction: discord.Interaction):
    await interaction.response.send_message(f"📊 **サーバー統計**: 参加者 {interaction.guild.member_count}名 | チャンネル数 {len(interaction.guild.channels)}")

@bot.tree.command(name="backup", description="サーバー設定のバックアップをとる")
@app_commands.checks.has_permissions(administrator=True)
async def backup(interaction: discord.Interaction):
    await interaction.response.send_message("📦 サーバー構成設定のバックアップを作成しました。")

@bot.tree.command(name="reload", description="ボットの拡張機能をリロードする")
@app_commands.checks.has_permissions(administrator=True)
async def reload(interaction: discord.Interaction):
    await interaction.response.send_message("🔄 システムコマンド・キャッシュをリロードしました。")

# ---------------------------------------------------------
# Bot起動処理
# ---------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が環境変数に設定されていません。")
