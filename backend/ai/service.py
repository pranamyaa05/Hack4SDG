from threading import Lock
from time import perf_counter

import httpx
from pydantic import ValidationError

from .models import VisionAnalysis
from .providers import AISettings, GeminiProvider, OllamaProvider, ProviderError


class AnalysisService:
    def __init__(self, settings: AISettings, client: httpx.Client):
        self.settings = settings
        self.client = client
        self.lock = Lock()

    def run(self, provider_name, image, notes, track):
        provider = (
            OllamaProvider(self.settings, self.client)
            if provider_name == "ollama"
            else GeminiProvider(self.settings, self.client)
        )
        started = perf_counter()
        for attempt in (1, 2):
            try:
                output = provider.generate(image, notes, track)
                if len(output) > 16000:
                    raise ProviderError("invalid_response")
                analysis = VisionAnalysis.model_validate_json(output)
                return analysis, "ok", attempt, (perf_counter() - started) * 1000
            except ValidationError:
                error = "invalid_response"
            except ProviderError as exc:
                error = exc.code
                if error not in {"invalid_response"}:
                    break
        return (
            None,
            "invalid_response" if error == "invalid_response" else "unavailable",
            attempt,
            (perf_counter() - started) * 1000,
        )
