#!/bin/bash
# ideogram_batch.sh - Process batch JSON files directly

if [ "$#" -lt 2 ]; then
    echo "ERROR: Usage: $0 BATCH_FILE SAVE_DIR [CAMPAIGN_PREFIX]"
    exit 1
fi

BATCH_FILE="$1"
SAVE_DIR="$2"
CAMPAIGN_PREFIX="$3"

# Get script directory for credentials
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load API key
API_KEY=$(python3 -c "
import json, os
try:
    with open('$SCRIPT_DIR/credentials.json', 'r') as f:
        creds = json.load(f)
    print(creds.get('ideogram_api_key', ''))
except:
    print('')
")

if [ -z "$API_KEY" ]; then
    echo "ERROR: No API key found"
    exit 1
fi

# Check if batch file exists
if [ ! -f "$BATCH_FILE" ]; then
    echo "ERROR: Batch file not found: $BATCH_FILE"
    exit 1
fi

# Create save directory
mkdir -p "$SAVE_DIR"

ENDPOINT="https://api.ideogram.ai/generate"

# Parse JSON and process prompts
python3 -c "
import json, sys, os, subprocess
import time

# Load batch file
with open('$BATCH_FILE', 'r') as f:
    batch = json.load(f)

prompts = batch.get('prompts', [])
campaign_name = batch.get('campaign_name', '')

if not prompts:
    print('ERROR: No prompts found in batch file')
    sys.exit(1)

print(f'Processing {len(prompts)} prompts...')

# Get campaign prefix from shell variable
campaign_prefix = '$CAMPAIGN_PREFIX'

# Process each prompt
success_count = 0
for i, prompt in enumerate(prompts, 1):
    if campaign_prefix and campaign_prefix.strip():
        filename = f'{campaign_prefix}_{str(i).zfill(3)}.png'
    else:
        # Create slug from prompt
        slug = prompt.lower().strip().replace(' ', '_')[:40]
        slug = ''.join(c for c in slug if c.isalnum() or c in '_-')
        ts = int(time.time())
        filename = f'{slug}_{ts}_{i}.png'
    
    save_path = '$SAVE_DIR/' + filename
    
    print(f'Generating {i}/{len(prompts)}: {filename}')
    
    # Build JSON payload
    payload = {
        'image_request': {
            'prompt': prompt,
            'aspect_ratio': 'ASPECT_16_9'
        }
    }
    
    # Make API call using curl
    import subprocess
    curl_cmd = [
        'curl', '-s', '-X', 'POST', '$ENDPOINT',
        '-H', 'Api-Key: $API_KEY',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(payload)
    ]
    
    try:
        response = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        if response.returncode == 0:
            response_data = json.loads(response.stdout)
            if 'data' in response_data and len(response_data['data']) > 0:
                image_url = response_data['data'][0].get('url', '')
                if image_url:
                    # Download image
                    download_cmd = ['curl', '-s', '-o', save_path, image_url]
                    download_result = subprocess.run(download_cmd, timeout=30)
                    if download_result.returncode == 0 and os.path.exists(save_path):
                        print(f'✓ Generated {i}/{len(prompts)}: {filename}')
                        success_count += 1
                    else:
                        print(f'✗ Failed to download {i}/{len(prompts)}: {filename}')
                else:
                    print(f'✗ No image URL {i}/{len(prompts)}: {filename}')
            else:
                print(f'✗ API error {i}/{len(prompts)}: {filename}')
        else:
            print(f'✗ Curl failed {i}/{len(prompts)}: {filename}')
    except Exception as e:
        print(f'✗ Exception {i}/{len(prompts)}: {filename} - {e}')
    
    # Small delay to avoid API rate limits
    time.sleep(1)

print(f'Batch complete: {success_count}/{len(prompts)} successful')
"