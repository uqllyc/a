import datetime
import json
import os
import sys
from threading import Thread
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

# --------------------------------------------------
# 【Render無料枠対応】Webサーバー用設定
# --------------------------------------------------
app = Flask("")


@app.route("/")
def home():
  return "Bot is running!"


def run():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  t = Thread(target=run)
  t.start()


# --------------------------------------------------
# 【設定】ご自身の環境のIDとトークンに書き換えてください
# --------------------------------------------------
BOARD_CHANNEL_ID = 1542868096640098444  # 掲示板チャンネルのID（数字）
LOG_CHANNEL_ID = 1542866592566747166  # 管理者用ログチャンネル（通報もここに届きます）
BOT_TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "post_count.json"  # 投稿番号の保存用ファイル

intents = discord.Intents.default()
intents.message_content = True


def load_post_id():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("current_post_id", 0)
    except Exception:
      return 0
  return 0


def save_post_id(post_id):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump({"current_post_id": post_id}, f)


class AnonymousBoardBot(commands.Bot):

  def __init__(self):
    super().__init__(command_prefix="!", intents=intents)
    self.current_post_id = load_post_id()

  async def setup_hook(self):
    self.add_view(PanelView())
    self.add_view(PostButtonsView())
    await self.tree.sync()


bot = AnonymousBoardBot()


# --------------------------------------------------
# 1. 投稿用ポップアップ画面（Modal）
# --------------------------------------------------
class PostModal(discord.ui.Modal, title="投稿"):

  def __init__(self, is_anonymous: bool):
    super().__init__()
    self.is_anonymous = is_anonymous

  content = discord.ui.TextInput(
      label="投稿内容",
      style=discord.TextStyle.paragraph,
      placeholder="ここに投稿したい内容を入力してください",
      required=True,
      max_length=1000,
  )

  async def on_submit(self, interaction: discord.Interaction):
    bot.current_post_id += 1
    post_id = bot.current_post_id
    save_post_id(post_id)

    board_channel = interaction.guild.get_channel(BOARD_CHANNEL_ID)
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    author_name = "匿名" if self.is_anonymous else interaction.user.display_name

    embed = discord.Embed(description=self.content.value, color=0x2B2D31)
    embed.set_author(name=f"{post_id} : {author_name} • {now_str}")

    if not self.is_anonymous:
      embed.set_thumbnail(url=interaction.user.display_avatar.url)

    # 掲示板に送信
    if board_channel:
      await board_channel.send(embed=embed, view=PostButtonsView())

    # 管理者用ログ送信
    log_embed = discord.Embed(
        title=f"【投稿ログ】No.{post_id}",
        color=0x2B2D31,
        timestamp=datetime.datetime.now(),
    )
    log_embed.add_field(
        name="投稿者",
        value=f"{interaction.user.mention} ({interaction.user.name})",
        inline=False,
    )
    log_embed.add_field(
        name="投稿種別",
        value="匿名投稿" if self.is_anonymous else "公開投稿",
        inline=True,
    )
    log_embed.add_field(name="内容", value=self.content.value, inline=False)

    if log_channel:
      await log_channel.send(embed=log_embed)

    await interaction.response.send_message(
        "投稿が完了しました！", ephemeral=True
    )


# --------------------------------------------------
# 2. 投稿カード下部のボタン（匿名 / 非匿名 / 通報）
# --------------------------------------------------
class PostButtonsView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="匿名で投稿",
      style=discord.ButtonStyle.secondary,
      emoji="👤",
      custom_id="card_post_anon_persistent",
  )
  async def post_anon_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(PostModal(is_anonymous=True))

  @discord.ui.button(
      label="非匿名で投稿",
      style=discord.ButtonStyle.primary,
      emoji="👤",
      custom_id="card_post_public_persistent",
  )
  async def post_public_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(PostModal(is_anonymous=False))

  @discord.ui.button(
      label="通報",
      style=discord.ButtonStyle.danger,
      custom_id="report_button_persistent",
  )
  async def report_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)

    # 通報元のメッセージ情報を取得
    message = interaction.message
    post_title = (
        message.embeds[0].author.name if message.embeds else "不明な投稿"
    )
    post_content = (
        message.embeds[0].description if message.embeds else "内容なし"
    )

    # 管理者ログチャンネルへ通報通知を送信
    if log_channel:
      report_embed = discord.Embed(
          title="🚨 通報通知",
          color=0xED4245,  # 赤色
          timestamp=datetime.datetime.now(),
      )
      report_embed.add_field(
          name="通報者",
          value=f"{interaction.user.mention} ({interaction.user.name})",
          inline=False,
      )
      report_embed.add_field(
          name="対象投稿", value=post_title, inline=False
      )
      report_embed.add_field(
          name="投稿内容", value=post_content, inline=False
      )
      report_embed.add_field(
          name="投稿URL", value=message.jump_url, inline=False
      )

      await log_channel.send(embed=report_embed)

    await interaction.response.send_message(
        "通報を受け付けました。", ephemeral=True
    )


# --------------------------------------------------
# 3. 設置用メインパネル
# --------------------------------------------------
class PanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="👤 匿名で投稿",
      style=discord.ButtonStyle.secondary,
      custom_id="panel_post_anon_persistent",
  )
  async def post_anonymous(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(PostModal(is_anonymous=True))

  @discord.ui.button(
      label="👤 非匿名で投稿",
      style=discord.ButtonStyle.primary,
      custom_id="panel_post_public_persistent",
  )
  async def post_public(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(PostModal(is_anonymous=False))


# --------------------------------------------------
# 4. コマンド・イベント設定
# --------------------------------------------------
@bot.event
async def on_ready():
  print(
      f"Logged in as {bot.user} - 起動完了（現在の投稿ID: {bot.current_post_id}）"
  )


@bot.tree.command(
    name="setup_panel", description="掲示板の投稿パネルを設置します"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_panel(interaction: discord.Interaction):
  embed = discord.Embed(
      title="💬 匿名掲示板",
      description=" 匿名 非匿名を選び投稿してください。",
      color=0x2B2D31,
  )
  await interaction.channel.send(embed=embed, view=PanelView())
  await interaction.response.send_message(
      "パネルを設置しました！", ephemeral=True
  )


if __name__ == "__main__":
  # Render用のWebサーバーをバックグラウンドで起動
  keep_alive()

  # Botの起動
  if BOT_TOKEN:
    bot.run(BOT_TOKEN)
  else:
    print("Error: DISCORD_TOKEN is not set.")
