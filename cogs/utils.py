import json
import os
import aiofiles

async def load_json(file_path):
    if os.path.exists(file_path):
        async with aiofiles.open(file_path, 'r') as f:
            try:
                contents = await f.read()
                return json.loads(contents)
            except json.JSONDecodeError:
                return {}
    return {}

async def save_json(data, file_path):
    async with aiofiles.open(file_path, 'w') as f:
        await f.write(json.dumps(data, indent=4))
