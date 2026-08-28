import os
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask
import discord
from discord.ext import commands

# JST（日本時間）の定義
JST = timezone(timedelta(hours=+9))
post_count = 0

app = Flask(__name__)

TOKEN = os.environ.get("DISCORD_TOKEN")
BOARD_CHANNEL_ID = int(os.environ.get("BOARD_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Keep-alive 用の最小限 Flask Web サーバー
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
# 投稿用モーダル (Discord内で直接入力する枠)
# ==========================================
class PostModal(discord.ui.Modal):
    def __init__(self, is_anon: bool, reply_target: str = None):
        title_type = "匿名投稿" if is_anon else "名前表示投稿"
        if reply_target:
            title_type += f" ({reply_target}へ返信)"
        
        super().__init__(title=title_type)
        self.is_anon = is_anon
        self.reply_target = reply_target

        # メッセージ入力枠（大きめの縦長エリア）
        self.content_input = discord.ui.TextInput(
            label='メッセージ本文',
            style=discord.TextStyle.paragraph,
            placeholder='ここに投稿内容を入力してください...',
            required=True,
            max_length=2000,
            row=0
        )
        self.add_item(self.content_input)

        # 画像URL入力枠（任意）
        self.image_url_input = discord.ui.TextInput(
            label='画像URL（任意）',
            style=discord.TextStyle.short,
            placeholder='https://... (画像の直リンクがあれば入力)',
            required=False,
            row=1
        )
        self.add_item(self.image_url_input)

    async def on_submit(self, interaction: discord.Interaction):
        global post_count
        await interaction.response.defer(ephemeral=True)

        post_count += 1
        board_channel = bot.get_channel(BOARD_CHANNEL_ID)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not board_channel:
            await interaction.followup.send("エラー: BOARD_CHANNEL_ID が設定されていません。", ephemeral=True)
            return

        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

        body_text = self.content_input.value
        if self.reply_target:
            body_text = f"> **{self.reply_target} への返信**\n" + body_text

        display_author = "匿名" if self.is_anon else interaction.user.display_name
        
        # 背景色になじむ真っ黒寄りの埋め込みカラー (0x000000)
        embed = discord.Embed(description=body_text, color=0x000000)
        header_text = f"#{post_count} | {display_author} | {now_jst}"

        if self.is_anon:
            embed.set_author(name=header_text)
        else:
            embed.set_author(name=header_text, icon_url=interaction.user.display_avatar.url)

        # 画像URLが指定されている場合の設定
        img_url = self.image_url_input.value.strip()
        if img_url and (img_url.startswith("http://") or img_url.startswith("https://")):
            embed.set_image(url=img_url)

        post_view = PostItemView(post_num=post_count)
        sent_msg = await board_channel.send(embed=embed, view=post_view)

        # ログ送信
        if log_channel:
            log_embed = discord.Embed(
                title=f"【投稿ログ #{post_count}】",
                description=body_text,
                color=0x2b2d31
            )
            log_embed.add_field(name="投稿者", value=f"{interaction.user.mention} ({interaction.user.id})")
            log_embed.add_field(name="表示タイプ", value="匿名" if self.is_anon else "名前表示")
            log_embed.add_field(name="投稿時間", value=now_jst)
            log_embed.add_field(name="対象メッセージ", value=sent_msg.jump_url)
            await log_channel.send(embed=log_embed)

        await interaction.followup.send("投稿が送信されました！", ephemeral=True)

# ==========================================
# ボタン配置・各種コンポーネント
# ==========================================
class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        self.post_num = post_num

    @discord.ui.button(label="匿名返信", style=discord.ButtonStyle.primary, custom_id="item_reply_anon")
    async def reply_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anon=True, reply_target=f"#{self.post_num}"))

    @discord.ui.button(label="名前返信", style=discord.ButtonStyle.secondary, custom_id="item_reply_named")
    async def reply_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anon=False, reply_target=f"#{self.post_num}"))

    @discord.ui.button(label="匿名投稿", style=discord.ButtonStyle.success, custom_id="item_post_anon")
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anon=True))

    @discord.ui.button(label="名前投稿", style=discord.ButtonStyle.secondary, custom_id="item_post_named")
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anon=False))

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(target_post=f"#{self.post_num}"))

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名で投稿", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anon=True))

    @discord.ui.button(label="名前表示で投稿", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anon=False))

    @discord.ui.button(label="通報する", style=discord.ButtonStyle.danger, custom_id="btn_report")
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

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

# ==========================================
# イベント・コマンド
# ==========================================
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    bot.add_view(PanelView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="setup_panel", description="掲示板パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 掲示板",
        description="🔹 **匿名投稿**: 名前を隠して投稿\n"
                    "⚙️ **名前投稿**: ユーザー名を表示して投稿\n"
                    "🚨 **通報**: 違反投稿を通知",
        color=0x000000
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

if __name__ == "__main__":
    if TOKEN:
        keep_alive()
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
