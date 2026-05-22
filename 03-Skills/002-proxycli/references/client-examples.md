# Client SDK 範例

> 主檔 SKILL.md 已收一條速查指引，這份是各語言的完整使用範例。


`CompletionResponse` 內建兩個欄位，不論請求是否指定 provider、是否觸發 fallback：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `actual_provider` | string | 實際執行的 provider（fallback 後會不同於請求） |
| `actual_model` | string | 實際使用的模型 ID |

### Python SDK（use_proxycli）
```python
from proxy import ai_detail
result = ai_detail("用一句話介紹你自己", project="web-app", group="chatbot")
print(result["content"])
print(f"provider: {result['actual_provider']}")  # e.g. "openai"（fallback）
print(f"model:    {result['actual_model']}")     # e.g. "gpt-4o-mini"
```

### 直接用 gRPC（Python）
```python
import grpc, aiproxy_pb2 as pb, aiproxy_pb2_grpc as rpc

channel = grpc.insecure_channel("clip.twloop.com:50051")
stub = rpc.AIProxyStub(channel)
meta = [("authorization", "Bearer <token>")]

resp = stub.Complete(
    pb.CompletionRequest(
        prompt="用一句話介紹你自己",
        project="web-app",
        group="chatbot",         # v3.0.0 起必填
        # 不指定 provider，自動挑可用的
        # effort="low",          # 可選（Claude thinking）
    ),
    metadata=meta,
)
print(resp.content, resp.actual_provider, resp.actual_model)
```

### Node.js
```js
client.Complete(
  { prompt: "用一句話介紹你自己", project: "web-app", group: "chatbot", effort: "" },
  meta,
  (err, resp) => {
    if (err) return console.error(err.message);
    console.log(resp.content, resp.actual_provider, resp.actual_model);
  }
);
```

### TypeScript（型別參考）
```ts
interface CompletionResponse {
  content: string;
  input_tokens: number;
  output_tokens: number;
  tokens_estimated: boolean;
  latency_ms: number;
  actual_provider: string;   // fallback 時會與請求不同
  actual_model: string;
}
```

