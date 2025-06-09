#!/usr/bin/env python3
"""
Split Family Guy video into 62-second chunks and convert to 1080x1920 (portrait) - CONCURRENT VERSION
"""
import subprocess
import math
import os
import concurrent.futures
import threading
import time

# Thread-safe counter for progress
progress_lock = threading.Lock()
completed_chunks = 0
total_chunks = 0

def process_chunk(chunk_info):
    global completed_chunks
    
    i, start_time, input_file, chunk_duration, output_width, output_height = chunk_info
    output_file = f"chunks/family_guy_chunk_{i:03d}.mp4"
    
    # FFmpeg command with GPU acceleration - NO AUDIO for speed
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-i', input_file,
        '-t', str(chunk_duration),
        '-vf', f'scale={output_width}:{output_height}:force_original_aspect_ratio=increase,crop={output_width}:{output_height}',
        '-c:v', 'h264_videotoolbox',  # GPU encoder
        '-b:v', '3M',                 # 3Mbps bitrate
        '-maxrate', '5M',             # Max 5Mbps
        '-allow_sw', '1',             # Software fallback
        '-an',                        # No audio - much faster!
        output_file
    ]
    
    try:
        start = time.time()
        subprocess.run(cmd, check=True, capture_output=True)
        duration = time.time() - start
        
        # Update progress thread-safely
        with progress_lock:
            global completed_chunks
            completed_chunks += 1
            print(f"✓ [{completed_chunks}/{total_chunks}] Chunk {i:03d} done in {duration:.1f}s: {output_file}")
        
        return True, i, output_file
    except subprocess.CalledProcessError as e:
        with progress_lock:
            completed_chunks += 1
            print(f"✗ [{completed_chunks}/{total_chunks}] Chunk {i:03d} FAILED: {e}")
        return False, i, output_file

def split_video():
    global total_chunks, completed_chunks
    
    input_file = "family_guy_720p.mp4"  # Use existing downloaded file
    chunk_duration = 62  # seconds
    output_width = 1080
    output_height = 1920
    max_workers = 10  # Concurrent tasks
    
    # Get video duration
    cmd = f'ffprobe -v quiet -print_format json -show_format "{input_file}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    import json
    data = json.loads(result.stdout)
    total_duration = float(data['format']['duration'])
    
    # Calculate number of chunks
    num_chunks = math.ceil(total_duration / chunk_duration)
    total_chunks = num_chunks
    completed_chunks = 0
    
    print(f"Video duration: {total_duration:.1f}s")
    print(f"Chunk duration: {chunk_duration}s")
    print(f"Number of chunks: {num_chunks}")
    print(f"Concurrent workers: {max_workers}")
    print("-" * 50)
    
    # Create output directory
    os.makedirs("chunks", exist_ok=True)
    
    # Prepare all chunk tasks
    chunk_tasks = []
    for i in range(num_chunks):
        start_time = i * chunk_duration
        chunk_tasks.append((i, start_time, input_file, chunk_duration, output_width, output_height))
    
    # Process chunks concurrently
    start_time = time.time()
    success_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_chunk = {
            executor.submit(process_chunk, task): task[0] 
            for task in chunk_tasks
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_chunk):
            try:
                success, chunk_id, output_file = future.result()
                if success:
                    success_count += 1
            except Exception as e:
                chunk_id = future_to_chunk[future]
                print(f"✗ Chunk {chunk_id} failed with exception: {e}")
    
    total_time = time.time() - start_time
    
    print("-" * 50)
    print(f"DONE! Processed {num_chunks} chunks in {total_time:.1f}s")
    print(f"Success: {success_count}/{num_chunks}")
    print(f"Failed: {num_chunks - success_count}/{num_chunks}")
    print(f"Average: {total_time/num_chunks:.2f}s per chunk")
    print(f"Output: chunks/ directory")

if __name__ == "__main__":
    split_video()