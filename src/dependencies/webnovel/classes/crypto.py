from Crypto.Cipher import DES3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from base64 import b64encode
import traceback


def des_gen_encrypt(data_: str, key: str, iv: str) -> str:
    """
    encrypts data_ using DES3 with init vector and padding using CBC mode, key gets cut down to len 24
    returns string
    returns None if encryption failed (invalid input or idiot programmer)
    """
    byte_key = str.encode(key[:24])
    byte_iv = str.encode(iv)
    byte_data = str.encode(data_)
    try:
        cipher = DES3.new(byte_key, iv=byte_iv, mode=DES3.MODE_CBC)
        ct = cipher.encrypt(pad(byte_data, DES3.block_size))
        return str(b64encode(ct))

    except ValueError as e:
        #missing logging stuff
        print("invalid input, maybe key does not fulfull length requirements (at least 24 bytes)")
        traceback.print_exc()

    except Exception as e:
        print("Something went horribly wrong. IDFK what.")
        traceback.print_exc()

    return None

def des_encrypt(data_: str, key: str) -> str:
    """
    encrypts data_ using DES3 without init vector and padding to 16 byte keys as well using CBC mode
    returns string
    returns None if encryption failed (invalid input or idiot programmer)
    """

    if len(key) == 16:
        key += key[:8]
        byte_key = str.encode(key[:24])
    else:
        byte_key = str.encode(key[:24])
    byte_data = str.encode(data_)
    byte_iv = bytes(8)
    try:
        cipher = DES3.new(byte_key, iv=byte_iv, mode=DES3.MODE_CBC)
        ct = cipher.encrypt(pad(byte_data, DES3.block_size))
        return str(b64encode(ct))
    except ValueError as e:
        #missing logging stuff
        print("invalid input, maybe key does not fulfull length requirements (8 bytes)")
        traceback.print_exc()

    except Exception as e:
        print("Something went horribly wrong. IDFK what.")
        traceback.print_exc()

def aes_encrypt(data_: str, key: str, iv: str) -> str:
    """
    encrypts data_ using AES with init vector and padding using CBC mode
    returns string
    returns None if encryption failed (invalid input or idiot programmer)
    """

    byte_key = str.encode(key[:32])
    byte_iv = str.encode(iv)
    byte_data = str.encode(data_)
    try:
        cipher = AES.new(byte_key, iv=byte_iv, mode=AES.MODE_CBC)
        ct = cipher.encrypt(pad(byte_data, AES.block_size))
        return str(b64encode(ct))

    except ValueError as e:
        #missing logging stuff
        print("invalid input, maybe key does not fulfull length requirements (at least 32 bytes)")
        traceback.print_exc()

    except Exception as e:
        print("Something went horribly wrong. IDFK what.")
        traceback.print_exc()
