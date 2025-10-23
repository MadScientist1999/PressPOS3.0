from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import os
import subprocess
import base64
import hashlib

# Set a password for the .p12 file
def openssl(companyName):
    # Define directory path
    directory_path = certificates_path
    
    # Define file paths
    private_key_path = f"{directory_path}/{companyName}_Tprivate.pem"
    certificate_path = f"{directory_path}/{companyName}_Tcertificate.pem"
    output_p12_path = f"{directory_path}/{companyName}_Tcertificate.p12"
    
    # Construct the OpenSSL command
    p12_password = f"{companyName}123"
    with open(f'{directory_path}/{companyName}_Tpassword.txt', 'w') as file:
        file.write(p12_password)

    command = [
        "openssl", "pkcs12", "-export",
        "-out", output_p12_path,
        "-inkey", private_key_path,
        "-in", certificate_path,
        "-passout", f"pass:{p12_password}"
    ]
    
    # Execute the command
    subprocess.run(command, check=True)

def get_first16chars_of_signature(signature: str)->str:
            """
            Returns first 16 chars of the md5 hash of the signature by first converts from base64 to hex, then from hex to md5

            Parameters: 
            signature(str): receipt signature

            Returns:
            str: first 16 chars of the md5 hash of the signature
            """
            if not isinstance(signature, str) or not signature:
                raise ValueError("Input must be a non-empty string.")

            try:
                # Decode Base64 string to bytes
                byte_array = base64.b64decode(signature)
            except (ValueError, base64.binascii.Error) as e:
                raise ValueError("Invalid Base64 string.") from e

            # Convert bytes to a hexadecimal string
            hex_str = byte_array.hex()

            # Compute MD5 hash of the hexadecimal string
            md5_hash = hashlib.md5(bytes.fromhex(hex_str)).hexdigest()

            # Return the first 16 characters of the MD5 hash
            return md5_hash[:16]


def createKeys(companyName):
    # Create a directory path
    directory_path = certificates_path
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)
    
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Save the private key to a file
    with open(f'{directory_path}/{companyName}_Tprivate.pem', 'wb') as file:
        file.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    public_key = private_key.public_key()
    # Save the public key to a file
    with open(f'{directory_path}/{companyName}_Tpublic.pem', 'wb') as file:
        file.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
        
    return private_key
  
def createCertificateRequest(commonName, serial):
    directory_path = f"Certificates"   
    
    private_key = createKeys(serial)
    
    # Create a Certificate Signing Request (CSR)
    csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
        x509.NameAttribute(x509.NameOID.COMMON_NAME, commonName),
    ])).sign(private_key, hashes.SHA256(), default_backend())

    with open(f"{directory_path}/{serial}_TCN.txt", "w") as file:
        file.write(commonName)
    
    with open(f"{directory_path}/{serial}_TcertificateRequest.pem", "wb") as file:
        file.write(csr.public_bytes(serialization.Encoding.PEM))
    
    print(csr)
    csr = csr.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    
    return csr

def md5_hash(data):
    # Convert the data to a byte-encoded string
    data_bytes = data.encode('utf-8')
    
    # Create an MD5 hash object
    md5 = hashlib.md5()

    
    # Update the hash object with the data
    md5.update(data_bytes)
    
    # Retrieve the hexadecimal digest of the hash
    hash_hex= md5.hexdigest()
    
    
    return hash_hex


def hash_data(data):
            hash_object = hashlib.sha256(data.encode('utf-8'))
            return base64.b64encode(hash_object.digest()).decode('utf-8')


def sign_data(branch, data):
    key_bytes = branch.private_key.read()  # FieldFile -> bytes
    # Load the private key
    private_key = serialization.load_pem_private_key(
        key_bytes,
        password=None,  # Add password if your key is encrypted
    )
    
    signature = private_key.sign(
        data.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')
