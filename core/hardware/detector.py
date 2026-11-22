"""
Hardware and AI Acceleration Detection Engine.
Detects Intel CPU, RAM, Intel UHD/Iris/Arc GPU, disk storage,
and OpenVINO/ONNX Runtime acceleration status on Windows 11.
"""

import os
import shutil
import platform
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import psutil

from core.logging.logger import get_logger

logger = get_logger("hardware_detector")


@dataclass
class CPUInfo:
    model: str = "Unknown"
    physical_cores: int = 1
    logical_cores: int = 1
    current_usage_percent: float = 0.0
    frequency_mhz: float = 0.0
    is_intel: bool = False


@dataclass
class RAMInfo:
    total_gb: float = 0.0
    available_gb: float = 0.0
    used_gb: float = 0.0
    usage_percent: float = 0.0


@dataclass
class GPUInfo:
    name: str = "Unknown"
    vendor: str = "Unknown"
    is_intel: bool = False
    openvino_supported: bool = False
    device_id: str = "GPU"


@dataclass
class StorageInfo:
    drive_path: str = "C:\\"
    total_gb: float = 0.0
    free_gb: float = 0.0
    used_gb: float = 0.0
    usage_percent: float = 0.0
    is_sufficient: bool = True


@dataclass
class OpenVINOInfo:
    available: bool = False
    version: str = "Not Installed"
    available_devices: List[str] = field(default_factory=list)
    recommended_device: str = "CPU"
    has_intel_gpu_acceleration: bool = False


@dataclass
class SystemHardwareReport:
    os_name: str = ""
    os_version: str = ""
    cpu: CPUInfo = field(default_factory=CPUInfo)
    ram: RAMInfo = field(default_factory=RAMInfo)
    gpus: List[GPUInfo] = field(default_factory=list)
    storage: StorageInfo = field(default_factory=StorageInfo)
    openvino: OpenVINOInfo = field(default_factory=OpenVINOInfo)
    hardware_acceleration_tier: str = "STANDARD_CPU"
    max_recommended_ai_channels: int = 4

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HardwareDetector:
    """Probes host hardware and AI acceleration capabilities."""

    @staticmethod
    def detect_cpu() -> CPUInfo:
        cpu = CPUInfo()
        try:
            cpu.model = platform.processor() or "Generic x86_64"
            # On Windows, platform.processor() might be an architecture string. Try environment or registry if needed.
            brand = os.environ.get("PROCESSOR_IDENTIFIER", "")
            if "Intel" in cpu.model or "Intel" in brand:
                cpu.is_intel = True
            
            # Use psutil for core metrics
            cpu.physical_cores = psutil.cpu_count(logical=False) or 1
            cpu.logical_cores = psutil.cpu_count(logical=True) or 1
            cpu.current_usage_percent = psutil.cpu_percent(interval=None)
            
            freq = psutil.cpu_freq()
            if freq:
                cpu.frequency_mhz = round(freq.current, 1)
        except Exception as e:
            logger.warning("Error detecting CPU metrics: %s", e)
        return cpu

    @staticmethod
    def detect_ram() -> RAMInfo:
        ram = RAMInfo()
        try:
            vm = psutil.virtual_memory()
            ram.total_gb = round(vm.total / (1024 ** 3), 2)
            ram.available_gb = round(vm.available / (1024 ** 3), 2)
            ram.used_gb = round((vm.total - vm.available) / (1024 ** 3), 2)
            ram.usage_percent = round(vm.percent, 1)
        except Exception as e:
            logger.warning("Error detecting RAM metrics: %s", e)
        return ram

    @staticmethod
    def detect_storage(path: str = ".") -> StorageInfo:
        storage = StorageInfo()
        try:
            storage.drive_path = os.path.abspath(path)
            usage = shutil.disk_usage(path)
            storage.total_gb = round(usage.total / (1024 ** 3), 2)
            storage.free_gb = round(usage.free / (1024 ** 3), 2)
            storage.used_gb = round(usage.used / (1024 ** 3), 2)
            storage.usage_percent = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0.0
            storage.is_sufficient = storage.free_gb >= 10.0
        except Exception as e:
            logger.warning("Error detecting storage metrics: %s", e)
        return storage

    @staticmethod
    def detect_openvino() -> OpenVINOInfo:
        ov = OpenVINOInfo()
        try:
            import openvino as ov_module
            ov.available = True
            ov.version = getattr(ov_module, "__version__", "Available")
            
            from openvino import Core
            core = Core()
            devices = core.available_devices
            ov.available_devices = list(devices)
            
            if "GPU" in devices:
                ov.recommended_device = "GPU"
                ov.has_intel_gpu_acceleration = True
            elif "CPU" in devices:
                ov.recommended_device = "CPU"
            else:
                ov.recommended_device = "AUTO"
        except ImportError:
            ov.available = False
            ov.version = "Not Installed"
            logger.info("OpenVINO is not installed; falling back to CPU runtime.")
        except Exception as e:
            ov.available = False
            logger.warning("Error initializing OpenVINO Core: %s", e)
        return ov

    @staticmethod
    def detect_gpus(openvino_info: OpenVINOInfo) -> List[GPUInfo]:
        gpus: List[GPUInfo] = []
        try:
            if openvino_info.available:
                from openvino import Core
                core = Core()
                for dev in openvino_info.available_devices:
                    if "GPU" in dev:
                        gpu = GPUInfo()
                        gpu.device_id = dev
                        try:
                            # Query full device name from OpenVINO runtime
                            full_name = core.get_property(dev, "FULL_DEVICE_NAME")
                            gpu.name = str(full_name)
                        except Exception:
                            gpu.name = f"OpenVINO {dev}"
                        
                        if "Intel" in gpu.name:
                            gpu.vendor = "Intel"
                            gpu.is_intel = True
                        gpu.openvino_supported = True
                        gpus.append(gpu)
        except Exception as e:
            logger.warning("Error querying OpenVINO GPU properties: %s", e)
            
        if not gpus and openvino_info.has_intel_gpu_acceleration:
            gpus.append(GPUInfo(
                name="Intel Integrated Graphics (OpenVINO Accelerated)",
                vendor="Intel",
                is_intel=True,
                openvino_supported=True,
                device_id="GPU"
            ))
        return gpus

    @classmethod
    def generate_full_report(cls, storage_path: str = ".") -> SystemHardwareReport:
        """Runs full hardware probing and builds the system capability report."""
        report = SystemHardwareReport()
        report.os_name = platform.system()
        report.os_version = platform.version()
        
        report.cpu = cls.detect_cpu()
        report.ram = cls.detect_ram()
        report.storage = cls.detect_storage(storage_path)
        report.openvino = cls.detect_openvino()
        report.gpus = cls.detect_gpus(report.openvino)
        
        # Capability assessment
        if report.openvino.has_intel_gpu_acceleration:
            report.hardware_acceleration_tier = "INTEL_GPU_OPENVINO"
            # i5-12400 + UHD 730 can easily handle 16-32 channels with substream AI
            report.max_recommended_ai_channels = min(32, report.cpu.logical_cores * 3)
        elif report.cpu.is_intel:
            report.hardware_acceleration_tier = "INTEL_CPU_OPENVINO"
            report.max_recommended_ai_channels = min(16, report.cpu.logical_cores)
        else:
            report.hardware_acceleration_tier = "GENERIC_CPU"
            report.max_recommended_ai_channels = max(2, report.cpu.logical_cores // 2)
            
        logger.info(
            "Hardware Detection: Tier=%s, CPU=%s (%d cores), RAM=%.1fGB, OpenVINO=%s, Devices=%s",
            report.hardware_acceleration_tier,
            report.cpu.model,
            report.cpu.logical_cores,
            report.ram.total_gb,
            report.openvino.available,
            report.openvino.available_devices,
        )
        return report
