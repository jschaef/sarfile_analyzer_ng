"""Smoke test against the deployed lab MCP endpoint (TLS + bearer gate)."""

import asyncio
import os
import ssl
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "https://dus-lab-sar.lab.dus.suse.com:9443/mcp"
TOKEN = sys.argv[1]

# Lab cert lacks the Authority Key Identifier extension; Python >=3.13
# verifies strictly by default -> relax only that flag, keep CA pinning.
CTX = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT


def client_factory(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(verify=CTX, headers=headers, timeout=timeout, auth=auth)


async def main():
    async with streamablehttp_client(
        URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        httpx_client_factory=client_factory,
    ) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("tools:", len(tools.tools), sorted(t.name for t in tools.tools)[:5], "...")
            res = await s.call_tool("list_sar_files", {})
            print("list_sar_files:", res.content[0].text.replace("\n", " ")[:150])
            res = await s.call_tool(
                "generate_chart",
                {"file": "2026-07-23_hec45v294010_2026-02-18", "header": "Load",
                 "metric": "ldavg-5", "backend": "bokeh", "format": "png"},
            )
            for block in res.content:
                if block.type == "text":
                    print("chart:", block.text)
                else:
                    print(f"inline image: {block.type}, mime={block.mimeType}")


asyncio.run(main())
