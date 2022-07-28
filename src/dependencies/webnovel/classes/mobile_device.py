import time
from Crypto.Cipher import DES3
from Crypto.Cipher import DES
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from base64 import b64encode
import traceback
import random

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
    encrypts data_ using DES (?) with init vector and padding using CBC mode
    returns string
    returns None if encryption failed (invalid input or idiot programmer)
    """

    byte_key = str.encode(key[:8])
    byte_data = str.encode(data_)
    byte_iv = bytes(8)
    try:
        cipher = DES.new(byte_key, iv=byte_iv, mode=DES.MODE_CBC)
        ct = cipher.encrypt(pad(byte_data, DES.block_size))
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

class ApiDeviceSpec:
    # imei: str
    # app_version: str
    # userId: int
    # ukey: str
    # autoLoginSessionKey: str
    # appSource: str = "2000002" # from the app's runtime settings, defaults to value of appSource2
    # versionCode: str = "223"
    wd_token_key = "jxmslsiodjfpwe01"
    wd_token_iv = "webnovel-mobiles"
    qd_info_key = "0821CAAD409B8402"
    signature_key = "bMyzJ1D7Kl7zt9mwjegtJGMoF53msSfP"
    signature_iv = "W9F1bXrz"
    
    csrftoken = "".join([str(random.choice("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")) for i in range(40)])


    def __init__(self, 
            imei: str, 
            app_version: str, 
            user_id: int, 
            ukey: str,
            auto_login_session_key: str, 
            app_source: str = "2000002", 
            version_code: str = "223"):

        self.imei = imei
        self.app_version = app_version
        self.user_id = user_id
        self.ukey = ukey
        self.auto_login_session_key = auto_login_session_key
        self.app_source = app_source
        self.version_code = version_code
        print(self.csrftoken)



class QiDeviceSpec(ApiDeviceSpec):
    # # imei: str
    # # app_version: str
    # screenWidth: str
    # screenHeight: str
    # androidVersion: str
    # phoneModel: str
    # # userId: int
    # # ukey: str
    # # autoLoginSessionKey: str
    # autoLoginExpiredTime: int
    # # appSource: str = "2000002" # from the app's runtime settings, defaults to value of appSource2
    # const1: str = "1" # hardcoded to 1?
    # # versionCode: str = "300"
    # appSource2: str = "2000002" # from config.txt, but defaults to "2000002"
    # const4: str = "4" # hardcoded to 4?
    # isEmulator: str = "0"
    # # imeiSigned: str = imei

    def __init__(self, 
        imei: str, 
        app_version: str, 
        user_id: int, 
        ukey: str,
        auto_login_session_key: str, 
        version_code: str,
        screen_width: str, 
        screen_height: str, 
        android_version: str, 
        phone_model: str,
        auto_login_expired_time: int, 
        const1: str = "1", 
        app_source: str = "2000002",
        app_source2: str = "2000002", 
        const4: str = "4",
        is_emulator: str = "0"):

        super().__init__(imei, app_version, user_id, ukey, auto_login_session_key, app_source,version_code)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.android_version = android_version
        self.phone_model = phone_model
        self.auto_login_expired_time = auto_login_expired_time
        self.const1 = const1
        self.app_source2 = app_source2
        self.const4 = const4
        self.is_emulator = is_emulator

    def copy(self):  # needed?
        pass

    def to_qd_info(self):
        des_encrypt(self.to_raw_qd_info(),self.qd_info_key)

    def to_wd_token(self) -> str:
        aes_encrypt(self.to_raw_wd_token(), self.wd_token_key, self.wd_token_iv)

    def to_signature(self, logged_in: bool):
        if self.user_id != 0:
            des_gen_encrypt(self.to_raw_signature(), self.signature_key, self.signature_iv)


    def to_raw_qd_info(self)-> str:
        return f"{self.imei}|{self.app_version}|{self.screen_width}|{self.screen_height}|" \
               f"{self.app_source}|{self.android_version}|{self.const1}|{self.phone_model}|{self.version_code}|" \
               f"{self.app_source2}|{self.const4}|{self.user_id}|{time.time()}|{self.is_emulator}"

    def to_raw_wd_token(self)-> str:
        return f"{self.imei}|{self.app_version}|{self.screen_width}|{self.screen_height}|" \
               f"{self.app_source}|{self.android_version}|{self.const1}|{self.phone_model}|{self.version_code}|" \
               f"{self.app_source2}|{time.time()}|{self.is_emulator}"

    def to_cookies(self)-> str:
        pass
        #TODO

    def to_user_agent(self)-> str:
        return f"Mozilla/mobile QDHWReaderAndroid/{self.app_version}/{self.version_code}/{self.app_source}/{self.imei}"

    def to_app_user_agent(self)-> str:
        return f"Mozilla/5.0 (Linux; Android {self.android_version}; {self.phone_model} Build/MMB29U; wv) " \
               f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/44.0.2403.119 Mobile Safari/537.36 " \
               f"QDJSSDK/1.0  QDHWReaderAndroid/{self.app_version}/{self.version_code}/{self.app_source}/{self.imei}"  # imei not at end on first launch?

    def to_raw_signature(self) -> str:  #what happened to loggedIn: Boolean variable?
        return f"{self.imei}|{self.imei}|{time.time() / 1000}"  # System.currentTimeMillis() / 1000





if __name__ == '__main__':
    WD_TOKEN_KEY = "jxmslsiodjfpwe01"
    WD_TOKEN_IV = "webnovel-mobiles"
    QD_INFO_KEY = "0821CAAD409B8402"
    SIGNATURE_KEY = "bMyzJ1D7Kl7zt9mwjegtJGMoF53msSfP"
    SIGNATURE_IV = "W9F1bXrz"
    print(len(WD_TOKEN_KEY))
    print(len(WD_TOKEN_IV))
    print(len(QD_INFO_KEY))
    print(len(SIGNATURE_KEY))
    print(len(SIGNATURE_IV))


    print(aes_encrypt("abcdefghijklm", WD_TOKEN_KEY, WD_TOKEN_IV))
    #Iy6AOT1A8d8Gg2+8zQT6DQ==

    print(des_gen_encrypt("abcdefghijklm", SIGNATURE_KEY, SIGNATURE_IV))
    #YNDKtEtrfGf1f+wEmyJQwQ==

    print(des_encrypt("abcdefghijklm", QD_INFO_KEY))
    #rrJjrxDePIZGEvjxswU9Yw==
