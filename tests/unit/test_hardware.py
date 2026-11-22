"""
Unit tests for Hardware Detection Engine.
"""

from core.hardware.detector import HardwareDetector, SystemHardwareReport


def test_detect_cpu():
    cpu = HardwareDetector.detect_cpu()
    assert cpu.logical_cores >= 1
    assert cpu.physical_cores >= 1
    assert isinstance(cpu.model, str)
    assert cpu.current_usage_percent >= 0.0


def test_detect_ram():
    ram = HardwareDetector.detect_ram()
    assert ram.total_gb > 0.0
    assert ram.available_gb >= 0.0
    assert 0.0 <= ram.usage_percent <= 100.0


def test_detect_storage():
    storage = HardwareDetector.detect_storage(".")
    assert storage.total_gb > 0.0
    assert storage.free_gb >= 0.0
    assert 0.0 <= storage.usage_percent <= 100.0


def test_detect_openvino():
    ov = HardwareDetector.detect_openvino()
    # OpenVINO is installed in this environment
    assert ov.available is True
    assert len(ov.available_devices) > 0
    assert "CPU" in ov.available_devices or "GPU" in ov.available_devices


def test_generate_full_report():
    report = HardwareDetector.generate_full_report()
    assert isinstance(report, SystemHardwareReport)
    assert report.cpu.logical_cores >= 1
    assert report.ram.total_gb > 0.0
    assert report.hardware_acceleration_tier in ["INTEL_GPU_OPENVINO", "INTEL_CPU_OPENVINO", "GENERIC_CPU"]
    assert report.max_recommended_ai_channels >= 2
    
    report_dict = report.to_dict()
    assert "cpu" in report_dict
    assert "openvino" in report_dict
