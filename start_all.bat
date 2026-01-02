cd ./ComfyUI_windows_portable
start cmd /k call run_nvidia_gpu_fast_fp16_accumulation.bat
cd ..
python -s bot.py