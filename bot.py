import os
import io
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands

JST = timezone(timedelta(hours=+9))
post_count = 0

# ==========================================
# 1. Webサーバー (Render用)
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
# 2. UIコンポーネント（永続化対応）
# ==========================================
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

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="panel_btn_anon")
    async def cb_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextPostModal(is_anonymous=True))

    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.primary, custom_id="panel_btn_named")
    async def cb_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextPostModal(is_anonymous=False))

    @discord.ui.button(label="匿名画像", style=discord.ButtonStyle.success, custom_id="panel_btn_img_anon")
    async def cb_img_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_private_upload_thread(interaction, is_anonymous=True)

    @discord.ui.button(label="非匿名画像", style=discord.ButtonStyle.success, custom_id="panel_btn_img_named")
    async def cb_img_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_private_upload_thread(interaction, is_anonymous=False)

class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        target_id = f"_{post_num}"
        reply_str = f"#{post_num}"

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
            await create_private_upload_thread(interaction, is_anonymous=True, reply_target=reply_str)
        btn_img_anon.callback = cb_img_anon
        self.add_item(btn_img_anon)

        btn_img_named = discord.ui.Button(label="非匿名画像", style=discord.ButtonStyle.success, custom_id=f"btn_img_named{target_id}", row=0)
        async def cb_img_named(interaction: discord.Interaction):
            await create_private_upload_thread(interaction, is_anonymous=False, reply_target=reply_str)
        btn_img_named.callback = cb_img_named
        self.add_item(btn_img_named)

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

# ==========================================
# 3. Bot本体・処理
# ==========================================
TOKEN = os.environ.get("DISCORD_TOKEN")
BOARD_CHANNEL_ID = 1543324230018408592
LOG_CHANNEL_ID = 1543053996950945844

intents = discord.Intents.default()
intents.message_content = True

class CustomBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(PanelView())

bot = CustomBot(command_prefix="!", intents=intents)

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

    raw_text = content if content else "（メディア投稿）"
    body_text = f"> **{reply_target} への返信**\n" + raw_text if reply_target else raw_text
    author_name = "匿名" if is_anonymous else interaction.user.display_name

    embed = discord.Embed(description=body_text, color=0x000000)
    header_text = f"#{post_count} | {author_name} | {now_jst}"

    if is_anonymous:
        embed.set_author(name=header_text)
    else:
        embed.set_author(name=header_text, icon_url=interaction.user.display_avatar.url)

    post_view = PostItemView(post_num=post_count)
    
    if files:
        sent_msg = await board_channel.send(embed=embed, files=files, view=post_view)
    else:
        sent_msg = await board_channel.send(embed=embed, view=post_view)

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
        log_embed.add_field(name="🖼️ メディア添付", value=has_file, inline=True)
        log_embed.add_field(name="⏰ 投稿時間", value=now_jst, inline=True)
        log_embed.add_field(name="🔗 メッセージリンク", value=sent_msg.jump_url, inline=False)
        
        await log_channel.send(embed=log_embed)

    if not interaction.response.is_done():
        await interaction.response.send_message("投稿が完了しました！", ephemeral=True)

# 移動しやすいよう「スレッドへ移動」ボタンリンクを提示する仕組み
async def create_private_upload_thread(interaction: discord.Interaction, is_anonymous: bool, reply_target: str = None):
    channel = interaction.channel
    anon_str = "匿名" if is_anonymous else "非匿名"
    target_str = f"（{reply_target} 宛て）" if reply_target else ""

    thread = await channel.create_thread(
        name=f"🔒-{anon_str}-メディアアップロード-{interaction.user.name}",
        type=discord.ChannelType.private_thread,
        auto_archive_duration=60,
        invitable=False
    )
    
    await thread.add_user(interaction.user)

    target_tag = f"R:{reply_target}" if reply_target else "R:NONE"
    await thread.send(f"__SYS_CONFIG__ | A:{is_anonymous} | {target_tag} | U:{interaction.user.id}", delete_after=0)

    await thread.send(
        f"📷 **【{anon_str}画像・動画投稿{target_str}】**\n"
        f"{interaction.user.mention} ここに画像や動画を送信してください。\n"
        f"※送信完了後、この部屋は自動的に削除されます。"
    )

    # 1タップで移動できるダイレクトURLボタンを設置
    thread_view = discord.ui.View()
    thread_button = discord.ui.Button(
        label="👉 送信部屋へ移動する",
        style=discord.ButtonStyle.link,
        url=thread.jump_url
    )
    thread_view.add_item(thread_button)

    await interaction.response.send_message(
        f"🔒 自分専用の送信部屋を作成しました！下のボタンを押して移動してください。",
        view=thread_view,
        ephemeral=True
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.Thread) and message.channel.name.startswith("🔒-"):
        thread = message.channel

        is_anonymous = True
        reply_target = None
        
        async for history_msg in thread.history(limit=10, oldest_first=True):
            if "__SYS_CONFIG__" in history_msg.content:
                parts = history_msg.content.split(" | ")
                is_anonymous = (parts[1].split(":")[1] == "True")
                target_val = parts[2].split(":")[1]
                reply_target = target_val if target_val != "NONE" else None
                break

        files = []
        for attachment in message.attachments:
            file_bytes = await attachment.read()
            files.append(discord.File(fp=io.BytesIO(file_bytes), filename=attachment.filename))

        fake_interaction = type('obj', (object,), {
            'user': message.author,
            'response': type('obj', (object,), {'is_done': lambda: True})()
        })()

        await send_board_post(
            interaction=fake_interaction,
            content=message.content,
            is_anonymous=is_anonymous,
            reply_target=reply_target,
            files=files
        )

        try:
            await thread.delete()
        except Exception:
            pass
        return

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="setup_panel", description="掲示板パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 掲示板",
        description="匿名 非匿名で投稿?!\n"
                    "画像投稿時は「匿名画像」または「非匿名画像」を押した後に画像をチャットへ送信します。",
        color=0x000000
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

@bot.tree.command(name="nuke", description="実行したチャンネルのメッセージをすべて消去して再作成します")
@app_commands.checks.has_permissions(administrator=True)
async def nuke(interaction: discord.Interaction):
    channel = interaction.channel
    position = channel.position
    
    await interaction.response.send_message("💣 チャンネルをリセットしています...", ephemeral=True)
    
    new_channel = await channel.clone(reason="Nuke command executed")
    await new_channel.edit(position=position)
    await channel.delete(reason="Nuke command executed")
    
    embed = discord.Embed(
        title="💥 Nuke 完了",
        description="このチャンネルの全メッセージが消去されました。",
        color=0xff0000
    )
    await new_channel.send(embed=embed)

@nuke.error
async def nuke_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ このコマンドを実行するには「管理者権限」が必要です。", ephemeral=True)

if __name__ == "__main__":
    if TOKEN:
        keep_alive()
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
