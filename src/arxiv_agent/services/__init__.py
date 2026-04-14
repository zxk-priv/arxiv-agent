"""业务编排层。

这一层连接配置、外部客户端和本地缓存，是项目的“主流程”所在位置。
UI 和 CLI 都应该优先调用这里提供的服务，而不是直接拼装底层模块。
"""

from .digest_service import DigestService, digest_needs_abstract_refresh

__all__ = ["DigestService", "digest_needs_abstract_refresh"]
