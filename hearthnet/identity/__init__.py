from __future__ import annotations

"""hearthnet.identity — M01 Identity module.

Provides Ed25519 key management, canonical JSON, signing/verification,
and node/community manifests.
"""

from hearthnet.identity.keys import (
    IdentityError,
    KeyPair,
    canonical_json,
    full_node_id,
    generate,
    load,
    load_or_generate,
    parse_node_id,
    save,
    short_node_id,
    sign_payload,
    verify_payload,
    verify_payload_with_node_id,
)
from hearthnet.identity.manifest import (
    CommunityManifest,
    ManifestError,
    NodeManifest,
    build_community_manifest,
    build_node_manifest,
    verify_community_manifest,
    verify_node_manifest,
)

__all__ = [
    # keys
    "KeyPair",
    "IdentityError",
    "generate",
    "load",
    "load_or_generate",
    "save",
    "canonical_json",
    "sign_payload",
    "verify_payload",
    "verify_payload_with_node_id",
    "short_node_id",
    "full_node_id",
    "parse_node_id",
    # manifest
    "ManifestError",
    "NodeManifest",
    "CommunityManifest",
    "build_node_manifest",
    "verify_node_manifest",
    "build_community_manifest",
    "verify_community_manifest",
]
