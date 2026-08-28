import os
import io
import threading
from datetime import datetime, timezone, timedelta
import aiohttp
from flask import Flask
import discord
from discord.ext import commands

# JST（日本時間）の定義
JST = timezone(timedelta(hours=+9))

# 投稿番号カウンター（メモリ上で管理）
post_count = 0

# ==========================================
# 1. Webサーバー（Render用）
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

# --- 投稿・返信共通モーダル ---
class PostModal(discord.ui.Modal):
    def __init__(self, is_anonymous: bool, reply_target: str = None):
        self.is_anonymous = is_anonymous
        self.reply_target = reply_target
        
        if reply_target:
            title_text = f'💬 返信 ({reply_target}へ)'
            placeholder_text = f'{reply_target} への返信を入力...'
        else:
            title_text = '📝 新規投稿（匿名）' if is_anonymous else '📝 新規投稿（名前表示）'
            placeholder_text = 'ここにメッセージを入力してください...'
            
        super().__init__(title=title_text)

        self.content = discord.ui.TextInput(
            label='メッセージ',
            style=discord.TextStyle.paragraph,
            placeholder=placeholder_text,
            required=True,
            max_length=1000,
        )
        self.add_item(self.content)

        self.image_url = discord.ui.TextInput(
            label='画像URL（任意）',
            style=discord.TextStyle.short,
            placeholder='https://... (画像の直リンクを貼るとDiscord内に取り込みます)',
            required=False,
            max_length=500,
        )
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        global post_count
        post_count += 1

        board_channel = bot.get_channel(BOARD_CHANNEL_ID)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not board_channel:
            await interaction.response.send_message(
                "エラー: 投稿先のチャンネルが見つかりません。BOARD_CHANNEL_IDを確認してください。", 
                ephemeral=True
            )
            return

        # 処理中のメッセージを表示（タイムアウト防止）
        await interaction.response.defer(ephemeral=True)

        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
        author_name = "匿名" if self.is_anonymous else interaction.user.display_name
        
        message_body = self.content.value
        if self.reply_target:
            message_body = f"> **{self.reply_target} への返信**\n" + message_body

        embed = discord.Embed(
            description=message_body,
            color=0x2b2d31
        )
        
        header_text = f"#{post_count} | {author_name} | {now_jst}"

        if self.is_anonymous:
            embed.set_author(name=header_text)
        else:
            embed.set_author(
                name=header_text,
                icon_url=interaction.user.display_avatar.url
            )

        # 外部URLの画像を読み込み、Discord内部ファイルに変換する処理
        file_to_send = None
        img_url = self.image_url.value.strip()

        if img_url and (img_url.startswith("http://") or img_url.startswith("https://")):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(img_url) as resp:
                        if resp.status == 200:
                            img_data = await resp.read()
                            
                            ext = "png"
                            if ".jpg" in img_url.lower() or ".jpeg" in img_url.lower():
                                ext = "jpg"
                            elif ".gif" in img_url.lower():
                                ext = "gif"
                            
                            filename = f"image_{post_count}.{ext}"
                            # Botがファイルとして保持する
                            file_to_send = discord.File(io.BytesIO(img_data), filename=filename)
                            # 埋め込み画像に内部アタッチメントとして指定（外部リンクを遮断）
                            embed.set_image(url=f"attachment://{filename}")
            except Exception as e:
                print(f"画像読み込みエラー: {e}")

        # メッセージ送信（ファイルとしてDiscord内に保存）
        post_view = PostItemView(post_num=post_count)
        if file_to_send:
            sent_message = await board_channel.send(embed=embed, file=file_to_send, view=post_view)
        else:
            sent_message = await board_channel.send(embed=embed, view=post_view)

        # 管理者ログ
        if log_channel:
            log_embed = discord.Embed(
                title=f"【投稿ログ #{post_count}】",
                description=message_body,
                color=0x3498db
            )
            log_embed.add_field(name="投稿者", value=f"{interaction.user.mention} ({interaction.user.id})")
            log_embed.add_field(name="表示タイプ", value="匿名" if self.is_anonymous else "名前表示")
            log_embed.add_field(name="投稿時間", value=now_jst)
            log_embed.add_field(name="対象メッセージ", value=sent_message.jump_url)
            await log_channel.send(embed=log_embed)

        await interaction.followup.send("投稿が完了しました！", ephemeral=True)


# --- 通報用モーダル ---
class ReportModal(discord.ui.Modal):
    def __init__(self, target_post: str = None):
        title_text = f'🚨 通報 ({target_post})' if target_post else '🚨 管理者への通報フォーム'
        super().__init__(title=title_text)

        default_reason = f"{target_post} についての通報: " if target_post else ""
        
        self.report_reason = discord.ui.TextInput(
            label='通報内容・理由',
            style=discord.TextStyle.paragraph,
            placeholder='違反投稿の理由などを入力してください...',
            default=default_reason,
            required=True,
            max_length=1000,
        )
        self.add_item(self.report_reason)

    async def on_submit(self, interaction: discord.Interaction):
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not log_channel:
            await interaction.response.send_message(
                "エラー: 通報先（LOG_CHANNEL_ID）が設定されていません。", 
                ephemeral=True
            )
            return

        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
        report_embed = discord.Embed(
            title="🚨【通報が届きました】",
            description=self.report_reason.value,
            color=0xff0000
        )
        report_embed.add_field(name="通報者", value=f"{interaction.user.mention} ({interaction.user.id})")
        report_embed.add_field(name="通報日時", value=now_jst)
        
        await log_channel.send(embed=report_embed)
        await interaction.response.send_message("通報を管理者に送信しました。", ephemeral=True)


# --- 各投稿メッセージの下につくボタン一覧 ---
class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        self.post_num = post_num

    @discord.ui.button(label="匿名返信", style=discord.ButtonStyle.primary, custom_id="item_reply_anon")
    async def reply_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = f"#{self.post_num}"
        await interaction.response.send_modal(PostModal(is_anonymous=True, reply_target=target))

    @discord.ui.button(label="名前返信", style=discord.ButtonStyle.secondary, custom_id="item_reply_named")
    async def reply_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = f"#{self.post_num}"
        await interaction.response.send_modal(PostModal(is_anonymous=False, reply_target=target))

    @discord.ui.button(label="匿名投稿", style=discord.ButtonStyle.success, custom_id="item_post_anon")
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anonymous=True))

    @discord.ui.button(label="名前投稿", style=discord.ButtonStyle.secondary, custom_id="item_post_named")
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anonymous=False))

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = f"#{self.post_num}"
        await interaction.response.send_modal(ReportModal(target_post=target))


# --- メインパネルのボタン設定 ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名で投稿", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anonymous=True))

    @discord.ui.button(label="名前表示で投稿", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anonymous=False))

    @discord.ui.button(label="通報する", style=discord.ButtonStyle.danger, custom_id="btn_report")
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
@bot.tree.command(name="setup_panel", description="掲示板の投稿・通報パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 掲示板パネル",
        description="用途に合わせて下のボタンを押して投稿してください。\n\n"
                    "🔹 **匿名で投稿**: 名前を隠して新規投稿します\n"
                    "⚙️ **名前表示で投稿**: ユーザー名を表示して新規投稿します\n"
                    "🚨 **通報する**: 違反内容を管理者に通知します",
        color=0x3498db
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

if __name__ == "__main__":
    if TOKEN:
        keep_alive()
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
