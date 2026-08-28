import os
import threading
from flask import Flask
import discord
from discord.ext import commands

# ==========================================
# 1. Renderのポート監視エラー（No open ports）回避用Webサーバー
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
# 2. Discord Bot の設定と処理
# ==========================================
TOKEN = os.environ.get("DISCORD_TOKEN")
BOARD_CHANNEL_ID = int(os.environ.get("BOARD_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- 投稿用モーダル（匿名・記名共通） ---
class PostModal(discord.ui.Modal):
    def __init__(self, is_anonymous: bool):
        self.is_anonymous = is_anonymous
        # モーダルのタイトルを動的に変更
        title_text = '📝 投稿フォーム（匿名）' if is_anonymous else '📝 投稿フォーム（公開名）'
        super().__init__(title=title_text)

        self.content = discord.ui.TextInput(
            label='投稿内容',
            style=discord.TextStyle.paragraph,
            placeholder='ここにメッセージを入力してください...',
            required=True,
            max_length=1000,
        )
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        board_channel = bot.get_channel(BOARD_CHANNEL_ID)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not board_channel:
            await interaction.response.send_message(
                "エラー: 投稿先のチャンネルが見つかりません。BOARD_CHANNEL_IDを確認してください。", 
                ephemeral=True
            )
            return

        # 掲示板用 Embed
        embed = discord.Embed(
            description=self.content.value,
            color=0x2b2d31
        )
        if self.is_anonymous:
            embed.set_author(name="匿名ユーザー")
        else:
            embed.set_author(
                name=interaction.user.display_name, 
                icon_url=interaction.user.display_avatar.url
            )

        sent_message = await board_channel.send(embed=embed)

        # 管理者ログ用 Embed
        if log_channel:
            log_embed = discord.Embed(
                title="【投稿ログ】",
                description=self.content.value,
                color=0x3498db
            )
            log_embed.add_field(name="投稿者", value=f"{interaction.user.mention} ({interaction.user.id})")
            log_embed.add_field(name="匿名設定", value="有効（匿名）" if self.is_anonymous else "無効（公開）")
            log_embed.add_field(name="対象メッセージ", value=sent_message.jump_url)
            await log_channel.send(embed=log_embed)

        await interaction.response.send_message("投稿が完了しました！", ephemeral=True)


# --- 通報用モーダル ---
class ReportModal(discord.ui.Modal, title='🚨 管理者への通報フォーム'):
    report_reason = discord.ui.TextInput(
        label='通報内容・理由',
        style=discord.TextStyle.paragraph,
        placeholder='違反投稿のURLや不適切な内容、理由などを入力してください...',
        required=True,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not log_channel:
            await interaction.response.send_message(
                "エラー: 通報先（LOG_CHANNEL_ID）が設定されていません。", 
                ephemeral=True
            )
            return

        report_embed = discord.Embed(
            title="🚨【通報が届きました】",
            description=self.report_reason.value,
            color=0xff0000
        )
        report_embed.add_field(name="通報者", value=f"{interaction.user.mention} ({interaction.user.id})")
        report_embed.add_field(name="通報日時", value=discord.utils.format_dt(interaction.created_at, style='F'))
        
        await log_channel.send(embed=report_embed)
        await interaction.response.send_message("通報を管理者に送信しました。ご協力ありがとうございます。", ephemeral=True)


# --- 設置パネルのボタン設定 ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # 1. 匿名投稿ボタン
    @discord.ui.button(label="匿名で投稿", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anonymous=True))

    # 2. 記名（名前表示）投稿ボタン
    @discord.ui.button(label="名前表示で投稿", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal(is_anonymous=False))

    # 3. 通報ボタン
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
                    "🔹 **匿名**: 名前を隠して投稿\n"
                    "⚙️ **非匿名**: Discord名を表示して投稿\n"
                    "🚨 **通報する**: 違反内容を管理者に通知",
        color=0x3498db
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
