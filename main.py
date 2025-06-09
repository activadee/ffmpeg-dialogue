# URL-only approach - no downloads, just generate FFmpeg commands
import subprocess
import json

# No duration calculation needed - let ffmpeg handle it

def process_video_config():
    items = []
    for item in _input.all():
        input_data = item['json']
        config = input_data[0] if isinstance(input_data, list) else input_data
        
        # Get background video
        bg_video = next((el for el in config['elements'] if el['type'] == 'video'), None)
        if not bg_video:
            raise ValueError("No background video found")
        
        # Process Google Drive URLs with better validation
        def process_gdrive_url(url):
            if 'drive.google.com' in url:
                file_id = None
                if 'id=' in url:
                    file_id = url.split('id=')[1].split('&')[0]
                elif '/file/d/' in url:
                    file_id = url.split('/file/d/')[1].split('/')[0]
                if file_id:
                    # Check if file ID looks valid (should be alphanumeric)
                    if file_id and len(file_id) > 20 and file_id.replace('_', '').replace('-', '').isalnum():
                        return f"https://drive.google.com/uc?export=download&id={file_id}"
                    else:
                        print(f"Warning: Google Drive file ID looks invalid: {file_id}")
            return url
        
        # Collect URLs
        bg_url = process_gdrive_url(bg_video['src'])
        
        audio_urls = []
        image_data = []
        
        # Collect audio URLs and image data from scenes
        if 'scenes' in config:
            for i, scene in enumerate(config['scenes']):
                if 'elements' in scene:
                    for element in scene['elements']:
                        if element['type'] == 'audio':
                            if element.get('src'):
                                audio_url = process_gdrive_url(element['src'])
                                if audio_url and audio_url.strip():
                                    audio_urls.append(audio_url)
                        elif element['type'] == 'image':
                            if element.get('src'):
                                img_url = process_gdrive_url(element['src'])
                                image_data.append({
                                    'url': img_url,
                                    'x': element.get('x', 0),
                                    'y': element.get('y', 0),
                                    'scene_index': i
                                })
        
        print(f"Found {len(audio_urls)} audio files and {len(image_data)} images")
        
        # Build FFmpeg command with URLs
        cmd_parts = ['ffmpeg', '-y']
        
        # Add background video with loop
        cmd_parts.extend(['-stream_loop', '-1', '-i', f'"{bg_url}"'])
        
        # Add audio inputs for concatenation
        for i, audio_url in enumerate(audio_urls):
            cmd_parts.extend(['-i', f'"{audio_url}"'])
        
        # Add unique image inputs only
        unique_image_urls = []
        for img in image_data:
            if img['url'] not in unique_image_urls:
                unique_image_urls.append(img['url'])
                cmd_parts.extend(['-i', f'"{img["url"]}"'])
        
        # Build filter complex
        filters = []
        
        # Concatenate all audio files sequentially 
        if len(audio_urls) > 1:
            audio_inputs = ''.join([f'[{i+1}:a]' for i in range(len(audio_urls))])
            filters.append(f'{audio_inputs}concat=n={len(audio_urls)}:v=0:a=1[concatenated_audio]')
            
            # Get duration of concatenated audio and add 2 seconds
            filters.append(f'[concatenated_audio]apad=pad_dur=2[final_audio]')
            audio_map = '[final_audio]'
        elif len(audio_urls) == 1:
            # Single audio with 2 second padding
            filters.append(f'[1:a]apad=pad_dur=2[final_audio]')
            audio_map = '[final_audio]'
        else:
            audio_map = '0:a'
        
        # Simple image overlay like in debug-overlay.sh
        current_video = '0:v'
        
        # For now, just overlay the first image if available (like your working example)
        if len(image_data) > 0:
            img_input_idx = len(audio_urls) + 1  # First image input
            x_pos = image_data[0]["x"]
            y_pos = image_data[0]["y"]
            
            print(f"Overlaying image at index {img_input_idx}, position ({x_pos},{y_pos})")
            
            # Scale and overlay image (exactly like your working example)
            filters.append(f'[{img_input_idx}:v]scale=200:200[img]')
            filters.append(f'[{current_video}][img]overlay={x_pos}:{y_pos}[final_video]')
            current_video = 'final_video'
        
        # Complete command
        if filters:
            cmd_parts.extend(['-filter_complex', f'"{";".join(filters)}"'])
            if current_video != '0:v':
                cmd_parts.extend(['-map', f'"[{current_video}]"'])
            else:
                cmd_parts.extend(['-map', '"0:v"'])
        else:
            cmd_parts.extend(['-map', '"0:v"'])
        
        cmd_parts.extend(['-map', f'"{audio_map}"'])
        cmd_parts.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])
        cmd_parts.extend(['-s', f"{config['width']}x{config['height']}"])
        
        # Enhanced shortest flags to fix filter_complex + stream_loop issues
        cmd_parts.extend(['-shortest', '-fflags', '+shortest', '-max_interleave_delta', '100M'])
        cmd_parts.append('output.mp4')
        
        items.append({
            'json': {
                'success': True,
                'ffmpeg_command': ' '.join(cmd_parts),
                'background_url': bg_url,
                'audio_urls': audio_urls,
                'image_data': image_data,
                'config': {
                    'width': config['width'],
                    'height': config['height'],
                    'audio_count': len(audio_urls),
                    'image_count': len(image_data),
                    'scene_count': len(config.get('scenes', [])),
                    'note': 'Duration determined by concatenated audio + 2 seconds'
                }
            }
        })
    
    return items

# Execute when running in n8n and return items directly
try:
    return process_video_config()
except Exception as e:
    return [{'json': {'success': False, 'error': str(e)}}]