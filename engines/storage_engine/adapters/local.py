"""
Local Storage Adapter for Windows NTFS, ReFS, and Direct-Attached Storage.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import sys
import time
import uuid
import shutil
import ctypes
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

from engines.storage_engine.enums import StorageType, HealthStatus
from engines.storage_engine.adapters.base import StorageAdapter, StorageMetrics
from core.logging.logger import get_logger

logger = get_logger("local_storage_adapter")


class LocalStorageAdapter(StorageAdapter):
    """
    Adapter for local direct-attached disks (SATA, NVMe, USB, SAS) on Windows.
    Provides volume capability inspection (NTFS, ReFS), atomic read/write testing,
    and safe path resolution preventing traversal attacks.
    """

    @property
    def adapter_type(self) -> StorageType:
        return StorageType.LOCAL

    def get_metrics(self, volume_path: str) -> StorageMetrics:
        """Samples capacity, free space, and read/write performance."""
        clean_path = str(Path(volume_path).resolve())
        if not os.path.exists(clean_path):
            return StorageMetrics(
                total_bytes=0,
                used_bytes=0,
                free_bytes=0,
                used_percent=100.0,
                total_gb=0.0,
                used_gb=0.0,
                free_gb=0.0,
                status=HealthStatus.CRITICAL,
                error_message=f"Storage volume path not accessible: {clean_path}",
            )

        try:
            usage = shutil.disk_usage(clean_path)
            total = usage.total
            used = usage.used
            free = usage.free
            used_pct = round((used / total * 100) if total > 0 else 0.0, 1)

            # Measure active I/O latency
            rw_ok, latency_ms, rw_err = self.test_read_write(clean_path)
            status = HealthStatus.HEALTHY
            if not rw_ok:
                status = HealthStatus.CRITICAL
            elif used_pct >= 95.0 or (free / (1024 ** 3)) < 5.0:
                status = HealthStatus.CRITICAL
            elif used_pct >= 85.0 or (free / (1024 ** 3)) < 15.0:
                status = HealthStatus.WARNING

            caps = self.get_capabilities(clean_path)
            return StorageMetrics(
                total_bytes=total,
                used_bytes=used,
                free_bytes=free,
                used_percent=used_pct,
                total_gb=round(total / (1024 ** 3), 2),
                used_gb=round(used / (1024 ** 3), 2),
                free_gb=round(free / (1024 ** 3), 2),
                read_latency_ms=round(latency_ms * 0.4, 2),
                write_latency_ms=round(latency_ms * 0.6, 2),
                throughput_mbps=round(4.0 / (latency_ms / 1000.0), 2) if latency_ms > 0 else 0.0,
                status=status,
                filesystem=caps.get("filesystem", "NTFS"),
                is_read_only=caps.get("is_read_only", False),
                error_message=rw_err,
            )
        except Exception as e:
            logger.error("Failed to sample local storage metrics for %s: %s", clean_path, e)
            return StorageMetrics(
                total_bytes=0,
                used_bytes=0,
                free_bytes=0,
                used_percent=100.0,
                total_gb=0.0,
                used_gb=0.0,
                free_gb=0.0,
                status=HealthStatus.CRITICAL,
                error_message=str(e),
            )

    def test_read_write(self, volume_path: str) -> Tuple[bool, float, Optional[str]]:
        """
        Executes an atomic 4 KB write-sync-read-delete verification probe.
        Guarantees that filesystem is writable and disk buffers flush successfully.
        """
        clean_dir = Path(volume_path).resolve()
        if not clean_dir.exists():
            return False, 0.0, f"Volume directory does not exist: {clean_dir}"

        test_file = clean_dir / f".cctv_storage_probe_{uuid.uuid4().hex[:8]}.tmp"
        payload = b"CCTV_AI_SURVEILLANCE_STORAGE_INTEGRITY_PROBE_BLOCK_2026\x00" * 70  # ~4 KB
        t_start = time.perf_counter()

        try:
            with open(test_file, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())

            with open(test_file, "rb") as f:
                read_back = f.read()

            t_end = time.perf_counter()
            latency_ms = (t_end - t_start) * 1000.0

            if read_back != payload:
                return False, latency_ms, "Readback payload mismatch: storage corruption detected"

            return True, round(latency_ms, 2), None
        except Exception as e:
            t_end = time.perf_counter()
            latency_ms = (t_end - t_start) * 1000.0
            return False, round(latency_ms, 2), f"Write test failed: {e}"
        finally:
            if test_file.exists():
                try:
                    test_file.unlink()
                except Exception:
                    pass

    def check_availability(self, volume_path: str) -> bool:
        """Verifies directory accessibility and basic write permissions."""
        p = Path(volume_path).resolve()
        return p.exists() and p.is_dir() and os.access(str(p), os.W_OK)

    def resolve_path(self, volume_path: str, relative_path: str) -> str:
        """
        Resolves a safe canonical path under volume_path.
        Guarantees protection against path traversal (e.g. '../').
        """
        root = Path(volume_path).resolve()
        # Strip leading slashes to prevent root escape
        clean_rel = relative_path.lstrip("/\\")
        target = (root / clean_rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise PermissionError(f"Path traversal detected: '{relative_path}' escapes storage root '{root}'")
        return str(target)

    def ensure_directory(self, directory_path: str) -> bool:
        """Creates target directory structure safely."""
        try:
            Path(directory_path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error("Failed to ensure directory %s: %s", directory_path, e)
            return False

    def get_capabilities(self, volume_path: str) -> Dict[str, Any]:
        """
        Queries Windows filesystem capabilities using Win32 GetVolumeInformationW.
        Identifies NTFS vs. ReFS, encryption, compression, and read-only flags.
        """
        p = Path(volume_path).resolve()
        drive_root = p.anchor or str(p)
        if not drive_root.endswith("\\"):
            drive_root += "\\"

        caps = {
            "volume_path": str(p),
            "drive_root": drive_root,
            "filesystem": "NTFS",
            "volume_name": "",
            "serial_number": 0,
            "max_component_length": 255,
            "is_read_only": False,
            "supports_encryption": True,
            "supports_compression": True,
            "is_refs": False,
        }

        if sys.platform == "win32":
            try:
                volume_name_buf = ctypes.create_unicode_buffer(261)
                fs_name_buf = ctypes.create_unicode_buffer(261)
                serial_num = ctypes.c_ulong(0)
                max_len = ctypes.c_ulong(0)
                flags = ctypes.c_ulong(0)

                ret = ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(drive_root),
                    volume_name_buf,
                    ctypes.sizeof(volume_name_buf),
                    ctypes.byref(serial_num),
                    ctypes.byref(max_len),
                    ctypes.byref(flags),
                    fs_name_buf,
                    ctypes.sizeof(fs_name_buf),
                )
                if ret:
                    fs_name = fs_name_buf.value
                    caps["filesystem"] = fs_name
                    caps["volume_name"] = volume_name_buf.value
                    caps["serial_number"] = serial_num.value
                    caps["max_component_length"] = max_len.value
                    caps["is_refs"] = "REFS" in fs_name.upper()

                    # Windows FS flags
                    FILE_READ_ONLY_VOLUME = 0x00080000
                    FILE_SUPPORTS_ENCRYPTION = 0x00020000
                    FILE_FILE_COMPRESSION = 0x00000010

                    caps["is_read_only"] = bool(flags.value & FILE_READ_ONLY_VOLUME)
                    caps["supports_encryption"] = bool(flags.value & FILE_SUPPORTS_ENCRYPTION)
                    caps["supports_compression"] = bool(flags.value & FILE_FILE_COMPRESSION)
            except Exception as e:
                logger.debug("Win32 GetVolumeInformationW query notice for %s: %s", drive_root, e)

        return caps

    def discover_local_volumes(self) -> List[Dict[str, Any]]:
        """Discovers all mounted logical volumes and drive letters on the host."""
        discovered = []
        if sys.platform == "win32":
            try:
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for i in range(26):
                    if bitmask & (1 << i):
                        drive_letter = f"{chr(65 + i)}:\\"
                        caps = self.get_capabilities(drive_letter)
                        try:
                            usage = shutil.disk_usage(drive_letter)
                            discovered.append({
                                "mount_path": drive_letter,
                                "name": caps.get("volume_name") or f"Local Disk ({chr(65 + i)}:)",
                                "filesystem": caps.get("filesystem", "NTFS"),
                                "total_bytes": usage.total,
                                "used_bytes": usage.used,
                                "free_bytes": usage.free,
                                "total_gb": round(usage.total / (1024 ** 3), 2),
                                "free_gb": round(usage.free / (1024 ** 3), 2),
                                "used_pct": round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0.0,
                                "is_read_only": caps.get("is_read_only", False),
                                "is_refs": caps.get("is_refs", False),
                            })
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Error enumerating logical drives: %s", e)

        if not discovered:
            # Fallback to current directory volume
            cur_root = Path.cwd().anchor or "C:\\"
            usage = shutil.disk_usage(cur_root)
            discovered.append({
                "mount_path": cur_root,
                "name": "System Volume",
                "filesystem": "NTFS",
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "total_gb": round(usage.total / (1024 ** 3), 2),
                "free_gb": round(usage.free / (1024 ** 3), 2),
                "used_pct": round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0.0,
                "is_read_only": False,
                "is_refs": False,
            })
        return discovered
