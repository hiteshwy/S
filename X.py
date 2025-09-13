import discord
from discord import app_commands, ui, ButtonStyle, HTTPException
import docker
import psutil
import json
import os
import asyncio
from dotenv import load_dotenv
from typing import List, Optional

# --- Configuration ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_USER_IDS = [int(uid) for uid in os.getenv('ADMIN_USER_IDS', '').split(',') if uid]
HOSTNAME = os.getenv('HOSTNAME', 'darknode')
WATERMARK = os.getenv('WATERMARK', 'DarkNode')
DOCKER_IMAGE = os.getenv('DOCKER_IMAGE', 'ubuntu:22.04')
# Note: The DATA_DIR is now a blank string, so files are saved to the bot's root folder.
DATA_DIR = os.getenv('DATA_DIR', '')

# --- File Paths ---
SESSIONS_FILE = os.path.join(DATA_DIR, 'sessions.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

# --- Bot Setup ---
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- Helper Functions ---
def get_embed(title: str, description: str, color=0x000000):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f'{WATERMARK} | Host: {HOSTNAME}')
    return embed

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

def load_data(file_path: str):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, 'r') as f:
        return json.load(f)

def save_data(data: dict, file_path: str):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def install_tmate_script(container_name: str):
    """Generates a script to install tmate inside the container."""
    return f"""
    apt-get update && apt-get install -y openssh-server curl sudo tmate
    """

def get_tmate_session(container):
    """
    Executes 'tmate' inside the container and extracts the SSH link.
    """
    try:
        # Start a tmate session and detach
        _, stream = container.exec_run('tmate -S /tmp/tmate.sock -F "#{tmate_ssh}" new', stream=True)
        # Give tmate a moment to start and generate the link
        asyncio.sleep(3)
        # Read the stream to get the SSH link
        output = b"".join(stream).decode('utf-8').strip()
        if not output or 'tmate' in output:
            raise Exception("Failed to get tmate SSH link. Check if tmate is installed correctly.")
        return output
    except Exception as e:
        print(f"Error getting tmate session for {container.name}: {e}")
        return None

# --- Docker & Data Management ---
docker_client = docker.from_env()

async def create_vps(ram_mb: int, cpu_cores: int, disk_gb: int, container_name: str, user_id: int):
    """Deploys an Ubuntu container with tmate and records the session."""
    sessions = load_data(SESSIONS_FILE)
    if container_name in sessions:
        return None, "A container with that name already exists."

    try:
        container = docker_client.containers.run(
            DOCKER_IMAGE,
            name=container_name,
            detach=True,
            tty=True,
            stdin_open=True,
            mem_limit=f'{ram_mb}m',
            cpus=cpu_cores,
        )
        print(f"Container '{container_name}' started.")

        exec_id = container.exec_run(install_tmate_script(container_name))
        await asyncio.sleep(10)  # Wait for tmate to install
        
        tmate_link = get_tmate_session(container)
        
        sessions[container_name] = {
            'user_id': user_id,
            'state': 'running',
            'ram_mb': ram_mb,
            'cpu_cores': cpu_cores,
            'disk_gb': disk_gb,
            'tmate_link': tmate_link
        }
        save_data(sessions, SESSIONS_FILE)
        return container, tmate_link
    except docker.errors.APIError as e:
        print(f"Docker API Error: {e}")
        return None, f"Docker API Error: {e}"
    except Exception as e:
        print(f"Error creating VPS: {e}")
        return None, f"An unexpected error occurred: {e}"

# --- Modals ---
class DeployModal(ui.Modal, title='Deploy a New VPS'):
    def __init__(self):
        super().__init__()
        self.container_name_input = ui.TextInput(
            label="Container Name",
            placeholder="e.g., my-vps-01",
            required=True,
        )
        self.ram_input = ui.TextInput(
            label="RAM (MB)",
            placeholder="e.g., 512",
            required=True,
        )
        self.cpu_input = ui.TextInput(
            label="CPU Cores",
            placeholder="e.g., 1",
            required=True,
        )
        self.disk_input = ui.TextInput(
            label="Disk Size (GB)",
            placeholder="e.g., 5",
            required=True,
        )
        self.user_id_input = ui.TextInput(
            label="User ID (Deploy for another user)",
            placeholder="Your ID by default",
            required=False
        )

        self.add_item(self.container_name_input)
        self.add_item(self.ram_input)
        self.add_item(self.cpu_input)
        self.add_item(self.disk_input)
        self.add_item(self.user_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        container_name = self.container_name_input.value
        try:
            ram = int(self.ram_input.value)
            cpu = int(self.cpu_input.value)
            disk = int(self.disk_input.value)
            user_id = int(self.user_id_input.value) if self.user_id_input.value else interaction.user.id
        except ValueError:
            await interaction.followup.send(embed=get_embed(
                "❌ Invalid Input", "RAM, CPU, and Disk must be numbers."), ephemeral=True)
            return

        container, tmate_link = await create_vps(ram, cpu, disk, container_name, user_id)
        
        if container:
            # Send the tmate link via DM
            user = await client.fetch_user(user_id)
            try:
                dm_embed = get_embed("✅ VPS Deployed!", 
                    f"Your new VPS named `{container_name}` has been deployed.\n"
                    f"**SSH Link:** `{tmate_link}`\n\n"
                    "**This is a private link. Do not share it.**"
                )
                await user.send(embed=dm_embed)
            except HTTPException:
                pass # Can't DM user, continue without sending
            
            await interaction.followup.send(
                embed=get_embed("✅ VPS Deployed Successfully!", 
                f"VPS `{container_name}` has been created for user ID `{user_id}`.\n"
                f"The SSH link has been sent to their DMs."
            ))
        else:
            await interaction.followup.send(
                embed=get_embed("❌ Deployment Failed", f"Could not deploy the VPS. Reason: {tmate_link}"),
                ephemeral=True
            )

# --- Views ---
class ManageView(ui.View):
    def __init__(self, container_name: str, user_id: int):
        super().__init__()
        self.container_name = container_name
        self.user_id = user_id

    @ui.button(label="Start", style=ButtonStyle.green)
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.user_id and not is_admin(interaction.user.id):
            await interaction.followup.send(embed=get_embed("❌ Access Denied", "You can only manage your own VPS."), ephemeral=True)
            return
        
        try:
            container = docker_client.containers.get(self.container_name)
            container.start()
            sessions = load_data(SESSIONS_FILE)
            sessions[self.container_name]['state'] = 'running'
            save_data(sessions, SESSIONS_FILE)
            await interaction.followup.send(embed=get_embed("✅ VPS Started", f"Container `{self.container_name}` has been started."))
        except docker.errors.NotFound:
            await interaction.followup.send(embed=get_embed("❌ Error", "Container not found."), ephemeral=True)

    @ui.button(label="Stop", style=ButtonStyle.red)
    async def stop_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.user_id and not is_admin(interaction.user.id):
            await interaction.followup.send(embed=get_embed("❌ Access Denied", "You can only manage your own VPS."), ephemeral=True)
            return
        
        try:
            container = docker_client.containers.get(self.container_name)
            container.stop()
            sessions = load_data(SESSIONS_FILE)
            sessions[self.container_name]['state'] = 'stopped'
            save_data(sessions, SESSIONS_FILE)
            await interaction.followup.send(embed=get_embed("✅ VPS Stopped", f"Container `{self.container_name}` has been stopped."))
        except docker.errors.NotFound:
            await interaction.followup.send(embed=get_embed("❌ Error", "Container not found."), ephemeral=True)

    @ui.button(label="Restart", style=ButtonStyle.primary)
    async def restart_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.user_id and not is_admin(interaction.user.id):
            await interaction.followup.send(embed=get_embed("❌ Access Denied", "You can only manage your own VPS."), ephemeral=True)
            return
        
        try:
            container = docker_client.containers.get(self.container_name)
            container.restart()
            sessions = load_data(SESSIONS_FILE)
            sessions[self.container_name]['state'] = 'running'
            save_data(sessions, SESSIONS_FILE)
            await interaction.followup.send(embed=get_embed("✅ VPS Restarted", f"Container `{self.container_name}` has been restarted."))
        except docker.errors.NotFound:
            await interaction.followup.send(embed=get_embed("❌ Error", "Container not found."), ephemeral=True)

    @ui.button(label="Delete", style=ButtonStyle.grey)
    async def delete_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.user_id and not is_admin(interaction.user.id):
            await interaction.followup.send(embed=get_embed("❌ Access Denied", "You can only manage your own VPS."), ephemeral=True)
            return
        
        try:
            container = docker_client.containers.get(self.container_name)
            container.remove(force=True)
            sessions = load_data(SESSIONS_FILE)
            del sessions[self.container_name]
            save_data(sessions, SESSIONS_FILE)
            await interaction.followup.send(embed=get_embed("✅ VPS Deleted", f"Container `{self.container_name}` has been permanently deleted."))
        except docker.errors.NotFound:
            await interaction.followup.send(embed=get_embed("❌ Error", "Container not found."), ephemeral=True)
        
    @ui.button(label="Regen-SSH", style=ButtonStyle.secondary)
    async def regen_ssh_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.user.id != self.user_id and not is_admin(interaction.user.id):
            await interaction.followup.send(embed=get_embed("❌ Access Denied", "You can only manage your own VPS."), ephemeral=True)
            return
            
        try:
            container = docker_client.containers.get(self.container_name)
            tmate_link = get_tmate_session(container)
            if tmate_link:
                sessions = load_data(SESSIONS_FILE)
                sessions[self.container_name]['tmate_link'] = tmate_link
                save_data(sessions, SESSIONS_FILE)
                
                user = await client.fetch_user(session_data['user_id'])
                dm_embed = get_embed("✅ New SSH Link", f"A new SSH link for `{container_name}` has been generated:\n`{tmate_link}`")
                await user.send(embed=dm_embed)
                
                await interaction.followup.send(embed=get_embed("✅ SSH Link Regenerated", "A new SSH link has been sent to your DMs."))
            else:
                await interaction.followup.send(embed=get_embed("❌ Error", "Failed to regenerate tmate session."), ephemeral=True)
        except docker.errors.NotFound:
            await interaction.followup.send(embed=get_embed("❌ Error", "Container not found."), ephemeral=True)

# --- Commands ---
@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('Syncing slash commands...')
    await tree.sync()
    print('Syncing complete.')
    if not os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, 'w') as f:
            json.dump({}, f)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump({}, f)

@tree.command(name="deploy", description="[ADMIN-ONLY] Deploy a new VPS.")
@app_commands.check(lambda interaction: is_admin(interaction.user.id))
async def deploy_command(interaction: discord.Interaction):
    await interaction.response.send_modal(DeployModal())

@tree.command(name="sysinfo", description="Shows detailed host system information.")
async def sysinfo_command(interaction: discord.Interaction):
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    embed = get_embed("🖥️ System Information", "Detailed host resource usage.")
    embed.add_field(name="CPU Usage", value=f"`{cpu_percent:.2f}%`", inline=True)
    embed.add_field(name="Memory Usage", value=f"`{memory.percent:.2f}%` ({memory.used / 1024**3:.2f}GB / {memory.total / 1024**3:.2f}GB)", inline=True)
    embed.add_field(name="Disk Usage", value=f"`{disk.percent:.2f}%` ({disk.used / 1024**3:.2f}GB / {disk.total / 1024**3:.2f}GB)", inline=False)
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="list", description="List your deployed VPS instances.")
async def list_command(interaction: discord.Interaction):
    sessions = load_data(SESSIONS_FILE)
    user_sessions = [
        (name, data) for name, data in sessions.items()
        if data['user_id'] == interaction.user.id or is_admin(interaction.user.id)
    ]
    
    if not user_sessions:
        await interaction.response.send_message(embed=get_embed("⚠️ No VPS Found", "You don't have any deployed VPS instances."), ephemeral=True)
        return
        
    description = ""
    for name, data in user_sessions:
        description += f"• **{name}**\n"
        description += f"  > Status: `{data['state'].capitalize()}`\n"
        description += f"  > Specs: `{data['ram_mb']}MB RAM, {data['cpu_cores']} CPU, {data['disk_gb']}GB Disk`\n"

    embed = get_embed("📋 Your VPS Instances", description)
    await interaction.response.send_message(embed=embed)

@tree.command(name="manage", description="Manage your deployed VPS instances with interactive buttons.")
@app_commands.describe(container_name="The name of the VPS container you want to manage.")
async def manage_command(interaction: discord.Interaction, container_name: str):
    sessions = load_data(SESSIONS_FILE)
    session_data = sessions.get(container_name)
    
    if not session_data or (session_data['user_id'] != interaction.user.id and not is_admin(interaction.user.id)):
        await interaction.response.send_message(embed=get_embed("❌ Not Found", "You do not have a VPS with that name."), ephemeral=True)
        return
        
    embed = get_embed(f"⚙️ Managing: {container_name}", "Use the buttons below to control your VPS.")
    embed.add_field(name="Status", value=f"`{session_data['state'].capitalize()}`", inline=True)
    embed.add_field(name="Specs", value=f"`{session_data['ram_mb']}MB RAM, {session_data['cpu_cores']} CPU, {session_data['disk_gb']}GB Disk`", inline=True)
    
    view = ManageView(container_name, session_data['user_id'])
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="regen-ssh", description="Regenerates the tmate SSH link for a VPS.")
@app_commands.describe(container_name="The name of the VPS container to regenerate the SSH link for.")
async def regen_ssh_command(interaction: discord.Interaction, container_name: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    sessions = load_data(SESSIONS_FILE)
    session_data = sessions.get(container_name)
    
    if not session_data or (session_data['user_id'] != interaction.user.id and not is_admin(interaction.user.id)):
        await interaction.followup.send(embed=get_embed("❌ Not Found", "You do not have a VPS with that name."), ephemeral=True)
        return
    
    try:
        container = docker_client.containers.get(container_name)
        tmate_link = get_tmate_session(container)
        
        if tmate_link:
            session_data['tmate_link'] = tmate_link
            save_data(sessions, SESSIONS_FILE)
            
            user = await client.fetch_user(session_data['user_id'])
            dm_embed = get_embed("✅ New SSH Link", f"A new SSH link for `{container_name}` has been generated:\n`{tmate_link}`")
            await user.send(embed=dm_embed)
            
            await interaction.followup.send(embed=get_embed("✅ SSH Link Regenerated", "A new SSH link has been sent to your DMs."))
        else:
            await interaction.followup.send(embed=get_embed("❌ Error", "Failed to regenerate tmate session."), ephemeral=True)

    except docker.errors.NotFound:
        await interaction.followup.send(embed=get_embed("❌ Error", "Container not found."), ephemeral=True)

# --- Run Bot ---
client.run(DISCORD_TOKEN)
