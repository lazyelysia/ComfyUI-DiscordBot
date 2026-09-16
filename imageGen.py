import os
import json
import uuid
import random
import tempfile
import configparser
from io import BytesIO
from typing import List, Dict, Any, Optional
from pathlib import Path

import websockets
import httpx
from PIL import Image
from configEdit import config_loader

# ---------------------------------------------------------------------------
# API Client Helpers
# ---------------------------------------------------------------------------
def get_server_address() -> str:
    return config_loader.get('LOCAL', 'SERVER_ADDRESS', fallback='127.0.0.1:8188')

async def queue_prompt(prompt: Dict[str, Any], client_id: str) -> Dict[str, Any]:
    url = f"http://{get_server_address()}/prompt"
    payload = {"prompt": prompt, "client_id": client_id}
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload)
        res.raise_for_status()
        return res.json()

async def get_image_bytes(filename: str, subfolder: str, folder_type: str) -> bytes:
    url = f"http://{get_server_address()}/view"
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        return res.content

async def get_history(prompt_id: str) -> Dict[str, Any]:
    url = f"http://{get_server_address()}/history/{prompt_id}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        res.raise_for_status()
        return res.json()

async def upload_image(filepath: str, subfolder: str = None, folder_type: str = None, overwrite: bool = False) -> Dict[str, Any]:
    url = f"http://{get_server_address()}/upload/image"
    data = {'overwrite': str(overwrite).lower()}
    if subfolder:
        data['subfolder'] = subfolder
    if folder_type:
        data['type'] = folder_type

    async with httpx.AsyncClient() as client:
        with open(filepath, 'rb') as f:
            files = {'image': f}
            res = await client.post(url, files=files, data=data)
            res.raise_for_status()
            return res.json()


# ---------------------------------------------------------------------------
# Image Generator Class
# ---------------------------------------------------------------------------
class ImageGenerator:
    def __init__(self):
        self.client_id = str(uuid.uuid4())
        self.server_address = get_server_address()
        self.uri = f"ws://{self.server_address}/ws?clientId={self.client_id}"
        self.ws = None

    async def connect(self):
        self.ws = await websockets.connect(self.uri)

    async def get_images(self, prompt: Dict[str, Any]) -> List[Image.Image]:
        if not self.ws:
            await self.connect()

        response = await queue_prompt(prompt, self.client_id)
        prompt_id = response['prompt_id']
        currently_executing = None
        output_images = []

        async for out in self.ws:
            message = json.loads(out)
            msg_type = message.get('type')
            
            if msg_type == 'execution_start':
                currently_executing = message['data']['prompt_id']

            elif msg_type == 'executing' and prompt_id == currently_executing:
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break

        history_response = await get_history(prompt_id)
        history = history_response.get(prompt_id, {})

        for node_output in history.get('outputs', {}).values():
            if 'images' in node_output:
                for img_info in node_output['images']:
                    image_data = await get_image_bytes(img_info['filename'], img_info['subfolder'], img_info['type'])
                    if 'final_output' in img_info['filename']:
                        output_images.append(Image.open(BytesIO(image_data)))

        return output_images

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None


# ---------------------------------------------------------------------------
# Node Population
# ---------------------------------------------------------------------------
def trace_to_text_node(workflow: Dict[str, Any], start_node_id: str) -> Optional[str]:
    """Recursively traces backward from sampler links to find origin text encoders."""
    node = workflow.get(str(start_node_id))
    if not node:
        return None

    class_type = node.get("class_type", "")
    if class_type in ("CLIPTextEncode", "CLIPTextEncodeSDXL", "BNK_CLIPTextEncodeAdvanced"):
        return str(start_node_id)

    inputs = node.get("inputs", {})
    for value in inputs.values():
        if isinstance(value, list) and len(value) > 0:
            parent_id = str(value[0])
            if parent_id in workflow:
                result = trace_to_text_node(workflow, parent_id)
                if result:
                    return result
    return None


def find_prompt_node_ids(workflow: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Finds positive and negative prompt node IDs via KSampler links."""
    pos_id, neg_id = None, None

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        if "KSampler" in class_type or "SamplerCustom" in class_type:
            inputs = node.get("inputs", {})

            if "positive" in inputs and isinstance(inputs["positive"], list):
                pos_id = trace_to_text_node(workflow, str(inputs["positive"][0]))

            if "negative" in inputs and isinstance(inputs["negative"], list):
                neg_id = trace_to_text_node(workflow, str(inputs["negative"][0]))

            if pos_id or neg_id:
                break

    return pos_id, neg_id


def populate_nodes(
    workflow: Dict[str, Any],
    prompt: str,
    negative_prompt: Optional[str] = None,
    seed: Optional[int] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """Populates workflow parameters using standard ConfigParser syntax via config_loader.config."""
    cfg_parser = config_loader.config

    # Helper function for clean ConfigParser fallbacks
    def get_cfg(section: str, option: str, default: Optional[str] = None) -> Optional[str]:
        if cfg_parser.has_section(section) and cfg_parser.has_option(section, option):
            return cfg_parser.get(section, option)
        return default

    # 1. Read config values using .get()
    checkpoint_name = get_cfg('CHECKPOINT', 'checkpoint_name')
    diffusion_model_name = get_cfg('DIFFUSION_MODEL', 'diffusion_model_name')
    lora_name = get_cfg('LORA', 'lora_name')
    lora_strength = float(get_cfg('LORA', 'strength', '1.0'))
    vae_name = get_cfg('VAE', 'vae_name')
    
    width = int(get_cfg('TEXT2IMG', 'width', '1024'))
    height = int(get_cfg('TEXT2IMG', 'height', '1328'))
    
    steps = int(get_cfg('BASE_SAMPLER_CFG', 'steps', '8'))
    cfg = float(get_cfg('BASE_SAMPLER_CFG', 'cfg', '1.0'))
    sampler_name = get_cfg('BASE_SAMPLER_CFG', 'sampler', 'er_sde')
    scheduler = get_cfg('BASE_SAMPLER_CFG', 'scheduler', 'simple')

    # 2. Format Prompts with config templates
    pos_template = get_cfg('PROMPT_TEMPLATE', 'pos', '')
    neg_template = get_cfg('PROMPT_TEMPLATE', 'neg', '')

    full_positive_prompt = f"{prompt}, {pos_template}".strip(", ") if pos_template else prompt
    full_negative_prompt = negative_prompt if negative_prompt is not None else neg_template

    # 3. Dynamic Prompt Connection Tracing
    pos_node_id, neg_node_id = find_prompt_node_ids(workflow)

    # 4. Traverse & Update Nodes
    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        inputs = node.setdefault("inputs", {})

        # A. Prompts
        if str(node_id) == str(pos_node_id):
            inputs["text"] = full_positive_prompt
            print(f"Positive: {full_positive_prompt}")
        elif str(node_id) == str(neg_node_id):
            inputs["text"] = full_negative_prompt
            print(f"Negative: {full_negative_prompt}")

        # B. Seed Node
        elif class_type in ("SeedNode", "KSamplerSeed") or "seed" in class_type.lower():
            if seed is not None and "seed" in inputs:
                inputs["seed"] = seed
                print(f"Seed: {seed}")

        # C1. Checkpoint Loader
        elif class_type in ("CheckpointLoaderSimple", "CheckpointLoader"):
            if checkpoint_name:
                inputs["ckpt_name"] = checkpoint_name
                print(f"Checkpoint: {checkpoint_name}")

        # C2. Diffusion Model Loader
        elif class_type in ("UNETLoader", "DiffusionModel"):
            if diffusion_model_name:
                inputs["unet_name"] = diffusion_model_name
                print(f"Diffusion Model: {diffusion_model_name}")

        # D. LoRA Loader
        elif class_type in ("LoraLoader", "LoraLoaderModelOnly"):
            if lora_name:
                inputs["lora_name"] = lora_name
                if "strength_model" in inputs:
                    inputs["strength_model"] = lora_strength
                    print(f"Lora: {lora_name} with strength {lora_strength}")
                if "strength_clip" in inputs:
                    inputs["strength_clip"] = lora_strength
                    print(f"Lora Strength (CLIP): {lora_name} with strength {lora_strength}")

        # E. VAE Loader
        elif class_type == "VAELoader":
            if vae_name:
                inputs["vae_name"] = vae_name
                print(f"VAE: {vae_name}")

        # F. KSampler Parameters
        elif "KSampler" in class_type or "SamplerCustom" in class_type:
            if seed is not None and "seed" in inputs and not isinstance(inputs["seed"], list):
                inputs["seed"] = seed
            if steps:
                inputs["steps"] = steps
            if cfg:
                inputs["cfg"] = cfg
            if sampler_name and "sampler_name" in inputs:
                inputs["sampler_name"] = sampler_name
            if scheduler and "scheduler" in inputs:
                inputs["scheduler"] = scheduler

        # G. Latent Dimensions
        elif class_type == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height

        # H. Img2Img / Upscale Loaders
        elif class_type == "LoadImage" and filename:
            inputs["image"] = filename

    return workflow


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
async def generate_images(prompt: str, negative_prompt: str, seed: int) -> List[Image.Image]:
    config_file_path = config_loader.get('TEXT2IMG', 'CONFIG')
    with open(config_file_path, 'r') as f:
        workflow = json.load(f)

    generator = ImageGenerator()
    try:
        await generator.connect()
        print('----- Generating Image -----')
        populate_nodes(workflow, prompt, negative_prompt, seed)
        return await generator.get_images(workflow)
    finally:
        await generator.close()


async def generate_alternatives(image: Image.Image, prompt: str, negative_prompt: str, seed: int) -> List[Image.Image]:
    temp_filepath = None
    generator = ImageGenerator()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            image.save(temp_file, format="PNG")
            temp_filepath = temp_file.name

        response_data = await upload_image(temp_filepath)
        filename = response_data['name']

        config_file_path = config_loader.get('IMG2IMG', 'CONFIG')
        with open(config_file_path, 'r') as f:
            workflow = json.load(f)

        await generator.connect()
        print('----- Refining Image -----')
        populate_nodes(workflow, prompt, negative_prompt, seed, filename)
        return await generator.get_images(workflow)
    finally:
        await generator.close()
        if temp_filepath and os.path.exists(temp_filepath):
            os.unlink(temp_filepath)


async def upscale_image(image: Image.Image, prompt: str, negative_prompt: str, seed: int) -> Optional[Image.Image]:
    temp_filepath = None
    generator = ImageGenerator()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            image.save(temp_file, format="PNG")
            temp_filepath = temp_file.name

        response_data = await upload_image(temp_filepath)
        filename = response_data['name']

        config_file_path = config_loader.get('UPSCALE', 'CONFIG')
        with open(config_file_path, 'r') as f:
            workflow = json.load(f)

        await generator.connect()
        print('----- Upscaling Image -----')
        populate_nodes(workflow, prompt, negative_prompt, seed, filename)
        images = await generator.get_images(workflow)
        return images[0] if images else None
    finally:
        await generator.close()
        if temp_filepath and os.path.exists(temp_filepath):
            os.unlink(temp_filepath)