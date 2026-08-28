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

# 画像を一時保持する辞書 {user_id: [attachment_files]}
user_images = {}

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

# --- 投稿用ポップアップ（モーダル） ---
class ImagePostModal(discord.ui.Modal):
    def __init__(self, is_anonymous: bool, reply_target: str = None):
        target_str = f"（{reply_target} 宛て）" if reply_target else ""
        anon_str = "匿名" if is_anonymous else "非匿名"
        super().__init__(title=f'{anon_str}投稿{target_str}')

        self.is_anonymous = is_anonymous
        self.reply_target = reply_target

        self.content_input = discord.ui.TextInput(
            label='メッセージ',
            style=discord.TextStyle.paragraph,
            placeholder='メッセージを入力してください（画像のみの場合は空欄でOK）...',
            required=False,
            max_length=2000,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        global post_count

        board_channel = bot.get_channel(BOARD_CHANNEL_ID)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not board_channel:
            await interaction.response.send_message("エラー: BOARD_CHANNEL_IDが設定されていません。", ephemeral=True)
            return

        # 一時保存していた画像データを取得
        files_to_send = user_images.pop(interaction.user.id, [])

        post_count += 1
        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

        raw_text = self.content_input.value if self.content_input.value else "（画像のみ）"

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

        # 掲示板へ投稿送信
        post_view = PostItemView(post_num=post_count)
        if files_to_send:
            sent_msg = await board_channel.send(embed=embed, files=files_to_send, view=post_view)
        else:
            sent_msg = await board_channel.send(embed=embed, view=post_view)

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

        await interaction.response.send_message("投稿が完了しました！", ephemeral=True)

# --- 画像投稿用の匿名/非匿名選択ビュー（DM内） ---
class ImageChoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary)
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=True))

    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.secondary)
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=False))

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

# ==========================================
# 各投稿メッセージの下につくボタン一覧（指定順）
# 配置: 匿名 | 非匿名 | 画像 | 匿名返信 | 非匿名返信 | 通報
# ==========================================
class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        self.post_num = post_num

    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="item_post_anon")
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=True))

    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.secondary, custom_id="item_post_named")
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=False))

    @discord.ui.button(label="画像", style=discord.ButtonStyle.success, custom_id="item_post_image")
    async def post_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📷 **画像投稿の手順**\nこのチャンネルに直接画像を送信（ドラッグ＆ドロップ）してください。\n送信されるとそのまま匿名/非匿名を選んで投稿できます。",
            ephemeral=True
        )

    @discord.ui.button(label="匿名返信", style=discord.ButtonStyle.primary, custom_id="item_reply_anon")
    async def reply_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=True, reply_target=f"#{self.post_num}"))

    @discord.ui.button(label="非匿名返信", style=discord.ButtonStyle.secondary, custom_id="item_reply_named")
    async def reply_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=False, reply_target=f"#{self.post_num}"))

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(target_post=f"#{self.post_num}"))

# --- メインパネルのボタン設定 ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=True))

    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagePostModal(is_anonymous=False))

    @discord.ui.button(label="画像", style=discord.ButtonStyle.success, custom_id="btn_post_image")
    async def open_post_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📷 **画像投稿の手順**\nこのチャンネルに直接画像を送信（ドラッグ＆ドロップ）してください。\n送信されるとそのまま匿名/非匿名を選んで投稿できます。",
            ephemeral=True
        )

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="btn_report")
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

# --- 画像付きメッセージの検知 ＆ 誤送信削除 ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id == BOARD_CHANNEL_ID:
        # 画像が添付されている場合
        if message.attachments:
            files = []
            for attachment in message.attachments:
                file_data = await attachment.to_file()
                files.append(file_data)
            
            user_images[message.author.id] = files

            # 画像メッセージは即削除して他者から見えないようにする
            try:
                await message.delete()
            except Exception:
                pass

            # DMへ「匿名」「非匿名」ボタンを直接送信
            try:
                await message.author.send(
                    content="🖼️ **画像を受け取りました！**\n「匿名」か「非匿名」を選んでメッセージを入力してください。",
                    view=ImageChoiceView()
                )
            except discord.Forbidden:
                pass
            return

        # 画像がない直接メッセージは即削除
        try:
            await message.delete()
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
        description="**匿名 / 非匿名**: テキストのみ投稿\n"
                    "**画像**: 画像付き投稿の手順案内\n"
                    "**通報**: 管理者へ通報",
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
