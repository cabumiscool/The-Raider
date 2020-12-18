import json


def decode_qi_content(binary_content: bytes):
    """Decodes the Qi response into a JSON object"""
    content_str = binary_content.decode()
    return json.loads(content_str)
