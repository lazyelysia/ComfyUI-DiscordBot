# SDXL-DiscordBot


<p float="left" align="center">
  <img src="https://raw.githubusercontent.com/WillAngus/ComfyUI-SDXL-DiscordBot/refs/heads/main/assets/txt2img.jpg" height="300px" align="top" />
  <img src="https://raw.githubusercontent.com/WillAngus/ComfyUI-SDXL-DiscordBot/refs/heads/main/assets/commands.jpg" height="300px" align="top" />
</p>

**SDXL-DiscordBot** is a Discord bot designed specifically for image generation using any SDXL/Illustrious based model. It's inspired by the features of the Midjourney Discord bot, offering capabilities like text-to-image generation, variations in outputs, and the ability to upscale, with hires. fix.

<div align="center">

</div>


## Key Features:

1. **Text-to-Image Generation**: Convert your ideas into visuals. Just type in a positive+negative prompt, and the bot will generate an image that matches your text. This version has a configurable prompt template that will be prepended to the start of every prompt.

2. **Variations on Outputs**: Not satisfied with the first image? The bot can produce multiple variations by resampling your image.

3. **Upscale Outputs**: Apply hires. fix to your images to increase the resolution as well as adding detail. Perfect for when you need higher resolution visuals.

4. **Custom Workflows with ComfyUI**: The bot comes with default configurations that cater to most users. However, if you have specific needs, it supports custom ComfyUI workflows, allowing you to tailor the bot's operations to your exact requirements.

## Quick Start 

### 1. **Create a discord bot using the Discord developer portal**
1. Turn on ‘Developer mode’ in your Discord account settings.
2. Click on ‘Discord API’.
3. In the Developer portal, click on ‘[Applications](https://discord.com/developers/applications)’. Log in again and then, back in the ‘Applications’ menu, click on ‘New Application’.
4. Name the bot and then click ‘Create’.
5. Go to the ‘Bot’ menu and generate a token using ‘Add Bot’.
6. Program your bot using the bot token and save the file.
7. Define other details for your bot under ‘General Information’.
9. Click on ‘OAuth2’, activate ‘bot’, set the permissions, and then click on ‘Copy’.
10. Select your server to add your bot to it.

### 2. **Download & Extract**
- [Download the latest executable](https://github.com/WillAngus/ComfyUI-SDXL-DiscordBot/releases) suitable for your OS.
- Extract the zip file to your desired location.

### 3. **Configuration**
- Open `config.properties` using a text editor. If cloned from github, rename and use `config.properties.example`.
- Set your Discord bot token: Find `[BOT][TOKEN]` and replace the placeholder with your token.
- Enter the filename of your checkpoint, lora and VAE. (This step can be done in the discord client with slash commands).

### 4. **Run locally via ComfyUI**
- Set your ComfyUI URL: Replace the placeholder in `[LOCAL][SERVER_ADDRESS]` with your ComfyUI URL (default is `127.0.0.1:8188`).
- Update the source: Change `[BOT][SDXL_SOURCE]` to 'LOCAL'.
- Enter your ComfyUI directory eg. `COMFY_DIR=C:\Users\YOUR_USERNAME\Documents\ComfyUI`
- Download and add models to ComfyUI, eg:
  - [Illustrious-XL](https://civitai.com/models/795765?modelVersionId=889818) → `checkpoints` folder
  - [Stabilizer IL/NAI](https://civitai.com/models/971952?modelVersionId=2334017)→ `loras` folder
  - [SDXL-VAE-FP16-Fix](https://huggingface.co/madebyollin/sdxl-vae-fp16-fix)→ `vae` folder
  - [4x_foolhardy_Remacri](https://civitai.com/models/147759?modelVersionId=164821) → `upscale_models` folder
- Ensure that ComfyUI is running while the bot is running

### 5. **Run the App**
***Release:***
- Double-click on `bot.exe` to launch.
- **Note for Windows users:** If Windows Defender warns about an "unknown publisher", you can safely ignore it. You might also need to whitelist this app in your antivirus software.

***Developent:***
- Double-click on `start.bat` to launch.


