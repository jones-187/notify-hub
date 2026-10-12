"""在进程内通过 ASGITransport 打 MCP 端口的测试客户端。

MCP 应用的 lifespan 负责启动会话管理器。用 httpx 的 ASGITransport 时
必须自己进入 lifespan，否则请求会报 “Task group is not initialized”。
"""

import json

INITIALIZE_PARAMS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "notify-hub-tests", "version": "0"},
}


class McpHttpClient:
    def __init__(self, http, token, path="/mcp"):
        self._http = http
        self._token = token
        self._path = path
        self._session_id = None
        self._last_id = 0

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id is not None:
            headers["mcp-session-id"] = self._session_id
        return headers

    @staticmethod
    def _payload(response):
        """streamable HTTP 可能用 SSE 回包，取最后一条事件。"""
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/event-stream"):
            events = [
                line[len("data: ") :]
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            return json.loads(events[-1]) if events else None
        return response.json()

    async def _post(self, method, params=None):
        self._last_id += 1
        body = {"jsonrpc": "2.0", "id": self._last_id, "method": method}
        if params is not None:
            body["params"] = params
        response = await self._http.post(self._path, headers=self._headers(), json=body)
        return response, self._payload(response)

    async def initialize(self):
        response, payload = await self._post("initialize", INITIALIZE_PARAMS)
        self._session_id = response.headers.get("mcp-session-id")
        await self._http.post(
            self._path,
            headers=self._headers(),
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        return payload

    async def list_tools(self):
        _, payload = await self._post("tools/list", {})
        return payload["result"]["tools"]

    async def call_tool(self, name, arguments):
        _, payload = await self._post(
            "tools/call", {"name": name, "arguments": arguments}
        )
        return payload["result"]

    @staticmethod
    def text(result):
        return result["content"][0]["text"]

    @classmethod
    def json(cls, result):
        return json.loads(cls.text(result))
