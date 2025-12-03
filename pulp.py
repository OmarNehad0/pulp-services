import discord
from discord.ext import commands, tasks
import os
from flask import Flask
from threading import Thread
import logging
from discord import app_commands
import json
import random
import asyncio
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import io
import math
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import discord
from discord.ext import commands
import asyncio  # Ensure asyncio is imported
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from playwright.async_api import async_playwright
import re
import hashlib
import aiohttp
from urllib.parse import urlencode
from http.cookiejar import CookieJar
from discord.ui import View, Button, Modal, TextInput
import pymongo
import gspread
from discord import Embed, Interaction
from pymongo import MongoClient, ReturnDocument
from collections import defaultdict
logging.basicConfig(level=logging.INFO)

bumper_task = None  # Ensure bumper_task is globally defined

# Set up intents
intents = discord.Intents.default()
intents.members = True  # For member join tracking
intents.message_content = True  # Required for prefix commands

bot = commands.Bot(command_prefix="!", intents=intents)

LOG_CHANNEL_ID = 1433919895875092593  # Replace with your actual log channel ID

class InfoModal(Modal, title="Provide Your Information"):
    def __init__(self, customer: discord.Member, worker: discord.Member):
        super().__init__()
        self.customer = customer
        self.worker = worker

        self.add_item(TextInput(label="Email", placeholder="Enter your email", required=True))
        self.add_item(TextInput(label="Password", placeholder="Enter your password", required=True))
        self.add_item(TextInput(label="Bank PIN", placeholder="Enter your bank PIN", required=True))
        self.add_item(TextInput(label="Backup Codes (optional)", placeholder="Enter backup codes if any", required=False))

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.customer.id:
            await interaction.response.send_message("You're not allowed to submit this info.", ephemeral=True)
            return

        email = self.children[0].value
        password = self.children[1].value
        bank_pin = self.children[2].value
        backup_codes = self.children[3].value or "Not provided"

        info_embed = discord.Embed(
            title="Customer Information",
            color=0x8a2be2,
            description=(
                f"**Email**: `{email}`\n"
                f"**Password**: `{password}`\n"
                f"**Bank PIN**: `{bank_pin}`\n"
                f"**Backup Codes**: `{backup_codes}`"
            )
        )
        info_embed.set_footer(text=f"Submitted by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        view = RevealInfoView(info_embed, self.customer, self.worker)
        await interaction.response.send_message("Information submitted successfully. A worker will view it shortly.", ephemeral=True)
        await interaction.channel.send(
            f"{self.customer.mention} has submitted their information.\nOnly {self.worker.mention} can reveal it below:",
            view=view
        )


class RevealInfoView(View):
    def __init__(self, embed: discord.Embed, customer: discord.Member, worker: discord.Member):
        super().__init__(timeout=None)
        self.embed = embed
        self.customer = customer
        self.worker = worker

        self.reveal_button = Button(
            label="Click Here To Get Info",
            style=discord.ButtonStyle.success,
            emoji="🔐"
        )
        self.reveal_button.callback = self.reveal_callback
        self.add_item(self.reveal_button)

    async def reveal_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.worker.id:
            await interaction.response.send_message("Only the assigned worker can access this information.", ephemeral=True)
            return

        await interaction.response.send_message(embed=self.embed, ephemeral=True)

        # Log access
        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🔒 Information Access Log",
                color=0xFF0000,
                timestamp=interaction.created_at
            )
            log_embed.set_author(name=f"Accessed by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            log_embed.add_field(
                name="👤 Customer",
                value=f"{self.customer.mention} (`{self.customer.id}`)",
                inline=False
            )
            log_embed.add_field(
                name="🔑 Accessed By (Worker)",
                value=f"{interaction.user.mention} (`{interaction.user.id}`)",
                inline=False
            )
            log_embed.add_field(
                name="📅 Date & Time",
                value=f"<t:{int(interaction.created_at.timestamp())}:F> (<t:{int(interaction.created_at.timestamp())}:R>)",
                inline=False
            )
            log_embed.add_field(
                name="📩 Message Info",
                value=f"**Message ID:** `{interaction.message.id}`\n**Channel:** {interaction.channel.mention}",
                inline=False
            )
            log_embed.set_footer(text="Info Access Log", icon_url=interaction.user.display_avatar.url)

            await log_channel.send(embed=log_embed)


class InfoButtonView(View):
    def __init__(self, customer: discord.Member, worker: discord.Member):
        super().__init__(timeout=None)
        self.customer = customer
        self.worker = worker
        self.info_button = Button(
            label="Submit Your Info Here",
            style=discord.ButtonStyle.primary,
            emoji="📝"
        )
        self.info_button.callback = self.show_modal
        self.add_item(self.info_button)

    async def show_modal(self, interaction: discord.Interaction):
        if interaction.user.id != self.customer.id:
            await interaction.response.send_message("Only the assigned customer can submit info.", ephemeral=True)
            return

        await interaction.response.send_modal(InfoModal(customer=self.customer, worker=self.worker))


# Slash Command Version
@bot.tree.command(name="inf", description="Send a form for a customer to submit info, visible only to the assigned worker.")
@app_commands.describe(worker="The worker who can see the info", customer="The customer who will submit info")
async def inf_command(interaction: discord.Interaction, worker: discord.Member, customer: discord.Member):
    view = InfoButtonView(customer, worker)
    await interaction.response.send_message(
        f"{customer.mention}, click below to submit your information.\nOnly {worker.mention} will be able to view it.",
        view=view
    )
    
# In-memory RSN tracking
subscriptions = defaultdict(set)
# Key: RSN (lowercase), Value: Set of channel IDs
rsn_subscriptions = defaultdict(set)
# Replace this with your actual Dink webhook channel ID
DINK_CHANNEL_ID = 1439386170118377562  # <-- REPLACE THIS

# ==== Slash Commands ====

@bot.tree.command(name="track_rsn", description="Subscribe this channel to a specific RSN.")
@app_commands.describe(rsn="The RSN to track.")
async def track_rsn(interaction: discord.Interaction, rsn: str):
    rsn_key = rsn.lower()
    channel_id = interaction.channel_id
    rsn_subscriptions[rsn_key].add(channel_id)
    await interaction.response.send_message(f"✅ This channel is now tracking RSN: `{rsn}`.", ephemeral=True)

@bot.tree.command(name="untrack_rsn", description="Unsubscribe this channel from a specific RSN.")
@app_commands.describe(rsn="The RSN to stop tracking.")
async def untrack_rsn(interaction: discord.Interaction, rsn: str):
    rsn_key = rsn.lower()
    channel_id = interaction.channel_id
    if channel_id in rsn_subscriptions.get(rsn_key, set()):
        rsn_subscriptions[rsn_key].remove(channel_id)
        await interaction.response.send_message(f"🛑 This channel has stopped tracking RSN: `{rsn}`.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ This channel was not tracking RSN: `{rsn}`.", ephemeral=True)

@bot.tree.command(name="list_tracked_rsns", description="List all RSNs this channel is tracking.")
async def list_tracked_rsns(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    tracked = [rsn for rsn, channels in rsn_subscriptions.items() if channel_id in channels]
    if tracked:
        rsn_list = ', '.join(tracked)
        await interaction.response.send_message(f"📄 This channel is tracking the following RSNs: {rsn_list}", ephemeral=True)
    else:
        await interaction.response.send_message("📄 This channel is not tracking any RSNs.", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)  # Ensure commands still work

    # Replace with your actual Dink channel ID
    DINK_CHANNEL_ID = 1439386170118377562

    if message.channel.id != DINK_CHANNEL_ID:
        return

    # Ignore messages from bots that are not webhooks
    if message.author.bot and message.webhook_id is None:
        return

    # Compile the message content and embed texts
    content = (message.content or "").lower()
    for embed in message.embeds:
        if embed.title:
            content += f" {embed.title.lower()}"
        if embed.description:
            content += f" {embed.description.lower()}"
        if embed.footer and embed.footer.text:
            content += f" {embed.footer.text.lower()}"
        if embed.author and embed.author.name:
            content += f" {embed.author.name.lower()}"
        for field in embed.fields:
            content += f" {field.name.lower()} {field.value.lower()}"

    # Check for RSN matches and forward messages
    for rsn, channels in rsn_subscriptions.items():
        if rsn in content:
            for channel_id in channels:
                try:
                    target_channel = await bot.fetch_channel(channel_id)
                    if message.embeds:
                        for embed in message.embeds:
                            await target_channel.send(embed=embed)
                    if message.attachments:
                        for attachment in message.attachments:
                            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                                await target_channel.send(attachment.url)
                except Exception as e:
                    print(f"Error forwarding message to channel {channel_id}: {e}")
            break  # Stop after the first matching RSN


# Connect to MongoDB using the provided URI from Railway
mongo_uri = os.getenv("MONGO_URI")  # You should set this in your Railway environment variables
client = MongoClient(mongo_uri)

# Choose your database
db = client['MongoDB_pulp_server']  # Replace with the name of your database

# Access collections (equivalent to Firestore collections)
wallets_collection = db['wallets']
orders_collection = db['orders']
counters_collection = db["order_counters"]  # New collection to track order ID


# The fixed orders posting channel
ORDERS_CHANNEL_ID = 1433919267711094845
# Allowed roles for commands
ALLOWED_ROLES = {1433451021736087743, 1434344428767809537, 1433480285688692856,1433848962166685778}

def has_permission(user: discord.Member):
    return any(role.id in ALLOWED_ROLES for role in user.roles)

async def log_command(interaction: discord.Interaction, command_name: str, details: str):
    # Mapping of servers to their respective log channels
    LOG_CHANNELS = {
        1433450572702285966: 1433919895875092593  # Server 1 → Log Channel 1
    }

    for guild_id, channel_id in LOG_CHANNELS.items():
        log_guild = interaction.client.get_guild(guild_id)  # Get the guild
        if log_guild:
            log_channel = log_guild.get_channel(channel_id)  # Get the log channel
            if log_channel:
                embed = discord.Embed(title="📜 Command Log", color=discord.Color.red())
                embed.add_field(name="👤 User", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                embed.add_field(name="💻 Command", value=command_name, inline=False)
                embed.add_field(name="📜 Details", value=details, inline=False)
                embed.set_footer(text=f"Used in: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                await log_channel.send(embed=embed)
            else:
                print(f"⚠️ Log channel not found in {log_guild.name} ({channel_id})")
        else:
            print(f"⚠️ Log guild not found: {guild_id}")

# Function to get wallet data (updated to handle both m and $)
def get_wallet(user_id):
    # Attempt to fetch the user's wallet data from MongoDB
    wallet_data = wallets_collection.find_one({"user_id": user_id})

    # If the wallet doesn't exist in the database, create a new one with default values
    if not wallet_data:
        print(f"Wallet not found for {user_id}, creating new wallet...")
        wallet_data = {
            "user_id": user_id,
            "wallet_dollars": 0,  # Initialize with 0$
            "spent_dollars": 0,  # Initialize with 0$ spent
            "deposit_dollars": 0     # Initialize with 0M deposit
        }
        # Insert the new wallet into the database
        wallets_collection.insert_one(wallet_data)
        print(f"New wallet created for {user_id}: {wallet_data}")

    return wallet_data
# Function to update wallet in MongoDB
def update_wallet(user_id, field, value, currency):
    # Convert all values to float safely
    try:
        value = float(value)
    except:
        print(f"❌ ERROR: Invalid value passed to update_wallet: {value}")
        return

    # Make sure the wallet document exists
    wallet_data = get_wallet(user_id)

    # If the field doesn't exist, initialize it
    if field not in wallet_data:
        wallets_collection.update_one(
            {"user_id": user_id},
            {"$set": {field: 0}},
            upsert=True
        )

    # Increment safely
    wallets_collection.update_one(
        {"user_id": user_id},
        {"$inc": {field: value}},
        upsert=True
    )

@bot.tree.command(name="wallet", description="Check a user's wallet balance")
async def wallet(interaction: discord.Interaction, user: discord.Member = None):
    # Define role IDs for special access (e.g., self-only role)
    self_only_roles = {1433500886721757215, 1433497500949413908} 
    allowed_roles = {1433451021736087743, 1434344428767809537, 1433480285688692856,1433848962166685778}

    # Check if the user has permission
    user_roles = {role.id for role in interaction.user.roles}
    has_self_only_role = bool(self_only_roles & user_roles)  # User has at least one self-only role
    has_allowed_role = bool(allowed_roles & user_roles)  # User has at least one allowed role

    # If the user has no valid role, deny access
    if not has_self_only_role and not has_allowed_role:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    # If user has only a self-only role (and not an allowed role), force them to check their own wallet
    if has_self_only_role and not has_allowed_role:
        user = interaction.user  

    # Default to interaction user if no target user is specified
    if user is None:
        user = interaction.user

    # Fetch wallet data
    user_id = str(user.id)
    wallet_data = get_wallet(user_id)
    
    # Default missing fields to 0
    wallet_dollars = wallet_data.get('wallet_dollars', 0)
    spent_dollars = wallet_data.get('spent_dollars', 0)
    deposit_dollars = wallet_data.get('deposit_dollars', 0)

    # Get user's avatar (fallback to default image)
    default_thumbnail = "https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif?ex=6930e694&is=692f9514&hm=97793a52982a40faa96ee65e6bef259afc8cc2167b3518bbf681c2fcd5b1ba99&=&width=120&height=120"
    thumbnail_url = user.avatar.url if user.avatar else default_thumbnail
    

    # Create embed message
    embed = discord.Embed(title=f"{user.display_name}'s Wallet 💳", color=discord.Color.from_rgb(139, 0, 0))
    embed.set_thumbnail(url=thumbnail_url)
    embed.add_field(
        name="Wallet",
        value=f"```💵 ${wallet_dollars}```",
        inline=False
    )
    embed.add_field(
    name="Deposit",
    value=f"```🕵️ ${deposit_dollars}```",
    inline=False
    )
    embed.add_field(
        name="Spent",
        value=f"```✍️ ${spent_dollars}```",
        inline=False
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif?ex=6930e694&is=692f9514&hm=d23318b8712a50f41e96c7d7d1bead229034c3df451c7e478cffd25e5efadf1d&=&width=520&height=72")

    # Ensure requester avatar exists
    requester_avatar = interaction.user.avatar.url if interaction.user.avatar else default_thumbnail
    embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=requester_avatar)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="add_remove_spent", description="Add or remove spent value from a user's wallet")
@app_commands.choices(
    action=[
        discord.app_commands.Choice(name="Add", value="add"),
        discord.app_commands.Choice(name="Remove", value="remove")
    ],
    currency=[
        discord.app_commands.Choice(name="$ (dollars)", value="$")
    ]
)
async def add_remove_spent(
    interaction: discord.Interaction,
    user: discord.Member,
    action: str,
    currency: str,
    value: float
):
    if not has_permission(interaction.user):  # Check role permissions
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)

    # Always use dollars only
    field_name = 'spent_dollars'

    # Fetch wallet
    wallet_data = get_wallet(user_id)
    spent_dollars = wallet_data.get(field_name, 0)

    # Handle remove action
    if action == "remove":
        if spent_dollars < value:
            await interaction.response.send_message("⚠ Insufficient spent balance to remove!", ephemeral=True)
            return
        update_wallet(user_id, field_name, -value, currency="$")
    else:
        update_wallet(user_id, field_name, value, currency="$")

    # Fetch updated wallet
    updated_wallet = get_wallet(user_id)
    spent_dollars = updated_wallet.get("spent_dollars", 0)

    # Build embed (Dollars only)
    embed = discord.Embed(
        title=f"{user.display_name}'s Wallet 💳", 
        color=discord.Color.from_rgb(139, 0, 0)
    )

    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

    embed.add_field(
        name="✍️ Spent ($)",
        value=f"```${spent_dollars}```",
        inline=False
    )

    embed.set_footer(
        text=f"Updated by {interaction.user.display_name}",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else user.default_avatar.url
    )

    await interaction.response.send_message(
        f"✅ {action.capitalize()} {value}$ spent.",
        embed=embed
    )

    # Log command
    await log_command(
        interaction,
        "add_remove_spent",
        f"User: {user.mention} | Action: {action} | Value: {value}$"
    )


async def check_and_assign_roles(user: discord.Member, spent_dollars: float, client):
    """
    Assigns roles based ONLY on dollars spent ($). 
    Thresholds are in pure USD — no M system used at all.
    """

    # Dollar-based rank thresholds
    role_milestones = {
        1: 1445599793169698887,       
        250: 1433928960714215445,     
        500: 1433928982017085442,     
        1000: 1433928992401920036,    
        1500: 1433929008302788618,    
        2000: 1433929026086371338,    
        5000: 1436228719541747765     
    }

    total_spent = float(spent_dollars)

    congrats_channel = client.get_channel(1445599237604769994)
    if congrats_channel is None:
        try:
            congrats_channel = await client.fetch_channel(1445599237604769994)
        except Exception as e:
            print(f"[ERROR] Could not fetch congrats channel: {e}")
            return

    print(f"[DEBUG] {user.display_name} - Total Spent: ${total_spent}")

    for threshold, role_id in sorted(role_milestones.items()):
        role = user.guild.get_role(role_id)
        if not role:
            print(f"[ERROR] Role ID {role_id} not found!")
            continue

        if total_spent >= threshold and role not in user.roles:
            await user.add_roles(role)
            embed = discord.Embed(
                title="🎉 Congratulations!",
                description=f"{user.mention} has reached **${threshold:,}+** spent and earned a new role!",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

            embed.add_field(
                name="🏅 New Role Earned:",
                value=role.mention,
                inline=False
            )

            embed.set_footer(
                text="Keep spending to reach new Lifetime Rank! ✨",
                icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif"
            )

            embed.set_author(
                name="✅ Pulp System ✅",
                icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif"
            )

            await congrats_channel.send(embed=embed)



@bot.tree.command(name="wallet_add_remove", description="Add or remove dollars in a user's wallet (USD only)")
@app_commands.choices(
    action=[
        discord.app_commands.Choice(name="Add", value="add"),
        discord.app_commands.Choice(name="Remove", value="remove")
    ]
)
@app_commands.describe(
    notes="Optional reason for adding/removing money (will be logged)"
)
async def wallet_add_remove(
    interaction: discord.Interaction,
    user: discord.Member,
    action: str,
    value: float,
    notes: str = None  # <-- optional notes argument
):
    if not has_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)
    wallet_data = get_wallet(user_id)

    wallet_key = "wallet_dollars"
    current_wallet = wallet_data.get(wallet_key, 0)

    # REMOVE
    if action == "remove":
        if current_wallet < value:
            await interaction.response.send_message(
                f"⚠️ Cannot remove ${value:,}. User only has ${current_wallet:,}.",
                ephemeral=True
            )
            return
        update_wallet(user_id, wallet_key, -value, "$")

    # ADD
    else:
        update_wallet(user_id, wallet_key, value, "$")

    # Refresh wallet after update
    updated = get_wallet(user_id)
    wallet_dollars = updated.get("wallet_dollars", 0)
    deposit_dollars = updated.get("deposit_dollars", 0)
    spent_dollars = updated.get("spent_dollars", 0)

    embed = discord.Embed(
        title=f"{user.display_name}'s Wallet 💳",
        color=discord.Color.from_rgb(139, 0, 0)
    )

    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

    embed.add_field(name="Deposit", value=f"```🕵️ ${deposit_dollars:,}```", inline=False)
    embed.add_field(name="Wallet", value=f"```💵 ${wallet_dollars:,}```", inline=False)
    embed.add_field(name="Spent", value=f"```✍️ ${spent_dollars:,}```", inline=False)

    embed.set_footer(
        text=f"Updated by {interaction.user.display_name}",
        icon_url=interaction.user.avatar.url
    )

    embed.set_image(
        url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif?ex=6930e694&is=692f9514&hm=d23318b8712a50f41e96c7d7d1bead229034c3df451c7e478cffd25e5efadf1d&=&width=520&height=72"
    )

    await interaction.response.send_message(
        f"✅ {action.capitalize()}ed **${value:,}** to {user.mention}'s wallet.",
        embed=embed
    )

    # Log command, include notes if provided
    log_message = f"User: {user.mention} | Action: {action} | Value: ${value:,}"
    if notes:
        log_message += f" | Notes: {notes}"
    
    await log_command(
        interaction,
        "wallet_add_remove",
        log_message
    )

    # Update rank roles (USD ONLY)
    await check_and_assign_roles(user, spent_dollars, interaction.client)





@bot.tree.command(name="deposit", description="Set or remove a user's deposit value")
@app_commands.choices(action=[
    discord.app_commands.Choice(name="Set", value="set"),
    discord.app_commands.Choice(name="Remove", value="remove")
])
async def deposit(interaction: discord.Interaction, user: discord.Member, action: str, value: int):
    if not has_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)
    wallet_data = get_wallet(user_id)

    deposit_key = "deposit_dollars"
    current_deposit = wallet_data.get(deposit_key, 0)

    if action == "set":
        new_deposit = current_deposit + value
    elif action == "remove":
        if value > current_deposit:
            await interaction.response.send_message(
                f"⚠ Cannot remove ${value:,}. The user only has ${current_deposit:,} in deposit.",
                ephemeral=True
            )
            return
        new_deposit = current_deposit - value

    # Update MongoDB
    update_wallet(user_id, deposit_key, new_deposit - current_deposit, "$")
    updated_wallet = get_wallet(user_id)

    deposit_value = f"```🕵️ ${updated_wallet.get(deposit_key, 0):,}```"
    wallet_dollars = f"{updated_wallet.get('wallet_dollars', 0):,}"
    spent_dollars = f"{updated_wallet.get('spent_dollars', 0):,}"

    embed = discord.Embed(title=f"{user.display_name}'s Wallet 💳", color=discord.Color.from_rgb(139, 0, 0))
    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

    embed.add_field(name="Deposit",value=f"```🕵️ ${deposit_value}```", inline=False)
    embed.add_field(
        name="Wallet",
        value=f"```💵 ${wallet_dollars}```",
        inline=False
    )
    embed.add_field(
        name="Spent",
        value=f"```✍️ ${spent_dollars}```",
        inline=False
    )

    embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.avatar.url)
    embed.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif?ex=6930e694&is=692f9514&hm=d23318b8712a50f41e96c7d7d1bead229034c3df451c7e478cffd25e5efadf1d&=&width=520&height=72")

    await interaction.response.send_message(
        f"✅ {action.capitalize()}ed deposit value for {user.name} by ${value:,}.",
        embed=embed
    )

    await log_command(
        interaction,
        "Deposit Set/Remove",
        f"User: {user.mention} (`{user.id}`)\nAction: {action.capitalize()}\nAmount: ${value:,}"
    )




@bot.tree.command(name="tip", description="Tip $ to another user.")
@app_commands.describe(user="User to tip", value="Amount to tip")
async def tip(interaction: discord.Interaction, user: discord.Member, value: int):
    sender_id = str(interaction.user.id)
    recipient_id = str(user.id)

    wallet_key = "wallet_dollars"
    symbol = "$"

    sender_wallet = get_wallet(sender_id)
    recipient_wallet = get_wallet(recipient_id)

    if sender_wallet.get(wallet_key, 0) < value:
        await interaction.response.send_message(f"❌ You don't have enough {symbol} to tip!", ephemeral=True)
        return

    # Update wallets
    update_wallet(sender_id, wallet_key, -value, "$")
    update_wallet(recipient_id, wallet_key, value, "$")

    # Refresh data
    sender_wallet = get_wallet(sender_id)
    recipient_wallet = get_wallet(recipient_id)

    # Sender Embed
    embed_sender = discord.Embed(title=f"{interaction.user.display_name}'s Updated Wallet 💳", color=discord.Color.from_rgb(139, 0, 0))
    embed_sender.set_thumbnail(url=interaction.user.avatar.url)
    embed_sender.add_field(
        name="Wallet",
        value=f"```💵 ${sender_wallet.get('wallet_dollars', 0):,}```",
        inline=False
    )
    embed_sender.add_field(
        name="Deposit",
        value=f"```🕵️ ${sender_wallet.get('deposit_dollars', 0):,}```",
        inline=False
    )
    embed_sender.add_field(
        name="Spent",
        value=f"```✍️ ${sender_wallet.get('spent_dollars', 0):,}```",
        inline=False
    )
    embed_sender.set_footer(text=f"Tip sent to {user.display_name}", icon_url=user.avatar.url)
    embed_sender.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif?ex=6930e694&is=692f9514&hm=d23318b8712a50f41e96c7d7d1bead229034c3df451c7e478cffd25e5efadf1d&=&width=520&height=72")

    # Recipient Embed
    embed_recipient = discord.Embed(title=f"{user.display_name}'s Updated Wallet 💳", color=discord.Color.from_rgb(139, 0, 0))
    embed_recipient.set_thumbnail(url=user.avatar.url)
    embed_recipient.add_field(
        name="Wallet",
        value=f"```💵 ${recipient_wallet.get('wallet_dollars', 0):,}```",
        inline=False
    )
    embed_recipient.add_field(
        name="Deposit",
        value=f"```🕵️ ${recipient_wallet.get('deposit_dollars', 0):,}```",
        inline=False
    )
    embed_recipient.add_field(
        name="Spent",
        value=f"```✍️ ${recipient_wallet.get('spent_dollars', 0):,}```",
        inline=False
    )
    embed_recipient.set_footer(text=f"Tip received from {interaction.user.display_name}", icon_url=interaction.user.avatar.url)
    embed_recipient.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif?ex=6930e694&is=692f9514&hm=d23318b8712a50f41e96c7d7d1bead229034c3df451c7e478cffd25e5efadf1d&=&width=520&height=72")

    # Channel message
    await interaction.response.send_message(f"💸 {interaction.user.mention} tipped {user.mention} **${value:,}**!")
    await interaction.channel.send(embed=embed_sender)
    await interaction.channel.send(embed=embed_recipient)

    # DM both users, ignore errors if DMs are off
    try:
        await interaction.user.send(f"✅ You tipped **${value:,}** to {user.display_name}!", embed=embed_sender)
    except discord.Forbidden:
        pass
    try:
        await user.send(f"🎉 You received **${value:,}** as a tip from {interaction.user.display_name}!", embed=embed_recipient)
    except discord.Forbidden:
        pass



class OrderButton(View):
    def __init__(self, order_id, deposit_required, customer_id, original_channel_id, message_id, post_channel_id):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.deposit_required = deposit_required
        self.customer_id = customer_id
        self.original_channel_id = original_channel_id
        self.message_id = message_id
        self.post_channel_id = post_channel_id

    @discord.ui.button(label="Apply For The Job✅", style=discord.ButtonStyle.primary)
    async def accept_job(self, interaction: Interaction, button: discord.ui.Button):
        order = orders_collection.find_one({"_id": self.order_id})
        if not order:
            await interaction.response.send_message("Order not found!", ephemeral=True)
            return
        # ✅ Prevent same user from applying multiple times
        existing_applicants = order.get("applicants", [])
        if interaction.user.id in existing_applicants:
            await interaction.response.send_message("You have already applied for this order!", ephemeral=True)
            return
        skip_deposit = discord.utils.get(interaction.user.roles, id=1434981057962446919) is not None

        # Only check deposit if required and skip_deposit is False
        if self.deposit_required > 0 and not skip_deposit:
            user_wallet = get_wallet(str(interaction.user.id))
            if user_wallet.get("deposit_dollars", 0) < self.deposit_required:
                await interaction.response.send_message(
                    f"You do not have enough $ deposit to claim this order! Required: {self.deposit_required}$",
                    ephemeral=True
                )
                return

        if order.get("worker"):
            await interaction.response.send_message("This order has already been claimed!", ephemeral=True)
            return
        orders_collection.update_one(
            {"_id": self.order_id},
            {"$push": {"applicants": interaction.user.id}},
            upsert=True
        )
        # ✅ Get all orders currently in-progress for this applicant
        current_orders = list(orders_collection.find({"worker": interaction.user.id, "status": "in_progress"}))
        if current_orders:
            in_progress_text = "\n".join([f"• Order #{o['_id']} - {o.get('description','No description')}" for o in current_orders])
        else:
            in_progress_text = "None"

        # ✅ Send application notification and store the message object
        bot_spam_channel = bot.get_channel(1433919298027655218)
        if bot_spam_channel:
            embed = discord.Embed(title="📌 Job Application Received", color=discord.Color.from_rgb(139, 0, 0))
            embed.add_field(name="👷 Applicant", value=interaction.user.mention, inline=True)
            embed.add_field(name="🆔 Order ID", value=str(self.order_id), inline=True)
            embed.add_field(name="🛠 Current Orders in Progress", value=in_progress_text, inline=False)
            embed.set_footer(text="Choose to Accept or Reject the applicant.")

            # ✅ Store the message object
            message_obj = await bot_spam_channel.send(embed=embed)

            # ✅ Pass message_obj to ApplicationView
            application_view = ApplicationView(
                self.order_id, interaction.user.id, self.customer_id,
                self.original_channel_id, self.message_id, self.post_channel_id,
                self.deposit_required, message_obj
            )
            await message_obj.edit(view=application_view)  # Attach the buttons
            orders_collection.update_one(
                {"_id": self.order_id},
                {"$push": {"applicant_messages": message_obj.id}},
                upsert=True
            )

        await interaction.response.send_message("Your application has been submitted for review!", ephemeral=True)


class ApplicationView(View):
    def __init__(self, order_id, applicant_id, customer_id, original_channel_id, message_id, post_channel_id, deposit_required, message_obj):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.applicant_id = applicant_id  # ✅ This is the worker
        self.customer_id = customer_id
        self.original_channel_id = original_channel_id
        self.message_id = message_id
        self.post_channel_id = post_channel_id
        self.deposit_required = deposit_required  
        self.message_obj = message_obj  # Store the applicant's message object

    @button(label="✅ Accept", style=ButtonStyle.success)
    async def accept_applicant(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        order = orders_collection.find_one({"_id": self.order_id})
        if not order:
            await interaction.followup.send("Order not found!", ephemeral=True)
            return

        if order.get("worker"):
            await interaction.followup.send("This order has already been claimed!", ephemeral=True)
            return

        # Assign worker in DB
        orders_collection.update_one({"_id": self.order_id}, {"$set": {"worker": self.applicant_id}})

        # Delete other applicants
        bot_spam_channel = bot.get_channel(1433919298027655218)
        if bot_spam_channel and "applicant_messages" in order:
            for msg_id in order.get("applicant_messages", []):
                if msg_id != self.message_obj.id:
                    try:
                        msg = await bot_spam_channel.fetch_message(msg_id)
                        await msg.delete()
                    except:
                        pass
            orders_collection.update_one(
                {"_id": self.order_id},
                {"$unset": {"applicant_messages": ""}}
            )

        # Retrieve values
        description = order.get("description", "No description provided.")
        value = order.get("value", "N/A")
        deposit_required = order.get("deposit_required", "N/A")

        # Grant worker access to order channel
        original_channel = bot.get_channel(self.original_channel_id)
        if original_channel:
            worker = interaction.guild.get_member(self.applicant_id)
            if worker:
                await original_channel.set_permissions(worker, read_messages=True, send_messages=True)
            else:
                await interaction.followup.send("❌ Could not find the applicant in the server!", ephemeral=True)
                return

            # Embed for claimed order (same style as before)
            embed = discord.Embed(title="👷‍♂️ Order Claimed", color=discord.Color.from_rgb(139, 0, 0))
            embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
            embed.set_author(name="✅ Pulp System ✅", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
            embed.add_field(name="📕 Description", value=description, inline=False)
            embed.add_field(name="👷 Worker", value=f"<@{self.applicant_id}>", inline=True)
            embed.add_field(name="📌 Customer", value=f"<@{self.customer_id}>", inline=True)
            embed.add_field(name="💵 Deposit Required", value=f"**```{deposit_required}$```**", inline=True)
            embed.add_field(name="💰 Order Value", value=f"**```{value}$```**", inline=True)
            embed.add_field(name="🆔 Order ID", value=self.order_id, inline=True)
            embed.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif")
            embed.set_footer(text="Pulp System", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
            sent_message = await original_channel.send(embed=embed)
            await sent_message.pin()

            # Notify customer and worker
            claim_message = f"**Hello! <@{self.customer_id}>, <@{self.applicant_id}> is Assigned To Be Your Worker For This Job. You Can Provide Your Account Info Using This Command `/inf`**"
            await original_channel.send(claim_message)

        # Delete original post
        post_channel = bot.get_channel(self.post_channel_id)
        if post_channel:
            try:
                message = await post_channel.fetch_message(self.message_id)
                await message.delete()
            except:
                pass

        # Delete applicant message
        try:
            await self.message_obj.delete()
        except:
            pass

        await interaction.followup.send("Applicant accepted and added to the order channel!", ephemeral=True)

    @button(label="❌ Reject", style=ButtonStyle.danger)
    async def reject_applicant(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        orders_collection.update_one(
            {"_id": self.order_id},
            {"$pull": {"applicant_messages": self.message_obj.id}}
        )
        try:
            await self.message_obj.delete()
        except:
            pass
        await interaction.followup.send(f"Applicant <@{self.applicant_id}> has been rejected.", ephemeral=True)





@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Reload buttons for active orders
    for order in orders_collection.find({"worker": None}):  # Only for unclaimed orders
        channel = bot.get_channel(order["channel_id"])
        if channel:
            try:
                message = await channel.fetch_message(order["message_id"])
                view = OrderButton(order["_id"], order["deposit_required"], order["customer"], order["original_channel_id"], order["message_id"], order["post_channel_id"])
                await message.edit(view=view)
            except discord.NotFound:
                print(f"Order message {order['message_id']} not found, skipping.")
    
    print("Re-registered all active order buttons!")

def get_next_order_id():
    counter = counters_collection.find_one({"_id": "order_counter"})
    
    if not counter:
        # Initialize the counter to 1 if it does not exist
        counters_collection.insert_one({"_id": "order_counter", "seq": 1})
        return 1  # First order ID should be 1

    # Increment and return the next order ID
    counter = counters_collection.find_one_and_update(
        {"_id": "order_counter"},
        {"$inc": {"seq": 1}},  # Increment the existing counter
        return_document=ReturnDocument.AFTER
    )
    return counter["seq"]

@bot.tree.command(name="post", description="Post a new order or assign directly to a worker (USD only).")
@app_commands.describe(
    customer="The customer for the order",
    value="The value of the order (in $)",
    deposit_required="The deposit required for the order",
    holder="The holder of the order",
    channel="The channel to post the order (optional)",
    description="Description of the order",
    image="Image URL to show at the bottom of the embed",
    worker="Optional: Assign a worker directly (acts like /set)",
    pricing_agent="Pricing agent to take half of the helper commission"
)
async def post(
    interaction: discord.Interaction,
    customer: discord.Member,
    pricing_agent: discord.Member,
    value: float,
    deposit_required: float,
    holder: discord.Member,
    description: str,
    channel: discord.TextChannel = None,
    image: str = None,
    worker: discord.Member = None
):
    if not has_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    order_id = get_next_order_id()
    original_channel_id = interaction.channel.id

    # Default channel if not provided
    if not channel:
        channel = interaction.guild.get_channel(1433919267711094845)

    # Format numbers
    formatted_value = f"{value:,.2f}$"
    formatted_deposit = f"{deposit_required:,.2f}$"

    # Embed creation
    embed = discord.Embed(title="New Order", color=discord.Color.from_rgb(139, 0, 0))
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
    embed.set_author(name="💼 Order Posted", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
    embed.description = f"📕 **Description:**\n{description}"
    embed.add_field(name="💰 Value", value=f"**```{formatted_value}```**", inline=True)
    embed.add_field(name="💵 Deposit Required", value=f"**```{formatted_deposit}```**", inline=True)
    embed.add_field(name="🕵️‍♂️ Holder", value=holder.mention, inline=True)

    if image:
        embed.set_image(url=image)
    else:
        embed.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif")

    embed.set_footer(text=f"Order ID: {order_id}", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")

    # ----------- If worker is provided → act like /set -----------
    if worker:
        skip_deposit = discord.utils.get(worker.roles, id=1434981057962446919) is not None

        if not skip_deposit:
            wallet_data = get_wallet(str(worker.id))
            worker_deposit = wallet_data.get("deposit_dollars", 0)
            if worker_deposit < deposit_required:
                await interaction.response.send_message(
                    f"⚠️ {worker.display_name} does not have enough deposit. Required: {formatted_deposit}, Available: {worker_deposit}$",
                    ephemeral=True
                )
                return

        message = await channel.send(embed=embed)
        message_id = message.id

        orders_collection.insert_one({
            "_id": order_id,
            "customer": customer.id,
            "worker": worker.id,
            "pricing_agent": pricing_agent.id if pricing_agent else None,
            "value": value,
            "deposit_required": deposit_required,
            "holder": holder.id,
            "message_id": message_id,
            "channel_id": channel.id,
            "original_channel_id": original_channel_id,
            "description": description,
            "status": "in_progress",
            "currency": "$",
            "posted_by": interaction.user.id
        })

        # Update wallets
        update_wallet(str(customer.id), "spent_dollars", deposit_required, "$")
        if not skip_deposit:
            update_wallet(str(worker.id), "wallet_dollars", round(deposit_required * 0.85, 2), "$")

        # Give permissions to worker
        await channel.set_permissions(worker, read_messages=True, send_messages=True)

        await interaction.response.send_message(f"✅ Order assigned directly to {worker.mention}!", ephemeral=True)
        return

    # ----------- Normal post if no worker assigned -----------
    role_ping = None
    role1 = discord.utils.get(interaction.guild.roles, id=1433500886721757215)
    role2 = discord.utils.get(interaction.guild.roles, id=1208792946401615902)
    if role1:
        role_ping = role1.mention
    elif role2:
        role_ping = role2.mention

    message = await channel.send(f"{role_ping}" if role_ping else None, embed=embed)
    await message.edit(view=OrderButton(order_id, deposit_required, customer.id, original_channel_id, message.id, channel.id))

    orders_collection.insert_one({
        "_id": order_id,
        "customer": customer.id,
        "worker": None,
        "value": value,
        "deposit_required": deposit_required,
        "holder": holder.id,
        "message_id": message.id,
        "channel_id": channel.id,
        "original_channel_id": original_channel_id,
        "description": description,
        "currency": "$",
        "posted_by": interaction.user.id
    })

    # Confirmation and log
    confirmation_embed = embed.copy()
    confirmation_embed.title = "✅ Order Posted Successfully"
    await interaction.channel.send(embed=confirmation_embed)

    await interaction.response.send_message("💵 Order posted successfully in USD!", ephemeral=True)

    await log_command(
        interaction,
        "Order Posted",
        f"Customer: {customer.mention} (`{customer.id}`)\n"
        f"Value: {formatted_value}\n"
        f"Deposit Required: {formatted_deposit}\n"
        f"Holder: {holder.mention} (`{holder.id}`)\n"
        f"Channel: {channel.mention}\n"
        f"Description: {description}"
    )

FEEDBACK_CHANNEL_ID= 1433532064753389629

@bot.tree.command(name="complete", description="Mark an order as completed (USD only).")
@app_commands.describe(
    order_id="Order ID to complete",
    commission="Server commission % (default 20%)",
    support_agent="Optional: Support agent to take part of helper commission"
)
async def complete(interaction: Interaction, order_id: int, support_agent: discord.Member, commission: float = 20.0 ):
    # Permission check
    if not has_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    # Fetch order
    order = orders_collection.find_one({"_id": order_id})
    if not order:
        await interaction.response.send_message("❌ Order not found!", ephemeral=True)
        return

    if order.get("status") == "completed":
        await interaction.response.send_message("⚠️ This order has already been completed.", ephemeral=True)
        return

    # ------------ VALUE SANITIZER (USD ONLY) ------------
    def fix_value(v):
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace("$", "").replace(",", "").strip().lower()
        if s.endswith("k"):
            return float(s[:-1]) * 1000
        elif s.endswith("m"):
            return float(s[:-1]) * 1_000_000
        return float(s)

    value = fix_value(order["value"])

    # IDs
    customer_id = str(order["customer"])
    worker_id = str(order["worker"])
    helper_id = order.get("posted_by")
    pricing_agent_id = order.get("pricing_agent")
    support_agent_id = support_agent.id if support_agent else None

    # Percentages
    # Commission
    commission_total = round(value * (commission / 100), 2)
    worker_payment = round(value - commission_total, 2)

    # Total extra share (3% of value) distributed among helpers
    total_extra = round(value * 0.03, 2)
    split_count = sum([1 if helper_id else 0, 1 if pricing_agent_id else 0, 1 if support_agent else 0])
    per_person_share = round(total_extra / split_count, 2) if split_count > 0 else 0

    helper_payment = 0
    pricing_payment = per_person_share if pricing_agent_id else 0
    support_payment = per_person_share if support_agent else 0

    # Deduct extra shares from commission
    adjusted_commission = round(commission_total - total_extra, 2)


    # Update wallets
    update_wallet(customer_id, "spent_dollars", value, "$")
    update_wallet(worker_id, "wallet_dollars", worker_payment, "$")
    if pricing_agent_id:
        update_wallet(str(pricing_agent_id), "wallet_dollars", pricing_payment, "$")
    if support_agent:
        update_wallet(str(support_agent.id), "wallet_dollars", support_payment, "$")

    # Mark order as completed
    orders_collection.update_one({"_id": order_id}, {"$set": {"status": "completed"}})

    # Assign roles if needed
    guild = interaction.guild
    customer = guild.get_member(int(customer_id))
    if customer:
        await check_and_assign_roles(customer, value, interaction.client)
    else:
        print(f"[ERROR] Customer {customer_id} not found in the Discord server.")

    # ---------- Original Channel Embed ----------
    original_channel = bot.get_channel(order["original_channel_id"])
    if original_channel:
        embed = Embed(title="✅ Order Completed", color=discord.Color.from_rgb(139, 0, 0))
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        embed.set_author(name="Pulp System", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        embed.add_field(name="📕 Description", value=order.get("description", "No description provided."), inline=False)
        embed.add_field(name="👷 Worker", value=f"<@{worker_id}>", inline=True)
        embed.add_field(name="📌 Customer", value=f"<@{customer_id}>", inline=True)
        embed.add_field(name="💰 Value", value=f"**{value}$**", inline=True)
        total_extra_text = helper_payment + pricing_payment + support_payment
        embed.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif")
        embed.set_footer(text=f"📜 Order ID: {order_id}", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        await original_channel.send(embed=embed)

        # ---------- Security Reminder ----------
        security = Embed(
            title="🔒 Security Reminder",
            description=(f"**<@{customer_id}>**\n\n"
                         "__Please do the following immediately:__\n"
                         "• **Change your account password**\n"
                         "• **End All Sessions**\n"
                         "• **Change your bank PIN** (Optional)\n"),
            color=discord.Color.gold()
        )
        security.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        security.set_author(name="Pulp System", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        security.set_footer(text="Pulp System • Please confirm once done", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        security.add_field(name="⚠️ Action Required", value="**This is for your safety. Please confirm here once changed.**", inline=False)
        await original_channel.send(content=f"<@{customer_id}>", embed=security)

        # ---------- Feedback Embed + Buttons ----------
        class FeedbackModal(Modal):
            def __init__(self, default_stars=5):
                super().__init__(title="Service Feedback")
                self.stars_input = TextInput(
                    label="Rating (1–5 ⭐)",
                    style=TextStyle.short,
                    default=str(default_stars),
                    placeholder="1–5 stars",
                    max_length=1,
                    required=True
                )
                self.review_input = TextInput(
                    label="We Appreciate A Detailed Review!",
                    style=TextStyle.paragraph,
                    placeholder="Describe your service experience...",
                    required=True,
                    max_length=500
                )
                self.add_item(self.stars_input)
                self.add_item(self.review_input)

            async def on_submit(self, interaction: Interaction):
                try:
                    stars = int(self.stars_input.value)
                    if stars < 1 or stars > 5:
                        stars = 5
                except:
                    stars = 5
                stars_text = "<:Glimmer:1441041235547525120>" * stars
                review = self.review_input.value

                embed = Embed(
                    title="🌟 Pulp Vouches! 🌟",
                    color=discord.Color.from_rgb(200, 0, 0),
                    description=(
                        f"**Date:** `{interaction.created_at.strftime('%B %d, %Y')}`\n"
                        f"**Discord User:** `{interaction.user.name}`\n\n"
                        f"**Rating:** {stars_text}\n"
                        f"**Vouch:**\n{review}"
                    )
                )
                embed.set_author(name=f"{interaction.user.name} left a vouch!", icon_url=interaction.user.display_avatar.url)
                embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
                embed.set_footer(text="Thank you for your feedback!", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
                feedback_channel = bot.get_channel(FEEDBACK_CHANNEL_ID)
                if feedback_channel:
                    await feedback_channel.send(embed=embed)
                    await interaction.response.send_message("✅ Thank you for your feedback!", ephemeral=True)
                else:
                    await interaction.response.send_message("⚠️ Feedback channel not found!", ephemeral=True)

        class FeedbackView(View):
            def __init__(self):
                super().__init__(timeout=None)
                self.add_item(Button(label="Rate / Give Feedback ⭐", style=discord.ButtonStyle.primary))
                self.add_item(Button(
                    label="Vouch For Us On Sythe!. (2% CashBack)",
                    url="https://www.sythe.org/threads/pulp-services-vouch-thread/",
                    style=discord.ButtonStyle.url,
                    emoji=discord.PartialEmoji(name="1332330797998280724", id=1445611458208727111)
                ))

            @discord.ui.button(label="Rate / Give Feedback ⭐", style=discord.ButtonStyle.primary)
            async def feedback_button(self, interaction: Interaction, button: Button):
                await interaction.response.send_modal(FeedbackModal(default_stars=5))

        feedback_embed = Embed(
            title="📝 Vouch For Us!",
            color=discord.Color.from_rgb(200, 0, 0),
            description=(
                "**We Appreciate Your Vouch on [Sythe](https://www.sythe.org/threads/pulp-services-vouch-thread/).**\n"
                "✨ **Get a +10% Discount** When You Vouch.\n"
                "**Check Discounts Here.** <#1433917514412462090> \n\n"
                "**Please select your rating below.**\n"
                "Once Selected, You Will Be Asked To Leave A Review."
            )
        )
        feedback_embed.set_author(name="Pulp System", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        feedback_embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        feedback_embed.set_footer(text="Pulp Services", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")

        view = FeedbackView()
        await original_channel.send(embed=feedback_embed, view=view)

    # ---------- DM Worker ----------
    worker = bot.get_user(order["worker"])
    if worker:
        dm_embed = Embed(title="✅ Order Completed", color=discord.Color.from_rgb(139, 0, 0))
        dm_embed.add_field(name="📕 Description", value=order.get("description", "No description provided."), inline=False)
        dm_embed.add_field(name="💰 Value", value=f"**{value}$**", inline=True)
        dm_embed.add_field(name="👷‍♂️ Your Payment", value=f"**{worker_payment}$**", inline=True)
        dm_embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        try:
            await worker.send(embed=dm_embed)
        except discord.Forbidden:
            print(f"[WARNING] Could not DM worker {worker.id}. DMs may be closed.")

    notify_channel = bot.get_channel(1445612754533880001)
    if notify_channel:
        # Only include pricing_agent and support_agent in this embed
        embed = discord.Embed(
            title=f"🎯 Agents Commission Summary",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        embed.set_author(name="Pulp System", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")
        embed.set_footer(text="Pulp System", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif")

        embed.add_field(name="📜 Order ID", value=f"`{order_id}`", inline=True)
        embed.add_field(name="💰 Order Value", value=f"**```{value}$```**", inline=True)

        if pricing_agent_id and pricing_payment > 0:
            embed.add_field(name="💼 Pricing Agent Share", value=f"<@{pricing_agent_id}> — **{pricing_payment}$**", inline=True)
        if support_agent_id and support_payment > 0:
            embed.add_field(name="🛡 Support Agent Share", value=f"<@{support_agent_id}> — **{support_payment}$**", inline=True)

        await notify_channel.send(embed=embed)


    # ---------- Final Response ----------
    await interaction.followup.send("✅ Order marked as completed successfully!", ephemeral=True)

    # ---------- Log Command ----------
    await log_command(
        interaction,
        "Order Completed",
        f"📦 **Order ID:** `{order_id}`\n"
        f"👷 **Worker:** <@{worker_id}>\n"
        f"💰 **Value:** ${value:,.2f}\n"
        f"💸 **Worker Take:** ${worker_payment:,.2f}\n"
        f"💼 **Commission {commission}%:** ${adjusted_commission:,.2f}\n"
        f"🎁 **Extra Rewards Total:** ${helper_payment + pricing_payment + support_payment:,.2f}\n"
        f"🧾 **Posted By:** <@{helper_id}>"
    )



# 📌 /order_deletion command
@bot.tree.command(name="order_deletion", description="Delete an order.")
async def order_deletion(interaction: Interaction, order_id: int):
    if not has_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    order = orders_collection.find_one({"_id": order_id})
    
    if not order:
        await interaction.response.send_message("❌ Order not found!", ephemeral=True)
        return

    # Delete the order message in the orders channel
    order_channel = bot.get_channel(order["channel_id"])
    if order_channel:
        try:
            message = await order_channel.fetch_message(order["message_id"])
            await message.delete()
        except discord.NotFound:
            print(f"⚠️ Message for order {order_id} not found in orders channel. Skipping deletion.")

    # Delete the original post message in the interaction channel
    original_channel = bot.get_channel(order["original_channel_id"])
    if original_channel:
        try:
            original_message = await original_channel.fetch_message(order["message_id"])
            await original_message.delete()
        except discord.NotFound:
            print(f"⚠️ Original message for order {order_id} not found. Skipping deletion.")

    # Remove the order from MongoDB
    orders_collection.delete_one({"_id": order_id})
    
    await interaction.response.send_message(f"✅ Order {order_id} has been successfully deleted.", ephemeral=True)
    await log_command(interaction, "Order Deleted", f"Order ID: {order_id}\nDeleted by: {interaction.user.mention} (`{interaction.user.id}`)")

@bot.tree.command(name="view_order", description="View details of an order")
async def view_order(interaction: discord.Interaction, order_id: int):
    # Required role IDs
    allowed_roles = {1433451021736087743, 1434344428767809537, 1433480285688692856,1433848962166685778}

    # Check if user has at least one of the required roles
    if not any(role.id in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    order = orders_collection.find_one({"_id": order_id})
    
    if not order:
        await interaction.response.send_message("❌ Order not found.", ephemeral=True)
        return

    # Extract values safely, handling possible None values
    worker_id = order.get("worker", {}).get("low") if isinstance(order.get("worker"), dict) else order.get("worker", "Not Assigned")
    customer_id = order.get("customer", {}).get("low") if isinstance(order.get("customer"), dict) else order.get("customer", "Unknown")
    holder_id = order.get("holder", {}).get("low") if isinstance(order.get("holder"), dict) else order.get("holder", "N/A")
    
    deposit = order.get("deposit_required", 0)
    value = order.get("value", 0)
    description = order.get("description", "No description provided")

    # Get status, default to "In Progress"
    status = order.get("status", "In Progress").capitalize()

    embed = discord.Embed(title="📦 Order Details", color=discord.Color.from_rgb(139, 0, 0))
    embed.add_field(name="📊 Status", value=status, inline=False)
    embed.set_author(name="Pulp System", icon_url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif?ex=6930e694&is=692f9514&hm=97793a52982a40faa96ee65e6bef259afc8cc2167b3518bbf681c2fcd5b1ba99&=&width=120&height=120")
    embed.add_field(name="👷 Worker", value=f"<@{worker_id}>" if isinstance(worker_id, int) else worker_id, inline=False)
    embed.add_field(name="📌 Customer", value=f"<@{customer_id}>" if isinstance(customer_id, int) else customer_id, inline=False)
    embed.add_field(name="🎟️ Holder", value=f"<@{holder_id}>" if isinstance(holder_id, int) else holder_id, inline=False)
    embed.add_field(name="📕 Description", value=description, inline=False)
    embed.add_field(name="💵 Deposit", value=f"**```{deposit}$```**", inline=True)
    embed.add_field(name="💰 Order Value", value=f"**```{value}$```**", inline=True)
    embed.add_field(name="🆔 Order ID", value=order_id, inline=False)
    embed.set_image(url="https://media.discordapp.net/attachments/1445150831233073223/1445590514127732848/Footer_2.gif?ex=6930e694&is=692f9514&hm=d23318b8712a50f41e96c7d7d1bead229034c3df451c7e478cffd25e5efadf1d&=&width=520&height=72")
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1445150831233073223/1445590515256000572/Profile.gif?ex=6930e694&is=692f9514&hm=97793a52982a40faa96ee65e6bef259afc8cc2167b3518bbf681c2fcd5b1ba99&=&width=120&height=120")
    await interaction.response.send_message(embed=embed)


# Syncing command tree for slash commands
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()  # Sync all slash commands
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# Flask setup for keeping the bot alive (Replit hosting)
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    thread = Thread(target=run)
    thread.start()

# Add restart command for the bot (Owner-only)
@bot.command()
@commands.is_owner()
async def restart(ctx):
    await ctx.send("Restarting bot...")
    os.execv(__file__, ['python'] + os.sys.argv)

# Retrieve the token from the environment variable
token = os.getenv('DISCORD_BOT_TOKEN')
if not token:
    print("Error: DISCORD_BOT_TOKEN is not set in the environment variables.")
    exit(1)

# Keep the bot alive for Replit hosting
keep_alive()

@bot.command()
async def test(ctx):
    await ctx.send("Bot is responding!")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")
# Run the bot with the token
bot.run(token)
