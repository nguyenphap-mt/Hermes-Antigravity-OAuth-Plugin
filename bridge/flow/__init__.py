"""Google Flow integration module for Hermes Agent.

Provides Camofox autonomous browser bridge to interact with Google Flow
(labs.google/fx/tools/flow) for high-quality video and image generation.
"""

try:
    from tools.antigravity_bridge.flow.automation import GoogleFlowClient, FlowResult
    from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
    from tools.antigravity_bridge.flow import generators
except ImportError:
    try:
        from bridge.flow.automation import GoogleFlowClient, FlowResult
        from bridge.flow.camofox_bridge import CamofoxFlowBridge
        from bridge.flow import generators
    except ImportError:
        try:
            from flow.automation import GoogleFlowClient, FlowResult
            from flow.camofox_bridge import CamofoxFlowBridge
            import generators
        except ImportError:
            from .automation import GoogleFlowClient, FlowResult
            from .camofox_bridge import CamofoxFlowBridge
            from . import generators

try:
    from bridge.flow.flow_auth_service import FlowAuthService
    from bridge.flow.flow_refresh_daemon import FlowRefreshDaemon, ensure_flow_token
except ImportError:
    try:
        from tools.antigravity_bridge.flow.flow_auth_service import FlowAuthService
        from tools.antigravity_bridge.flow.flow_refresh_daemon import FlowRefreshDaemon, ensure_flow_token
    except ImportError:
        pass

__all__ = [
    "GoogleFlowClient",
    "FlowResult",
    "CamofoxFlowBridge",
    "generators",
    "FlowAuthService",
    "FlowRefreshDaemon",
    "ensure_flow_token",
]
