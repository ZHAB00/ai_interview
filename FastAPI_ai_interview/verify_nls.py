"""Quick script to verify Alibaba Cloud NLS credentials are valid.

Usage: python verify_nls.py

Tests:
  1. Token acquisition (AccessKey ID + Secret)
  2. TTS synthesis (Appkey + Token) — generates a short "hello" audio
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.ws.audio_handler import AliyunTokenManager, AliyunTTSProvider


async def main():
    print("=" * 60)
    print("  Alibaba Cloud NLS Credential Verification")
    print("=" * 60)

    checks = [
        ("ALIYUN_ACCESS_KEY_ID", settings.ALIYUN_ACCESS_KEY_ID),
        ("ALIYUN_ACCESS_KEY_SECRET", settings.ALIYUN_ACCESS_KEY_SECRET),
        ("ALIYUN_NLS_APPKEY", settings.ALIYUN_NLS_APPKEY),
    ]
    all_ok = True
    for name, val in checks:
        ok = bool(val)
        if ok:
            print(f"  [OK] {name} = {val[:4]}...{val[-4:]}")
        else:
            print(f"  [MISSING] {name}")
            all_ok = False

    if not all_ok:
        print("\n  Fill in missing values in .env and retry.")
        return

    # Step 1: Token
    print("\n  1. Token acquisition...")
    mgr = AliyunTokenManager(
        settings.ALIYUN_ACCESS_KEY_ID,
        settings.ALIYUN_ACCESS_KEY_SECRET,
    )
    token = await mgr.get_token()

    if not token:
        print("     [FAIL] Token acquisition failed — check AccessKey ID/Secret")
        print("=" * 60)
        return

    print(f"     [OK] Token acquired (expires epoch {mgr._expire_at})")

    # Step 2: TTS (validates appkey + token together)
    print("\n  2. TTS connectivity (appkey + token)...")
    provider = AliyunTTSProvider(appkey=settings.ALIYUN_NLS_APPKEY)
    audio = await provider.synthesize("测试")

    if audio and len(audio) > 100:
        print(f"     [OK] TTS returned {len(audio)} bytes of audio (appkey valid)")
    elif audio and len(audio) <= 100:
        print(f"     [WARN] TTS returned only {len(audio)} bytes — check appkey")
    else:
        print("     [FAIL] TTS failed — check appkey or service activation")

    print("=" * 60)
    print("  Done. All credentials valid." if (token and audio) else "  Done — see issues above.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
