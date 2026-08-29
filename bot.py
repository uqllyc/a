import os
import threading
import asyncio
from datetime import datetime, timezone, timedelta
from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands

JST = timezone(timedelta(hours=+9))
post_count = 0
pending_image_users = {}

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
        # メッセージを出さずに内部応答のみ行ってタイムアウトを防止
        await interaction.response.defer(ephemeral=True)
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
        await interaction.response.defer(ephemeral=True)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            return

        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
        report_embed = discord.Embed(title="🚨【通報】", description=self.report_reason.value, color=0xff0000)
        report_embed.add_field(name="通報者", value=f"{interaction.user.mention} ({interaction.user.name} / ID: `{interaction.user.id}`)")
        report_embed.add_field(name="通報日時", value=now_jst)

        await log_channel.send(embed=report_embed)

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="panel_btn_anon")
    async def cb_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextPostModal(is_anonymous=True))

    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.primary, custom_id="panel_btn_named")
    async def cb_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextPostModal(is_anonymous=False))

    @discord.ui.button(label="匿名メディア", style=discord.ButtonStyle.success, custom_id="panel_btn_img_anon")
    async def cb_img_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await prompt_image_upload(interaction, is_anonymous=True)

    @discord.ui.button(label="非匿名メディア", style=discord.ButtonStyle.success, custom_id="panel_btn_img_named")
    async def cb_img_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await prompt_image_upload(interaction, is_anonymous=False)

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

        btn_img_anon = discord.ui.Button(label="匿名メディア", style=discord.ButtonStyle.success, custom_id=f"btn_img_anon{target_id}", row=0)
        async def cb_img_anon(interaction: discord.Interaction):
            await prompt_image_upload(interaction, is_anonymous=True)
        btn_img_anon.callback = cb_img_anon
        self.add_item(btn_img_anon)

        btn_img_named = discord.ui.Button(label="非匿名メディア", style=discord.ButtonStyle.success, custom_id=f"btn_img_named{target_id}", row=0)
        async def cb_img_named(interaction: discord.Interaction):
            await prompt_image_upload(interaction, is_anonymous=False)
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
BOARD_CHANNEL_ID = 1543316045786386493
LOG_CHANNEL_ID = 1543053996950945844

intents = discord.Intents.default()
intents.message_content = True

class CustomBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(PanelView())

bot = CustomBot(command_prefix="!", intents=intents)

async def send_board_post(interaction: discord.Interaction, content: str, is_anonymous: bool, reply_target: str = None, media_urls: list = None):
    global post_count
    board_channel = bot.get_channel(BOARD_CHANNEL_ID)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if not board_channel:
        return

    post_count += 1
    now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    raw_text = content if content else "（メディア投稿）"
    body_text = f"> **{reply_target} への返信**\n" + raw_text if reply_target else raw_text
    
    if media_urls:
        urls_str = "\n".join(media_urls)
        body_text += f"\n{urls_str}"

    author_name = "匿名" if is_anonymous else interaction.user.display_name

    embed = discord.Embed(description=body_text, color=0x000000)
    header_text = f"#{post_count} | {author_name} | {now_jst}"

    if is_anonymous:
        embed.set_author(name=header_text)
    else:
        embed.set_author(name=header_text, icon_url=interaction.user.display_avatar.url)

    post_view = PostItemView(post_num=post_count)
    sent_msg = await board_channel.send(embed=embed, view=post_view)

    if log_channel:
        log_embed = discord.Embed(
            title=f"📋 【投稿ログ #{post_count}】",
            description=body_text,
            color=0x2b2d31
        )
        user_info = f"{interaction.user.mention}\n**名前:** {interaction.user.name}\n**ID:** `{interaction.user.id}`"
        log_embed.add_field(name="👤 投稿者（本人）", value=user_info, inline=True)
        log_embed.add_field(name="👁️ 表示形式", value="匿名" if is_anonymous else "非匿名", inline=True)
        
        if reply_target:
            log_embed.add_field(name="💬 返信先", value=reply_target, inline=True)
            
        has_file = "あり" if media_urls else "なし"
        log_embed.add_field(name="🖼️ メディア添付", value=has_file, inline=True)
        log_embed.add_field(name="⏰ 投稿時間", value=now_jst, inline=True)
        log_embed.add_field(name="🔗 メッセージリンク", value=sent_msg.jump_url, inline=False)
        
        await log_channel.send(embed=log_embed)

async def prompt_image_upload(interaction: discord.Interaction, is_anonymous: bool, reply_target: str = None):
    pending_image_users[interaction.user.id] = {
        "is_anonymous": is_anonymous,
        "reply_target": reply_target
    }
    anon_str = "匿名" if is_anonymous else "非匿名"
    target_str = f"（{reply_target} 宛て）" if reply_target else ""
    
    await interaction.response.send_message(
        f"📷 **【{anon_str}メディア投稿{target_str}】**\n"
        f"このチャンネルに画像または動画をそのまま送信してください。\n"
        f"※送信後に元のメッセージは自動削除され、掲示板へ反映されます。",
        ephemeral=True
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id == BOARD_CHANNEL_ID:
        user_id = message.author.id

        if user_id in pending_image_users:
            config = pending_image_users.pop(user_id)
            media_urls = [att.url for att in message.attachments]

            fake_interaction = type('obj', (object,), {
                'user': message.author
            })()

            await send_board_post(
                interaction=fake_interaction,
                content=message.content,
                is_anonymous=config["is_anonymous"],
                reply_target=config["reply_target"],
                media_urls=media_urls
            )
            
            try:
                await message.delete()
            except Exception:
                pass
            return

        try:
            await message.delete()
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
        description="匿名・非匿名で投稿可能です。\n"
                    "画像や動画の投稿は「匿名メディア」または「非匿名メディア」を押した後にチャットへ送信してください。",
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
