"""
Video Gateway Package for Real-Time CCTV Streaming.
Exports the central FrameDistributionHub singleton.
"""

from web.gateway.hub import FrameDistributionHub, ClientSubscription, frame_distribution_hub

__all__ = ["FrameDistributionHub", "ClientSubscription", "frame_distribution_hub"]
