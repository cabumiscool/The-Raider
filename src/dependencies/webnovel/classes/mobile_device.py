import time
from Crypto.Cipher import DES3
from Crypto.Util.Padding import pad
from base64 import b64encode
import traceback


def des_gen_encrypt(data_: str, key: str, iv: str) -> bytes:    #is that the wanted return type?
    """
    encrypts data_ using DES3 with init vector and padding using CBC mode
    returns bytes (so far?)
    may return empty bytes object if encryption failed (invalid input or idiot programmer)
    """
    ct_b64 = bytes("")
    try:
        key_par = DES3.adjust_key_parity(bytes(key))
        #not entirely sure if bytes() works as intended
        cipher = DES3.new(key_par, mode=DES3.MODE_CBC, iv=bytes(iv))        
        #pkcs7 should work for any blocksize, pkcs5 is specifically for 8 byte blocksizes
        ct = cipher.encrypt(pad(data_, DES3.block_size, style="pkcs7"))     
        ct_b64 = b64encode(ct)

    except ValueError as e:
        #missing logging stuff
        print("invalid input, maybe key does not fulfull length requirements (16 or 24 bytes)")
        traceback.print_exc()

    except Exception as e:
        print("Something went horribly wrong. IDFK what.")
        traceback.print_exc()

    return ct_b64

    """
    def des_gen_encrypt(data_: str, key: str, iv: str):
        
    ivSpec = IvParameterSpec(iv.encode())
    # keyBytes = key.toByteArray(charset("UTF-8"))
    keyBytes = key.encode("UTF-8")

    keySpec = SecretKeySpec(keyBytes, "DESede")
    key = SecretKeyFactory.getInstance("desede").generateSecret(keySpec)
    cipher = Cipher.getInstance("DESede/CBC/PKCS5Padding")

    return if (cipher == null) {
        ""
    } else {
        cipher.init(Cipher.ENCRYPT_MODE, key, ivSpec)
        DatatypeConverter.printBase64Binary(cipher.doFinal(data.toByteArray()))
    }
    """#old code


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

    #
    # csrftoken??
    #

    def __init__(self, imei: str, app_version: str, user_id: int, ukey: str,
                 auto_login_session_key: str, app_source: str = "2000002", version_code: str = "223"):
        self.imei = imei
        self.app_version = app_version
        self.user_id = user_id
        self.ukey = ukey
        self.auto_login_session_key = auto_login_session_key
        self.app_source = app_source
        self.version_code = version_code




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

    def __init__(self, imei: str, app_version: str, user_id: int, ukey: str,
                auto_login_session_key: str, version_code: str,
                screen_width: str, screen_height: str, android_version: str, phone_model: str,
                auto_login_expired_time: int, const1: str = "1", app_source: str = "2000002",
                app_source2: str = "2000002", const4: str = "4",
                is_emulator: str = "0"):
        super().__init__(imei, app_version, user_id, ukey, auto_login_session_key, app_source,
                         version_code)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.android_version = android_version
        self.phone_model = phone_model
        self.auto_login_expired_time = auto_login_expired_time
        self.const1 = const1
        self.app_source2 = app_source2
        self.const4 = const4
        self.is_emulator = is_emulator
        pass

    def to_cookies(self):
        pass

    def to_raw_wd_token(self):
        return f"{self.imei}|{self.app_version}|{self.screen_width}|{self.screen_height}|" \
               f"{self.app_source}|{self.android_version}|{self.const1}|{self.phone_model}|{self.version_code}|" \
               f"{self.app_source2}|{time.time()}|{self.is_emulator}"

    def to_raw_qd_info(self):
        return f"{self.imei}|{self.app_version}|{self.screen_width}|{self.screen_height}|" \
               f"{self.app_source}|{self.android_version}|{self.const1}|{self.phone_model}|{self.version_code}|" \
               f"{self.app_source2}|{self.const4}|{self.user_id}|{time.time()}|{self.is_emulator}"

    def to_user_agent(self):
        return f"Mozilla/mobile QDHWReaderAndroid/{self.app_version}/{self.version_code}/{self.app_source}/{self.imei}"

    def to_app_user_agent(self):
        return f"Mozilla/5.0 (Linux; Android {self.android_version}; {self.phone_model} Build/MMB29U; wv) " \
               f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/44.0.2403.119 Mobile Safari/537.36 " \
               f"QDJSSDK/1.0  QDHWReaderAndroid/{self.app_version}/{self.version_code}/{self.app_source}/{self.imei}"  # imei not at end on first launch?

    def to_raw_signature(self):
        return f"{self.imei}|{self.imei}|{time.time() / 1000}"  # System.currentTimeMillis() / 1000

    def copy(self):  # needed?
        pass

    def to_signature(self, logged_in: bool = None):
        # if logged_in is None:
        #     logged_in = self.user_id != 0
        des_gen_encrypt(self.to_raw_signature(), self.signature_key, self.signature_iv)

if __name__ == '__main__':
    data = QiDeviceSpec(
        "ffffffffc7bc4d0fffffffff497b5588",
        "4.7.1",
        0,
        None,
        None,
        291,
        "1080",
        "1920",
        "6.0.1",
        "SM-G900F",
        None
    )
    print(True)
    # QiDeviceSpec()
