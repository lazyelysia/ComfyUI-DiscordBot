import os
import sys
import random
import platform
import tempfile
from datetime import datetime
from math import ceil, sqrt
from typing import List, Optional

import discord
from discord import app_commands
from PIL import Image

from configEdit import config_loader, setup_config, get_models

# ---------------------------------------------------------------------------
# Bot Init & Imports
# ---------------------------------------------------------------------------
TOKEN, IMAGE_SOURCE = setup_config()
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

if IMAGE_SOURCE == "LOCAL":
    from imageGen import generate_images, upscale_image, generate_alternatives


# Dynamic autocomplete fetchers for slash commands
async def lora_autocomplete(
    interaction: discord.Interaction, 
    current: str
) -> List[app_commands.Choice[str]]:
    loras = get_models('loras')
    current_lower = current.lower().strip()
    choices = []

    for lora in loras:
        if not current_lower or current_lower in lora.lower():
            # Truncate label safely if total path exceeds 100 chars
            display_name = lora if len(lora) <= 100 else f"...{lora[-97:]}"
            choices.append(app_commands.Choice(name=display_name, value=lora[:100]))
            
        if len(choices) >= 25:  # Discord UI hard limit
            break

    return choices


async def checkpoint_autocomplete(
    interaction: discord.Interaction, 
    current: str
) -> List[app_commands.Choice[str]]:
    checkpoints = get_models('checkpoints')
    current_lower = current.lower().strip()
    choices = []

    for ckpt in checkpoints:
        if not current_lower or current_lower in ckpt.lower():
            display_name = ckpt if len(ckpt) <= 100 else f"...{ckpt[-97:]}"
            choices.append(app_commands.Choice(name=display_name, value=ckpt[:100]))
            
        if len(choices) >= 25:
            break

    return choices


@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user.name} ({client.user.id})')


# ---------------------------------------------------------------------------
# UI Components & Buttons
# ---------------------------------------------------------------------------
class ImageButton(discord.ui.Button):
    def __init__(self, label: str, emoji: str, row: int, callback_fn):
        super().__init__(label=label, style=discord.ButtonStyle.grey, emoji=emoji, row=row)
        self._callback_fn = callback_fn

    async def callback(self, interaction: discord.Interaction):
        await self._callback_fn(interaction, self)


class Buttons(discord.ui.View):
    def __init__(self, prompt: str, negative_prompt: Optional[str], seed: int, images: List[Image.Image], timeout: int = 180):
        super().__init__(timeout=timeout)
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.images = images
        self.seed = seed

        total_buttons = len(images) * 2 + 1
        if total_buttons > 25:
            self.images = images[:12]

        reroll_row = 1 if total_buttons <= 21 else 0

        # Add variation buttons (V1, V2...)
        for idx in range(len(self.images)):
            row = (idx + 1) // 5 + reroll_row
            btn = ImageButton(f"V{idx + 1}", "♻️", row, self.generate_alternatives_and_send)
            self.add_item(btn)

        # Add upscale buttons (U1, U2...)
        for idx in range(len(self.images)):
            row = (idx + len(self.images) + 1) // 5 + reroll_row
            btn = ImageButton(f"U{idx + 1}", "⬆️", row, self.upscale_and_send)
            self.add_item(btn)

    async def generate_alternatives_and_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        index = int(button.label[1:]) - 1
        
        images = await generate_alternatives(self.images[index], self.prompt, self.negative_prompt, self.seed)
        collage_path = create_collage(images)

        try:
            message = f"{interaction.user.mention} here are your alternative images:"
            await interaction.followup.send(
                content=message,
                file=discord.File(fp=collage_path, filename='collage.png'),
                view=Buttons(self.prompt, self.negative_prompt, self.seed, images)
            )
        finally:
            if os.path.exists(collage_path):
                os.remove(collage_path)

    async def upscale_and_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        index = int(button.label[1:]) - 1

        upscaled_image = await upscale_image(self.images[index], self.prompt, self.negative_prompt, self.seed)
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        upscaled_path = f"./out/upscaled_{timestamp}.png"
        upscaled_image.save(upscaled_path)

        try:
            message = f"{interaction.user.mention} here is your upscaled image:"
            await interaction.followup.send(
                content=message,
                file=discord.File(fp=upscaled_path, filename='upscaled.png')
            )
        finally:
            if os.path.exists(upscaled_path):
                os.remove(upscaled_path)

    @discord.ui.button(label="Re-roll", style=discord.ButtonStyle.green, emoji="🎲", row=0)
    async def reroll_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        button.disabled = True
        
        new_seed = random.randint(0, 999_999_999_999_999)
        images = await generate_images(self.prompt, self.negative_prompt, new_seed)
        collage_path = create_collage(images)

        try:
            message = f"{interaction.user.mention} asked me to re-imagine \"{self.prompt}\":"
            await interaction.followup.send(
                content=message,
                file=discord.File(fp=collage_path, filename='collage.png'),
                view=Buttons(self.prompt, self.negative_prompt, new_seed, images)
            )
        finally:
            if os.path.exists(collage_path):
                os.remove(collage_path)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def create_collage(images: List[Image.Image]) -> str:
    num_images = len(images)
    num_cols = ceil(sqrt(num_images))
    num_rows = ceil(num_images / num_cols)
    
    collage_width = max(image.width for image in images) * num_cols
    collage_height = max(image.height for image in images) * num_rows
    collage = Image.new('RGB', (collage_width, collage_height))

    for idx, image in enumerate(images):
        row = idx // num_cols
        col = idx % num_cols
        collage.paste(image, (col * image.width, row * image.height))

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S_%f')
    collage_path = f"./out/collage_{timestamp}.png"
    collage.save(collage_path)
    return collage_path


# ---------------------------------------------------------------------------
# Slash Commands
# ---------------------------------------------------------------------------
@tree.command(name="imagine", description="Generate an image based on input text")
@app_commands.describe(prompt='Prompt for the image being generated')
@app_commands.describe(negative_prompt='Prompt for what you want to steer the AI away from')
@app_commands.describe(seed='The seed used to generate the image')
async def imagine(
    interaction: discord.Interaction, 
    prompt: str, 
    negative_prompt: Optional[str] = None, 
    seed: Optional[int] = None
):
    # Acknowledge immediately to prevent Discord interaction timeout (3s limit)
    await interaction.response.defer(thinking=True)
    
    actual_seed = seed if seed is not None else random.randint(0, 999_999_999_999_999)
    images = await generate_images(prompt, negative_prompt, actual_seed)
    collage_path = create_collage(images)

    try:
        message = f"{interaction.user.mention} Summoned an image."
        await interaction.followup.send(
            content=message,
            file=discord.File(fp=collage_path, filename='collage.png'),
            view=Buttons(prompt, negative_prompt, actual_seed, images)
        )
    finally:
        if os.path.exists(collage_path):
            os.remove(collage_path)


@tree.command(name="size", description="Change the image width and height")
async def cmd_size(interaction: discord.Interaction, width: int, height: int):
    config_loader.set_size(width, height)
    await interaction.response.send_message(f"{interaction.user.mention} Image size changed to: `{width} x {height}`")


@tree.command(name="checkpoint", description="Change the selected checkpoint for image generation")
@app_commands.autocomplete(checkpoint=checkpoint_autocomplete)
async def cmd_checkpoint(interaction: discord.Interaction, checkpoint: str):
    config_loader.set_value('CHECKPOINT', 'CHECKPOINT_NAME', checkpoint)
    await interaction.response.send_message(f"{interaction.user.mention} Checkpoint changed to: `{checkpoint}`")


@tree.command(name="steps", description="Change the amount of steps for image generation")
async def cmd_steps(interaction: discord.Interaction, steps: int):
    config_loader.set_value('BASE_SAMPLER_CFG', 'STEPS', str(steps))
    await interaction.response.send_message(f"{interaction.user.mention} Steps changed to: `{steps}`")


@tree.command(name="lora", description="Change the selected lora for image generation")
@app_commands.autocomplete(lora=lora_autocomplete)
@app_commands.describe(strength='The strength of the lora')
async def cmd_lora(interaction: discord.Interaction, lora: str, strength: float):
    config_loader.set_value('LORA', 'LORA_NAME', lora)
    config_loader.set_value('LORA', 'STRENGTH', str(strength))
    await interaction.response.send_message(f"{interaction.user.mention} Lora changed to: `{lora}` at `{strength}`")


# ---------------------------------------------------------------------------
# Bot Entry Point
# ---------------------------------------------------------------------------
try:
    client.run(TOKEN)
except Exception as error:
    print("An exception occurred:", error)
    if platform.system() == "Windows":
        os.system('pause')