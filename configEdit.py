import os
import sys
import configparser
from pathlib import Path
from typing import List, Tuple, Optional

class DynamicConfigLoader:
    def __init__(self, config_path: str = 'config.properties'):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self._last_mtime = 0.0
        self.reload_if_changed()

    def reload_if_changed(self, force: bool = False):
        """Reloads config if modified on disk, or if forced after a write."""
        try:
            current_mtime = os.path.getmtime(self.config_path)
            if force or current_mtime > self._last_mtime:
                self.config.read(self.config_path)
                self._last_mtime = os.path.getmtime(self.config_path)
        except FileNotFoundError:
            pass

    def get(self, section: str, option: str, fallback: str = "") -> str:
        self.reload_if_changed()
        return self.config.get(section, option, fallback=fallback)

    def get_node_list(self, section: str, option: str) -> List[str]:
        raw_val = self.get(section, option)
        return [node.strip() for node in raw_val.split(",") if node.strip()]

    def set_value(self, section: str, key: str, value: str):
        """Safely updates a configuration value on disk and syncs memory."""
        self.reload_if_changed()
        if not self.config.has_section(section):
            self.config.add_section(section)
        
        self.config.set(section, key, str(value))
        
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)
        
        # Force update the modification timestamp in memory
        self.reload_if_changed(force=True)

    def set_size(self, width: int, height: int):
        """Updates width and height in a single file operation."""
        self.reload_if_changed()
        if not self.config.has_section('TEXT2IMG'):
            self.config.add_section('TEXT2IMG')
        
        self.config.set('TEXT2IMG', 'WIDTH', str(width))
        self.config.set('TEXT2IMG', 'HEIGHT', str(height))
        
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)
            
        self.reload_if_changed(force=True)

# Global configuration instance
config_loader = DynamicConfigLoader('config.properties')

def setup_config() -> Tuple[str, str]:
    if not os.path.exists('config.properties'):
        print("[ERROR] No config file: Please rename 'config.properties.example' to 'config.properties' and restart.")
        if sys.platform == "win32":
            os.system('pause')
        sys.exit(1)

    os.makedirs('./out', exist_ok=True)
    return config_loader.get('BOT', 'TOKEN'), config_loader.get('BOT', 'SDXL_SOURCE')


def get_models(folder_type: str) -> list[str]:
    """
    Recursively fetch models from ComfyUI subdirectories.
    folder_type: 'loras' / 'checkpoints' / 'diffusion_models'
    """
    try:
        # Fetch comfy_dir from [LOCAL] section in config.properties
        comfy_dir = config_loader.config['LOCAL']['comfy_dir']
    except KeyError:
        print("[Warning] Could not find 'comfy_dir' in [LOCAL] section of config.properties.")
        return []

    # Map folder types to standard ComfyUI model folder names
    folder_map = {
        'loras': 'loras',
        'checkpoints': 'checkpoints',
        'diffusion_models': 'diffusion_models'
    }

    subfolder = folder_map.get(folder_type.lower(), folder_type.lower())
    target_dir = os.path.abspath(os.path.join(comfy_dir, "models", subfolder))

    if not os.path.exists(target_dir):
        print(f"[Warning] Model directory does not exist: {target_dir}")
        return []

    model_extensions = ('.safetensors', '.ckpt', '.pt')
    models = []

    # Recursively traverse subdirectories
    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.lower().endswith(model_extensions):
                full_path = os.path.join(root, file)
                # Calculate relative path
                rel_path = os.path.relpath(full_path, target_dir)
                clean_path = rel_path.replace("\\", "/")
                models.append(clean_path)

    return sorted(models)