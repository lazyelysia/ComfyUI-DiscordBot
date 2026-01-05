import discord
import discord.ext
from discord import app_commands
import configparser
import os
import sys
import random
from PIL import Image
from datetime import datetime
from math import ceil, sqrt
from configEdit import setup_config, set_size, get_models, set_value

# setting up the bot
TOKEN, IMAGE_SOURCE = setup_config()
intents = discord.Intents.default() 
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

if IMAGE_SOURCE == "LOCAL":
    from imageGen import generate_images, upscale_image, generate_alternatives

global CHECKPOINTS
global LORAS
CHECKPOINTS = get_models('checkpoints')
LORAS = get_models('loras')

def get_choices(type):
    arr = []
    if type == 'checkpoints':
        for x in CHECKPOINTS:
            arr.append(app_commands.Choice(name=x,value=x))
    if type == 'loras':
        for y in LORAS:
            arr.append(app_commands.Choice(name=y,value=y))
    return arr

global checkpoint_choices
global lora_choices
checkpoint_choices = get_choices('checkpoints')
lora_choices = get_choices('loras')

# sync the slash command to your server
@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user.name} ({client.user.id})')

class ImageButton(discord.ui.Button):
    def __init__(self, label, emoji, row, callback):
        super().__init__(label=label, style=discord.ButtonStyle.grey, emoji=emoji, row=row)
        self._callback = callback

    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self)


class Buttons(discord.ui.View):
    def __init__(self, prompt, negative_prompt, seed, images, *, timeout=180):
        super().__init__(timeout=timeout)
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.images = images
        self.seed = seed

        total_buttons = len(images) * 2 + 1  # For both alternative and upscale buttons + re-roll button
        if total_buttons > 25:  # Limit to 25 buttons
            images = images[:12]  # Adjust to only use the first 12 images

        # Determine if re-roll button should be on its own row
        reroll_row = 1 if total_buttons <= 21 else 0

        # Dynamically add alternative buttons
        for idx, _ in enumerate(images):
            row = (idx + 1) // 5 + reroll_row  # Determine row based on index and re-roll row
            btn = ImageButton(f"V{idx + 1}", "♻️", row, self.generate_alternatives_and_send)
            self.add_item(btn)

        # Dynamically add upscale buttons
        for idx, _ in enumerate(images):
            row = (idx + len(images) + 1) // 5 + reroll_row  # Determine row based on index, number of alternative buttons, and re-roll row
            btn = ImageButton(f"U{idx + 1}", "⬆️", row, self.upscale_and_send)
            self.add_item(btn)

    async def generate_alternatives_and_send(self, interaction, button):
        index = int(button.label[1:]) - 1  # Extract index from label
        await interaction.response.send_message("Creating some alternatives, this shouldn't take too long...")
        images = await generate_alternatives(self.images[index], self.prompt, self.negative_prompt, self.seed)
        collage_path = create_collage(images)
        final_message = f"{interaction.user.mention} here are your alternative images"
        await interaction.channel.send(content=final_message, file=discord.File(fp=collage_path, filename='collage.png'), view=Buttons(self.prompt, self.negative_prompt, self.seed, images))

    async def upscale_and_send(self, interaction, button):
        index = int(button.label[1:]) - 1  # Extract index from label
        await interaction.response.send_message("Upscaling the image, this shouldn't take too long...")
        upscaled_image = await upscale_image(self.images[index], self.prompt, self.negative_prompt, self.seed)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        upscaled_image_path = f"./out/upscaledImage_{timestamp}.png"
        upscaled_image.save(upscaled_image_path)
        final_message = f"{interaction.user.mention} here is your upscaled image"
        await interaction.channel.send(content=final_message, file=discord.File(fp=upscaled_image_path, filename='upscaled_image.png'))

    @discord.ui.button(label="Re-roll", style=discord.ButtonStyle.green, emoji="🎲", row=0)
    async def reroll_image(self, interaction, btn):
        await interaction.response.send_message(f"{interaction.user.mention} asked me to re-imagine \"{self.prompt}\", this shouldn't take too long...")
        btn.disabled = True
        await interaction.message.edit(view=self)
        seed = random.randint(0,999999999999999)
        # Generate a new image with the same prompt
        images = await generate_images(self.prompt,self.negative_prompt, seed)

        # Construct the final message with user mention
        final_message = f"{interaction.user.mention} asked me to re-imagine \"{self.prompt}\", here is what I imagined for them."
        await interaction.channel.send(content=final_message, file=discord.File(fp=create_collage(images), filename='collage.png'), view = Buttons(self.prompt,self. negative_prompt, seed, images))

def create_collage(images):
    num_images = len(images)
    num_cols = ceil(sqrt(num_images))
    num_rows = ceil(num_images / num_cols)
    collage_width = max(image.width for image in images) * num_cols
    collage_height = max(image.height for image in images) * num_rows
    collage = Image.new('RGB', (collage_width, collage_height))

    for idx, image in enumerate(images):
        row = idx // num_cols
        col = idx % num_cols
        x_offset = col * image.width
        y_offset = row * image.height
        collage.paste(image, (x_offset, y_offset))

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    collage_path = f"./out/images_{timestamp}.png"
    collage.save(collage_path)

    return collage_path

@tree.command(name="imagine", description="Generate an image based on input text")
@app_commands.describe(prompt='Prompt for the image being generated')
@app_commands.describe(negative_prompt='Prompt for what you want to steer the AI away from')
@app_commands.describe(seed='The seed used to generate the image')
async def imagine(interaction: discord.Interaction, prompt: str, negative_prompt: str = None, seed: int = None):
    # Send an initial message
    await interaction.response.send_message(f"{interaction.user.mention} Summoning image from another realm.")
    # Generate the image and get progress updates
    images = await generate_images(prompt, negative_prompt, seed)
    # Construct the final message with user mention
    final_message = f"{interaction.user.mention} Summoned image."
    await interaction.channel.send(content=final_message, file=discord.File(fp=create_collage(images), filename='collage.png'), view=Buttons(prompt,negative_prompt,seed,images))

@tree.command(name="size", description="Change the image width")
async def size(interaction: discord.Interaction, width: int, height: int):
    set_size(width, height)
    await interaction.response.send_message(f"{interaction.user.mention} Image size changed to: `{width} x {height}`")

@tree.command(name="checkpoint", description="Change the selected checkpoint for image generation")
@app_commands.choices(options = checkpoint_choices)
async def choices(interaction:discord.Interaction,options:app_commands.Choice[str]):
    set_value('CHECKPOINT', 'CHECKPOINT_NAME', options.value)
    await interaction.response.send_message(f"{interaction.user.mention} Checkpoint changed to: `{options.value}`")

@tree.command(name="lora", description="Change the selected lora for image generation")
@app_commands.choices(options = lora_choices)
@app_commands.describe(strength='The strength of the lora')
async def choices(interaction:discord.Interaction,options:app_commands.Choice[str], strength: float):
    set_value('LORA', 'LORA_NAME', options.value)
    set_value('LORA', 'STRENGTH', str(strength))
    await interaction.response.send_message(f"{interaction.user.mention} Lora changed to: `{options.value}` at `{strength}`")

# run the bot
try:
    client.run(TOKEN)
except Exception as error:
    print("An exception occurred:", error)
    os.system('pause')