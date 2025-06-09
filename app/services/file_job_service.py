"""
File-based job management service for async video generation
Simple, reliable solution that works across multiple workers
"""
import json
import os
import uuid
import fcntl
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from ..config.logging_config import get_logger
from ..config.settings import settings
from ..models.video_config import VideoConfig

logger = get_logger(__name__)


class JobStatus(Enum):
    """Job status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FileJobService:
    """File-based job management service"""
    
    def __init__(self):
        self.jobs_dir = Path(settings.output_dir) / "jobs"
        self.jobs_dir.mkdir(exist_ok=True)
        
        self.executor = ThreadPoolExecutor(
            max_workers=getattr(settings, 'video_generation_workers', 2),
            thread_name_prefix="video-gen"
        )
        
        # Start cleanup thread
        self._start_cleanup_thread()
        
        logger.info(f"FileJobService initialized with {self.executor._max_workers} workers")
        logger.info(f"Job storage directory: {self.jobs_dir}")
    
    def _get_job_file(self, job_id: str) -> Path:
        """Get the file path for a job"""
        return self.jobs_dir / f"{job_id}.json"
    
    def _read_job_file(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Safely read a job file with file locking"""
        job_file = self._get_job_file(job_id)
        
        if not job_file.exists():
            return None
        
        try:
            with open(job_file, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read job file {job_id}: {e}")
            return None
    
    def _write_job_file(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """Safely write a job file with file locking"""
        job_file = self._get_job_file(job_id)
        
        try:
            with open(job_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
                json.dump(job_data, f, indent=2)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Failed to write job file {job_id}: {e}")
            return False
    
    def _update_job_file(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Safely update a job file with file locking"""
        job_file = self._get_job_file(job_id)
        
        if not job_file.exists():
            return False
        
        try:
            with open(job_file, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
                job_data = json.load(f)
                job_data.update(updates)
                job_data['updated_at'] = datetime.utcnow().isoformat()
                
                f.seek(0)
                json.dump(job_data, f, indent=2)
                f.truncate()
            return True
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Failed to update job file {job_id}: {e}")
            return False
    
    def create_job(self, config: VideoConfig) -> str:
        """Create a new video generation job"""
        job_id = str(uuid.uuid4())
        
        job_data = {
            "job_id": job_id,
            "video_id": job_id,
            "status": JobStatus.PENDING.value,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": 0,
            "current_step": "Queued",
            "error": None,
            "result": None,
            "download_url": None,
            "output_size_mb": None,
            "duration_seconds": None,
            "config": config.model_dump()
        }
        
        if self._write_job_file(job_id, job_data):
            logger.info(f"Created job {job_id}")
            return job_id
        else:
            raise Exception(f"Failed to create job file for {job_id}")
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status as dictionary"""
        job_data = self._read_job_file(job_id)
        if job_data:
            # Remove the config from status response to keep it clean
            status_data = job_data.copy()
            status_data.pop('config', None)
            return status_data
        return None
    
    def submit_job(self, job_id: str, generation_func, *args, **kwargs):
        """Submit a job for background execution"""
        def run_job():
            try:
                self.update_job_status(job_id, JobStatus.PROCESSING, "Starting video generation")
                result = generation_func(job_id, *args, **kwargs)
                self.complete_job(job_id, result)
            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}")
                self.fail_job(job_id, str(e))
        
        future = self.executor.submit(run_job)
        logger.info(f"Job {job_id} submitted for processing")
        return future
    
    def update_job_status(self, job_id: str, status: JobStatus, current_step: str = None, progress: int = None):
        """Update job status and progress"""
        updates = {
            "status": status.value
        }
        
        if status == JobStatus.PROCESSING:
            # Set started_at only once
            job_data = self._read_job_file(job_id)
            if job_data and not job_data.get('started_at'):
                updates['started_at'] = datetime.utcnow().isoformat()
        
        if current_step:
            updates['current_step'] = current_step
            logger.info(f"Job {job_id}: {current_step}")
        
        if progress is not None:
            updates['progress'] = min(100, max(0, progress))
        
        self._update_job_file(job_id, updates)
    
    def update_job_progress(self, job_id: str, progress: int, step: str = None):
        """Update job progress percentage"""
        self.update_job_status(job_id, JobStatus.PROCESSING, step, progress)
    
    def complete_job(self, job_id: str, result: Dict[str, Any]):
        """Mark job as completed with results"""
        completed_at = datetime.utcnow().isoformat()
        
        # Calculate duration if started_at exists
        job_data = self._read_job_file(job_id)
        duration_seconds = None
        if job_data and job_data.get('started_at'):
            started_at = datetime.fromisoformat(job_data['started_at'])
            completed_at_dt = datetime.fromisoformat(completed_at)
            duration_seconds = (completed_at_dt - started_at).total_seconds()
        
        updates = {
            "status": JobStatus.COMPLETED.value,
            "completed_at": completed_at,
            "progress": 100,
            "current_step": "Completed",
            "result": result,
            "download_url": result.get('download_url'),
            "output_size_mb": result.get('output_size_mb'),
            "duration_seconds": duration_seconds
        }
        
        self._update_job_file(job_id, updates)
        logger.info(f"Job {job_id} completed successfully in {duration_seconds:.1f}s" if duration_seconds else f"Job {job_id} completed successfully")
    
    def fail_job(self, job_id: str, error: str):
        """Mark job as failed with error message"""
        updates = {
            "status": JobStatus.FAILED.value,
            "completed_at": datetime.utcnow().isoformat(),
            "error": error,
            "current_step": "Failed"
        }
        
        self._update_job_file(job_id, updates)
        logger.error(f"Job {job_id} failed: {error}")
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or processing job"""
        job_data = self._read_job_file(job_id)
        
        if job_data and job_data['status'] in [JobStatus.PENDING.value, JobStatus.PROCESSING.value]:
            updates = {
                "status": JobStatus.CANCELLED.value,
                "completed_at": datetime.utcnow().isoformat(),
                "current_step": "Cancelled"
            }
            
            if self._update_job_file(job_id, updates):
                logger.info(f"Job {job_id} cancelled")
                return True
        
        return False
    
    def list_jobs(self, status: Optional[JobStatus] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List jobs with optional status filter"""
        jobs = []
        
        # Get all job files
        job_files = list(self.jobs_dir.glob("*.json"))
        
        # Sort by modification time (newest first)
        job_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        for job_file in job_files[:limit * 2]:  # Read more in case some are filtered
            job_id = job_file.stem
            job_data = self._read_job_file(job_id)
            
            if job_data:
                # Filter by status if specified
                if status is None or job_data['status'] == status.value:
                    # Remove config from list response
                    list_data = job_data.copy()
                    list_data.pop('config', None)
                    list_data.pop('result', None)  # Also remove large result data
                    jobs.append(list_data)
                    
                    if len(jobs) >= limit:
                        break
        
        return jobs
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get job statistics"""
        job_files = list(self.jobs_dir.glob("*.json"))
        total_jobs = len(job_files)
        
        status_counts = {status.value: 0 for status in JobStatus}
        completed_durations = []
        
        for job_file in job_files:
            job_data = self._read_job_file(job_file.stem)
            if job_data:
                status = job_data.get('status')
                if status in status_counts:
                    status_counts[status] += 1
                
                # Collect duration data
                if status == JobStatus.COMPLETED.value and job_data.get('duration_seconds'):
                    completed_durations.append(job_data['duration_seconds'])
        
        avg_duration = (
            sum(completed_durations) / len(completed_durations)
            if completed_durations else 0
        )
        
        return {
            "total_jobs": total_jobs,
            "status_counts": status_counts,
            "average_duration_seconds": round(avg_duration, 1),
            "active_workers": len(self.executor._threads) if hasattr(self.executor, '_threads') else 0,
            "max_workers": self.executor._max_workers
        }
    
    def _start_cleanup_thread(self):
        """Start background thread to cleanup old job files"""
        def cleanup_old_jobs():
            while True:
                try:
                    time.sleep(300)  # Check every 5 minutes
                    self._cleanup_old_jobs()
                except Exception as e:
                    logger.error(f"Error in cleanup thread: {e}")
        
        cleanup_thread = threading.Thread(
            target=cleanup_old_jobs,
            daemon=True,
            name="job-cleanup"
        )
        cleanup_thread.start()
    
    def _cleanup_old_jobs(self):
        """Remove old completed/failed job files"""
        cutoff_time = datetime.utcnow() - timedelta(hours=1)  # 1 hour
        job_files = list(self.jobs_dir.glob("*.json"))
        
        removed_count = 0
        for job_file in job_files:
            job_data = self._read_job_file(job_file.stem)
            
            if job_data and job_data['status'] in [JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]:
                completed_at = job_data.get('completed_at')
                if completed_at:
                    try:
                        completed_dt = datetime.fromisoformat(completed_at)
                        if completed_dt < cutoff_time:
                            job_file.unlink()
                            removed_count += 1
                            logger.debug(f"Cleaned up old job file: {job_file.name}")
                    except (ValueError, OSError) as e:
                        logger.warning(f"Failed to cleanup job file {job_file.name}: {e}")
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old job files")
    
    def shutdown(self):
        """Shutdown the job service gracefully"""
        logger.info("Shutting down FileJobService...")
        self.executor.shutdown(wait=True)
        logger.info("FileJobService shutdown complete")


# Global job service instance
job_service = FileJobService()