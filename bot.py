import discord
from discord.ext import commands
from datetime import datetime
import io

# ==========================================
# CONFIGURATION - METS TES IDs ICI
# ==========================================
SERVER_ID = 1537102137362874528          # Ton ID de serveur
CATEGORY_ID = 1537191025884266556        # Catégorie des tickets
STAFF_ROLE_ID = 1537103049145974894      # ID du rôle Staff
LOGS_CHANNEL_ID = 1537192279423328418    # Salon #logs-ticket général
MOD_NOTES_CHANNEL_ID = 1537278151065862226 # Salon où les modérateurs voient leur note

# Couleur blanche pour les embeds V2
WHITE_COLOR = 0xffffff

# Emojis personnalisés
EMOJI_OUI = "<:oui:1537274095660695572>"
EMOJI_NON = "<:non:1537275068932165733>"

# Options du menu déroulant
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
    }
]

# Dictionnaire pour stocker quel modérateur gère quel ticket
ticket_claimers = {}

# ==========================================
# INITIALISATION DU BOT
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# FONCTIONS DE VÉRIFICATION
# ==========================================
def is_staff_or_admin(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    # Vérification stricte : Rôle Staff explicite ou perm Admin
    has_staff_role = any(role.id == STAFF_ROLE_ID for role in member.roles)
    return member.guild_permissions.administrator or has_staff_role

def is_ticket_channel(channel) -> bool:
    if not isinstance(channel, discord.TextChannel):
        return False
    return channel.category_id == CATEGORY_ID and channel.name.startswith("ticket-")

# ==========================================
# 1. BOUTONS DE DÉVOILEMENT DE NOTE (SALON MODO)
# ==========================================
class RevealRatingView(discord.ui.View):
    def __init__(self, mod_id: int, rater_mention: str, stars: str, rating_val: str, ticket_type: str):
        super().__init__(timeout=None)
        self.mod_id = mod_id
        self.rater_mention = rater_mention
        self.stars = stars
        self.rating_val = rating_val
        self.ticket_type = ticket_type

    @discord.ui.button(label="Oui", style=discord.ButtonStyle.success, emoji=EMOJI_OUI)
    async def reveal_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.mod_id:
            await interaction.response.send_message(f"{EMOJI_NON} Seul le modérateur concerné peut cliquer ici !", ephemeral=True)
            return

        embed = discord.Embed(
            title="⭐ Ta Note de Ticket",
            description=(
                "───────────────────\n"
                f"Le membre {self.rater_mention} t'a attribué la note de : **{self.stars}** (`{self.rating_val}/5`)\n\n"
                f"*Type de ticket :* **{self.ticket_type}**\n"
                "───────────────────"
            ),
            color=WHITE_COLOR
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @discord.ui.button(label="Non", style=discord.ButtonStyle.danger, emoji=EMOJI_NON)
    async def reveal_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.mod_id:
            await interaction.response.send_message(f"{EMOJI_NON} Seul le modérateur concerné peut cliquer ici !", ephemeral=True)
            return

        embed = discord.Embed(
            description=f"D'accord {interaction.user.mention}, bonne continuation et continue de prendre en charge des tickets ! 👍",
            color=WHITE_COLOR
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)

# ==========================================
# 2. MENU DE NOTATION (EN MP)
# ==========================================
class RatingSelect(discord.ui.Select):
    def __init__(self, ticket_type: str, claimed_mod_id: int):
        self.ticket_type = ticket_type
        self.claimed_mod_id = claimed_mod_id
        options = [
            discord.SelectOption(label="⭐ (1/5)", value="1", description="Très mauvais"),
            discord.SelectOption(label="⭐⭐ (2/5)", value="2", description="Passable"),
            discord.SelectOption(label="⭐⭐⭐ (3/5)", value="3", description="Moyen"),
            discord.SelectOption(label="⭐⭐⭐⭐ (4/5)", value="4", description="Bon"),
            discord.SelectOption(label="⭐⭐⭐⭐⭐ (5/5)", value="5", description="Excellent"),
        ]
        super().__init__(
            placeholder="Notez le service",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        rating_value = self.values[0]
        stars = "⭐" * int(rating_value)
        
        await interaction.response.send_message(f"❤️ Merci pour votre avis ! Vous avez attribué la note de {stars}.", ephemeral=True)
        
        self.view.stop()
        await interaction.message.edit(view=None)

        if self.claimed_mod_id:
            try:
                mod_channel = await interaction.client.fetch_channel(MOD_NOTES_CHANNEL_ID)
                if mod_channel:
                    try:
                        mod_user = await interaction.client.fetch_user(self.claimed_mod_id)
                        mod_mention = mod_user.mention
                    except Exception:
                        mod_mention = f"<@{self.claimed_mod_id}>"

                    embed_ask = discord.Embed(
                        title="❓ Question sur votre prestation",
                        description=(
                            "───────────────────\n"
                            f"{mod_mention}, veux-tu savoir la note donnée par {interaction.user.mention} ?\n"
                            "───────────────────"
                        ),
                        color=WHITE_COLOR
                    )
                    
                    view_reveal = RevealRatingView(
                        mod_id=self.claimed_mod_id,
                        rater_mention=interaction.user.mention,
                        stars=stars,
                        rating_val=rating_value,
                        ticket_type=self.ticket_type
                    )
                    
                    await mod_channel.send(embed=embed_ask, view=view_reveal)
            except Exception as e:
                print(f"[ERREUR SALON NOTE] {e}")

class RatingView(discord.ui.View):
    def __init__(self, ticket_type: str, claimed_mod_id: int):
        super().__init__(timeout=60.0)
        self.message = None
        self.add_item(RatingSelect(ticket_type, claimed_mod_id))

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass

# ==========================================
# 3. MODAL FERMETURE DE TICKET
# ==========================================
class CloseTicketModal(discord.ui.Modal, title="Clôture du ticket"):
    def __init__(self, ticket_type: str, ticket_owner_id: int, claimed_mod_id: int):
        super().__init__()
        self.ticket_type = ticket_type
        self.ticket_owner_id = ticket_owner_id
        self.claimed_mod_id = claimed_mod_id

    reason = discord.ui.TextInput(
        label="Raison de la fermeture",
        placeholder="Indique la raison ici (optionnel)...",
        style=discord.TextStyle.short,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Création des logs et suppression du ticket...", ephemeral=True)
        close_reason = self.reason.value or "Aucune raison fournie"
        channel = interaction.channel

        if not self.claimed_mod_id:
            async for msg in channel.history(limit=50):
                if not msg.author.bot and is_staff_or_admin(msg.author):
                    self.claimed_mod_id = msg.author.id
                    break

        owner_user = interaction.guild.get_member(self.ticket_owner_id)
        if not owner_user:
            async for first_msg in channel.history(limit=5, oldest_first=True):
                if first_msg.mentions:
                    owner_user = first_msg.mentions[0]
                    break

        # Envoi MP
        dm_sent = False
        if owner_user:
            try:
                embed_dm = discord.Embed(
                    description=(
                        f"> {owner_user.mention} Votre ticket a été marqué comme résolu !\n"
                        "───────────────────\n"
                        "> Merci de laisser une note sur le service, cela nous aidera à l'améliorer."
                    ),
                    color=WHITE_COLOR
                )
                rating_view = RatingView(ticket_type=self.ticket_type, claimed_mod_id=self.claimed_mod_id)
                dm_msg = await owner_user.send(embed=embed_dm, view=rating_view)
                rating_view.message = dm_msg
                dm_sent = True
            except discord.Forbidden:
                pass

        # Génération des logs TXT
        log_lines = ["---- LOG DE TICKET ----\n\n"]
        messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
        
        for msg in messages:
            timestamp = msg.created_at.strftime("%d/%m/%Y %H:%M")
            author_str = f"{msg.author.name}"
            
            msg_content = msg.clean_content if msg.content else ""
            if msg.embeds:
                msg_content += f" <EMBED {msg.embeds[0].title or 'Ticket ouvert par ' + msg.author.name}>"
            if msg.attachments:
                attachments_urls = " ".join([att.url for att in msg.attachments])
                msg_content += f" [Fichiers: {attachments_urls}]"

            log_lines.append(f"{timestamp} - {author_str}: {msg_content}\n")

        log_text = "".join(log_lines)
        file_data = io.BytesIO(log_text.encode("utf-8"))
        log_file = discord.File(file_data, filename="log.txt")

        # Salon #logs-ticket
        logs_channel = interaction.guild.get_channel(LOGS_CHANNEL_ID)
        if logs_channel:
            owner_mention = owner_user.mention if owner_user else f"<@{self.ticket_owner_id}>"
            mod_mention = f"<@{self.claimed_mod_id}>" if self.claimed_mod_id else "Aucun"

            embed_log = discord.Embed(
                title="📋 Log - Ticket Fermé",
                description="───────────────────",
                color=WHITE_COLOR,
                timestamp=datetime.now()
            )
            embed_log.add_field(name="Nom du salon", value=f"`{channel.name}`", inline=True)
            embed_log.add_field(name="Type", value=f"{self.ticket_type}", inline=True)
            embed_log.add_field(name="Auteur", value=owner_mention, inline=False)
            embed_log.add_field(name="Modérateur", value=mod_mention, inline=False)
            embed_log.add_field(name="Fermé par", value=interaction.user.mention, inline=False)
            embed_log.add_field(name="Raison", value=close_reason, inline=False)
            embed_log.add_field(name="MP Envoyé", value=f"{EMOJI_OUI} Oui" if dm_sent else f"{EMOJI_NON} Non (MP désactivés)", inline=False)
            
            await logs_channel.send(embed=embed_log, file=log_file)

        ticket_claimers.pop(channel.id, None)
        await channel.delete(reason=close_reason)

# ==========================================
# 4. CONTROLES DU TICKET
# ==========================================
class TicketControlView(discord.ui.View):
    def __init__(self, ticket_type: str = "Inconnu", ticket_owner_id: int = 0):
        super().__init__(timeout=None)
        self.ticket_type = ticket_type
        self.ticket_owner_id = ticket_owner_id

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="btn_close_ticket", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        claimed_mod_id = ticket_claimers.get(interaction.channel_id, 0)
        await interaction.response.send_modal(
            CloseTicketModal(ticket_type=self.ticket_type, ticket_owner_id=self.ticket_owner_id, claimed_mod_id=claimed_mod_id)
        )

# ==========================================
# 5. MENU DÉROULANT DU PANEL
# ==========================================
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for opt in OPTIONS_TICKET:
            options.append(discord.SelectOption(
                label=opt["label"],
                value=opt["value"],
                emoji=opt["emoji"],
                description=opt["description"]
            ))
        super().__init__(
            placeholder="Sélectionne une catégorie...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_select_menu_main"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_value = self.values[0]
        selected_option = next((opt for opt in OPTIONS_TICKET if opt["value"] == selected_value), None)

        guild = interaction.guild
        user = interaction.user
        category = guild.get_channel(CATEGORY_ID)
        staff_role = guild.get_role(STAFF_ROLE_ID)

        channel_name = f"ticket-{selected_value}-{user.name}".lower().replace(" ", "-")
        if category:
            existing_channel = discord.utils.get(category.text_channels, name=channel_name)
            if existing_channel:
                await interaction.response.send_message(f"{EMOJI_NON} Tu as déjà un ticket ouvert ici : {existing_channel.mention}", ephemeral=True)
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )

        embed_welcome = discord.Embed(
            title=f"Support Tag - {selected_option['label']}",
            description=(
                f"Bienvenue {user.mention} !\n"
                "───────────────────\n"
                "Un membre de l'équipe va te prendre en charge d'ici quelques instants.\n\n"
                "Merci d'expliquer clairement ta demande ci-dessous."
            ),
            color=WHITE_COLOR
        )
        
        view = TicketControlView(ticket_type=selected_option["label"], ticket_owner_id=user.id)
        await ticket_channel.send(embed=embed_welcome, view=view)
        
        await interaction.response.send_message(f"{EMOJI_OUI} Ton ticket a été créé avec succès : {ticket_channel.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# ==========================================
# 6. ÉVÉNEMENT DÉTECTION MESSAGE STAFF
# ==========================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if is_ticket_channel(message.channel):
        # Vérifie impérativement si l'auteur du message a le rôle staff (1537103049145974894) ou Admin
        if is_staff_or_admin(message.author) and message.channel.id not in ticket_claimers:
            ticket_claimers[message.channel.id] = message.author.id
            embed_taken = discord.Embed(
                description=(
                    "───────────────────\n"
                    f"🙋‍♂️ {message.author.mention} a pris en charge ce ticket !\n"
                    "───────────────────"
                ),
                color=WHITE_COLOR
            )
            await message.channel.send(embed=embed_taken)

    await bot.process_commands(message)

# ==========================================
# 7. ÉVÉNEMENT ON_READY
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())

    guild_obj = discord.Object(id=SERVER_ID)
    try:
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"[SUCCESS] Synchro réussie : {len(synced)} commande(s) active(s) sur le serveur.")
    except Exception as e:
        print(f"[ERROR] Erreur lors de la synchro : {e}")

    print(f"[INFO] Bot connecté en tant que : {bot.user}")

# ==========================================
# 8. COMMANDES SLASH
# ==========================================

@bot.tree.command(name="setup-ticket", description="Envoie le panel de support ticket")
async def setup_ticket(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(f"{EMOJI_NON} Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
        return

    embed = discord.Embed(
        description=(
            "# Support Tag\n"
            "───────────────────\n"
            "si tu veux rejoindre les **membre UFC** ou être un **anti Pdo** fait un ticket qui est pour ! \n\n"
            "Notre équipe est connecter `7j/24h` pour vous acompagnez dans notre project !"
        ),
        color=WHITE_COLOR
    )

    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message(f"{EMOJI_OUI} Panel envoyé avec succès dans ce salon !", ephemeral=True)

@bot.tree.command(name="rename", description="Renomme le salon du ticket")
@discord.app_commands.describe(nouveau_nom="Le nouveau nom à donner au salon")
async def rename_ticket(interaction: discord.Interaction, nouveau_nom: str):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message(f"{EMOJI_NON} Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    if not is_ticket_channel(interaction.channel):
        await interaction.response.send_message(f"{EMOJI_NON} Cette commande ne peut être utilisée que dans un salon de ticket !", ephemeral=True)
        return

    formatted_name = nouveau_nom.lower().replace(" ", "-")
    try:
        old_name = interaction.channel.name
        await interaction.channel.edit(name=formatted_name)
        await interaction.response.send_message(f"{EMOJI_OUI} Salon renommé : `{old_name}` ➔ `{formatted_name}`", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"{EMOJI_NON} Erreur lors du renommage : {e}", ephemeral=True)

@bot.tree.command(name="add", description="Ajoute un membre au ticket")
@discord.app_commands.describe(membre="Le membre à ajouter au salon")
async def add_member(interaction: discord.Interaction, membre: discord.Member):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message(f"{EMOJI_NON} Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    if not is_ticket_channel(interaction.channel):
        await interaction.response.send_message(f"{EMOJI_NON} Cette commande ne peut être utilisée que dans un salon de ticket !", ephemeral=True)
        return

    try:
        await interaction.channel.set_permissions(membre, read_messages=True, send_messages=True)
        await interaction.response.send_message(f"{EMOJI_OUI} {membre.mention} a été ajouté au ticket.")
    except Exception as e:
        await interaction.response.send_message(f"{EMOJI_NON} Impossible d'ajouter ce membre : {e}", ephemeral=True)

@bot.tree.command(name="remove", description="Retire un membre du ticket")
@discord.app_commands.describe(membre="Le membre à retirer du salon")
async def remove_member(interaction: discord.Interaction, membre: discord.Member):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message(f"{EMOJI_NON} Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    if not is_ticket_channel(interaction.channel):
        await interaction.response.send_message(f"{EMOJI_NON} Cette commande ne peut être utilisée que dans un salon de ticket !", ephemeral=True)
        return

    try:
        await interaction.channel.set_permissions(membre, overwrite=None)
        await interaction.response.send_message(f"🚫 {membre.mention} a été retiré du ticket.")
    except Exception as e:
        await interaction.response.send_message(f"{EMOJI_NON} Impossible de retirer ce membre : {e}", ephemeral=True)

@bot.tree.command(name="claim", description="S'attribuer manuellement la prise en charge du ticket")
async def claim_ticket(interaction: discord.Interaction):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message(f"{EMOJI_NON} Seul le staff peut prendre en charge un ticket.", ephemeral=True)
        return

    if not is_ticket_channel(interaction.channel):
        await interaction.response.send_message(f"{EMOJI_NON} Cette commande ne peut être utilisée que dans un salon de ticket !", ephemeral=True)
        return

    ticket_claimers[interaction.channel.id] = interaction.user.id
    embed_claim = discord.Embed(
        description=(
            "───────────────────\n"
            f"🙋‍♂️ Ce ticket est désormais pris en charge par {interaction.user.mention}.\n"
            "───────────────────"
        ),
        color=WHITE_COLOR
    )
    await interaction.response.send_message(embed=embed_claim)

# ===============================================
# 9. LANCEMENT DU BOT
# ===============================================
import os

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN:
    bot.run(TOKEN)
else:
    print("Erreur : La variable DISCORD_TOKEN n'a pas été trouvée !")