import os
import threading
from flask import Flask
import discord
from discord.ext import commands

# ==========================================
# 1. Renderのポート監視エラー（No open ports）回避用のWebサーバー
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    # Renderから割り当てられたPORT（デフォルトは10000）でWebサーバーを起動
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# スレッドを使ってバックグラウンドでWebサーバーを実行
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

# --- 投稿入力用フォーム（モーダル） ---
class PostModal(discord.ui.Modal, title='匿名掲示板 投稿フォーム'):
    content = discord.ui.TextInput(
        label='投稿内容',
        style=discord.TextStyle.paragraph,
        placeholder='ここにメッセージを入力してください...',
        required=True,
        max_length=1000,
    )
    
    is_anonymous = discord.ui.TextInput(
        label='匿名で投稿しますか？（「はい」または「いいえ」）',
        style=discord.TextStyle.short,
        placeholder='はい',
        default='はい',
        required=False,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        board_channel = bot.get_channel(BOARD_CHANNEL_ID)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not board_channel:
            await interaction.response.send_message(
                "エラー: 投稿先のチャンネルが見つかりません。BOARD_CHANNEL_IDを確認してください。", 
                ephemeral=True
            )
            return

        anon_text = self.is_anonymous.value.strip()
        use_anon = anon_text in ["はい", "yes", "Y", "1", ""]

        # 掲示板へ送信するメッセージ
        embed = discord.Embed(
            description=self.content.value,
            color=0x2b2d31
        )
        if use_anon:
            embed.set_author(name="匿名ユーザー")
        else:
            embed.set_author(
                name=interaction.user.display_name, 
                icon_url=interaction.user.display_avatar.url
            )

        sent_message = await board_channel.send(embed=embed)

        # 管理者ログ用
        if log_channel:
            log_embed = discord.Embed(
                title="【投稿ログ】",
                description=self.content.value,
                color=0xff0000
            )
            log_embed.add_field(name="投稿者", value=f"{interaction.user.mention} ({interaction.user.id})")
            log_embed.add_field(name="匿名設定", value="有効" if use_anon else "無効")
            log_embed.add_field(name="対象メッセージ", value=sent_message.jump_url)
            await log_channel.send(embed=log_embed)

        await interaction.response.send_message("投稿が完了しました！", ephemeral=True)

# --- パネルのボタン ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="投稿する", style=discord.ButtonStyle.primary, custom_id="open_post_modal_btn")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PostModal())

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
@bot.tree.command(name="setup_panel", description="掲示板の投稿パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 匿名掲示板",
        description="下の「投稿する」ボタンを押すと入力画面が開きます。",
        color=0x3498db
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

# 実行
if __name__ == "__main__":
    if TOKEN:
        keep_alive()  # ダミーWebサーバーを起動してRenderのエラーを回避
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
