import websockets
import uuid
import json
import random
import urllib.request
import urllib.parse
from PIL import Image
from io import BytesIO
import configparser
import os
import tempfile
import requests

# Read config.properties
config = configparser.ConfigParser()
config.read('config.properties')
server_address  = config['LOCAL']['SERVER_ADDRESS']
text2img_config = config['TEXT2IMG']['CONFIG']
img2img_config  = config['IMG2IMG']['CONFIG']
upscale_config  = config['UPSCALE']['CONFIG']

def queue_prompt(prompt, client_id):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req =  urllib.request.Request("http://{}/prompt".format(server_address), data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
        return json.loads(response.read())
    
def upload_image(filepath, subfolder=None, folder_type=None, overwrite=False):
    url = f"http://{server_address}/upload/image"
    files = {'image': open(filepath, 'rb')}
    data = {
        'overwrite': str(overwrite).lower()
    }
    if subfolder:
        data['subfolder'] = subfolder
    if folder_type:
        data['type'] = folder_type
    response = requests.post(url, files=files, data=data)
    return response.json()

class ImageGenerator:
    def __init__(self):
        self.client_id = str(uuid.uuid4())
        self.uri = f"ws://{server_address}/ws?clientId={self.client_id}"
        self.ws = None

    async def connect(self):
        self.ws = await websockets.connect(self.uri)

    async def get_images(self, prompt):
        if not self.ws:
            await self.connect()
    
        prompt_id = queue_prompt(prompt, self.client_id)['prompt_id']
        currently_Executing_Prompt = None
        output_images = []
        async for out in self.ws:
            message = json.loads(out)
            if message['type'] == 'execution_start':
                currently_Executing_Prompt = message['data']['prompt_id']

            if message['type'] == 'executing' and prompt_id == currently_Executing_Prompt:
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break
                
        history = get_history(prompt_id)[prompt_id]

        for node_id in history['outputs']:
            node_output = history['outputs'][node_id]
            if 'images' in node_output:
                for image in node_output['images']:
                    image_data = get_image(image['filename'], image['subfolder'], image['type'])
                    if 'final_output' in image['filename']:
                        pil_image = Image.open(BytesIO(image_data))
                        output_images.append(pil_image)

        return output_images

    async def close(self):
        if self.ws:
            await self.ws.close()

def populate_nodes(workflow, workflow_type: str, sampler_type: str, prompt: str, negative_prompt: str, seed: int, filename = None):
    # Read config
    config.read('config.properties')
    checkpoint_node  = config.get(workflow_type, 'CHECKPOINT_NODE').split(',')
    prompt_nodes     = config.get(workflow_type, 'PROMPT_NODES').split(',')
    neg_prompt_nodes = config.get(workflow_type, 'NEG_PROMPT_NODES').split(',')
    rand_seed_nodes  = config.get(workflow_type, 'RAND_SEED_NODES').split(',') 
    sampler_nodes    = config.get(workflow_type, 'SAMPLER_NODES').split(',')
    lora_nodes       = config.get(workflow_type, 'LORA_NODES').split(',')
    vae_nodes        = config.get(workflow_type, 'VAE_NODES').split(',')
    if workflow_type == 'TEXT2IMG':
        latent_node  = config.get(workflow_type, 'LATENT_NODE').split(',')
        width        = config.get(workflow_type, 'WIDTH') 
        height       = config.get(workflow_type, 'HEIGHT') 
    if workflow_type != 'TEXT2IMG':
        file_input_nodes = config.get(workflow_type, 'FILE_INPUT_NODES').split(',')
    # Get params from config
    ckpt_name        = config.get('CHECKPOINT', 'CHECKPOINT_NAME')
    pos_template     = config.get('PROMPT_TEMPLATE', 'POS')
    neg_template     = config.get('PROMPT_TEMPLATE', 'NEG')
    sampler          = config.get(sampler_type, 'SAMPLER')
    scheduler        = config.get(sampler_type, 'SCHEDULER')
    steps            = config.get(sampler_type, 'STEPS')
    cfg              = config.get(sampler_type, 'CFG')
    lora_name        = config.get('LORA', 'LORA_NAME')
    lora_strength    = config.get('LORA', 'STRENGTH')
    vae_name         = config.get('VAE', 'VAE_NAME')
    # Modify the prompt dictionary
    if(checkpoint_node[0] != ''):
      for node in checkpoint_node:
          workflow[node]["inputs"]["ckpt_name"] = ckpt_name
          print('Checkpoint: ' + workflow[node]["inputs"]["ckpt_name"])
    if(prompt != None and prompt_nodes[0] != ''):
      for node in prompt_nodes:
          workflow[node]["inputs"]["text"] = pos_template + prompt
          print('Positive prompt: ' + workflow[node]["inputs"]["text"])
    if(neg_prompt_nodes[0] != ''):
      for node in neg_prompt_nodes:
          if (negative_prompt == None):
                workflow[node]["inputs"]["text"] = neg_template
          else:
                workflow[node]["inputs"]["text"] = neg_template + negative_prompt
          print('Negative prompt: ' + workflow[node]["inputs"]["text"])
    if(rand_seed_nodes[0] != ''):
      for node in rand_seed_nodes:
          if(seed != None):
            workflow[node]["inputs"]["seed"] = seed
          else:
            workflow[node]["inputs"]["seed"] = random.randint(0,999999999999999)
          print('Seed: ' + str(workflow[node]["inputs"]["seed"]))
    if(sampler_nodes[0] != ''):
      for node in sampler_nodes:
          workflow[node]["inputs"]["sampler_name"] = sampler
          workflow[node]["inputs"]["scheduler"] = scheduler
          workflow[node]["inputs"]["steps"] = steps
          workflow[node]["inputs"]["cfg"] = cfg
    if(lora_nodes[0] != ''):
      for node in lora_nodes:
          workflow[node]["inputs"]["lora_name"] = lora_name
          workflow[node]["inputs"]["strength_model"] = lora_strength
          print('Lora: ' + workflow[node]["inputs"]["lora_name"])
          print('Lora strength: ' + workflow[node]["inputs"]["strength_model"])
    if(vae_nodes[0] != ''):
      for node in vae_nodes:
          workflow[node]["inputs"]["vae_name"] = vae_name
    if(workflow_type == 'TEXT2IMG' and latent_node[0] != ''):
      for node in latent_node:
          workflow[node]["inputs"]["width"] = width
          workflow[node]["inputs"]["height"] = height
    if(workflow_type != 'TEXT2IMG' and file_input_nodes[0] != ''):
      for node in file_input_nodes:
          workflow[node]["inputs"]["image"] = filename

async def generate_images(prompt: str, negative_prompt: str, seed: int):
    # Read config
    config.read('config.properties')
    # Open comfy workflow
    with open(text2img_config, 'r') as file:
      workflow = json.load(file)
      
    generator = ImageGenerator()
    await generator.connect()
    print('----- Generating Image -----')
    # Populate nodes using config.properties
    populate_nodes(workflow, 'TEXT2IMG', 'BASE_SAMPLER_CFG', prompt, negative_prompt, seed)

    images = await generator.get_images(workflow)
    await generator.close()

    return images

async def generate_alternatives(image: Image.Image, prompt: str, negative_prompt: str, seed: int):
    # Read config
    config.read('config.properties')
    # Save temp png
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
      image.save(temp_file, format="PNG")
      temp_filepath = temp_file.name

    # Upload the temporary file using the upload_image method
    response_data = upload_image(temp_filepath)
    filename = response_data['name']
    with open(img2img_config, 'r') as file:
      workflow = json.load(file)
      
    generator = ImageGenerator()
    await generator.connect()
    print('----- Refining Image -----')
    # Populate nodes using config.properties
    populate_nodes(workflow, 'IMG2IMG', 'BASE_SAMPLER_CFG', prompt, negative_prompt, seed, filename)

    images = await generator.get_images(workflow)
    await generator.close()

    return images

async def generate_alternatives(image: Image.Image, prompt: str, negative_prompt: str, seed: int):
    # Read config
    config.read('config.properties')
    # Save temp png
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
      image.save(temp_file, format="PNG")
      temp_filepath = temp_file.name

    # Upload the temporary file using the upload_image method
    response_data = upload_image(temp_filepath)
    filename = response_data['name']
    with open(img2img_config, 'r') as file:
      workflow = json.load(file)
      
    generator = ImageGenerator()
    await generator.connect()
    print('----- Refining Image -----')
    # Populate nodes using config.properties
    populate_nodes(workflow, 'IMG2IMG', 'BASE_SAMPLER_CFG', prompt, negative_prompt, seed, filename)

    images = await generator.get_images(workflow)
    await generator.close()

    return images

async def upscale_image(image: Image.Image, prompt: str, negative_prompt: str, seed: int):
    # Read config
    config.read('config.properties')
    # Create temp png
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
      image.save(temp_file, format="PNG")
      temp_filepath = temp_file.name

    # Upload the temporary file using the upload_image method
    response_data = upload_image(temp_filepath)
    filename = response_data['name']
    with open(upscale_config, 'r') as file:
      workflow = json.load(file)

    generator = ImageGenerator()
    await generator.connect()
    print('----- Upscaling Image -----')
    # Populate nodes using config.properties
    populate_nodes(workflow, 'UPSCALE', 'REF_SAMPLER_CFG', prompt, negative_prompt, seed, filename)

    images = await generator.get_images(workflow)
    await generator.close()

    return images[0]