"""
Unit tests for Credential Vault Encryption and Device Persistence.
"""

import pytest
from core.security.crypto import CredentialVault, credential_vault
from database.database_manager import DatabaseManager
from database.models.devices import Device, DeviceCredential, DeviceDiscoveryRecord, NVRChannelMapping


def test_credential_vault_encryption_decryption():
    vault = CredentialVault(master_secret="test-unit-secret-2026")
    raw_pwd = "CameraAdmin@Secure99!"

    encrypted = vault.encrypt_password(raw_pwd)
    assert encrypted != raw_pwd
    assert len(encrypted) > 20

    decrypted = vault.decrypt_password(encrypted)
    assert decrypted == raw_pwd


def test_credential_vault_tamper_detection():
    vault = CredentialVault(master_secret="test-unit-secret-2026")
    encrypted = vault.encrypt_password("Secret123")
    
    # Tamper with base64 ciphertext token
    tampered = encrypted[:-4] + "AAAA"
    with pytest.raises(ValueError, match="Decryption failed"):
        vault.decrypt_password(tampered)


def test_device_credentials_db_persistence(test_db_manager: DatabaseManager):
    with test_db_manager.get_session() as session:
        dev = Device(
            name="Front Gate Cam",
            ip_address="192.168.1.105",
            port=80,
            rtsp_port=554,
            is_online=True,
        )
        session.add(dev)
        session.flush()

        raw_pwd = "MySecretCameraPassword"
        encrypted_token = credential_vault.encrypt_password(raw_pwd)

        cred = DeviceCredential(
            device_id=dev.id,
            username="security_admin",
            encrypted_password=encrypted_token,
            auth_type="DIGEST",
        )
        session.add(cred)
        session.flush()

        # Retrieve and verify decryption
        saved_cred = session.query(DeviceCredential).filter_by(device_id=dev.id).first()
        assert saved_cred is not None
        assert saved_cred.encrypted_password != raw_pwd
        assert credential_vault.decrypt_password(saved_cred.encrypted_password) == raw_pwd


def test_discovery_record_persistence(test_db_manager: DatabaseManager):
    with test_db_manager.get_session() as session:
        disc = DeviceDiscoveryRecord(
            ip_address="192.168.1.188",
            mac_address="44:19:B6:99:88:77",
            manufacturer="Hikvision",
            model="DS-2CD2043G2",
            onvif_port=80,
            rtsp_port=554,
            discovery_method="WS_DISCOVERY",
            is_added=False,
        )
        session.add(disc)
        session.flush()

        record = session.query(DeviceDiscoveryRecord).filter_by(ip_address="192.168.1.188").first()
        assert record is not None
        assert record.manufacturer == "Hikvision"
        assert record.mac_address == "44:19:B6:99:88:77"
