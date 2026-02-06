"""
LLM chat endpoint for natural language diagnosis creation.

Users describe network problems in natural language (Chinese/English),
and the LLM parses intent, extracts parameters, and creates diagnosis
tasks via the existing queue.
"""

import logging
import os
from datetime import datetime
from typing import Annotated, Literal

import anthropic
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
from netsherlock.schemas.config import DiagnosisMode

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
# System prompt & tool definition
# ============================================================

SYSTEM_PROMPT = """你是 NetSherlock 网络诊断助手。用户会用中文或英文描述网络问题，你需要：

1. 理解用户描述的网络问题
2. 提取诊断所需的参数
3. 当参数充分时，调用 create_diagnosis 工具创建诊断任务

参数推断规则：
- "延迟"、"慢"、"latency" → diagnosis_type = "latency"
- "丢包"、"丢失"、"drop"、"loss" → diagnosis_type = "packet_drop"
- "不通"、"断开"、"connectivity" → diagnosis_type = "connectivity"
- 如果提到 VM 名称（如 "vm-xxx"）但没有 IP，使用 src_vm_name/dst_vm_name 字段
- 如果提到 IP 地址，使用 src_host/dst_host 字段
- 如果涉及 VM，network_type = "vm"；如果是主机之间的问题，network_type = "system"
- 如果没有明确说明网络类型，根据是否提到 VM 来推断：有 VM 信息则为 "vm"，否则为 "system"

交互原则：
- 如果用户信息不足以创建诊断（例如缺少源地址），礼貌地询问缺少的信息
- 用中文回复用户
- 创建诊断后，简洁确认并告知诊断 ID
- 不要编造或猜测 IP 地址和 VM UUID"""

CREATE_DIAGNOSIS_TOOL = {
    "name": "create_diagnosis",
    "description": "创建网络诊断任务。当用户提供了足够的参数时调用此工具。",
    "input_schema": {
        "type": "object",
        "properties": {
            "network_type": {
                "type": "string",
                "enum": ["vm", "system"],
                "description": "网络类型：vm（虚拟机网络）或 system（主机网络）",
            },
            "diagnosis_type": {
                "type": "string",
                "enum": ["latency", "packet_drop", "connectivity"],
                "description": "诊断类型",
            },
            "src_host": {
                "type": "string",
                "description": "源主机管理 IP 地址",
            },
            "src_vm": {
                "type": "string",
                "description": "源 VM UUID",
            },
            "dst_host": {
                "type": "string",
                "description": "目标主机管理 IP 地址",
            },
            "dst_vm": {
                "type": "string",
                "description": "目标 VM UUID",
            },
            "src_vm_name": {
                "type": "string",
                "description": "源 VM 名称（用于通过 GlobalInventory 解析）",
            },
            "dst_vm_name": {
                "type": "string",
                "description": "目标 VM 名称（用于通过 GlobalInventory 解析）",
            },
            "description": {
                "type": "string",
                "description": "问题描述",
            },
        },
        "required": ["network_type", "diagnosis_type"],
    },
}


# ============================================================
# Chat handler
# ============================================================


def _get_anthropic_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured",
        )
    return anthropic.Anthropic(api_key=api_key)


async def _create_diagnosis_from_tool(params: dict) -> tuple[str, str]:
    """Create a diagnosis from tool-use parameters.

    Returns (diagnosis_id, confirmation_message).
    """
    # Build DiagnosticRequest for validation
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

    # Determine mode
    alert_type_for_mode = (
        "VMNetworkLatency" if diag_request.network_type == "vm" else "HostNetworkLatency"
    )
    effective_mode = determine_webhook_mode(alert_type=alert_type_for_mode)

    # Queue for processing
    request_data = diag_request.model_dump()
    request_data["mode"] = effective_mode.value
    request_data["alert_type"] = alert_type_for_mode
    await diagnosis_queue.put(("manual", diagnosis_id, request_data))

    # Store initial result
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
    client = _get_anthropic_client()

    # Build messages from history (last 20) + current message
    messages = []
    for msg in request.history[-20:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.message})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[CREATE_DIAGNOSIS_TOOL],
            messages=messages,
        )
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")

    # Process response blocks
    text_parts = []
    diagnosis_id = None
    action = "info"

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use" and block.name == "create_diagnosis":
            try:
                diagnosis_id, confirmation = await _create_diagnosis_from_tool(block.input)
                text_parts.append(confirmation)
                action = "created"
            except ValueError as e:
                # Validation failed — return as clarification
                text_parts.append(str(e))
                action = "clarified"

    reply = "\n".join(text_parts) if text_parts else "抱歉，我无法理解您的请求，请再描述一下。"

    if action == "info" and response.stop_reason == "tool_use":
        # Tool was invoked but we already handled it above
        pass
    elif action == "info" and any(
        keyword in reply for keyword in ["请提供", "请告诉", "需要", "哪个", "什么"]
    ):
        action = "clarified"

    return ChatResponse(reply=reply, diagnosis_id=diagnosis_id, action=action)
