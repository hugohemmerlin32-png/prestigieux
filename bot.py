from datetime import datetime
import io
import os
from threading import Thread
import discord
from discord.ext import commands
from flask import Flask

# ==========================================
# CONFIGURATION - IDs
# ==========================================
SERVER_ID = 1537102137362874528
CATEGORY_ID = 1537191025884266556
STAFF_ROLE_ID = 1537103049145974894
LOGS_CHANNEL_ID = 1537192279423328418
MOD_NOTES_CHANNEL_ID = 1537278151065862226

EMBED_V2_COLOR = 0x2b2d31
EMOJI_OUI = "<:oui:1537274095660695572>"
EMOJI_NON = "<:non:1537275068932165733>"

OPTIONS_TICKET = [
    {
        "label": "Devenir Membre UFC",
        "value": "ufc",
        "emoji": "<:723011member:1537208714858209362>",
        "description": "Pour rejoindre le groupe UFC.",
    },
    {
        "label": "Devenir Anti Pdo",
        "value": "antipdo",
        "emoji": "<:tlcharger__19_removebgpreview:1537119126315597924>",
        "description": "Pour rejoindre le groupe Anti-Pdo.",
    },
]

ticket_claimers = {}

# ==========================================
# INITIALISATION DU BOT
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


def is_staff_or_admin(member: discord.Member) -> bool:
  if not isinstance(member, discord.Member):
    return False
  has_staff_role = any(role.id == STAFF_ROLE_ID for role in member.roles)
  return member.guild_permissions.administrator or has_staff_role


def is_ticket_channel(channel) -> bool:
  if not isinstance(channel, discord.TextChannel):
    return False
  return channel.category_id == CATEGORY_ID and channel.name.startswith(
      "ticket-"
  )


# ==========================================
# VUES ET INTERFACES
# ==========================================
class RevealRatingView(discord.ui.View):

  def __init__(
      self,
      mod_id: int,
      rater_mention: str,
      stars: str,
      rating_val: str,
      ticket_type: str,
  ):
    super().__init__(timeout=None)
    self.mod_id = mod_id
    self.rater_mention = rater_mention
    self.stars = stars
    self.rating_val = rating_val
    self.ticket_type = ticket_type

  @discord.ui.button(
      label="Oui", style=discord.ButtonStyle.success, emoji=EMOJI_OUI
  )
  async def reveal_yes(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if interaction.user.id != self.mod_id:
      await interaction.response.send_message(
          f"{EMOJI_NON} Seul le modérateur concerné peut cliquer ici !",
          ephemeral=True,
      )
      return
    embed = discord.Embed(
        title="⭐ Ta Note de Ticket",
        description=(
            f"Le membre {self.rater_mention} t'a attribué la note de :"
            f" **{self.stars}** (`{self.rating_val}/5`)\n\n*Ticket type :"
            f" {self.ticket_type}*"
        ),
        color=EMBED_V2_COLOR,
    )
    await interaction.response.edit_message(content=None, embed=embed, view=None)

  @discord.ui.button(
      label="Non", style=discord.ButtonStyle.danger, emoji=EMOJI_NON
  )
  async def reveal_no(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if interaction.user.id != self.mod_id:
      await interaction.response.send_message(
          f"{EMOJI_NON} Seul le modérateur concerné peut cliquer ici !",
          ephemeral=True,
      )
      return
    embed = discord.Embed(
        description=(
            f"D'accord {interaction.user.mention}, bonne continuation et"
            " continue de prendre en charge des tickets ! 👍"
        ),
        color=EMBED_V2_COLOR,
    )
    await interaction.response.edit_message(content=None, embed=embed, view=None)


class RatingSelect(discord.ui.Select):

  def __init__(self, ticket_type: str, claimed_mod_id: int):
    self.ticket_type = ticket_type
    self.claimed_mod_id = claimed_mod_id
    options = [
        discord.SelectOption(
            label="⭐ (1/5)", value="1", description="Très mauvais"
        ),
        discord.SelectOption(
            label="⭐⭐ (2/5)", value="2", description="Passable"
        ),
        discord.SelectOption(
            label="⭐⭐⭐ (3/5)", value="3", description="Moyen"
        ),
        discord.SelectOption(
            label="⭐⭐⭐⭐ (4/5)", value="4", description="Bon"
        ),
        discord.SelectOption(
            label="⭐⭐⭐⭐⭐ (5/5)", value="5", description="Excellent"
        ),
    ]
    super().__init__(
        placeholder="Notez le service",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    rating_value = self.values[0]
    stars = "⭐" * int(rating_value)
    await interaction.response.send_message(
        f"❤️ Merci pour votre avis ! Vous avez attribué la note de {stars}.",
        ephemeral=True,
    )
    self.view.stop()
    await interaction.message.edit(view=None)

    if self.claimed_mod_id:
      try:
        mod_channel = await interaction.client.fetch_channel(
            MOD_NOTES_CHANNEL_ID
        )
        if mod_channel:
          try:
            mod_user = await interaction.client.fetch_user(self.claimed_mod_id)
            mod_mention = mod_user.mention
          except Exception:
            mod_mention = f"<@{self.claimed_mod_id}>"

          embed_ask = discord.Embed(
              title="❓ Question sur votre prestation",
              description=(
                  f"{mod_mention}, veux-tu savoir la note donnée par"
                  f" {interaction.user.mention} ?"
              ),
              color=EMBED_V2_COLOR,
          )
          view_reveal = RevealRatingView(
              self.claimed_mod_id,
              interaction.user.mention,
              stars,
              rating_value,
              self.ticket_type,
          )
          await mod_channel.send(embed=embed_ask, view=view_reveal)
      except Exception as e:
        print(f"[ERREUR SALON NOTE] {e}")


class RatingView(discord.ui.View):

  def __init__(self, ticket_type: str, claimed_mod_id: int):
    super().__init__(timeout=60.0)
    self.message = None
    self.add_item(RatingSelect(ticket_type, claimed_mod_id))


class CloseTicketModal(discord.ui.Modal, title="Clôture du ticket"):

  def __init__(
      self, ticket_type: str, ticket_owner_id: int, claimed_mod_id: int
  ):
    super().__init__()
    self.ticket_type = ticket_type
    self.ticket_owner_id = ticket_owner_id
    self.claimed_mod_id = claimed_mod_id

  reason = discord.ui.TextInput(
      label="Raison de la fermeture",
      placeholder="Indique la raison ici...",
      style=discord.TextStyle.short,
      required=False,
  )

  async def on_submit(self, interaction: discord.Interaction):
    await interaction.response.send_message(
        "Création des logs et suppression du ticket...", ephemeral=True
    )
    close_reason = self.reason.value or "Aucune raison fournie"
    channel = interaction.channel

    if not self.claimed_mod_id:
      async for msg in channel.history(limit=50):
        if not msg.author.bot and is_staff_or_admin(msg.author):
          self.claimed_mod_id = msg.author.id
          break

    owner_user = interaction.guild.get_member(self.ticket_owner_id)
    dm_sent = False
    if owner_user:
      try:
        embed_dm = discord.Embed(
            description=(
                f"> {owner_user.mention} Votre ticket a été marqué comme"
                " résolu !\n\n> Merci de laisser une note."
            ),
            color=EMBED_V2_COLOR,
        )
        rating_view = RatingView(
            self.ticket_type, self.claimed_mod_id
        )
        dm_msg = await owner_user.send(embed=embed_dm, view=rating_view)
        rating_view.message = dm_msg
        dm_sent = True
      except discord.Forbidden:
        pass

    log_lines = ["LOG DE TICKET\n\n"]
    messages = [
        msg async for msg in channel.history(limit=None, oldest_first=True)
    ]
    for msg in messages:
      ts = msg.created_at.strftime("%d/%m/%Y %H:%M")
      content = msg.clean_content
      if msg.embeds:
        content += " <EMBED>"
      if msg.attachments:
        content += " [Fichiers]"
      log_lines.append(f"{ts} - {msg.author.name}: {content}\n")

    log_file = discord.File(
        io.BytesIO("".join(log_lines).encode("utf-8")), filename="log.txt"
    )
    logs_channel = interaction.guild.get_channel(LOGS_CHANNEL_ID)
    if logs_channel:
      embed_log = discord.Embed(
          title="📋 Log - Ticket Fermé",
          color=EMBED_V2_COLOR,
          timestamp=datetime.now(),
      )
      embed_log.add_field(name="Type", value=self.ticket_type, inline=True)
      embed_log.add_field(
          name="Modérateur", value=f"<@{self.claimed_mod_id}>", inline=False
      )
      embed_log.add_field(name="Raison", value=close_reason, inline=False)
      await logs_channel.send(embed=embed_log, file=log_file)

    ticket_claimers.pop(channel.id, None)
    await channel.delete(reason=close_reason)


class TicketControlView(discord.ui.View):

  def __init__(self, ticket_type: str = "Inconnu", ticket_owner_id: int = 0):
    super().__init__(timeout=None)
    self.ticket_type = ticket_type
    self.ticket_owner_id = ticket_owner_id

  @discord.ui.button(
      label="Fermer le ticket",
      style=discord.ButtonStyle.danger,
      custom_id="btn_close_ticket",
      emoji="🔒",
  )
  async def close_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(
        CloseTicketModal(
            self.ticket_type,
            self.ticket_owner_id,
            ticket_claimers.get(interaction.channel_id, 0),
        )
    )


class TicketSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=opt["label"], value=opt["value"], emoji=opt["emoji"]
        )
        for opt in OPTIONS_TICKET
    ]
    super().__init__(
        placeholder="Sélectionne une catégorie...",
        options=options,
        custom_id="ticket_select_menu_main",
    )

  async def callback(self, interaction: discord.Interaction):
    selected = next(
        (opt for opt in OPTIONS_TICKET if opt["value"] == self.values[0]), None
    )
    chan_name = f"ticket-{self.values[0]}-{interaction.user.name}".lower()
    if discord.utils.get(interaction.guild.text_channels, name=chan_name):
      await interaction.response.send_message(
          "Ticket déjà ouvert.", ephemeral=True
      )
      return

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(
            read_messages=False
        ),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        ),
    }
    if staff_role := interaction.guild.get_role(STAFF_ROLE_ID):
      overwrites[staff_role] = discord.PermissionOverwrite(
          read_messages=True, send_messages=True
      )

    ticket_channel = await interaction.guild.create_text_channel(
        name=chan_name,
        category=interaction.guild.get_channel(CATEGORY_ID),
        overwrites=overwrites,
    )
    await ticket_channel.send(
        embed=discord.Embed(
            title=f"Support - {selected['label']}",
            description="Bienvenue, un membre du staff va vous aider.",
            color=EMBED_V2_COLOR,
        ),
        view=TicketControlView(selected["label"], interaction.user.id),
    )
    await interaction.response.send_message(
        f"Ticket créé : {ticket_channel.mention}", ephemeral=True
    )


class TicketPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.add_item(TicketSelect())


# ==========================================
# ÉVÉNEMENTS DU BOT
# ==========================================
@bot.event
async def on_message(message):
  if message.author.bot or not message.guild:
    return
  if (
      is_ticket_channel(message.channel)
      and is_staff_or_admin(message.author)
      and message.channel.id not in ticket_claimers
  ):
    ticket_claimers[message.channel.id] = message.author.id
    await message.channel.send(
        embed=discord.Embed(
            description=(
                f"🙋‍♂️ {message.author.mention} a pris en charge ce ticket !"
            ),
            color=EMBED_V2_COLOR,
        )
    )
  await bot.process_commands(message)


@bot.event
async def on_ready():
  bot.add_view(TicketPanelView())
  bot.add_view(TicketControlView())
  guild_obj = discord.Object(id=SERVER_ID)
  await bot.tree.sync(guild=guild_obj)
  print(f"Bot connecté : {bot.user}")


@bot.tree.command(name="setup-ticket")
async def setup_ticket(interaction: discord.Interaction):
  embed = discord.Embed(
      description=(
          "# Support Tag\nRejoins les membres UFC ou anti Pdo via un ticket !"
      ),
      color=EMBED_V2_COLOR,
  )
  await interaction.channel.send(embed=embed, view=TicketPanelView())
  await interaction.response.send_message("Panel envoyé.", ephemeral=True)


@bot.tree.command(name="claim", description="Prendre en charge un ticket")
async def claim_ticket(interaction: discord.Interaction):
  if not is_staff_or_admin(interaction.user):
    await interaction.response.send_message("Seul le staff peut claim.", ephemeral=True)
    return
  if not is_ticket_channel(interaction.channel):
    await interaction.response.send_message("Dans un salon de ticket uniquement.", ephemeral=True)
    return

  ticket_claimers[interaction.channel.id] = interaction.user.id
  embed = discord.Embed(
      description=f"🙋‍♂️ {interaction.user.mention} a pris en charge ce ticket !",
      color=EMBED_V2_COLOR,
  )
  await interaction.response.send_message(embed=embed)


# ==========================================
# SERVEUR FLASK & LANCEMENT
# ==========================================
app = Flask("")


@app.route("/")
def home():
  return "Bot en ligne"


def run():
  app.run(host="0.0.0.0", port=8080)


Thread(target=run).start()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Erreur : Aucun token trouvé !")
