"""
System Monitor Service (StatNode-inspired).
Provides system metrics collection, alerting, and history.
"""
import asyncio
import json
import logging
import platform
import shutil
import subprocess
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import psutil
import psutil._common

from app.core.config import settings
from app.core.events import event_bus, EventType, emit_sensor_data
from app.core.database import get_db
from app.models.system import SystemMetrics, AlertRule, Alert, AlertStatus, AlertSeverity

logger = logging.getLogger(__name__)


@dataclass
class GPUMetrics:
    """GPU metrics container."""
    gpu_percent: Optional[float] = None
    gpu_memory_percent: Optional[float] = None
    gpu_memory_used_mb: Optional[int] = None
    gpu_memory_total_mb: Optional[int] = None
    gpu_temp_c: Optional[float] = None
    gpu_fan_percent: Optional[float] = None
    gpu_name: Optional[str] = None
    gpu_source: Optional[str] = None


@dataclass
class SystemMetricsSnapshot:
    """Complete system metrics snapshot."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    cpu_percent: float = 0.0
    cpu_per_core: List[float] = field(default_factory=list)
    cpu_freq_current: Optional[float] = None
    cpu_freq_min: Optional[float] = None
    cpu_freq_max: Optional[float] = None
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    memory_available_gb: float = 0.0
    swap_percent: float = 0.0
    swap_used_gb: float = 0.0
    swap_total_gb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_read_mb_s: float = 0.0
    disk_write_mb_s: float = 0.0
    network_sent_mb_s: float = 0.0
    network_recv_mb_s: float = 0.0
    network_sent_total_mb: float = 0.0
    network_recv_total_mb: float = 0.0
    boot_time: Optional[datetime] = None
    cpu_temp_c: Optional[float] = None
    cpu_temp_source: Optional[str] = None
    thermal_zone_c: Optional[float] = None
    gpu_metrics: Optional[GPUMetrics] = None
    process_count: int = 0
    thread_count: int = 0
    top_processes: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly snapshot (no datetimes or dataclass objects)."""
        gpu = self.gpu_metrics
        return {
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "cpu_per_core": list(self.cpu_per_core),
            "cpu_freq_current": self.cpu_freq_current,
            "cpu_freq_min": self.cpu_freq_min,
            "cpu_freq_max": self.cpu_freq_max,
            "memory_percent": self.memory_percent,
            "memory_used_gb": round(self.memory_used_gb, 2),
            "memory_total_gb": round(self.memory_total_gb, 2),
            "memory_available_gb": round(self.memory_available_gb, 2),
            "swap_percent": self.swap_percent,
            "swap_used_gb": round(self.swap_used_gb, 2),
            "swap_total_gb": round(self.swap_total_gb, 2),
            "disk_percent": self.disk_percent,
            "disk_used_gb": round(self.disk_used_gb, 1),
            "disk_total_gb": round(self.disk_total_gb, 1),
            "disk_free_gb": round(self.disk_free_gb, 1),
            "disk_read_mb_s": round(self.disk_read_mb_s, 3),
            "disk_write_mb_s": round(self.disk_write_mb_s, 3),
            "network_sent_mb_s": round(self.network_sent_mb_s, 3),
            "network_recv_mb_s": round(self.network_recv_mb_s, 3),
            "network_sent_total_mb": round(self.network_sent_total_mb, 1),
            "network_recv_total_mb": round(self.network_recv_total_mb, 1),
            "cpu_temp_c": self.cpu_temp_c,
            "cpu_temp_source": self.cpu_temp_source,
            "thermal_zone_c": round(self.thermal_zone_c, 1) if self.thermal_zone_c is not None else None,
            "gpu_percent": gpu.gpu_percent if gpu else None,
            "gpu_memory_percent": gpu.gpu_memory_percent if gpu else None,
            "gpu_memory_used_mb": gpu.gpu_memory_used_mb if gpu else None,
            "gpu_memory_total_mb": gpu.gpu_memory_total_mb if gpu else None,
            "gpu_temp_c": gpu.gpu_temp_c if gpu else None,
            "gpu_fan_percent": gpu.gpu_fan_percent if gpu else None,
            "gpu_name": gpu.gpu_name if gpu else None,
            "gpu_source": gpu.gpu_source if gpu else None,
            "process_count": self.process_count,
            "thread_count": self.thread_count,
            "boot_time": self.boot_time.isoformat() if self.boot_time else None,
            "top_processes": list(self.top_processes),
        }


class SystemMonitor:
    """
    System monitoring service with alerting capabilities.
    Inspired by StatNode - provides Prometheus-compatible metrics and alerting.
    """
    
    def __init__(self):
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._interval = 5  # seconds
        self._history_size = 720  # 1 hour at 5s intervals
        self._history: deque = deque(maxlen=720)
        self._last_net_io = psutil.net_io_counters()
        self._last_disk_io = psutil.disk_io_counters()
        self._last_cpu_times = psutil.cpu_times()
        self._last_check = time.time()
        self._nvml = None
        self._gpu_available = self._check_gpu()
        self._gpu_static: Optional[Dict[str, Any]] = None
        self._gpu_static_at = 0.0
        self._cpu_temp_cache: Optional[float] = None
        self._cpu_temp_source: Optional[str] = None
        self._thermal_zone_cache: Optional[float] = None
        self._cpu_temp_checked_at = 0.0
        self._alert_rules_cache: List = []
        self._last_alert_times: Dict[str, datetime] = {}
    
    def _check_gpu(self) -> bool:
        """Check if GPU monitoring is available via NVML."""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml = pynvml
            return True
        except Exception:
            self._nvml = None
            return False

    # ------------------------------------------------------------------
    # Telemetry providers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Parse an nvidia-smi/WMI value that may be '[N/A]' or empty."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"n/a", "[n/a]", "none"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _gpu_static_info(self) -> Dict[str, Any]:
        """Best-effort GPU name/VRAM when NVML is unavailable (cached 5 min)."""
        now = time.time()
        if self._gpu_static is not None and now - self._gpu_static_at < 300:
            return self._gpu_static

        info: Dict[str, Any] = {}
        if platform.system() == "Windows":
            command = (
                "Get-CimInstance Win32_VideoController | "
                "Select-Object -First 1 Name,AdapterRAM | ConvertTo-Json -Compress"
            )
            try:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                raw = (result.stdout or "").strip()
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        name = str(data.get("Name") or "").strip()
                        info["gpu_name"] = name or None
                        ram = data.get("AdapterRAM")
                        if isinstance(ram, (int, float)) and ram > 0:
                            info["gpu_memory_total_mb"] = int(ram // (1024 * 1024))
            except Exception as exc:
                logger.debug("GPU WMI lookup failed: %s", exc)

        self._gpu_static = info
        self._gpu_static_at = now
        return info

    def _read_gpu_nvml(self) -> Optional[GPUMetrics]:
        """Read GPU telemetry through NVML (NVIDIA only)."""
        if not self._nvml:
            return None
        try:
            handle = self._nvml.nvmlDeviceGetHandleByIndex(0)
            util = self._nvml.nvmlDeviceGetUtilizationRates(handle)
            mem_info = self._nvml.nvmlDeviceGetMemoryInfo(handle)
            temp = self._nvml.nvmlDeviceGetTemperature(
                handle, self._nvml.NVML_TEMPERATURE_GPU
            )
            name = self._nvml.nvmlDeviceGetName(handle)
            try:
                fan = self._nvml.nvmlDeviceGetFanSpeed(handle)
            except Exception:
                fan = None

            return GPUMetrics(
                gpu_percent=float(util.gpu),
                gpu_memory_percent=(
                    (mem_info.used / mem_info.total) * 100 if mem_info.total else None
                ),
                gpu_memory_used_mb=int(mem_info.used // (1024 * 1024)),
                gpu_memory_total_mb=int(mem_info.total // (1024 * 1024)),
                gpu_temp_c=float(temp) if temp is not None else None,
                gpu_fan_percent=float(fan) if fan is not None else None,
                gpu_name=name.decode() if isinstance(name, bytes) else str(name),
                gpu_source="nvml",
            )
        except Exception as exc:
            logger.debug("NVML read failed: %s", exc)
            return None

    def _read_gpu_smi(self) -> Optional[GPUMetrics]:
        """Fallback GPU telemetry through the nvidia-smi executable."""
        executable = shutil.which("nvidia-smi")
        if not executable:
            return None

        fields = (
            "name,utilization.gpu,memory.used,memory.total,"
            "temperature.gpu,fan.speed"
        )
        try:
            result = subprocess.run(
                [executable, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            line = next(
                (item for item in (result.stdout or "").splitlines() if item.strip()),
                "",
            )
            if not line:
                return None
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 5:
                return None

            used_mb = self._to_float(parts[2])
            total_mb = self._to_float(parts[3])
            return GPUMetrics(
                gpu_percent=self._to_float(parts[1]),
                gpu_memory_percent=(
                    (used_mb / total_mb) * 100 if used_mb is not None and total_mb else None
                ),
                gpu_memory_used_mb=int(used_mb) if used_mb is not None else None,
                gpu_memory_total_mb=int(total_mb) if total_mb is not None else None,
                gpu_temp_c=self._to_float(parts[4]),
                gpu_fan_percent=self._to_float(parts[5]) if len(parts) > 5 else None,
                gpu_name=parts[0] or None,
                gpu_source="nvidia-smi",
            )
        except Exception as exc:
            logger.debug("nvidia-smi read failed: %s", exc)
            return None

    def _read_gpu(self) -> Optional[GPUMetrics]:
        """Layered GPU read: NVML -> nvidia-smi -> WMI name/VRAM only."""
        metrics = self._read_gpu_nvml() or self._read_gpu_smi()
        if metrics:
            return metrics

        static = self._gpu_static_info()
        if static.get("gpu_name") or static.get("gpu_memory_total_mb"):
            return GPUMetrics(
                gpu_name=static.get("gpu_name"),
                gpu_memory_total_mb=static.get("gpu_memory_total_mb"),
                gpu_source="wmi",
            )
        return None

    def _query_windows_cpu_temp(
        self,
    ) -> tuple[Optional[float], Optional[str], Optional[float]]:
        """Query Windows temperature providers.

        LibreHardwareMonitor/OpenHardwareMonitor expose real CPU package
        sensors. Without them, ACPI thermal zones are still reported but kept
        separate because desktops usually expose ambient/chipset zones there.
        """
        command = (
            "$ErrorActionPreference='SilentlyContinue';"
            "$s = Get-CimInstance -Namespace root/LibreHardwareMonitor "
            "-ClassName Sensor -ErrorAction SilentlyContinue | "
            "Where-Object { $_.SensorType -eq 'Temperature' -and "
            "$_.Name -match 'CPU Package|Core Max|CPU Total|CPU' } | "
            "Sort-Object Value -Descending | Select-Object -First 1;"
            "if ($s) { 'lhm|' + $s.Value; exit };"
            "$s = Get-CimInstance -Namespace root/OpenHardwareMonitor "
            "-ClassName Sensor -ErrorAction SilentlyContinue | "
            "Where-Object { $_.SensorType -eq 'Temperature' -and "
            "$_.Name -match 'CPU Package|Core Max|CPU Total|CPU' } | "
            "Sort-Object Value -Descending | Select-Object -First 1;"
            "if ($s) { 'ohm|' + $s.Value; exit };"
            "$z = Get-CimInstance -ClassName "
            "Win32_PerfFormattedData_Counters_ThermalZoneInformation "
            "-ErrorAction SilentlyContinue | "
            "Sort-Object HighPrecisionTemperature -Descending | "
            "Select-Object -First 1;"
            "if ($z) { 'tz|' + (($z.HighPrecisionTemperature / 10.0) - 273.15); exit };"
            "$t = Get-CimInstance -Namespace root/wmi "
            "-ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | "
            "Sort-Object CurrentTemperature -Descending | Select-Object -First 1;"
            "if ($t) { 'acpi|' + ((($t.CurrentTemperature / 10.0) - 273.15)) }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=8,
            )
            line = next(
                (item for item in (result.stdout or "").splitlines() if "|" in item),
                "",
            )
            if not line:
                return None, None, None
            source, _, raw_value = line.partition("|")
            source = source.strip() or None
            value = self._to_float(raw_value)
            if value is None or not -20 <= value <= 150:
                return None, None, None
            if source in {"lhm", "ohm"}:
                return value, source, None
            return None, None, value
        except Exception as exc:
            logger.debug("CPU temperature lookup failed: %s", exc)
            return None, None, None

    async def _read_cpu_temp(self) -> tuple[Optional[float], Optional[str], Optional[float]]:
        """Read CPU temperature, caching results for 30 s (subprocess is slow)."""
        if time.time() - self._cpu_temp_checked_at < 30:
            return (
                self._cpu_temp_cache,
                self._cpu_temp_source,
                self._thermal_zone_cache,
            )

        temp: Optional[float] = None
        source: Optional[str] = None
        thermal_zone: Optional[float] = None

        if hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures()
                for _name, entries in (temps or {}).items():
                    for entry in entries:
                        if entry.current and entry.current > 0:
                            if temp is None or entry.current > temp:
                                temp = float(entry.current)
                                source = "psutil"
            except Exception:
                pass

        if temp is None and platform.system() == "Windows":
            temp, source, thermal_zone = await asyncio.to_thread(
                self._query_windows_cpu_temp
            )

        self._cpu_temp_cache = temp
        self._cpu_temp_source = source
        self._thermal_zone_cache = thermal_zone
        self._cpu_temp_checked_at = time.time()
        return temp, source, thermal_zone
    
    async def start(self):
        """Start the monitoring loop."""
        if self.running:
            return
        
        self.running = True
        await self._refresh_alert_rules()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("System Monitor started")
    
    async def stop(self):
        """Stop the monitoring loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("System Monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                await self._collect_metrics()
                await self._check_alerts()
                await self._cleanup_old_alerts()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
            
            await asyncio.sleep(self._interval)
    
    async def _collect_metrics(self):
        """Collect system metrics."""
        try:
            # CPU
            def _cpu_and_io():
                cpu_pct = psutil.cpu_percent(interval=0.1)
                per_core = psutil.cpu_percent(percpu=True)
                freq = psutil.cpu_freq()
                d_usage = psutil.disk_usage('/')
                d_io = psutil.disk_io_counters()
                n_io = psutil.net_io_counters()
                return cpu_pct, per_core, freq, d_usage, d_io, n_io

            cpu_percent, cpu_per_core, cpu_freq, disk, disk_io, net_io = await asyncio.to_thread(_cpu_and_io)

            # Memory
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Temperatures (layered providers; cached to avoid slow subprocesses)
            cpu_temp, cpu_temp_source, thermal_zone = await self._read_cpu_temp()

            # GPU (NVML -> nvidia-smi -> WMI name/VRAM)
            gpu_metrics = await asyncio.to_thread(self._read_gpu)

            # Network and disk rates
            now = time.monotonic()
            dt = max(1e-6, now - self._last_check) if hasattr(self, "_last_check") and self._last_check else 1.0
            self._last_check = now

            if net_io and self._last_net_io:
                net_sent_mb_s = max(0.0, (net_io.bytes_sent - self._last_net_io.bytes_sent) / dt / (1024*1024))
                net_recv_mb_s = max(0.0, (net_io.bytes_recv - self._last_net_io.bytes_recv) / dt / (1024*1024))
            else:
                net_sent_mb_s = 0.0
                net_recv_mb_s = 0.0
            if net_io:
                self._last_net_io = net_io

            if disk_io and self._last_disk_io:
                disk_read_mb_s = max(0.0, (disk_io.read_bytes - self._last_disk_io.read_bytes) / dt / (1024*1024))
                disk_write_mb_s = max(0.0, (disk_io.write_bytes - self._last_disk_io.write_bytes) / dt / (1024*1024))
            else:
                disk_read_mb_s = 0.0
                disk_write_mb_s = 0.0
            if disk_io:
                self._last_disk_io = disk_io

            # Top processes & thread count
            def _scan_processes():
                procs = []
                threads = 0
                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                    try:
                        info = proc.info
                        if info['pid'] == 0 or (info.get('name') or '').lower() in {'system idle process', 'idle'}:
                            continue
                        try:
                            threads += proc.num_threads()
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            pass
                        if (info.get('cpu_percent') or 0.0) > 1.0 or (info.get('memory_percent') or 0.0) > 1.0:
                            procs.append(info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                procs.sort(key=lambda x: x.get('cpu_percent') or 0.0, reverse=True)
                return procs, threads

            processes, thread_count = await asyncio.to_thread(_scan_processes)
            
            # Create snapshot
            snapshot = SystemMetricsSnapshot(
                cpu_percent=cpu_percent,
                cpu_per_core=cpu_per_core,
                cpu_freq_current=cpu_freq.current if cpu_freq else None,
                cpu_freq_min=cpu_freq.min if cpu_freq else None,
                cpu_freq_max=cpu_freq.max if cpu_freq else None,
                memory_percent=mem.percent,
                memory_used_gb=mem.used / (1024**3),
                memory_total_gb=mem.total / (1024**3),
                memory_available_gb=mem.available / (1024**3),
                swap_percent=swap.percent,
                swap_used_gb=swap.used / (1024**3),
                swap_total_gb=swap.total / (1024**3),
                disk_percent=disk.percent,
                disk_used_gb=disk.used / (1024**3),
                disk_total_gb=disk.total / (1024**3),
                disk_free_gb=disk.free / (1024**3),
                disk_read_mb_s=disk_read_mb_s,
                disk_write_mb_s=disk_write_mb_s,
                network_sent_mb_s=net_sent_mb_s,
                network_recv_mb_s=net_recv_mb_s,
                network_sent_total_mb=(net_io.bytes_sent / (1024**2)) if net_io else 0.0,
                network_recv_total_mb=(net_io.bytes_recv / (1024**2)) if net_io else 0.0,
                boot_time=datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc),
                cpu_temp_c=cpu_temp,
                cpu_temp_source=cpu_temp_source,
                thermal_zone_c=thermal_zone,
                gpu_metrics=gpu_metrics,
                process_count=len(psutil.pids()),
                thread_count=thread_count,
                top_processes=processes[:10]
            )
            
            # Store in history
            self._history.append(snapshot)
            
            # Persist to database
            await self._persist_metrics(snapshot)
            
            # Emit event for real-time updates
            from app.core.events import event_bus, EventType, Event
            await event_bus.publish(Event(
                type=EventType.PC_METRICS_UPDATED,
                data={
                    "cpu_percent": cpu_percent,
                    "memory_percent": mem.percent,
                    "disk_percent": disk.percent,
                    "timestamp": datetime.utcnow().isoformat()
                },
                source="system_monitor"
            ))
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    async def _persist_metrics(self, snapshot: "SystemMetricsSnapshot"):
        """Persist metrics to database."""
        try:
            async for db in get_db():
                metrics = SystemMetrics(
                    cpu_percent=snapshot.cpu_percent,
                    cpu_per_core=snapshot.cpu_per_core,
                    cpu_freq_current=snapshot.cpu_freq_current,
                    cpu_freq_min=snapshot.cpu_freq_min,
                    cpu_freq_max=snapshot.cpu_freq_max,
                    memory_percent=snapshot.memory_percent,
                    memory_used_bytes=int(snapshot.memory_used_gb * 1024**3),
                    memory_total_bytes=int(snapshot.memory_total_gb * 1024**3),
                    memory_available_bytes=int(snapshot.memory_available_gb * 1024**3),
                    swap_percent=snapshot.swap_percent,
                    swap_used_bytes=int(snapshot.swap_used_gb * 1024**3),
                    swap_total_bytes=int(snapshot.swap_total_gb * 1024**3),
                    disk_percent=snapshot.disk_percent,
                    disk_used_bytes=int(snapshot.disk_used_gb * 1024**3),
                    disk_total_bytes=int(snapshot.disk_total_gb * 1024**3),
                    disk_free_bytes=int(snapshot.disk_free_gb * 1024**3),
                    disk_read_bytes_sec=int(snapshot.disk_read_mb_s * 1024**2),
                    disk_write_bytes_sec=int(snapshot.disk_write_mb_s * 1024**2),
                    network_sent_bytes_sec=int(snapshot.network_sent_mb_s * 1024**2),
                    network_recv_bytes_sec=int(snapshot.network_recv_mb_s * 1024**2),
                    network_sent_total=int(snapshot.network_sent_total_mb * 1024**2),
                    network_recv_total=int(snapshot.network_recv_total_mb * 1024**2),
                    gpu_percent=snapshot.gpu_metrics.gpu_percent if snapshot.gpu_metrics else None,
                    gpu_memory_percent=snapshot.gpu_metrics.gpu_memory_percent if snapshot.gpu_metrics else None,
                    gpu_memory_used_bytes=(snapshot.gpu_metrics.gpu_memory_used_mb * 1024**2) if snapshot.gpu_metrics and snapshot.gpu_metrics.gpu_memory_used_mb else None,
                    gpu_memory_total_bytes=(snapshot.gpu_metrics.gpu_memory_total_mb * 1024**2) if snapshot.gpu_metrics and snapshot.gpu_metrics.gpu_memory_total_mb else None,
                    gpu_temp_c=snapshot.gpu_metrics.gpu_temp_c if snapshot.gpu_metrics else None,
                    cpu_temp_c=snapshot.cpu_temp_c,
                    boot_time=snapshot.boot_time,
                    process_count=snapshot.process_count,
                    thread_count=snapshot.thread_count,
                )
                db.add(metrics)
                await db.commit()
        except Exception as e:
            logger.error(f"Error persisting metrics: {e}")
    
    async def _refresh_alert_rules(self):
        """Load active alert rules from database."""
        try:
            async for db in get_db():
                from sqlalchemy import select
                from app.models.system import AlertRule
                result = await db.execute(
                    select(AlertRule).where(AlertRule.is_active == True)
                )
                self._alert_rules_cache = result.scalars().all()
        except Exception as e:
            logger.error(f"Error refreshing alert rules: {e}")
    
    async def _check_alerts(self):
        """Check alert rules against current metrics."""
        if not self._history:
            return
        
        latest = self._history[-1]
        
        for rule in self._alert_rules_cache:
            try:
                value = self._get_metric_value(latest, rule.metric_type)
                if value is None:
                    continue
                
                triggered = self._check_condition(value, rule.condition, rule.threshold)
                
                if triggered:
                    await self._trigger_alert(rule, latest)
            except Exception as e:
                logger.error(f"Error checking alert rule {rule.name}: {e}")
    
    def _get_metric_value(self, snapshot, metric_type):
        """Extract metric value from snapshot."""
        mapping = {
            "cpu": snapshot.cpu_percent,
            "memory": snapshot.memory_percent,
            "disk": snapshot.disk_percent,
            "cpu_temp": snapshot.cpu_temp_c,
            "temperature": snapshot.cpu_temp_c,
            "network": snapshot.network_recv_mb_s + snapshot.network_sent_mb_s,
            "gpu": snapshot.gpu_metrics.gpu_percent if snapshot.gpu_metrics else None,
            "gpu_temp": snapshot.gpu_metrics.gpu_temp_c if snapshot.gpu_metrics else None,
            "gpu_memory": snapshot.gpu_metrics.gpu_memory_percent if snapshot.gpu_metrics else None,
        }
        return mapping.get(metric_type.value.lower())
    
    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        """Check if condition is met."""
        if condition == ">":
            return value > threshold
        elif condition == "<":
            return value < threshold
        elif condition == ">=":
            return value >= threshold
        elif condition == "<=":
            return value <= threshold
        elif condition == "==":
            return abs(value - threshold) < 0.001
        elif condition == "!=":
            return abs(value - threshold) >= 0.001
        return False
    
    async def _trigger_alert(self, rule, snapshot):
        """Trigger an alert."""
        value = self._get_metric_value(snapshot, rule.metric_type)
        if value is None:
            return
        threshold = rule.threshold

        # Check cooldown
        key = f"alert_{rule.id}"
        now = datetime.utcnow()
        if key in self._last_alert_times:
            if (now - self._last_alert_times[key]).total_seconds() < rule.cooldown_seconds:
                return
        
        self._last_alert_times[key] = now
        
        # Create alert
        async for db in get_db():
            from app.models.system import Alert, AlertSeverity
            alert = Alert(
                rule_id=rule.id,
                severity=rule.severity,
                message=f"{rule.name}: {rule.metric_type.value} {rule.condition} {threshold} (current: {value})",
                value=value,
                threshold=threshold,
                metric_type=rule.metric_type,
                alert_metadata={
                    "rule_name": rule.name,
                    "condition": rule.condition,
                    "threshold": threshold,
                    "duration_seconds": rule.duration_seconds,
                }
            )
            db.add(alert)
            await db.commit()
            
            # Emit event
            from app.core.events import event_bus, EventType, Event
            await event_bus.publish(Event(
                type=EventType.PC_ALERT_TRIGGERED,
                data={
                    "alert_id": str(alert.id),
                    "rule_name": rule.name,
                    "severity": rule.severity.value,
                    "message": alert.message,
                    "value": value,
                    "threshold": rule.threshold
                },
                source="system_monitor"
            ))
            
            # Send notifications
            await self._send_alert_notifications(rule, value)
    
    async def _send_alert_notifications(self, rule, value):
        """Send alert notifications via configured channels."""
        from app.services.notification_service import notification_service
        from app.models.notifications import NotificationPriority, NotificationChannel
        
        priority_map = {
            AlertSeverity.INFO: NotificationPriority.LOW,
            AlertSeverity.WARNING: NotificationPriority.NORMAL,
            AlertSeverity.CRITICAL: NotificationPriority.HIGH,
        }
        
        for channel in rule.notification_channels:
            await notification_service.send_notification(
                title=f"Alert: {rule.name}",
                message=f"Metric {rule.metric_type.value} {rule.condition} {rule.threshold} (current: {value:.2f})",
                priority=priority_map.get(rule.severity, NotificationPriority.NORMAL),
                category="alert",
                channels=[NotificationChannel(channel)] if isinstance(channel, str) else [NotificationChannel(c) for c in channel]
            )
    
    async def _cleanup_old_alerts(self):
        """Clean up old resolved alerts."""
        pass  # Implement retention policy
    
    def get_metrics(self) -> dict:
        """Get current metrics as a JSON-friendly dictionary."""
        if self._history:
            latest = self._history[-1]
            return latest.to_dict() if hasattr(latest, "to_dict") else latest
        return {}
    
    def get_history(self, duration_minutes: int = 60) -> List[dict]:
        """Get historical metrics."""
        if not self._history:
            return []
        # Snapshot timestamps are naive UTC, so compare against naive UTC rather
        # than epoch seconds (which would reinterpret them as local time).
        cutoff = datetime.utcnow() - timedelta(minutes=duration_minutes)
        return [
            m.to_dict() if hasattr(m, "to_dict") else m
            for m in self._history
            if hasattr(m, 'timestamp') and m.timestamp > cutoff
        ]
    
    def get_average_cpu(self, duration_minutes: int = 5) -> float:
        """Get average CPU usage over duration."""
        history = self.get_history(duration_minutes)
        if not history:
            return 0.0
        return sum(m.get("cpu_percent", 0) for m in history) / len(history)
    
    def get_alert_status(self) -> dict:
        """Get current alert status."""
        return {
            "active_rules": len(self._alert_rules_cache),
            "recent_alerts": len(self._last_alert_times),
            "rules": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "metric": r.metric_type.value,
                    "condition": r.condition,
                    "threshold": r.threshold,
                    "severity": r.severity.value
                }
                for r in self._alert_rules_cache
            ]
        }


# Global instance
system_monitor = SystemMonitor()