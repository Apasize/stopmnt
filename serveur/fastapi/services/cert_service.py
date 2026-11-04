"""
services/cert_service.py
Génération des certificats X.509 pour les dispositifs patients.
Chaque smartphone reçoit un certificat unique signé par la CA STOP-MNT.
Ce certificat lui permet de s'authentifier auprès de Mosquitto.
"""

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timezone, timedelta
import hashlib

from config import settings


def charger_ca():
    """Charge la CA depuis les fichiers montés dans le conteneur."""
    with open(settings.CA_CERT_PATH, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())
    with open(settings.CA_KEY_PATH, "rb") as f:
        ca_key = serialization.load_pem_private_key(f.read(), password=None)
    return ca_cert, ca_key


def generer_certificat_dispositif(device_id: str, patient_id: str) -> dict:
    """
    Génère un certificat X.509 pour un smartphone patient.

    Le CN (Common Name) est device_id — c'est lui que Mosquitto utilisera
    comme username grâce à use_identity_as_username=true.

    Retourne le certificat et la clé privée en format PEM (texte),
    ainsi que l'empreinte (fingerprint) pour le Device Registry.
    """
    ca_cert, ca_key = charger_ca()

    # Générer une nouvelle paire de clés pour le dispositif
    cle_privee = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Construire le certificat
    maintenant  = datetime.now(timezone.utc)
    expiration  = maintenant + timedelta(days=settings.CERT_VALIDITY_DAYS)

    cn = f"device-{device_id}"

    certificat = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BJ"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "STOPMNT"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]))
        .issuer_name(ca_cert.subject)
        .public_key(cle_privee.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant)
        .not_valid_after(expiration)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Sérialiser en PEM (format texte transportable)
    cert_pem = certificat.public_bytes(serialization.Encoding.PEM).decode()
    key_pem  = cle_privee.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # Calculer l'empreinte pour le Device Registry
    fingerprint = hashlib.sha256(
        certificat.public_bytes(serialization.Encoding.DER)
    ).hexdigest()

    return {
        "certificate_pem" : cert_pem,
        "private_key_pem" : key_pem,
        "fingerprint"     : fingerprint,
        "common_name"     : cn,
        "expires_at"      : expiration.isoformat(),
    }
