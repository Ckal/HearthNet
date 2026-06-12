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
    CommunityMember,
    CommunityPolicy,
    ManifestError,
    NodeManifest,
    RevokedEntry,
    build_community_manifest,
    build_node_manifest,
    verify_community_manifest,
    verify_node_manifest,
)

__all__ = [
    "CommunityManifest",
    "CommunityMember",
    "CommunityPolicy",
    "IdentityError",
    # keys
    "KeyPair",
    # manifest
    "ManifestError",
    "NodeManifest",
    "RevokedEntry",
    "build_community_manifest",
    "build_node_manifest",
    "canonical_json",
    "full_node_id",
    "generate",
    "load",
    "load_or_generate",
    "parse_node_id",
    "save",
    "short_node_id",
    "sign_payload",
    "verify_community_manifest",
    "verify_node_manifest",
    "verify_payload",
    "verify_payload_with_node_id",
]
