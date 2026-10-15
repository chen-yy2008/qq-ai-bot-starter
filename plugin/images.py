"""Fetch a single public HTTPS image through a DNS-pinning resolver; never files."""
import asyncio
import base64
import io
import ipaddress
import socket
from urllib.parse import urlsplit

MAX_BYTES = 4 * 1024 * 1024


def validate_url(url):
    p=urlsplit(url)
    if len(url)>8192 or p.scheme!="https" or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError("仅允许公网 HTTPS 图片")
    host=p.hostname.rstrip(".").lower()
    if host=="localhost" or host.endswith((".localhost",".local",".internal")):
        raise ValueError("禁止本地图片地址")
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        return host
    if not address.is_global:
        raise ValueError("禁止非公网图片地址")
    return host


def encode_frame(data):
    from PIL import Image
    if len(data)>MAX_BYTES:
        raise ValueError("图片超过 4 MiB")
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in ("JPEG","PNG","WEBP","GIF") or im.width*im.height>16_000_000:
            raise ValueError("图片格式或像素超限")
        im.seek(0)
        frame=im.convert("RGB")
        frame.thumbnail((1280,1280))
        out=io.BytesIO()
        frame.save(out,format="JPEG",quality=80)
    return "base64://"+base64.b64encode(out.getvalue()).decode("ascii")


async def prepare_image(url):
    import aiohttp
    host=validate_url(url)
    loop=asyncio.get_running_loop()
    records=await loop.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    addresses={x[4][0] for x in records}
    if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):
        raise ValueError("图片 DNS 包含非公网地址")

    class PinnedResolver(aiohttp.abc.AbstractResolver):
        async def resolve(self, requested_host, port=0, family=socket.AF_INET):
            if requested_host.rstrip(".").lower()!=host:
                raise OSError("图片主机改变")
            return [dict(hostname=host,host=ip,port=443,family=socket.AF_INET6 if ":" in ip else socket.AF_INET,proto=0,flags=0) for ip in addresses]
        async def close(self): pass

    connector=aiohttp.TCPConnector(resolver=PinnedResolver(),use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector,timeout=aiohttp.ClientTimeout(total=8),trust_env=False) as session:
        async with session.get(url,allow_redirects=False) as response:
            if response.status!=200 or response.content_length and response.content_length>MAX_BYTES:
                raise ValueError("图片不可用或过大")
            data=bytearray()
            async for part in response.content.iter_chunked(32768):
                data.extend(part)
                if len(data)>MAX_BYTES:
                    raise ValueError("图片过大")
    return await asyncio.to_thread(encode_frame,bytes(data))
