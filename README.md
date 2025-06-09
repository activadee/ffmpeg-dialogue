# Video Generator Server

A modular Flask application for generating videos with audio synchronization, image overlays, and subtitle support.

## Features

- 🎵 **Audio Concatenation**: Merge multiple audio files with precise timing
- 🖼️ **Image Overlays**: Add timed image overlays to videos
- 📝 **Subtitle Generation**: Automatic subtitle generation using HuggingFace Whisper
- 🌐 **Google Drive Support**: Handle Google Drive URLs with redirect following
- ⚡ **Concurrent Processing**: Multi-threaded audio analysis and transcription
- 💊 **Health Monitoring**: Comprehensive health checks and metrics
- 🛡️ **Error Handling**: Robust error handling and validation
- 🐳 **Docker Support**: Production-ready containerization

## Quick Start

### Option 1: Direct Python
```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python run.py
```

### Option 2: Environment Configuration
```bash
# Set environment variables
export VIDEO_GENERATOR_DEBUG=true
export VIDEO_GENERATOR_PORT=3002

# Run server
python run.py
```

### Option 3: Docker
```bash
# Build and run
docker build -t video-generator .
docker run -p 3002:3002 video-generator
```

## API Endpoints

### Video Generation
- `POST /generate-video` - Generate video from JSON configuration
- `GET /download/<video_id>` - Download generated video
- `GET /status/<video_id>` - Check video generation status
- `GET /videos` - List all generated videos
- `DELETE /videos/<video_id>` - Delete video

### Health & Monitoring
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed system status
- `GET /metrics` - System performance metrics
- `GET /ready` - Readiness probe (for Kubernetes)
- `GET /live` - Liveness probe (for Kubernetes)

## Configuration

### Environment Variables

- `FLASK_ENV`: Set to `production` for production deployments
- `PYTHONUNBUFFERED`: Set to `1` for better logging in containers

### Volumes

- `./generated_videos`: Persistent storage for generated videos

## Error Handling

- **Timeout**: 10 minutes max for video generation
- **Validation**: Checks for required fields and valid URLs
- **Cleanup**: Automatic removal of temporary files
- **Logging**: Comprehensive error logging and debugging info

## Example with n8n

1. **HTTP Request Node**: 
   - Method: `POST`
   - URL: `http://your-server:3002/generate-video`
   - Body: Your JSON configuration

2. **Wait/Polling**: 
   - Video generation can take 1-10 minutes depending on complexity

3. **Download**:
   - Use returned `download_url` to fetch the generated video

## Limitations

- Maximum video generation time: 10 minutes
- Files auto-deleted after 1 hour
- Supports common video/audio formats (MP4, MP3, WAV, etc.)
- Google Drive URLs must be publicly accessible