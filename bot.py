import os
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask
import discord
from discord.ext import commands

# JST（日本時間）の定義
JST = timezone(timedelta(hours=+9))

# 投稿番号カウンター（メモリ上で管理）
post_count = 0

# 画像投稿時の状態管理 {user_id: {"is_anonymous": bool, "reply_target": str or None}}
pending_image_users = {}

# ==========================================
# 1. Renderのポート監視エラー回避用Webサーバー
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# 2. Discord Bot 設定
# ==========================================
TOKEN = os.environ.get("DISCORD_TOKEN")

# ★ここに直接チャンネルID（18〜19桁の数字）を記入してください★
BOARD_CHANNEL_ID = 1542991170760872057  # 掲示板チャンネルID
LOG_CHANNEL_ID = 1542866592566747166    # 管理者用ログチャンネルID

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- 通常投稿用モーダル（テキストのみ） ---
class TextPostModal(discord.ui.Modal):
    def __init__(self, is_anonymous: bool, reply_target: str = None):
        target_str = f"（{reply_target} 宛て）" if reply_target else ""
        anon_str = "匿名" if is_anonymous else "非匿名"
        super().__init__(title=f'{anon_str}投稿{target_str}')

        self.is_anonymous = is_anonymous
        self.reply_target = reply_target

        self.content_input = discord.ui.TextInput(
            label='メッセージ',
            style=discord.TextStyle.paragraph,
            placeholder='メッセージを入力してください...',
            required=True,
            max_length=2000,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        await send_board_post(
            interaction=interaction,
            content=self.content_input.value,
            is_anonymous=self.is_anonymous,
            reply_target=self.reply_target
        )

# --- 通報用モーダル ---
class ReportModal(discord.ui.Modal):
    def __init__(self, target_post: str = None):
        title_text = f'🚨 通報 ({target_post})' if target_post else '🚨 管理者への通報'
        super().__init__(title=title_text)

        default_reason = f"{target_post} について: " if target_post else ""
        
        self.report_reason = discord.ui.TextInput(
            label='通報理由',
            style=discord.TextStyle.paragraph,
            placeholder='理由を入力してください...',
            default=default_reason,
            required=True,
            max_length=1000,
        )
        self.add_item(self.report_reason)

    async def on_submit(self, interaction: discord.Interaction):
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not log_channel:
            await interaction.response.send_message("エラー: LOG_CHANNEL_IDが設定されていません。", ephemeral=True)
            return

        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
        report_embed = discord.Embed(title="🚨【通報】", description=self.report_reason.value, color=0xff0000)
        report_embed.add_field(name="通報者", value=f"{interaction.user.mention} ({interaction.user.name} / ID: `{interaction.user.id}`)")
        report_embed.add_field(name="通報日時", value=now_jst)
        
        await log_channel.send(embed=report_embed)
        await interaction.response.send_message("通報を送信しました。", ephemeral=True)

# --- 投稿処理共通関数 ---
async def send_board_post(interaction: discord.Interaction, content: str, is_anonymous: bool, reply_target: str = None, files: list = None):
    global post_count

    board_channel = bot.get_channel(BOARD_CHANNEL_ID)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if not board_channel:
        if not interaction.response.is_done():
            await interaction.response.send_message("エラー: BOARD_CHANNEL_IDが設定されていません。", ephemeral=True)
        return

    post_count += 1
    now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    raw_text = content if content else "（画像のみ）"

    if reply_target:
        body_text = f"> **{reply_target} への返信**\n" + raw_text
    else:
        body_text = raw_text

    author_name = "匿名" if is_anonymous else interaction.user.display_name

    embed = discord.Embed(description=body_text, color=0x000000)
    header_text = f"#{post_count} | {author_name} | {now_jst}"

    if is_anonymous:
        embed.set_author(name=header_text)
    else:
        embed.set_author(name=header_text, icon_url=interaction.user.display_avatar.url)

    # 各投稿には「7つのボタン（新規4種＋返信2種＋通報）」を添付
    post_view = PostItemView(post_num=post_count)
    
    if files:
        sent_msg = await board_channel.send(embed=embed, files=files, view=post_view)
    else:
        sent_msg = await board_channel.send(embed=embed, view=post_view)

    # ログ送信（管理者用）
    if log_channel:
        log_embed = discord.Embed(
            title=f"📋 【投稿ログ #{post_count}】",
            description=raw_text,
            color=0x2b2d31
        )
        user_info = f"{interaction.user.mention}\n**名前:** {interaction.user.name}\n**ID:** `{interaction.user.id}`"
        log_embed.add_field(name="👤 投稿者（本人）", value=user_info, inline=True)
        log_embed.add_field(name="👁️ 表示形式", value="匿名" if is_anonymous else "非匿名", inline=True)
        
        if reply_target:
            log_embed.add_field(name="💬 返信先", value=reply_target, inline=True)
            
        has_file = "あり" if files else "なし"
        log_embed.add_field(name="🖼️ 画像添付", value=has_file, inline=True)
        log_embed.add_field(name="⏰ 投稿時間", value=now_jst, inline=True)
        log_embed.add_field(name="🔗 メッセージリンク", value=sent_msg.jump_url, inline=False)
        
        await log_channel.send(embed=log_embed)

    if not interaction.response.is_done():
        await interaction.response.send_message("投稿が完了しました！", ephemeral=True)

# --- 画像投稿待機用の案内 ---
async def prompt_image_upload(interaction: discord.Interaction, is_anonymous: bool, reply_target: str = None):
    pending_image_users[interaction.user.id] = {
        "is_anonymous": is_anonymous,
        "reply_target": reply_target
    }
    anon_str = "匿名" if is_anonymous else "非匿名"
    target_str = f"（{reply_target} 宛て）" if reply_target else ""
    
    await interaction.response.send_message(
        f"📷 **【{anon_str}画像投稿{target_str}】**\n"
        f"このチャンネルに画像（＋文章）をそのまま送信してください。\n"
        f"※送信後に投稿メッセージは自動削除され、掲示板へ反映されます。",
        ephemeral=True
    )

# ==========================================
# ボタンコンポーネント
# ==========================================

# 1. メインパネル用（新規投稿のみ：4つ）
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        # 匿名
        btn_anon = discord.ui.Button(label="匿名", style=discord.ButtonStyle.primary, custom_id="panel_btn_anon")
        async def cb_anon(interaction: discord.Interaction):
            await interaction.response.send_modal(TextPostModal(is_anonymous=True))
        btn_anon.callback = cb_anon
        self.add_item(btn_anon)

        # 非匿名
        btn_named = discord.ui.Button(label="非匿名", style=discord.ButtonStyle.primary, custom_id="panel_btn_named")
        async def cb_named(interaction: discord.Interaction):
            await interaction.response.send_modal(TextPostModal(is_anonymous=False))
        btn_named.callback = cb_named
        self.add_item(btn_named)

        # 匿名画像
        btn_img_anon = discord.ui.Button(label="匿名画像", style=discord.ButtonStyle.success, custom_id="panel_btn_img_anon")
        async def cb_img_anon(interaction: discord.Interaction):
            await prompt_image_upload(interaction, is_anonymous=True)
        btn_img_anon.callback = cb_img_anon
        self.add_item(btn_img_anon)

        # 非匿名画像
        btn_img_named = discord.ui.Button(label="非匿名画像", style=discord.ButtonStyle.success, custom_id="panel_btn_img_named")
        async def cb_img_named(interaction: discord.Interaction):
            await prompt_image_upload(interaction, is_anonymous=False)
        btn_img_named.callback = cb_img_named
        self.add_item(btn_img_named)

# 2. 各投稿メッセージ用（7つのボタン：新規4種 + 返信2種 + 通報）
class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        target_id = f"_{post_num}"
        reply_str = f"#{post_num}"

        # --- 1行目: 新規投稿ボタン (4つ) ---
        btn_anon = discord.ui.Button(label="匿名", style=discord.ButtonStyle.primary, custom_id=f"btn_anon{target_id}", row=0)
        async def cb_anon(interaction: discord.Interaction):
            await interaction.response.send_modal(TextPostModal(is_anonymous=True))
        btn_anon.callback = cb_anon
        self.add_item(btn_anon)

        btn_named = discord.ui.Button(label="非匿名", style=discord.ButtonStyle.primary, custom_id=f"btn_named{target_id}", row=0)
        async def cb_named(interaction: discord.Interaction):
            await interaction.response.send_modal(TextPostModal(is_anonymous=False))
        btn_named.callback = cb_named
        self.add_item(btn_named)

        btn_img_anon = discord.ui.Button(label="匿名画像", style=discord.ButtonStyle.success, custom_id=f"btn_img_anon{target_id}", row=0)
        async def cb_img_anon(interaction: discord.Interaction):
            await prompt_image_upload(interaction, is_anonymous=True)
        btn_img_anon.callback = cb_img_anon
        self.add_item(btn_img_anon)

        btn_img_named = discord.ui.Button(label="非匿名画像", style=discord.ButtonStyle.success, custom_id=f"btn_img_named{target_id}", row=0)
        async def cb_img_named(interaction: discord.Interaction):
            await prompt_image_upload(interaction, is_anonymous=False)
        btn_img_named.callback = cb_img_named
        self.add_item(btn_img_named)

        # --- 2行目: 返信 & 通報ボタン (3つ) ---
        btn_reply_anon = discord.ui.Button(label="匿名返信", style=discord.ButtonStyle.secondary, custom_id=f"btn_reply_anon{target_id}", row=1)
        async def cb_reply_anon(interaction: discord.Interaction):
            await interaction.response.send_modal(TextPostModal(is_anonymous=True, reply_target=reply_str))
        btn_reply_anon.callback = cb_reply_anon
        self.add_item(btn_reply_anon)

        btn_reply_named = discord.ui.Button(label="非匿名返信", style=discord.ButtonStyle.secondary, custom_id=f"btn_reply_named{target_id}", row=1)
        async def cb_reply_named(interaction: discord.Interaction):
            await interaction.response.send_modal(TextPostModal(is_anonymous=False, reply_target=reply_str))
        btn_reply_named.callback = cb_reply_named
        self.add_item(btn_reply_named)

        btn_report = discord.ui.Button(label="通報", style=discord.ButtonStyle.danger, custom_id=f"btn_report{target_id}", row=1)
        async def cb_report(interaction: discord.Interaction):
            await interaction.response.send_modal(ReportModal(target_post=reply_str))
        btn_report.callback = cb_report
        self.add_item(btn_report)

# --- メッセージ検知（画像投稿の処理 ＆ 直接入力メッセージ削除） ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id == BOARD_CHANNEL_ID:
        delete_task = bot.loop.create_task(message.delete())

        user_id = message.author.id

        if user_id in pending_image_users:
            config = pending_image_users.pop(user_id)
            
            files = []
            for attachment in message.attachments:
                file_data = await attachment.to_file()
                files.append(file_data)

            try:
                await delete_task
            except Exception:
                pass

            fake_interaction = type('obj', (object,), {
                'user': message.author,
                'response': type('obj', (object,), {'is_done': lambda: True})()
            })()

            await send_board_post(
                interaction=fake_interaction,
                content=message.content,
                is_anonymous=config["is_anonymous"],
                reply_target=config["reply_target"],
                files=files
            )
            return

        try:
            await delete_task
        except Exception:
            pass

    await bot.process_commands(message)

# --- Bot起動処理 ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    bot.add_view(PanelView())
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# --- パネル設置コマンド ---
@bot.tree.command(name="setup_panel", description="掲示板パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 掲示板",
        description="匿名 非匿名で投稿。\n"
                    "画像投稿時は「匿名画像」または「非匿名画像」を押した後に画像をチャットへ送信します。",
        color=0x000000
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

# 実行
if __name__ == "__main__":
    if TOKEN:
        keep_alive()
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
