import aiohttp
import asyncio
import json
from dependencies.webnovel.classes.mobile_device import QiDeviceSpec


def assemble_request_form(device: QiDeviceSpec):
    form = aiohttp.FormData(
        {
            "password": password,
            "source": device.app_source,
            "nextAction": "0",
            "signature": device.toSignature(),
            "autotime": "30",
            "version": this.deviceSpec.appVersion,
            "appid": "901",
            "username": email,
            "auto": "1",
            "areaid": "1",
            "type": "1",
            "format": "json"
        }
    )