"""Trust corporate TLS-inspecting proxy CAs for outbound HTTPS.

On corporate-managed devices, HTTPS traffic to public internet endpoints is
often intercepted by a TLS-inspecting proxy (e.g. Zscaler). The OS is told to
trust that proxy's root CA (via MDM), but Python's `certifi` package — which
most HTTP clients (boto3, opensearch-py, requests, ...) use to verify
certificates — ships its own separate, hardcoded CA bundle that doesn't
include it. This causes `CERTIFICATE_VERIFY_FAILED` errors for any HTTPS
call that the proxy intercepts.

This module fixes that by appending the relevant corporate root CA(s) to
`certifi`'s bundle, so those specific connections validate correctly.

Deliberately does NOT use `truststore` (which repoints Python's ssl module
at the OS-native trust store wholesale): on macOS that also routes
certificate validation for connections that never touch the corporate proxy
(e.g. Neptune reached via an SSH tunnel) through Apple's `SecTrustEvaluate`,
which is stricter than OpenSSL about some legitimately-issued AWS certs and
broke that previously-working path. Only supplementing certifi's bundle
keeps validation on the same (OpenSSL) code path for everything, and just
adds the one CA that's actually missing.

No-op (and never raises) on non-macOS platforms, if certifi isn't
installed, or if the corporate CA isn't found in the system keychain.
"""

from __future__ import annotations

import logging
import platform
import subprocess

logger = logging.getLogger(__name__)

# Common names of known corporate TLS-inspecting proxy root CAs to look for
# in the macOS System keychain. Add to this list if your organisation uses
# a different proxy.
_KNOWN_PROXY_CA_NAMES = [
    "Zscaler Root CA",
]

_SYSTEM_KEYCHAIN = "/Library/Keychains/System.keychain"


def trust_corporate_proxy_ca() -> None:
    """Append any known corporate proxy root CAs to certifi's bundle.

    Safe to call multiple times (e.g. on every process start) — checks
    whether each CA is already present before appending, and never raises.
    """
    if platform.system() != "Darwin":
        return

    try:
        import certifi
    except ImportError:
        return

    try:
        bundle_path = certifi.where()
        with open(bundle_path, encoding="utf-8") as f:
            bundle_contents = f.read()
    except OSError as e:
        logger.debug("Could not read certifi bundle: %s", e)
        return

    for ca_name in _KNOWN_PROXY_CA_NAMES:
        if ca_name in bundle_contents:
            continue  # already appended in a previous run

        pem = _export_cert_from_keychain(ca_name)
        if pem is None:
            continue

        try:
            with open(bundle_path, "a", encoding="utf-8") as f:
                f.write(f"\n# Added by dia._tls: corporate TLS-inspecting proxy CA\n# {ca_name}\n{pem}\n")
            logger.info("Added %r to certifi bundle at %s", ca_name, bundle_path)
        except OSError as e:
            logger.debug("Could not write to certifi bundle %s: %s", bundle_path, e)


def _export_cert_from_keychain(common_name: str) -> str | None:
    """Return the PEM text for a certificate in the System keychain, or None."""
    try:
        result = subprocess.run(
            ["security", "find-certificate", "-c", common_name, "-p", _SYSTEM_KEYCHAIN],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Could not query System keychain for %r: %s", common_name, e)
        return None

    pem = result.stdout.strip()
    if result.returncode != 0 or not pem.startswith("-----BEGIN CERTIFICATE-----"):
        return None
    return pem
