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
BOARD_CHANNEL_ID = int(os.environ.get("BOARD_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- 自分にしか見えない投稿フォームモーダル ---
class EphemeralPostModal(discord.ui.Modal):
    def __init__(self, is_anonymous: bool, reply_target: str = None):
        self.is_anonymous = is_anonymous
        self.reply_target = reply_target
        
        target_str = f"（{reply_target} 宛て）" if reply_target else ""
        type_str = "匿名投稿" if is_anonymous else "非匿名投稿"
        
        super().__init__(title=f"{type_str}{target_str}")

        self.post_content = discord.ui.TextInput(
            label='投稿本文',
            style=discord.TextStyle.paragraph,
            placeholder='本文を入力してください...',
            required=False,
            max_length=2000,
        )
        self.add_item(self.post_content)

        self.image_url = discord.ui.TextInput(
            label='画像URL (任意)',
            style=discord.TextStyle.short,
            placeholder='https://... (画像がある場合はURLを貼れます)',
            required=False,
        )
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        global post_count
        
        board_channel = bot.get_channel(BOARD_CHANNEL_ID)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not board_channel:
            await interaction.response.send_message("エラー: 投稿先のチャンネルが見つかりません。", ephemeral=True)
            return

        post_count += 1
        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

        raw_text = self.post_content.value if self.post_content.value else "（画像のみ）"

        if self.reply_target:
            body_text = f"> **{self.reply_target} への返信**\n" + raw_text
        else:
            body_text = raw_text

        author_name = "匿名" if self.is_anonymous else interaction.user.display_name

        embed = discord.Embed(description=body_text, color=0x000000)
        header_text = f"#{post_count} | {author_name} | {now_jst}"

        if self.is_anonymous:
            embed.set_author(name=header_text)
        else:
            embed.set_author(name=header_text, icon_url=interaction.user.display_avatar.url)

        # 画像URLが入力されている場合
        img_url_val = self.image_url.value.strip() if self.image_url.value else ""
        if img_url_val.startswith("http://") or img_url_val.startswith("https://"):
            embed.set_image(url=img_url_val)

        # 掲示板へ送信
        post_view = PostItemView(post_num=post_count)
        sent_msg = await board_channel.send(embed=embed, view=post_view)

        # 自分だけに送信完了通知（他の人には見えない）
        await interaction.response.send_message("掲示板に投稿しました！", ephemeral=True)

        # ログの記録
        if log_channel:
            log_embed = discord.Embed(
                title=f"【投稿ログ #{post_count}】",
                description=raw_text,
                color=0x2b2d31
            )
            log_embed.add_field(name="投稿者", value=f"{interaction.user.mention} ({interaction.user.id})")
            log_embed.add_field(name="表示タイプ", value="匿名" if self.is_anonymous else "非匿名")
            log_embed.add_field(name="投稿時間", value=now_jst)
            log_embed.add_field(name="対象メッセージ", value=sent_msg.jump_url)
            await log_channel.send(embed=log_embed)

# --- 自分にしか見えない案内画面を送る処理 ---
async def open_private_post_window(interaction: discord.Interaction, is_anonymous: bool, reply_target: str = None):
    # 自分だけにしか見えない入力フォームを開く
    await interaction.response.send_modal(EphemeralPostModal(is_anonymous=is_anonymous, reply_target=reply_target))

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
        report_embed.add_field(name="通報者", value=f"{interaction.user.mention} ({interaction.user.id})")
        report_embed.add_field(name="通報日時", value=now_jst)
        
        await log_channel.send(embed=report_embed)
        await interaction.response.send_message("通報を送信しました。", ephemeral=True)

# --- 直接メッセージ（誤送信）は最速で消去 ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    try:
        await message.delete()
    except Exception:
        pass

    await bot.process_commands(message)

# ==========================================
# 各投稿メッセージの下につくボタン一覧
# ==========================================
class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        self.post_num = post_num

    # 1. 匿名
    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="item_post_anon")
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_private_post_window(interaction, is_anonymous=True)

    # 2. 非匿名
    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.secondary, custom_id="item_post_named")
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_private_post_window(interaction, is_anonymous=False)

    # 3. 匿名返信
    @discord.ui.button(label="匿名返信", style=discord.ButtonStyle.success, custom_id="item_reply_anon")
    async def reply_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_private_post_window(interaction, is_anonymous=True, reply_target=f"#{self.post_num}")

    # 4. 非匿名返信
    @discord.ui.button(label="非匿名返信", style=discord.ButtonStyle.secondary, custom_id="item_reply_named")
    async def reply_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_private_post_window(interaction, is_anonymous=False, reply_target=f"#{self.post_num}")

    # 5. 通報
    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(target_post=f"#{self.post_num}"))

# --- メインパネルのボタン設定 ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_private_post_window(interaction, is_anonymous=True)

    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_private_post_window(interaction, is_anonymous=False)

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="btn_report")
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

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
        description="**匿名**: 名前を隠して投稿\n"
                    "**非匿名**: ユーザー名を表示して投稿\n"
                    "**通報**: 違反投稿を通知",
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
