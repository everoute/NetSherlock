"""
LLM chat endpoint for natural language diagnosis creation.

Users describe network problems in natural language (Chinese/English),
and the LLM parses intent, extracts parameters, and creates diagnosis
tasks via the existing queue.

Uses claude-agent-sdk for LLM calls, inheriting Claude Code's auth
(OAuth, API key, or cloud provider) automatically.
"""

import json
import logging
import re
from datetime import datetime
from typing import Annotated, Literal

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from netsherlock.api.webhook import (
    DiagnosisRequestSource,
    DiagnosisResult,
    DiagnosisStatus,
    DiagnosticRequest,
    diagnosis_queue,
    diagnosis_store,
    determine_webhook_mode,
    generate_diagnosis_id,
    verify_api_key,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================
# Models
# ============================================================


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    diagnosis_id: str | None = None
    action: Literal["created", "clarified", "info"] = "info"


# ============================================================
# System prompt
# ============================================================

SYSTEM_PROMPT = """你是 NetSherlock 网络诊断助手。用户会用中文或英文描述网络问题，你需要理解问题并提取诊断参数。

当用户提供了足够的信息来创建诊断任务时，请回复一个 JSON 代码块（用 ```json 包裹），格式如下：
```json
{"action": "create_diagnosis", "params": {"network_type": "...", "diagnosis_type": "...", ...}}
```

可用的参数字段：
- network_type: "vm"（虚拟机网络）或 "system"（主机网络）【必填】
- diagnosis_type: "latency"（延迟）、"packet_drop"（丢包）、"connectivity"（连通性）【必填】
- src_host: 源主机管理 IP 地址
- dst_host: 目标主机管理 IP 地址
- src_vm: 源 VM UUID
- dst_vm: 目标 VM UUID
- src_vm_name: 源 VM 名称（用于通过 GlobalInventory 解析）
- dst_vm_name: 目标 VM 名称
- description: 问题描述

参数推断规则：
- "延迟"、"慢"、"latency" → diagnosis_type = "latency"
- "丢包"、"丢失"、"drop"、"loss" → diagnosis_type = "packet_drop"
- "不通"、"断开"、"connectivity" → diagnosis_type = "connectivity"
- 如果提到 VM 名称但没有 IP，使用 src_vm_name/dst_vm_name
- 如果提到 IP 地址，使用 src_host/dst_host
- 如果涉及 VM，network_type = "vm"；否则为 "system"
- 如果没有明确说明网络类型，根据是否提到 VM 来推断

交互原则：
- 如果用户信息不足（例如缺少源地址），礼貌地询问缺少的信息，不要输出 JSON
- 用中文回复用户
- 创建诊断后，在 JSON 块之后简洁确认
- 不要编造或猜测 IP 地址和 VM UUID"""


# ============================================================
# Chat handler
# ============================================================


def _extract_diagnosis_json(text: str) -> dict | None:
    """Extract diagnosis JSON from assistant's response."""
    # Match ```json ... ``` blocks
    pattern = r"```json\s*\n?\s*(\{.*?\})\s*\n?\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        if data.get("action") == "create_diagnosis" and "params" in data:
            return data["params"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _clean_reply(text: str) -> str:
    """Remove the JSON block from the reply text shown to the user."""
    cleaned = re.sub(r"```json\s*\n?\s*\{.*?\}\s*\n?\s*```", "", text, flags=re.DOTALL)
    return cleaned.strip()


async def _create_diagnosis_from_params(params: dict) -> tuple[str, str]:
    """Create a diagnosis from extracted parameters.

    Returns (diagnosis_id, confirmation_message).
    """
    try:
        diag_request = DiagnosticRequest(
            network_type=params["network_type"],
            diagnosis_type=params.get("diagnosis_type", "latency"),
            src_host=params.get("src_host"),
            src_vm=params.get("src_vm"),
            dst_host=params.get("dst_host"),
            dst_vm=params.get("dst_vm"),
            src_vm_name=params.get("src_vm_name"),
            dst_vm_name=params.get("dst_vm_name"),
            description=params.get("description"),
        )
    except Exception as e:
        raise ValueError(f"参数验证失败: {e}")

    diagnosis_id = generate_diagnosis_id("chat")

    alert_type_for_mode = (
        "VMNetworkLatency" if diag_request.network_type == "vm" else "HostNetworkLatency"
    )
    effective_mode = determine_webhook_mode(alert_type=alert_type_for_mode)

    request_data = diag_request.model_dump()
    request_data["mode"] = effective_mode.value
    request_data["alert_type"] = alert_type_for_mode
    await diagnosis_queue.put(("manual", diagnosis_id, request_data))

    diagnosis_store[diagnosis_id] = DiagnosisResult(
        diagnosis_id=diagnosis_id,
        status=DiagnosisStatus.PENDING,
        started_at=datetime.now(),
        phase="queued",
        source=DiagnosisRequestSource.API,
        mode=effective_mode,
        network_type=diag_request.network_type,
        request_type=diag_request.diagnosis_type,
        src_host=diag_request.src_host or "",
        src_vm=diag_request.src_vm,
        dst_host=diag_request.dst_host,
        dst_vm=diag_request.dst_vm,
    )

    logger.info(f"Chat diagnosis queued: {diagnosis_id}")
    return diagnosis_id, f"已创建诊断任务 {diagnosis_id}"


@router.post("/chat", response_model=ChatResponse)
async def handle_chat(
    request: ChatRequest,
    _api_key: Annotated[str, Depends(verify_api_key)],
):
    """Handle a chat message, optionally creating a diagnosis."""
    # Build the full prompt with history context
    prompt_parts = [SYSTEM_PROMPT, ""]

    for msg in request.history[-20:]:
        role_label = "用户" if msg.role == "user" else "助手"
        prompt_parts.append(f"{role_label}: {msg.content}")

    prompt_parts.append(f"用户: {request.message}")
    prompt_parts.append("")
    prompt_parts.append("请回复用户（如果参数充分，包含 JSON 代码块）：")

    full_prompt = "\n".join(prompt_parts)

    try:
        # Use claude-agent-sdk which handles auth via claude CLI
        options = ClaudeAgentOptions(
            max_turns=1,
            system_prompt=SYSTEM_PROMPT,
            model="claude-haiku-4-5-20251001",
        )

        result_text = ""
        async for message in query(prompt=full_prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.result:
                    result_text = message.result
            elif isinstance(message, AssistantMessage):
                # Extract text from content blocks
                for block in message.content:
                    if hasattr(block, "text"):
                        result_text += block.text

    except Exception as e:
        logger.error(f"LLM query error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    if not result_text:
        return ChatResponse(
            reply="抱歉，我无法理解您的请求，请再描述一下。",
            action="info",
        )

    # Check if the response contains a diagnosis creation JSON
    diagnosis_params = _extract_diagnosis_json(result_text)

    if diagnosis_params:
        try:
            diagnosis_id, confirmation = await _create_diagnosis_from_params(diagnosis_params)
            reply = _clean_reply(result_text) or confirmation
            return ChatResponse(reply=reply, diagnosis_id=diagnosis_id, action="created")
        except ValueError as e:
            reply = _clean_reply(result_text) or str(e)
            return ChatResponse(reply=reply, action="clarified")

    # No JSON → clarification or general info
    action = "info"
    if any(keyword in result_text for keyword in ["请提供", "请告诉", "需要", "哪个", "什么"]):
        action = "clarified"

    return ChatResponse(reply=result_text, action=action)
