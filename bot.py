import datetime
import json
import os
import discord
from discord import app_commands
from discord.ext import commands

BOARD_CHANNEL_ID = 1542868096640098444  # 掲示板チャンネルID
LOG_CHANNEL_ID = 1542866592566747166  # 管理者用ログチャンネルID
BOT_TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "post_count.json"


def load_post_id():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("current_post_id", 0)
    except Exception:
      return 0
  return 0


def save_post_id(post_id):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump({"current_post_id": post_id}, f)


current_post_id = load_post_id()

intents = discord.Intents.default()
intents.message_content = True


# Discord内で開くモーダル画面
class PostModal(discord.ui.Modal, title="投稿"):

  content_input = discord.ui.TextInput(
      label="投稿",
      style=discord.TextStyle.paragraph,
      placeholder="本文（任意）",
      required=False,
      max_length=1800,
  )

  ref_input = discord.ui.TextInput(
      label="レス",
      style=discord.TextStyle.short,
      placeholder="引用する投稿番号（任意 例: 99）",
      required=False,
  )

  image_url_input = discord.ui.TextInput(
      label="画像・動画のURL",
      style=discord.TextStyle.short,
      placeholder="https://...（直リンクURLを入力・任意）",
      required=False,
  )

  async def on_submit(self, interaction: discord.Interaction):
    global current_post_id

    content = self.content_input.value
    ref_id = self.ref_input.value
    image_url = self.image_url_input.value

    if not content and not image_url:
      await interaction.response.send_message(
          "本文または画像URLを入力してください。", ephemeral=True
      )
      return

    current_post_id += 1
    post_id = current_post_id
    save_post_id(post_id)

    board_channel = interaction.guild.get_channel(BOARD_CHANNEL_ID)
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    description = content or ""
    if ref_id:
      description = f">> {ref_id}\n" + description

    embed = discord.Embed(description=description, color=0x2B2D31)
    embed.set_author(name=f"{post_id} : 匿名 • {now_str}")

    if image_url:
      embed.set_image(url=image_url)

    if board_channel:
      await board_channel.send(embed=embed, view=PostButtonsView())

    if log_channel:
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
          name="内容", value=content or "（本文なし）", inline=False
      )
      if image_url:
        log_embed.add_field(name="画像URL", value=image_url, inline=False)
      await log_channel.send(embed=log_embed)

    await interaction.response.send_message(
        "投稿が完了しました！", ephemeral=True
    )


class PostButtonsView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="投稿",
      style=discord.ButtonStyle.secondary,
      custom_id="post_button_persistent",
      emoji="✉️",
  )
  async def post_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(PostModal())

  @discord.ui.button(
      label="通報",
      style=discord.ButtonStyle.danger,
      custom_id="report_button_persistent",
  )
  async def report_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    message = interaction.message
    post_title = (
        message.embeds[0].author.name if message.embeds else "不明な投稿"
    )
    post_content = (
        message.embeds[0].description if message.embeds else "内容なし"
    )

    if log_channel:
      report_embed = discord.Embed(
          title="🚨 通報通知", color=0xED4245, timestamp=datetime.datetime.now()
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


class AnonymousBoardBot(commands.Bot):

  def __init__(self):
    super().__init__(command_prefix="!", intents=intents)

  async def setup_hook(self):
    self.add_view(PostButtonsView())
    await self.tree.sync()


bot = AnonymousBoardBot()


@bot.tree.command(
    name="setup_panel", description="掲示板に投稿ボタンパネルを設置します"
)
async def setup_panel(interaction: discord.Interaction):
  embed = discord.Embed(
      title="📝 匿名掲示板",
      description="下の「投稿」ボタンを押して投稿を作成してください。",
      color=0x5865F2,
  )
  await interaction.channel.send(embed=embed, view=PostButtonsView())
  await interaction.response.send_message(
      "パネルを設置しました。", ephemeral=True
  )


if __name__ == "__main__":
  if BOT_TOKEN:
    bot.run(BOT_TOKEN)
