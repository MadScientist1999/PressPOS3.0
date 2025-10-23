# license_checker.py
import hashlib
import datetime
import logging
import json
import subprocess

logging.basicConfig(
    filename="debug.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_machine_guid():
    try:
        output = subprocess.check_output(
            ['wmic', 'csproduct', 'get', 'uuid'],
            creationflags=0x08000000
        )
        guid = output.decode().strip().split('\n')[-1]
        return guid
    except Exception as e:
        logging.error(f"Failed to get machine GUID: {e}")
        return None

def validate_license():
    """Check if the license is valid and belongs to this device."""
    try:
        with open("license.lic", "r") as file:
            data = json.loads(file.read())

        stored_license = data["signature"]
        expiry_date = data["expiry_date"]
        device_id = get_machine_guid()
      
        license_data = {
            'device_id': device_id,
            'expiry_date': expiry_date
        }
        license_json = json.dumps(license_data, sort_keys=True)

        secret_key = "66bba0e0390689825d6ed1cfd866556c23d5674c4fd98d717aadb93c1a1f53da"
        joined = secret_key + license_json
   
        expected_license = hashlib.sha256(joined.encode()).hexdigest()

        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
       
        if stored_license == expected_license and today <= expiry_date:
            logging.info("License is valid.")
            return True, "License valid"
        else:
            logging.warning("❌ License expired or invalid.")
            return False, f"License expired or invalid. Device ID: {device_id}"

    except FileNotFoundError:
        logging.error("❌ License file not found.")
        return False, "License file not found"
    except ValueError as e:
        logging.error(f"License file corrupted or improperly formatted: {e}")
        return False, f"License file improperly formatted: {e}"
    except Exception as e:
        logging.exception(f"Unexpected error during license validation: {e}")
        return False, "Unexpected error"
