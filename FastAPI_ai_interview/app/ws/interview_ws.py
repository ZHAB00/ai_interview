"""WebSocket handler for real-time interview communication.

Manages full-duplex interview flow: text/audio question delivery, answer collection,
code submission review, audio recording, interrupt signaling, and session lifecycle.
"""

import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.interview import Interview
from app.models.user import User

if settings.USE_LANGGRAPH_ORCHESTRATOR:
    from app.services.langgraph_orchestrator import LangGraphOrchestrator as Orchestrator, OrchestratorState
else:
    from app.services.interview_orchestrator import InterviewOrchestrator as Orchestrator, OrchestratorState

from app.ws.audio_handler import AudioHandler
from app.ws.session_manager import session_manager

logger = logging.getLogger(__name__)

PING_INTERVAL = 30
PING_TIMEOUT = 10
SILENCE_PROMPT_SEC = 15  # seconds of actual user-silence before prompt (after TTS ends)

# Global audio handler singleton
audio_handler = AudioHandler()


async def _silence_prompt(
    websocket: WebSocket,
    interview_id: int,
    is_speaking: asyncio.Event,
):
    """After TTS finishes + 15s of silence, prompt the user to respond."""
    # Wait for TTS playback to finish before counting silence
    while is_speaking.is_set():
        await asyncio.sleep(0.5)
    await asyncio.sleep(SILENCE_PROMPT_SEC)
    try:
        await websocket.send_json({
            "type": "ai/text",
            "data": {"text": "我还在等待你的回答，请说出你的想法吧。", "is_final": True},
        })
        logger.info(f"沉默提示: interview_id={interview_id}")
    except Exception:
        pass


async def interview_handler(websocket: WebSocket, interview_id: int, token: str):
    """Main WebSocket handler for the interview session."""

    db = SessionLocal()
    orchestrator: InterviewOrchestrator | None = None
    tts_task: asyncio.Task | None = None
    tts_queue: asyncio.Queue[bytes] = asyncio.Queue()
    is_speaking = asyncio.Event()

    try:
        # ===== Authentication =====
        interview = await _authenticate(db, interview_id, token)
        if not interview:
            # Check if interview is completed — redirect to report instead of auth failure
            result = await db.execute(
                select(Interview).where(Interview.id == interview_id)
            )
            ended = result.scalar_one_or_none()
            if ended and ended.status in ("completed", "abandoned"):
                await websocket.close(code=4000, reason="面试已结束")
            else:
                await websocket.close(code=4001, reason="认证失败")
            return

        logger.info(
            f"WebSocket连接成功: interview_id={interview_id}, user_id={interview.user_id}"
        )

        # Build orchestrator
        from app.models.resume import Resume
        result = await db.execute(
            select(Resume).where(Resume.id == interview.resume_id)
        )
        resume = result.scalar_one_or_none()
        if not resume:
            await websocket.close(code=4004, reason="简历不存在")
            return

        orchestrator = Orchestrator(interview=interview, resume=resume, db=db)

        # Accept connection
        await websocket.accept()

        # Start audio recording
        await audio_handler.start_interview(interview_id)

        # Create session in Redis (extend TTL for reconnection)
        await session_manager.create_session(interview_id, {
            "stage": interview.current_stage or "",
            "status": "in_progress",
            "ws_token": token,
        })

        # ===== Start background tasks before sending messages =====
        ping_task = asyncio.create_task(_ping_loop(websocket))
        tts_player = asyncio.create_task(_tts_player(websocket, tts_queue, is_speaking))
        silence_task: asyncio.Task | None = None

        # ===== Start or Resume Interview =====
        was_in_progress = interview.status == "in_progress"
        if not was_in_progress:
            # Fresh start — save must succeed even if user disconnects during TTS
            start_msg = await orchestrator.start()
            try:
                await websocket.send_json(start_msg)
            except Exception:
                pass
            stage_msg = await orchestrator.begin_current_stage()
            if stage_msg:
                try:
                    await _send_response(websocket, stage_msg, tts_queue, is_speaking)
                except Exception:
                    pass  # user disconnected during first TTS, conversation saved below
            # Save initial state to DB for reconnection recovery
            orchestrator.interview.answers = json.dumps(
                orchestrator.conversation, ensure_ascii=False
            )
            await db.commit()
        else:
            # Reconnection — restore state without resetting timer or stage
            orchestrator.state = OrchestratorState.WAITING_FOR_ANSWER
            started = interview.started_at.replace(tzinfo=timezone.utc) if interview.started_at else datetime.now(timezone.utc)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            logger.info(
                f"面试续接: interview_id={interview_id}, "
                f"stage={interview.current_stage}, elapsed={elapsed:.0f}s"
            )
            # Rebuild dialogue from saved conversation
            resume_dialogue = []
            stage = interview.current_stage or orchestrator.current_stage()
            resume_dialogue.append({
                "role": "system",
                "text": f"已恢复面试连接，当前在【{stage}】环节",
                "time": "",
            })
            try:
                saved = interview.answers
                if saved:
                    conv = json.loads(saved) if isinstance(saved, str) else saved
                    for entry in conv:
                        q = entry.get("question_text")
                        a = entry.get("user_answer_text")
                        if q:
                            resume_dialogue.append({"role": "ai", "text": q, "time": ""})
                        if a:
                            resume_dialogue.append({"role": "user", "text": a, "time": ""})
                    # Restore current_question from the last unanswered entry
                    for entry in reversed(conv):
                        if entry.get("question_text") and not entry.get("user_answer_text"):
                            orchestrator.current_question = {
                                "text": entry["question_text"],
                                "is_follow_up": entry.get("is_follow_up", False),
                            }
                            break
            except (json.JSONDecodeError, TypeError):
                pass
            remaining = max(0, settings.INTERVIEW_MAX_DURATION - int(elapsed))
            await websocket.send_json({
                "type": "session/resumed",
                "data": {
                    "interview_id": interview_id,
                    "stage": interview.current_stage or orchestrator.current_stage(),
                    "message": "已恢复面试连接",
                    "dialogue": resume_dialogue,
                    "remaining_seconds": remaining,
                },
            })

        # ===== Main message loop =====

        try:
            while True:
                # Check timeout
                timeout_msg = await orchestrator.check_timeout()
                if timeout_msg:
                    await websocket.send_json(timeout_msg)
                    break

                # Check if orchestrator ended
                if orchestrator.state.value == "ended":
                    break

                raw = await asyncio.wait_for(
                    websocket.receive(), timeout=PING_INTERVAL + PING_TIMEOUT
                )

                # Handle binary audio frames
                if raw.get("type") == "websocket.receive" and raw.get("bytes"):
                    # Binary audio frame from client
                    audio_bytes = raw["bytes"]
                    audio_handler.append_chunk(interview_id, audio_bytes)
                    await session_manager.heartbeat(interview_id)
                    continue

                # Handle text/JSON messages
                text = raw.get("text", "")
                if not text:
                    continue

                message = json.loads(text)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "data": {}})
                    await session_manager.heartbeat(interview_id)
                    continue

                elif msg_type == "user/interrupt":
                    # Cancel silence timer — user is engaging
                    if silence_task:
                        silence_task.cancel()
                        silence_task = None
                    # Stop current TTS playback and clear stale utterance buffer
                    is_speaking.clear()
                    await _flush_tts_queue(tts_queue)
                    audio_handler.get_utterance_audio(interview_id)  # discard stale buffer
                    await websocket.send_json({
                        "type": "ai/status",
                        "data": {"status": "listening"},
                    })
                    logger.info(f"用户打断: interview_id={interview_id}")
                    continue

                elif msg_type == "user/speech_end":
                    # Cancel silence timer — user responded
                    if silence_task:
                        silence_task.cancel()
                        silence_task = None
                    # VAD detected end of speech — run STT on accumulated utterance audio
                    utterance_audio = audio_handler.get_utterance_audio(interview_id)
                    if not utterance_audio:
                        logger.debug(f"Empty utterance audio: interview_id={interview_id}")
                        # Notify frontend to clear parsing state
                        await websocket.send_json({
                            "type": "user/text_echo",
                            "data": {"text": ""},
                        })
                        continue
                    text_content = await audio_handler.speech_to_text(utterance_audio)
                    if not text_content or not text_content.strip():
                        logger.info(f"STT returned empty text: interview_id={interview_id}")
                        # Notify frontend to clear parsing state
                        await websocket.send_json({
                            "type": "user/text_echo",
                            "data": {"text": ""},
                        })
                        continue
                    logger.info(f"STT result: interview_id={interview_id}, text={text_content[:80]}...")
                    # Echo recognized text back to frontend for draft confirmation.
                    # Processing happens via user/text (auto-sent by frontend after draft delay)
                    # to avoid double-processing and cross-stage answer leakage.
                    await websocket.send_json({
                        "type": "user/text_echo",
                        "data": {"text": text_content},
                    })
                    continue

                elif msg_type == "user/text":
                    # Cancel silence timer — user is engaging
                    if silence_task:
                        silence_task.cancel()
                        silence_task = None
                    # Manual text input takes priority (revision 10)
                    text_content = message.get("data", {}).get("text", "")
                    if not text_content:
                        continue
                    response = await orchestrator.handle_text(text_content)

                elif msg_type == "control/submit_code":
                    code = message.get("data", {}).get("code", "")
                    language = message.get("data", {}).get("language", "python")
                    if not code:
                        continue
                    response = await orchestrator.handle_code(code, language)

                elif msg_type == "control/end_session":
                    response = await orchestrator.handle_end()

                else:
                    logger.warning(f"未知消息类型: {msg_type}")
                    continue

                if response:
                    await _send_response(websocket, response, tts_queue, is_speaking)
                    # Save conversation to DB after each interaction
                    if orchestrator:
                        orchestrator.interview.answers = json.dumps(
                            orchestrator.conversation, ensure_ascii=False
                        )
                        await db.commit()
                    # Start silence timer — prompt user if no response within timeout
                    resp_type = response.get("type", "")
                    if resp_type in ("ai/text", "control/stage_change") and orchestrator.state.value == "waiting_for_answer":
                        if silence_task:
                            silence_task.cancel()
                        silence_task = asyncio.create_task(
                            _silence_prompt(websocket, interview_id, is_speaking)
                        )

                if orchestrator.state.value == "ended":
                    break

        except asyncio.TimeoutError:
            logger.warning(f"WebSocket心跳超时: interview_id={interview_id}")
        except (WebSocketDisconnect, RuntimeError):
            logger.info(f"WebSocket断开: interview_id={interview_id}")
        except Exception as e:
            logger.error(f"WebSocket错误: {e}\n{traceback.format_exc()}")
        finally:
            ping_task.cancel()
            tts_player.cancel()
            if silence_task:
                silence_task.cancel()
            try:
                await asyncio.gather(ping_task, tts_player)
            except (asyncio.CancelledError, Exception):
                pass
            if silence_task:
                try:
                    await silence_task
                except (asyncio.CancelledError, Exception):
                    pass

            # Stop speaking and flush
            is_speaking.clear()

            # --- Audio merge (before final DB save to include URLs in report) ---
            audio_url = ""
            if orchestrator:
                audio_url = await audio_handler.end_interview(interview_id, user_id=interview.user_id) or ""
                if audio_url:
                    for ans in orchestrator.conversation:
                        if "user_answer_text" in ans and not ans.get("user_audio_url"):
                            ans["user_audio_url"] = audio_url
                    logger.info(f"录音URL已保存: {audio_url}")

            # --- Final state persistence ---
            # Keep in_progress on disconnect so user can reconnect within
            # INTERVIEW_MAX_DURATION. Normal end already set completed via finalize().
            if orchestrator:
                is_ended = orchestrator.state.value == "ended"
                if not is_ended and orchestrator.interview.status == "in_progress":
                    orchestrator.interview.status = "in_progress"

            if orchestrator:
                # Save answers with audio URLs (always, so reconnection can restore them)
                orchestrator.interview.answers = json.dumps(
                    orchestrator.conversation, ensure_ascii=False
                )
                await db.commit()

                # Only generate report when interview genuinely ended
                if is_ended:
                    logger.info(
                        f"后台生成报告: interview_id={interview_id}, audio={bool(audio_url)}"
                    )
                    asyncio.create_task(
                        orchestrator._generate_report_bg(interview_id)
                    )

            await session_manager.delete_session(interview_id)
            logger.info(f"WebSocket会话结束: interview_id={interview_id}")

    finally:
        await db.close()


async def _authenticate(
    db: AsyncSession, interview_id: int, token: str
) -> Interview | None:
    """Authenticate WebSocket connection via ws_token or JWT fallback."""

    # Load interview first
    result = await db.execute(
        select(Interview).where(Interview.id == interview_id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        logger.warning(f"面试不存在: interview_id={interview_id}")
        return None

    if interview.status in ("completed", "abandoned"):
        logger.warning(
            f"面试已结束: interview_id={interview_id}, status={interview.status}"
        )
        return None

    # ── Path 1: Redis ws_token ──
    redis_id = await session_manager.validate_token(token)
    if redis_id is not None:
        if redis_id == interview_id:
            return interview
        logger.warning(
            f"ws_token不匹配: redis={redis_id}, req={interview_id}"
        )
        return None

    # ── Path 2: JWT decode (ws_token is a self-contained JWT, also
    #           works as fallback for regular access tokens) ──
    try:
        payload = decode_token(token)
        token_type = payload.get("type", "")
        token_user_id = payload.get("sub")
        token_interview_id = payload.get("interview_id")

        if token_type == "ws":
            # ws_token JWT: must match both interview_id and user_id
            if token_interview_id == interview_id and str(interview.user_id) == str(token_user_id):
                logger.info(f"ws_token JWT验证成功: user_id={token_user_id}")
                return interview
            logger.warning(
                f"ws_token JWT不匹配: jwt_interview={token_interview_id}, "
                f"req_interview={interview_id}"
            )
        else:
            # Regular access/refresh token: verify user owns the interview
            if token_user_id and str(interview.user_id) == str(token_user_id):
                logger.info(f"JWT回退验证成功: user_id={token_user_id}")
                return interview
            logger.warning(
                f"JWT用户不匹配: token_sub={token_user_id}, "
                f"interview_user={interview.user_id}"
            )
    except Exception as e:
        logger.info(f"JWT解码失败: {e.__class__.__name__}: {e} | token={token[:20]}...")

    logger.warning(
        f"Token验证失败: interview_id={interview_id}, token={token[:20]}..."
    )
    return None


async def _ping_loop(websocket: WebSocket):
    """Send periodic pings to keep the connection alive."""
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            await websocket.send_json({"type": "pong", "data": {}})
        except Exception:
            break


async def _tts_player(
    websocket: WebSocket,
    queue: asyncio.Queue[bytes],
    is_speaking: asyncio.Event,
):
    """Play TTS audio chunks sequentially, respecting interrupt signals."""
    while True:
        try:
            audio_chunk = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        if not is_speaking.is_set():
            # Interrupted, discard
            queue.task_done()
            continue

        try:
            await websocket.send_bytes(audio_chunk)
        except Exception:
            break
        finally:
            queue.task_done()

        # After sending the last chunk, mark speaking as done
        if queue.empty():
            is_speaking.clear()


async def _flush_tts_queue(queue: asyncio.Queue):
    """Clear pending TTS audio from the queue."""
    while not queue.empty():
        try:
            queue.get_nowait()
            queue.task_done()
        except asyncio.QueueEmpty:
            break


async def _send_response(
    websocket: WebSocket,
    response: dict,
    tts_queue: asyncio.Queue[bytes],
    is_speaking: asyncio.Event,
):
    """Send response with TTS audio: generate TTS first, then text + audio sync.

    TTS is generated before text is sent, so text and voice arrive together.
    If TTS fails, text is still sent — the interview continues normally.
    """
    resp_type = response.get("type", "")

    if resp_type == "ai/text":
        is_final = response.get("data", {}).get("is_final", True)

        await websocket.send_json({
            "type": "ai/status",
            "data": {"status": "thinking"},
        })

        if is_final:
            text = response.get("data", {}).get("text", "")

            # Generate TTS first (so text + voice arrive together)
            tts_ready = False
            if text:
                await websocket.send_json({
                    "type": "ai/status",
                    "data": {"status": "speaking"},
                })
                tts_ready = await _tts_speak(text, tts_queue, is_speaking)

            # Send text after TTS is ready — sync with voice
            await websocket.send_json(response)

            if not tts_ready:
                # TTS failed or was empty — clear speaking state
                is_speaking.clear()
        else:
            await websocket.send_json(response)

    elif resp_type == "control/stage_change":
        question = response.get("data", {}).get("question", "")

        # Generate TTS first
        tts_ready = False
        if question:
            await websocket.send_json({
                "type": "ai/status",
                "data": {"status": "speaking"},
            })
            tts_ready = await _tts_speak(question, tts_queue, is_speaking)

        # Send text after TTS is ready — sync with voice
        await websocket.send_json(response)

        if not tts_ready:
            is_speaking.clear()

    else:
        # Safety: if response looks like raw LLM evaluation (missing "type" field,
        # has "action" key), wrap it so the frontend doesn't show raw JSON
        if resp_type == "" and "action" in response:
            text = response.get("message") or response.get("question_text") or ""
            response = {
                "type": "ai/text",
                "data": {"text": text, "is_final": True},
            }
        await websocket.send_json(response)


async def _tts_speak(
    text: str,
    tts_queue: asyncio.Queue[bytes],
    is_speaking: asyncio.Event,
) -> bool:
    """Generate TTS audio and queue it for playback. Timeout-safe.

    Returns True if TTS audio was generated and queued successfully.
    """
    try:
        tts_audio = await asyncio.wait_for(
            audio_handler.text_to_speech(text), timeout=25.0
        )
        if tts_audio:
            is_speaking.set()
            await tts_queue.put(tts_audio)
            return True
        return False
    except asyncio.TimeoutError:
        logger.error("TTS超时(25s)，跳过语音")
        return False
    except Exception as e:
        logger.error(f"TTS生成失败: {e}")
        return False
