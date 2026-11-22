"""
Unit tests for ONVIF Protocol, SOAP Response Parsing, and WS-Discovery.
"""

from integrations.onvif.client import ONVIFClient, ONVIFProfile, ONVIFCapabilities, ONVIFDeviceInformation
from integrations.onvif.discovery import CameraDiscoveryEngine, DiscoveredCamera

SAMPLE_WS_DISCOVERY_XML = """<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
          xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
          xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <wsa:EndpointReference>
          <wsa:Address>urn:uuid:12345678-abcd-ef01-2345-6789abcdef01</wsa:Address>
        </wsa:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>
          onvif://www.onvif.org/type/video_encoder
          onvif://www.onvif.org/name/Hikvision
          onvif://www.onvif.org/hardware/DS-2CD2043G2-I
          onvif://www.onvif.org/location/MainGate
        </d:Scopes>
        <d:XAddrs>http://192.168.1.120:80/onvif/device_service</d:XAddrs>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </Body>
</Envelope>"""

SAMPLE_DEV_INFO_SOAP_XML = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <s:Body>
    <tds:GetDeviceInformationResponse>
      <tds:Manufacturer>Hikvision</tds:Manufacturer>
      <tds:Model>DS-2CD2143G0-IS</tds:Model>
      <tds:FirmwareVersion>V5.6.5 build 200316</tds:FirmwareVersion>
      <tds:SerialNumber>DS-2CD2143G0-IS20200316AAWR123456789</tds:SerialNumber>
      <tds:HardwareId>88</tds:HardwareId>
    </tds:GetDeviceInformationResponse>
  </s:Body>
</s:Envelope>"""

SAMPLE_GET_PROFILES_SOAP_XML = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
            xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetProfilesResponse>
      <trt:Profiles token="Profile_1" fixed="true">
        <tt:Name>MainStream</tt:Name>
        <tt:VideoEncoderConfiguration token="VEC_001">
          <tt:Encoding>H264</tt:Encoding>
          <tt:Resolution>
            <tt:Width>1920</tt:Width>
            <tt:Height>1080</tt:Height>
          </tt:Resolution>
        </tt:VideoEncoderConfiguration>
      </trt:Profiles>
      <trt:Profiles token="Profile_2" fixed="true">
        <tt:Name>SubStream</tt:Name>
        <tt:VideoEncoderConfiguration token="VEC_002">
          <tt:Encoding>H264</tt:Encoding>
          <tt:Resolution>
            <tt:Width>640</tt:Width>
            <tt:Height>360</tt:Height>
          </tt:Resolution>
        </tt:VideoEncoderConfiguration>
      </trt:Profiles>
    </trt:GetProfilesResponse>
  </s:Body>
</s:Envelope>"""


def test_ws_discovery_xml_parsing():
    camera = CameraDiscoveryEngine.parse_ws_discovery_response(SAMPLE_WS_DISCOVERY_XML)
    assert camera is not None
    assert camera.ip_address == "192.168.1.120"
    assert camera.onvif_port == 80
    assert camera.manufacturer == "Hikvision"
    assert camera.model == "DS-2CD2043G2-I"
    assert camera.discovery_method == "WS_DISCOVERY"


def test_fingerprint_manufacturer():
    # Test Scopes
    assert CameraDiscoveryEngine.fingerprint_manufacturer(["onvif://www.onvif.org/name/Hikvision"], "") == "Hikvision"
    assert CameraDiscoveryEngine.fingerprint_manufacturer(["onvif://www.onvif.org/name/Dahua_IP_Camera"], "") == "Dahua"
    assert CameraDiscoveryEngine.fingerprint_manufacturer(["onvif://www.onvif.org/name/CP_PLUS_NVR"], "") == "CP PLUS"
    
    # Test MAC prefix
    assert CameraDiscoveryEngine.fingerprint_manufacturer([], "", mac="44:19:B6:11:22:33") == "Hikvision"
    assert CameraDiscoveryEngine.fingerprint_manufacturer([], "", mac="3C:EF:8C:AA:BB:CC") == "Dahua"


def test_onvif_ws_security_header_generation():
    client = ONVIFClient(ip_address="192.168.1.50", username="admin", password="SecretPassword123")
    header = client._build_ws_security_header()
    assert "<wsse:Username>admin</wsse:Username>" in header
    assert "PasswordDigest" in header
    assert "SecretPassword123" not in header  # Cleartext password is never in the header!


def test_onvif_soap_device_info_parsing():
    root = ONVIFClient._strip_namespaces(SAMPLE_DEV_INFO_SOAP_XML)
    mf = root.findtext(".//Manufacturer")
    md = root.findtext(".//Model")
    sn = root.findtext(".//SerialNumber")
    fw = root.findtext(".//FirmwareVersion")

    assert mf == "Hikvision"
    assert md == "DS-2CD2143G0-IS"
    assert fw.startswith("V5.6.5")
    assert "AAWR123456789" in sn


def test_onvif_soap_profiles_parsing():
    root = ONVIFClient._strip_namespaces(SAMPLE_GET_PROFILES_SOAP_XML)
    profiles = []
    for prof in root.findall(".//Profiles"):
        token = prof.attrib.get("token")
        name = prof.findtext("Name")
        w = int(prof.findtext(".//Resolution/Width"))
        h = int(prof.findtext(".//Resolution/Height"))
        profiles.append(ONVIFProfile(token=token, name=name, width=w, height=h))

    assert len(profiles) == 2
    assert profiles[0].token == "Profile_1"
    assert profiles[0].width == 1920
    assert profiles[0].height == 1080
    assert profiles[1].token == "Profile_2"
    assert profiles[1].width == 640
    assert profiles[1].height == 360
