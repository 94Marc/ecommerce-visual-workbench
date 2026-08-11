# image-worker

Consumes the same persisted image-task UUID contract as the AI worker. `REMOVE_BACKGROUND` routes
to rembg and `UPSCALE` routes to the external Real-ESRGAN executable. Both providers are disabled
by default, fail with `provider_unavailable` when their runtime is missing, and always create a new
`AssetVersion`.

The current development runner lives in `services/ai-worker/run.py` and uses the unified
`GenerationWorker`; production deployment may split queues without changing task payloads.
