def __getattr__(name):
    if name == "GrowthEngine":
        from growth.growth_engine import GrowthEngine
        return GrowthEngine
    elif name == "SelfHealer":
        from growth.self_healer import SelfHealer
        return SelfHealer
    elif name == "NetworkGuard":
        from growth.network_guard import NetworkGuard
        return NetworkGuard
    elif name in ("DesktopNotifier", "notifier"):
        from growth.notifier import DesktopNotifier, notifier
        return notifier if name == "notifier" else DesktopNotifier
    raise AttributeError(f"module 'growth' has no attribute '{name}'")

__all__ = ["GrowthEngine", "SelfHealer", "NetworkGuard", "DesktopNotifier", "notifier"]

