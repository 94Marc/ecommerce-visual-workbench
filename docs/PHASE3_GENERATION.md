# Phase 3：真实 AI 商品图片生成闭环

## 能力边界

Phase 3 复用 Phase 2 的 `RuleVersion`、`ProductVisualPlan` 和 `AssetSlot`。方案展开时，每个
槽位会生成一条结构化任务，包含商品快照、ORIGINAL 来源版本、平台/市场/类目、方案、槽位和
实际使用的规则版本。规则后续更新不会改变已创建任务。

真实能力：

- `ImageGenerationProvider` 是统一接口；当前真实适配器为 OpenAI Image API。
- OpenAI 适配器使用供应商原图作为 edit/reference 输入，并保存供应商 request ID。
- Redis Worker 处理任务，记录每次尝试、超时、失败码、可重试性及最终结果。
- 输出写入 MinIO/S3，并创建新的 `AssetVersion`。同一 AssetSlot 重新生成时追加版本，绝不覆盖。
- 规则复检读取生成文件的真实像素尺寸、MIME 和字节数，并校验比例、格式、文字/水印标记。
- 只有规则复检通过且人工审核通过的版本可以进入 ZIP。

模拟能力：

- `mock` provider 本地生成确定性的空白 PNG，不调用网络、不产生模型费用。
- Mock 会遵循目标画布尺寸，因此可以完整演练生成、规则复检、审核、重生成和导出流程；它不
  代表商品图的视觉质量。

当前未完成：

- 尚无自动视觉检测器识别图片中的文字和水印；真实 Provider 当前默认回报二者为 false，仍需
  人工审核兜底。
- 尚未实现额度/成本账单、并发限流、事务 outbox 和死信队列。
- 只接入 OpenAI 真实 Provider；其他模型服务可通过同一接口继续增加。

## 环境配置

默认配置不会访问付费接口：

```dotenv
IMAGE_GENERATION_PROVIDER=mock
IMAGE_GENERATION_TIMEOUT_SECONDS=120
IMAGE_GENERATION_MAX_ATTEMPTS=3
IMAGE_GENERATION_QUALITY=medium
IMAGE_GENERATION_OUTPUT_FORMAT=png
```

启用 OpenAI：

```dotenv
IMAGE_GENERATION_PROVIDER=openai
OPENAI_API_KEY=your-secret-from-a-secret-manager
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_BASE_URL=https://api.openai.com/v1
```

API 密钥只允许放在本地 `.env`、部署平台 Secret 或 CI Secret 中，不得提交到 Git。
如果 Provider 配置为 `openai` 但密钥为空，系统安全回退到 Mock。

## 启动与迁移

```shell
python -m pip install -e ".[dev]"
docker compose -f infra/docker/compose.yaml up -d
alembic upgrade head
uvicorn app.main:app --app-dir apps/api --reload
python services/ai-worker/run.py
```

## 操作流程

1. 创建 Product/SKU，上传至少一张 ORIGINAL。
2. 创建平台规则和 RuleVersion，再创建 ProductVisualPlan 与 AssetSlot。
3. `POST /api/v1/generation-jobs/from-plan`，请求体可包含 `plan_id`、可选
   `source_version_id` 和可选 `slot_ids`。
4. Worker 消费任务；通过 `GET /api/v1/generation-jobs/{job_id}` 查看状态，通过
   `/attempts` 查看每次尝试。
5. 失败任务可调用 `POST /api/v1/generation-jobs/{job_id}/retry`。已完成槽位可调用
   `POST /api/v1/generation-jobs/{job_id}/regenerate` 并传入 `feedback`。
6. 对输出版本创建 review：`approved`、`rejected` 或 `regenerate`；修改意见存入 comment，
   `regenerate` 会把意见写入下一任务 prompt。
7. 创建 export；服务只收集规则复检通过且人工审核通过的版本，并在 manifest 中记录
   AssetSlot、VisualPlan 和 RuleVersion。

## 测试保证

测试套件使用自动 fixture 强制 `IMAGE_GENERATION_PROVIDER=mock` 并移除 `OPENAI_API_KEY`。
OpenAI 适配器测试使用进程内 `MockTransport`，不会发出真实 HTTP 请求。
