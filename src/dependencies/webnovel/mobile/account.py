import aiohttp
import asyncio
import json
from dependencies.webnovel.classes.mobile_device import QiDeviceSpec


def assemble_request_form(device: QiDeviceSpec, email: str, password:str):
    form = aiohttp.FormData(
        {
            "password": password,
            "source": device.app_source,
            "nextAction": "0",
            "signature": device.to_signature(),
            "autotime": "30",
            "version": device.app_version,
            "appid": "901",
            "username": email,
            "auto": "1",
            "areaid": "1",
            "type": "1",
            "format": "json"
        }
    )