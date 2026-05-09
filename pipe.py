"""
title: DOU Assistant
author: DOU Assistant Team
description: |
  RAG chatbot for Doğuş University. Embeds the user's question (with
  conversation-aware rewriting for follow-ups), searches Qdrant, streams
  an answer from Azure OpenAI, and surfaces sources in the side panel.
version: 4.0.0
required_open_webui_version: 0.5.0
license: MIT
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional

import httpx
from pydantic import BaseModel, Field

EventEmitter = Callable[[dict], Awaitable[None]]


# =============================================================================
# Pipe
# =============================================================================
class Pipe:
    """An OpenWebUI Pipe Function.

    Pipes appear as standalone "models" in OpenWebUI's model picker. When the
    user sends a message, OpenWebUI calls `pipe(body, ...)`. Anything yielded
    is streamed to the chat. Status updates and citations are sent through
    `__event_emitter__`, which is how the polished sidebar UX works in
    ChatGPT-style interfaces.
    """

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------
    class Valves(BaseModel):
        # ---------- Azure OpenAI ----------
        AZURE_OPENAI_ENDPOINT: str = Field(
            default="https://douassistant-azureopenai.openai.azure.com",
            description="Azure OpenAI base endpoint, no trailing slash.",
        )
        AZURE_OPENAI_API_KEY: str = Field(
            default="",
            description="Azure OpenAI API key.",
        )
        AZURE_CHAT_DEPLOYMENT: str = Field(
            default="DeepSeek-V3.1",
            description="Chat-completion deployment name.",
        )
        AZURE_CHAT_API_VERSION: str = Field(
            default="2025-01-01-preview",
            description="Chat-completion API version.",
        )
        AZURE_EMBEDDING_DEPLOYMENT: str = Field(
            default="text-embedding-3-small",
            description="Embedding deployment. MUST match ingestion model.",
        )
        AZURE_EMBEDDING_API_VERSION: str = Field(
            default="2023-05-15",
            description="Embedding API version. MUST match ingestion.",
        )

        # ---------- Qdrant ----------
        QDRANT_URL: str = Field(
            default="https://qdrant.ardabulut.cloud",
            description="Qdrant cluster URL.",
        )
        QDRANT_API_KEY: str = Field(
            default="",
            description="Qdrant API key.",
        )
        QDRANT_COLLECTION: str = Field(
            default="douassistant",
            description="Qdrant collection to search.",
        )
        TOP_K: int = Field(
            default=8,
            description="Number of chunks to retrieve per query.",
        )
        SCORE_THRESHOLD: float = Field(
            default=0.40,
            description="Minimum cosine score to keep a chunk. 0 disables filtering.",
        )
        DEDUPE_BY_PAGE: bool = Field(
            default=True,
            description="Keep at most one chunk per (source, page) pair.",
        )

        # ---------- Context shaping ----------
        MAX_CONTEXT_CHARS: int = Field(
            default=18000,
            description="Total source-context character budget for the prompt.",
        )
        MAX_CHARS_PER_SOURCE: int = Field(
            default=2500,
            description="Maximum characters from a single chunk.",
        )

        # ---------- Conversation ----------
        ENABLE_QUERY_REWRITE: bool = Field(
            default=True,
            description="Rewrite follow-ups into standalone questions before embedding.",
        )
        HISTORY_TURNS: int = Field(
            default=4,
            description="Prior turns considered when rewriting follow-ups.",
        )

        # ---------- Prompting ----------
        SYSTEM_PROMPT: str = Field(
            default=(
                "Sen Doğuş Üniversitesi'nin resmi asistanısın (DOU Assistant). "
                "Görevin öğrencilere, akademisyenlere ve ziyaretçilere üniversitenin "
                "yönergeleri, duyuruları ve resmi belgeleri ışığında yardımcı olmaktır.\n\n"
                "Kurallar:\n"
                "1. Yalnızca aşağıda verilen 'Kaynak Bağlamı' içindeki bilgiyi kullan. "
                "Dış bilgi kullanma, tahmin yürütme.\n"
                "2. Bir bilgiye dayandığında parantez içinde kaynak numarasını ver: [1], [2].\n"
                '3. Kaynaklarda olmayan bir şey sorulursa açıkça "Bu konuda yayınlanmış '
                'belgelerde bilgi bulamadım." de ve mümkünse ilgili birime yönlendir.\n'
                "4. Yanıtın kısa, net, samimi ve Türkçe olsun. Soru başka bir dildeyse "
                "o dilde yanıtla.\n"
                "5. Tarih, miktar, e-posta, link gibi bilgileri kaynaktaki gibi birebir aktar; "
                "uydurma."
            ),
            description="System prompt prepended to every answer.",
        )
        REFUSAL_TEXT: str = Field(
            default=(
                "Bu konu hakkında üniversitenin yayınlanmış belgelerinde "
                "yeterli bilgi bulamadım. Lütfen ilgili birimle (öğrenci işleri, "
                "Erasmus ofisi, ilgili fakülte sekreterliği vb.) iletişime geçin."
            ),
            description="Shown when no chunk passes SCORE_THRESHOLD.",
        )

        # ---------- UX ----------
        EMIT_SOURCES: bool = Field(
            default=True,
            description="Send source citations to OpenWebUI's side panel.",
        )
        EMIT_STATUS: bool = Field(
            default=True,
            description="Stream 'Embedding…/Searching…/Generating…' status updates.",
        )
        DEBUG: bool = Field(
            default=False,
            description="Print debug info to OpenWebUI server logs.",
        )

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    def __init__(self):
        self.valves = self.Valves()
        # Shown in the model picker.
        self.name = "DOU Assistant"
        self.id = "dou_assistant"

    # =========================================================================
    # Public entry point  —  OpenWebUI calls this for every chat turn.
    # =========================================================================
    async def pipe(
        self,
        body: dict,
        __event_emitter__: Optional[EventEmitter] = None,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __task__: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        # OpenWebUI calls the pipe for several internal jobs (title generation,
        # tag suggestion, search-query crafting). Skip RAG for those and let a
        # plain LLM call handle them.
        if __task__ and __task__ != "":
            async for tok in self._handle_task(body):
                yield tok
            return

        try:
            self._require_valves()

            messages: list[dict] = body.get("messages") or []
            user_query = self._last_user_text(messages)
            if not user_query:
                yield "Hata: Kullanıcı mesajı boş."
                return

            await self._status(__event_emitter__, "Soru analiz ediliyor…")

            # 1. Standalone query for retrieval (not for the LLM).
            search_query = await self._build_search_query(messages, user_query)
            if self.valves.DEBUG:
                print(f"[DOU] search query: {search_query!r}")

            # 2. Retrieve.
            await self._status(__event_emitter__, "İlgili belgeler aranıyor…")
            vector = await self._embed(search_query)
            hits = await self._search(vector)
            chunks = self._select_chunks(hits)

            if not chunks:
                await self._status(
                    __event_emitter__,
                    "İlgili belge bulunamadı.",
                    done=True,
                )
                yield self.valves.REFUSAL_TEXT
                return

            # 3. Citations to the OpenWebUI side panel.
            if self.valves.EMIT_SOURCES and __event_emitter__:
                await self._emit_sources(__event_emitter__, chunks)

            await self._status(
                __event_emitter__,
                f"{len(chunks)} kaynak bulundu, yanıt oluşturuluyor…",
            )

            # 4. Stream the answer.
            llm_messages = self._prepare_llm_messages(
                messages, self._build_context_block(chunks)
            )
            async for token in self._stream_chat(llm_messages, body):
                yield token

            await self._status(__event_emitter__, "Tamamlandı.", done=True)

        except httpx.HTTPStatusError as exc:
            text = exc.response.text if exc.response is not None else str(exc)
            yield f"\n\n**HTTP {exc.response.status_code}** — {text[:500]}"
        except Exception as exc:
            if self.valves.DEBUG:
                import traceback

                traceback.print_exc()
            yield f"\n\n**Hata:** {type(exc).__name__}: {exc}"

    # =========================================================================
    # Task handler — bypass RAG for OpenWebUI's internal LLM jobs
    # =========================================================================
    async def _handle_task(self, body: dict) -> AsyncGenerator[str, None]:
        try:
            self._require_valves()
            messages = body.get("messages") or []
            async for token in self._stream_chat(messages, body):
                yield token
        except Exception as exc:
            yield f"[task error] {exc}"

    # =========================================================================
    # Validation
    # =========================================================================
    def _require_valves(self) -> None:
        if not self.valves.AZURE_OPENAI_API_KEY:
            raise RuntimeError("AZURE_OPENAI_API_KEY valve is empty.")
        if not self.valves.QDRANT_API_KEY:
            raise RuntimeError("QDRANT_API_KEY valve is empty.")

    # =========================================================================
    # Message helpers
    # =========================================================================
    @staticmethod
    def _content_to_text(content: Any) -> str:
        """OpenWebUI message content can be a str or a list of parts. Flatten."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if "text" in item:
                        parts.append(str(item["text"]))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(p for p in parts if p)
        return str(content or "")

    def _last_user_text(self, messages: list[dict]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return self._content_to_text(m.get("content")).strip()
        return ""

    @staticmethod
    def _has_followup_signal(messages: list[dict]) -> bool:
        return any(m.get("role") == "assistant" for m in messages)

    # =========================================================================
    # Conversation-aware query for retrieval
    # =========================================================================
    async def _build_search_query(self, messages: list[dict], user_query: str) -> str:
        """Embedding the bare last user message kills follow-up retrieval —
        "ya başvuru tarihi?" embeds to nothing useful. We ask the LLM to
        produce a standalone question first, then embed THAT.
        """
        if not self.valves.ENABLE_QUERY_REWRITE or not self._has_followup_signal(
            messages
        ):
            return user_query

        # Build a compact transcript.
        history_lines: list[str] = []
        for m in messages[-2 * self.valves.HISTORY_TURNS :]:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            text = self._content_to_text(m.get("content")).strip()
            if not text:
                continue
            label = "Kullanıcı" if role == "user" else "Asistan"
            history_lines.append(f"{label}: {text}")

        prompt = (
            "Aşağıdaki sohbet geçmişine bakarak, son kullanıcı sorusunu sohbete "
            "bağımlı olmayan, tek başına anlamlı bir Türkçe arama sorgusu olarak "
            "yeniden yaz. Sadece sorguyu döndür; açıklama veya tırnak ekleme.\n\n"
            "Sohbet:\n" + "\n".join(history_lines) + "\n\nStandalone sorgu:"
        )

        try:
            rewritten = await self._chat_once(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.0,
            )
        except Exception as exc:
            if self.valves.DEBUG:
                print(f"[DOU] rewrite failed, falling back: {exc}")
            return user_query

        rewritten = rewritten.strip().splitlines()[0].strip().strip('"').strip("'")
        return rewritten[:300] if rewritten else user_query

    # =========================================================================
    # Azure OpenAI — embeddings
    # =========================================================================
    async def _embed(self, text: str) -> list[float]:
        url = (
            f"{self.valves.AZURE_OPENAI_ENDPOINT.rstrip('/')}"
            f"/openai/deployments/{self.valves.AZURE_EMBEDDING_DEPLOYMENT}"
            f"/embeddings?api-version={self.valves.AZURE_EMBEDDING_API_VERSION}"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers=self._azure_headers(),
                json={"input": text},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]

    # =========================================================================
    # Azure OpenAI — chat (one-shot + streaming)
    # =========================================================================
    def _azure_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "api-key": self.valves.AZURE_OPENAI_API_KEY,
        }

    def _chat_url(self) -> str:
        return (
            f"{self.valves.AZURE_OPENAI_ENDPOINT.rstrip('/')}"
            f"/openai/deployments/{self.valves.AZURE_CHAT_DEPLOYMENT}"
            f"/chat/completions?api-version={self.valves.AZURE_CHAT_API_VERSION}"
        )

    async def _chat_once(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.2,
    ) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                self._chat_url(),
                headers=self._azure_headers(),
                json={
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            return (choices[0].get("message") or {}).get("content") or ""

    async def _stream_chat(
        self, messages: list[dict], body: dict
    ) -> AsyncGenerator[str, None]:
        payload: dict = {"messages": messages, "stream": True}
        # Pass through standard OpenAI knobs from the OpenWebUI body.
        for key in (
            "temperature",
            "top_p",
            "max_tokens",
            "frequency_penalty",
            "presence_penalty",
            "stop",
        ):
            if body.get(key) is not None:
                payload[key] = body[key]

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self._chat_url(),
                headers=self._azure_headers(),
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body_text = (await resp.aread()).decode("utf-8", errors="replace")
                    raise httpx.HTTPStatusError(
                        f"Azure chat completion failed: {body_text[:500]}",
                        request=resp.request,
                        response=resp,
                    )

                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if line == "data: [DONE]":
                        break
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    chunk = delta.get("content")
                    if chunk:
                        yield chunk

    # =========================================================================
    # Qdrant
    # =========================================================================
    async def _search(self, vector: list[float]) -> list[dict]:
        url = (
            f"{self.valves.QDRANT_URL.rstrip('/')}"
            f"/collections/{self.valves.QDRANT_COLLECTION}/points/search"
        )
        payload: dict = {
            "vector": vector,
            "limit": self.valves.TOP_K,
            "with_payload": True,
            "with_vector": False,
        }
        if self.valves.SCORE_THRESHOLD > 0:
            payload["score_threshold"] = self.valves.SCORE_THRESHOLD

        headers = {"Content-Type": "application/json"}
        if self.valves.QDRANT_API_KEY:
            headers["api-key"] = self.valves.QDRANT_API_KEY

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json().get("result", [])

    # =========================================================================
    # Chunk selection — dedupe + token-budget
    # =========================================================================
    def _select_chunks(self, hits: list[dict]) -> list[dict]:
        chunks: list[dict] = []
        seen_pages: set[tuple[str, Any]] = set()

        for hit in hits:
            payload = hit.get("payload") or {}
            text = (payload.get("text") or payload.get("content") or "").strip()
            if not text:
                continue

            metadata = payload.get("metadata") or {}
            source = metadata.get("source") or payload.get("source") or "unknown"
            page = metadata.get("page") or payload.get("page")
            display_name = (
                metadata.get("display_name")
                or metadata.get("name")
                or payload.get("name")
                or source
            )

            if self.valves.DEDUPE_BY_PAGE:
                key = (str(source), page)
                if key in seen_pages:
                    continue
                seen_pages.add(key)

            if len(text) > self.valves.MAX_CHARS_PER_SOURCE:
                text = text[: self.valves.MAX_CHARS_PER_SOURCE].rstrip() + "…"

            chunks.append(
                {
                    "id": len(chunks) + 1,
                    "text": text,
                    "source": str(source),
                    "name": str(display_name),
                    "page": page,
                    "score": hit.get("score"),
                }
            )

        # Enforce total context budget. We approximate XML-tag overhead as 80
        # chars per chunk so MAX_CONTEXT_CHARS is honoured even with markup.
        kept: list[dict] = []
        used = 0
        for c in chunks:
            cost = len(c["text"]) + 80
            if used + cost > self.valves.MAX_CONTEXT_CHARS:
                break
            kept.append(c)
            used += cost
        return kept

    # =========================================================================
    # Prompt construction
    # =========================================================================
    @staticmethod
    def _xml_escape(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _build_context_block(self, chunks: list[dict]) -> str:
        parts: list[str] = []
        for c in chunks:
            attrs = f'id="{c["id"]}" name="{self._xml_escape(c["name"])}"'
            if c["page"] not in (None, ""):
                attrs += f' page="{c["page"]}"'
            parts.append(f"<source {attrs}>\n{c['text']}\n</source>")
        return "\n\n".join(parts)

    def _prepare_llm_messages(
        self, messages: list[dict], context_block: str
    ) -> list[dict]:
        system_content = (
            f"{self.valves.SYSTEM_PROMPT}\n\n"
            "### Kaynak Bağlamı\n"
            f"{context_block}\n\n"
            "### Talimatlar\n"
            "Yanıtlarını YALNIZCA yukarıdaki kaynak bağlamına dayandır. "
            "Kullandığın her bilgi için ilgili kaynak numarasını [1], [2] gibi "
            "köşeli parantezlerle belirt. Birden fazla kaynak destekliyorsa "
            "[1][3] şeklinde ekle. Kaynaklarda olmayan bir şeyi söyleme."
        )

        # Drop any incoming system messages — we control the system prompt.
        history = [m for m in messages if m.get("role") != "system"]
        return [{"role": "system", "content": system_content}, *history]

    # =========================================================================
    # OpenWebUI events
    # =========================================================================
    async def _status(
        self,
        emit: Optional[EventEmitter],
        description: str,
        done: bool = False,
        hidden: bool = False,
    ) -> None:
        if not emit or not self.valves.EMIT_STATUS:
            return
        try:
            await emit(
                {
                    "type": "status",
                    "data": {
                        "description": description,
                        "done": done,
                        "hidden": hidden,
                    },
                }
            )
        except Exception:
            # Status emission is best-effort; never block the response on it.
            pass

    async def _emit_sources(self, emit: EventEmitter, chunks: list[dict]) -> None:
        try:
            await emit(
                {
                    "type": "source",
                    "data": {
                        "document": [c["text"] for c in chunks],
                        "metadata": [
                            {
                                "source": c["source"],
                                "name": c["name"],
                                "page": c["page"],
                                "score": c["score"],
                                "id": c["id"],
                            }
                            for c in chunks
                        ],
                        "source": {
                            "name": "Doğuş Üniversitesi Belgeleri",
                        },
                    },
                }
            )
        except Exception:
            pass
