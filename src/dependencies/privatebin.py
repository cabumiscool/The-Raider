import base64
import json
import os
import zlib

import aiohttp
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


async def base58_encode(v):
    # 58 char alphabet
    alphabet = b'123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    alphabet_len = len(alphabet)

    if isinstance(v, str) and not isinstance(v, bytes):
        v = v.encode('ascii')

    nPad = len(v)
    v = v.lstrip(b'\0')
    nPad -= len(v)

    l = 0
    for (i, c) in enumerate(v[::-1]):
        if isinstance(c, str):
            c = ord(c)
        l += c << (8 * i)

    string = b''
    while l:
        l, idx = divmod(l, alphabet_len)
        string = alphabet[idx:idx + 1] + string

    return alphabet[0:1] * nPad + string


async def json_encode(d):
    return json.dumps(d, separators=(',', ':')).encode('utf-8')


#
# The encryption format is described here:
# https://github.com/PrivateBin/PrivateBin/wiki/Encryption-format
#
async def privatebin_encrypt(paste_passphrase,
                             paste_password,
                             paste_plaintext,
                             paste_formatter,
                             paste_attachment_name,
                             paste_attachment,
                             paste_compress,
                             paste_burn,
                             paste_opendicussion):
    if paste_password:
        paste_passphrase += bytes(paste_password, 'utf-8')

    # PBKDF
    kdf_salt = bytes(os.urandom(8))
    kdf_iterations = 100000
    kdf_keysize = 256  # size of resulting kdf_key

    backend = default_backend()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(),
                     length=int(kdf_keysize / 8),  # 256bit
                     salt=kdf_salt,
                     iterations=kdf_iterations,
                     backend=backend)
    kdf_key = kdf.derive(paste_passphrase)

    # AES-GCM
    adata_size = 128

    cipher_iv = bytes(os.urandom(int(adata_size / 8)))
    cipher_algo = "aes"
    cipher_mode = "gcm"

    compression_type = "none"
    if paste_compress:
        compression_type = "zlib"

    # compress plaintext
    paste_data = {'paste': paste_plaintext}
    if paste_attachment_name and paste_attachment:
        paste_data['attachment'] = paste_attachment
        paste_data['attachment_name'] = paste_attachment_name
        print(paste_attachment_name)
        print(paste_attachment)

    if paste_compress:
        zobj = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        paste_blob = zobj.compress(await json_encode(paste_data)) + zobj.flush()
    else:
        paste_blob = await json_encode(paste_data)

    # Associated data to authenticate
    paste_adata = [
        [
            base64.b64encode(cipher_iv).decode("utf-8"),
            base64.b64encode(kdf_salt).decode("utf-8"),
            kdf_iterations,
            kdf_keysize,
            adata_size,
            cipher_algo,
            cipher_mode,
            compression_type,
        ],
        paste_formatter,
        int(paste_opendicussion),
        int(paste_burn),
    ]

    paste_adata_json = await json_encode(paste_adata)

    aesgcm = AESGCM(kdf_key)
    ciphertext = aesgcm.encrypt(cipher_iv, paste_blob, paste_adata_json)

    # Validate
    # aesgcm.decrypt(cipher_iv, ciphertext, paste_adata_json)

    paste_ciphertext = base64.b64encode(ciphertext).decode("utf-8")
    # print (paste_plaintext, 'test') this where the actual content is saved
    return paste_adata, paste_ciphertext


async def privatebin_send(paste_url,
                          paste_password,
                          paste_plaintext,
                          paste_formatter,
                          paste_attachment_name,
                          paste_attachment,
                          paste_compress,
                          paste_burn,
                          paste_opendicussion,
                          paste_expire):
    paste_passphrase = bytes(os.urandom(32))

    paste_adata, paste_ciphertext = await privatebin_encrypt(paste_passphrase,
                                                             paste_password,
                                                             paste_plaintext,
                                                             paste_formatter,
                                                             paste_attachment_name,
                                                             paste_attachment,
                                                             paste_compress,
                                                             paste_burn,
                                                             paste_opendicussion)

    # json payload for the post API
    # https://github.com/PrivateBin/PrivateBin/wiki/API
    payload = {
        "v": 2,
        "adata": paste_adata,
        "ct": paste_ciphertext,
        "meta": {
            "expire": paste_expire,
        }
    }

    # http content type
    headers = {'X-Requested-With': 'JSONHttpRequest'}
    url = paste_url

    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            try:
                async with session.post(url, data=await json_encode(payload)) as resp:
                    r = await resp.read()
                    r_s = r.decode()
                    result = json.loads(r_s)
                    break
            except Exception:
                pass

    # r = requests.post(paste_url,
    #                  data= await json_encode(payload),
    #                  headers=headers)
    # r.raise_for_status()

    # try:
    #    result = r.json()
    # except:
    #    print('Oops, error: %s' % (r.text))
    #    sys.exit(1)

    # paste_status = result['status']
    # if paste_status:
    #    paste_message = result['message']
    #    print("Oops, error: %s" % paste_message)
    #    sys.exit(1)

    # paste_id = result['id']
    # print (result, 'this is where the error is found')
    paste_url_id = result['url']
    # paste_deletetoken = result['deletetoken']

    # print('Delete paste: %s/?pasteid=%s&deletetoken=%s' % (paste_url, paste_id, paste_deletetoken))
    # print('')
    # print('### Paste (%s): %s%s#%s' %
    #      (paste_formatter,
    #       paste_url,
    #       paste_url_id,
    #       base58_encode(paste_passphrase).decode('utf-8')))
    base_encode = await base58_encode(paste_passphrase)
    # print ('it reaches till here')
    paste_w_url = ('%s%s#%s' %
                   (paste_url,
                    paste_url_id[1:],
                    base_encode.decode('utf-8')))
    # print (paste_w_url, '(1/1)')
    return paste_w_url


async def upload_to_privatebin(paste_plaintext, expire_time='1day'):
    paste_url = 'https://pstbn.top/'
    paste_formatter = 'markdown'
    paste_compress = True
    paste_expire = expire_time
    paste_opendicussion = 0
    paste_burn = 0
    paste_password = None
    paste_attachment_name = None
    paste_attachment = None

    u_url = await privatebin_send(paste_url,
                                  paste_password,
                                  paste_plaintext,
                                  paste_formatter,
                                  paste_attachment_name,
                                  paste_attachment,
                                  paste_compress,
                                  paste_burn,
                                  paste_opendicussion,
                                  paste_expire)

    # paste_w_url = paste_w_url
    return u_url


if __name__ == '__main__':
    import asyncio


    async def main():
        url = await upload_to_privatebin("sg")
        print(url)


    asyncio.run(main())
