#!/usr/bin/env python3
import os
import sys

def generate_keypair(output_dir=None):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    keys_dir = os.path.join(output_dir, "keys")
    os.makedirs(keys_dir, exist_ok=True)
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path = os.path.join(keys_dir, ".license_sign_private.pem")
    with open(priv_path, "wb") as f:
        f.write(private_pem)
    pub_path = os.path.join(keys_dir, ".license_verify_pubkey.pem")
    with open(pub_path, "wb") as f:
        f.write(public_pem)
    client_pub_path = os.path.join(output_dir, ".license_verify_pubkey.pem")
    with open(client_pub_path, "wb") as f:
        f.write(public_pem)
    print("Done: keys generated")
    return priv_path, pub_path

if __name__ == "__main__":
    generate_keypair()
