"""
Unit tests for Universal PTZ Controller, ONVIF PTZ SOAP Commands,
Preset Management, Home Position, and Vendor PTZ Adapters.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from integrations.onvif.client import (
    ONVIFClient, PTZCapabilities, PTZPreset, PTZDirection, PTZUnsupportedError
)
from engines.video_engine.ptz_controller import PTZController, ptz_controller
from integrations.hikvision.isapi_adapter import HikvisionISAPIAdapter
from integrations.dahua.cgi_adapter import DahuaCGIAdapter


SAMPLE_GET_CONFIGS_SOAP_XML = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
  <s:Body>
    <tptz:GetConfigurationsResponse>
      <tptz:PTZConfiguration token="PTZConfig_1">
        <tptz:Name>PTZ Configuration 1</tptz:Name>
        <tptz:NodeToken>PTZNode_1</tptz:NodeToken>
      </tptz:PTZConfiguration>
    </tptz:GetConfigurationsResponse>
  </s:Body>
</s:Envelope>"""

SAMPLE_GET_PRESETS_SOAP_XML = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"
            xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tptz:GetPresetsResponse>
      <tptz:Preset token="Preset_1">
        <tt:Name>Main Gate</tt:Name>
      </tptz:Preset>
      <tptz:Preset token="Preset_2">
        <tt:Name>Perimeter Fence</tt:Name>
      </tptz:Preset>
    </tptz:GetPresetsResponse>
  </s:Body>
</s:Envelope>"""

SAMPLE_SET_PRESET_SOAP_XML = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
  <s:Body>
    <tptz:SetPresetResponse>
      <tptz:PresetToken>Preset_3</tptz:PresetToken>
    </tptz:SetPresetResponse>
  </s:Body>
</s:Envelope>"""

SAMPLE_GET_DATETIME_SOAP_XML = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
            xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetSystemDateAndTimeResponse>
      <tds:SystemDateAndTime>
        <tt:DateTimeType>Manual</tt:DateTimeType>
        <tt:DaylightSavings>false</tt:DaylightSavings>
        <tt:TimeZone><tt:TZ>UTC</tt:TZ></tt:TimeZone>
        <tt:UTCDateTime>
          <tt:Time><tt:Hour>14</tt:Hour><tt:Minute>30</tt:Minute><tt:Second>45</tt:Second></tt:Time>
          <tt:Date><tt:Year>2026</tt:Year><tt:Month>11</tt:Month><tt:Day>25</tt:Day></tt:Date>
        </tt:UTCDateTime>
      </tds:SystemDateAndTime>
    </tds:GetSystemDateAndTimeResponse>
  </s:Body>
</s:Envelope>"""


class TestUniversalPTZController(unittest.TestCase):
    """Test suite for universal PTZ controls across ONVIF, vendor adapters, and controller."""

    def setUp(self):
        self.onvif_client = ONVIFClient(ip_address="192.168.1.100", port=80, username="admin", password="password123")
        self.onvif_client.capabilities.has_ptz = True
        self.onvif_client.capabilities.ptz_url = "http://192.168.1.100:80/onvif/ptz_service"

    def test_onvif_ptz_capability_detection(self):
        """Verifies parsing of PTZ capabilities and endpoints."""
        with patch.object(self.onvif_client, "_send_soap_request", return_value=SAMPLE_GET_CONFIGS_SOAP_XML):
            caps = self.onvif_client.ptz_get_capabilities()
            self.assertTrue(caps.has_ptz)
            self.assertTrue(caps.supports_continuous)
            self.assertTrue(caps.supports_relative)
            self.assertTrue(caps.supports_absolute)
            self.assertTrue(caps.supports_presets)
            self.assertTrue(caps.supports_home)

    def test_onvif_ptz_continuous_and_stop_move(self):
        """Verifies continuous movement SOAP request payload formatting and stop command."""
        with patch.object(self.onvif_client, "_send_soap_request", return_value="<ok/>") as mock_soap:
            self.onvif_client.ptz_continuous_move(profile_token="Profile_1", pan=0.5, tilt=-0.3, zoom=0.2)
            self.assertEqual(mock_soap.call_count, 1)
            call_body = mock_soap.call_args[1]["body_xml"]
            self.assertIn('x="0.50"', call_body)
            self.assertIn('y="-0.30"', call_body)
            self.assertIn('Zoom x="0.20"', call_body)

            self.onvif_client.ptz_stop(profile_token="Profile_1")
            self.assertEqual(mock_soap.call_count, 2)
            stop_body = mock_soap.call_args[1]["body_xml"]
            self.assertIn("<tptz:PanTilt>true</tptz:PanTilt>", stop_body)

    def test_onvif_ptz_relative_and_absolute_move(self):
        """Verifies relative and absolute PTZ translation commands."""
        with patch.object(self.onvif_client, "_send_soap_request", return_value="<ok/>") as mock_soap:
            self.onvif_client.ptz_relative_move(profile_token="Profile_1", pan=0.1, tilt=0.2, zoom=0.0, speed=0.8)
            call_body = mock_soap.call_args[1]["body_xml"]
            self.assertIn("<tptz:RelativeMove>", call_body)
            self.assertIn('x="0.10"', call_body)

            self.onvif_client.ptz_absolute_move(profile_token="Profile_1", pan=0.9, tilt=-0.8, zoom=0.5, speed=1.0)
            call_body_abs = mock_soap.call_args[1]["body_xml"]
            self.assertIn("<tptz:AbsoluteMove>", call_body_abs)
            self.assertIn('x="0.90"', call_body_abs)

    def test_onvif_preset_management(self):
        """Verifies preset query, creation, navigation, and deletion."""
        # 1. GetPresets
        with patch.object(self.onvif_client, "_send_soap_request", return_value=SAMPLE_GET_PRESETS_SOAP_XML):
            presets = self.onvif_client.ptz_get_presets("Profile_1")
            self.assertEqual(len(presets), 2)
            self.assertEqual(presets[0].token, "Preset_1")
            self.assertEqual(presets[0].name, "Main Gate")

        # 2. SetPreset
        with patch.object(self.onvif_client, "_send_soap_request", return_value=SAMPLE_SET_PRESET_SOAP_XML):
            assigned_token = self.onvif_client.ptz_set_preset("Profile_1", "Parking Lot")
            self.assertEqual(assigned_token, "Preset_3")

        # 3. GotoPreset
        with patch.object(self.onvif_client, "_send_soap_request", return_value="<ok/>") as mock_soap:
            self.onvif_client.ptz_goto_preset("Profile_1", "Preset_1", speed=0.75)
            self.assertIn("<tptz:PresetToken>Preset_1</tptz:PresetToken>", mock_soap.call_args[1]["body_xml"])

        # 4. RemovePreset
        with patch.object(self.onvif_client, "_send_soap_request", return_value="<ok/>") as mock_soap:
            success = self.onvif_client.ptz_remove_preset("Profile_1", "Preset_2")
            self.assertTrue(success)

    def test_onvif_home_position(self):
        """Verifies navigation and setting of home position."""
        with patch.object(self.onvif_client, "_send_soap_request", return_value="<ok/>") as mock_soap:
            self.onvif_client.ptz_goto_home_position("Profile_1", speed=1.0)
            self.assertIn("<tptz:GotoHomePosition>", mock_soap.call_args[1]["body_xml"])

            self.onvif_client.ptz_set_home_position("Profile_1")
            self.assertIn("<tptz:SetHomePosition>", mock_soap.call_args[1]["body_xml"])

    def test_unsupported_ptz_handling(self):
        """Verifies graceful handling when target camera does not support PTZ."""
        non_ptz_client = ONVIFClient(ip_address="192.168.1.101")
        non_ptz_client.capabilities.has_ptz = False

        caps = non_ptz_client.ptz_get_capabilities()
        self.assertFalse(caps.has_ptz)

        with self.assertRaises(PTZUnsupportedError):
            non_ptz_client.ptz_continuous_move("Profile_1", pan=1.0)

        with self.assertRaises(PTZUnsupportedError):
            non_ptz_client.ptz_goto_home_position("Profile_1")

        # Stop command on non-ptz camera should complete without raising
        non_ptz_client.ptz_stop("Profile_1")

    def test_onvif_time_synchronization(self):
        """Verifies querying and setting camera time via ONVIF."""
        with patch.object(self.onvif_client, "_send_soap_request", return_value=SAMPLE_GET_DATETIME_SOAP_XML):
            res = self.onvif_client.get_system_date_and_time()
            self.assertIn("2026-11-25", res["date_time_utc"])
            self.assertEqual(res["time_zone"], "UTC")

        with patch.object(self.onvif_client, "_send_soap_request", return_value="<ok/>") as mock_soap:
            dt = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
            success = self.onvif_client.set_system_date_and_time(dt, "UTC")
            self.assertTrue(success)
            self.assertIn("<tt:Hour>12</tt:Hour>", mock_soap.call_args[1]["body_xml"])

    def test_ptz_controller_universal_binding_and_directions(self):
        """Verifies PTZController directional controls, presets, and simulated movements."""
        controller = PTZController()

        # Simulated camera channel
        controller.register_camera("sim_cam_1", is_simulated=True)
        caps = controller.get_capabilities("sim_cam_1")
        self.assertTrue(caps.has_ptz)

        # Directional moves
        self.assertTrue(controller.move_direction("sim_cam_1", PTZDirection.UP, speed=0.5))
        self.assertTrue(controller.move_direction("sim_cam_1", PTZDirection.DOWN_RIGHT, speed=0.8))
        self.assertTrue(controller.move_direction("sim_cam_1", PTZDirection.ZOOM_IN, speed=0.6))
        self.assertTrue(controller.move_direction("sim_cam_1", PTZDirection.STOP))

        # Preset management
        token = controller.set_preset("sim_cam_1", "Office View")
        self.assertIsNotNone(token)
        presets = controller.get_presets("sim_cam_1")
        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0].name, "Office View")

        self.assertTrue(controller.goto_preset("sim_cam_1", token))
        self.assertTrue(controller.goto_home_position("sim_cam_1"))
        self.assertTrue(controller.remove_preset("sim_cam_1", token))
        self.assertEqual(len(controller.get_presets("sim_cam_1")), 0)

    def test_vendor_ptz_adapters(self):
        """Verifies vendor-specific PTZ control methods on Hikvision and Dahua adapters."""
        hik = HikvisionISAPIAdapter("192.168.1.50")
        self.assertTrue(hik.ptz_supported())
        with patch.object(hik, "_get", return_value="<ok/>"):
            with patch("httpx.Client.put") as mock_put:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_put.return_value = mock_resp
                self.assertTrue(hik.ptz_control(channel=1, command="RIGHT", speed=5))
                self.assertTrue(hik.ptz_control(channel=1, command="STOP"))

        dahua = DahuaCGIAdapter("192.168.1.60")
        self.assertTrue(dahua.ptz_supported())
        with patch.object(dahua, "_get", return_value="OK"):
            self.assertTrue(dahua.ptz_control(channel=1, command="UP", speed=4))
            self.assertTrue(dahua.ptz_control(channel=1, command="STOP"))


if __name__ == "__main__":
    unittest.main()
