"""
PC Monitor - System hardware monitoring service.
"""
import asyncio
import time
from collections import deque
from datetime import datetime
from typing import List, Dict, Any, Optional
import psutil
import platform
import logging

logger = logging.getLogger(__name__)


class PCMonitor:
    """Monitors PC hardware metrics."""
    
    def __init__(self, history_size: int = 720):  # 720 * 5s = 1 hour
        self.running = False
        self.history_size = history_size
        self._history: deque = deque(maxlen=history_size)
        self._task: Optional[asyncio.Task] = None
        self._update_interval = 5  # seconds
        
        # Initialize GPU monitoring if available
        self._gpu_available = self._check_gpu()
        
    def _check_gpu(self) -> bool:
        """Check if GPU monitoring is available."""
        try:
            import pynvml
            pynvml.nvmlInit()
            return True
        except Exception:
            return False
    
    async def start(self):
        """Start monitoring loop."""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("PC Monitor started")
    
    async def stop(self):
        """Stop monitoring loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PC Monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                metrics = self._collect_metrics()
                self._history.append(metrics)
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
            
            await asyncio.sleep(self._update_interval)
    
    def _collect_metrics(self) -> dict:
        """Collect current system metrics."""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        
        # Memory
        mem = psutil.virtual_memory()
        
        # Disk
        disk = psutil.disk_usage('/')
        
        # Network
        net = psutil.net_io_counters()
        
        # Temperatures (if available)
        cpu_temp = None
        try:
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                cpu_temp = max(t.current for t in temps['coretemp'])
            elif 'k10temp' in temps:
                cpu_temp = max(t.current for t in temps['k10temp'])
        except Exception:
            pass
        
        # GPU metrics
        gpu_percent = None
        gpu_memory_percent = None
        gpu_temp_c = None
        
        if self._gpu_available:
            try:
                import pynvml
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                
                gpu_percent = util.gpu
                gpu_memory_percent = (mem_info.used / mem_info.total) * 100
                gpu_temp_c = temp
            except Exception:
                pass
        
        # Top processes
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] > 1.0 or info['memory_percent'] > 1.0:
                    processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": cpu_percent,
            "cpu_per_core": psutil.cpu_percent(percpu=True),
            "memory_percent": mem.percent,
            "memory_used_gb": round(mem.used / (1024**3), 2),
            "memory_total_gb": round(mem.total / (1024**3), 2),
            "disk_percent": round((disk.used / disk.total) * 100, 1),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "network_sent_mb": round(net.bytes_sent / (1024**2), 2),
            "network_recv_mb": round(net.bytes_recv / (1024**2), 2),
            "gpu_percent": gpu_percent,
            "gpu_memory_percent": gpu_memory_percent,
            "gpu_temp_c": gpu_temp_c,
            "cpu_temp_c": cpu_temp,
            "top_processes": processes[:10]
        }
    
    def get_metrics(self) -> dict:
        """Get current metrics (or latest from history)."""
        if self._history:
            return self._history[-1]
        return self._collect_metrics()
    
    def get_history(self, duration_minutes: int = 60) -> List[dict]:
        """Get historical metrics for specified duration."""
        if not self._history:
            return []
        
        cutoff = time.time() - (duration_minutes * 60)
        return [
            m for m in self._history 
            if datetime.fromisoformat(m["timestamp"]).timestamp() > cutoff
        ]
    
    def get_top_processes(self, limit: int = 10) -> List[dict]:
        """Get top processes by CPU usage."""
        if not self._history:
            return []
        
        latest = self._history[-1]
        return latest.get("top_processes", [])[:limit]
    
    def get_average_cpu(self, duration_minutes: int = 5) -> float:
        """Get average CPU usage over duration."""
        history = self.get_history(duration_minutes)
        if not history:
            return 0.0
        return sum(m["cpu_percent"] for m in history) / len(history)
    
    def get_alert_status(self) -> dict:
        """Check for alert conditions."""
        if not self._history:
            return {"alerts": []}
        
        latest = self._history[-1]
        alerts = []
        
        if latest["cpu_percent"] > 90:
            alerts.append({"level": "critical", "metric": "cpu", "value": latest["cpu_percent"]})
        elif latest["cpu_percent"] > 80:
            alerts.append({"level": "warning", "metric": "cpu", "value": latest["cpu_percent"]})
        
        if latest["memory_percent"] > 90:
            alerts.append({"level": "critical", "metric": "memory", "value": latest["memory_percent"]})
        elif latest["memory_percent"] > 80:
            alerts.append({"level": "warning", "metric": "memory", "value": latest["memory_percent"]})
        
        if latest["disk_percent"] > 95:
            alerts.append({"level": "critical", "metric": "disk", "value": latest["disk_percent"]})
        elif latest["disk_percent"] > 85:
            alerts.append({"level": "warning", "metric": "disk", "value": latest["disk_percent"]})
        
        if latest.get("cpu_temp_c") and latest["cpu_temp_c"] > 85:
            alerts.append({"level": "critical", "metric": "cpu_temp", "value": latest["cpu_temp_c"]})
        elif latest.get("cpu_temp_c") and latest["cpu_temp_c"] > 75:
            alerts.append({"level": "warning", "metric": "cpu_temp", "value": latest["cpu_temp_c"]})
        
        return {"alerts": alerts}