#!/usr/bin/env python3
"""다중 Gemini API 키 상태(쿼터 소진 여부) 일괄 점검 스크립트.

환경 변수에 등록된 모든 GEMINI_API_KEY* 를 수집하여,
가장 저렴한 텍스트 생성 요청(1토큰)을 보내 상태(정상/429소진/에러)를 확인합니다.
"""
import os
import sys

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("google-genai 패키지가 필요합니다. (pip install -r scripts/requirements.txt)")
    sys.exit(1)


def main() -> None:
    env_keys = sorted(
        [k for k in os.environ.keys() if k.startswith("GEMINI_API_KEY")],
        key=lambda x: (0 if x == "GEMINI_API_KEY" else 1, x)
    )
    
    if not env_keys:
        print("환경 변수에 GEMINI_API_KEY 로 시작하는 키가 없습니다.")
        return

    print(f"총 {len(env_keys)}개의 API 키를 점검합니다...\n")
    
    for var_name in env_keys:
        api_key = os.environ[var_name].strip()
        masked = f"{api_key[:6]}****{api_key[-4:]}" if len(api_key) > 10 else "(미설정)"
        print(f"[{var_name}] {masked} ... ", end="", flush=True)
        
        if not api_key:
            print("❌ 빈 값입니다.")
            continue
            
        client = genai.Client(api_key=api_key)
        try:
            # 가장 가벼운 요청(출력 최대 1토큰)으로 상태만 테스트
            client.models.generate_content(
                model="gemini-2.5-flash", 
                contents="1",
                config=types.GenerateContentConfig(max_output_tokens=1)
            )
            print("✅ 정상 (쿼터 여유 있음)")
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "resource_exhausted" in msg or "quota" in msg:
                if "prepayment credits" in msg:
                    print("🚫 크레딧 소진 (AI Studio 결제 잔고 부족)")
                else:
                    print("⚠️ 무료 쿼터 소진 (429 Limit 초과 - 내일 회복됨)")
            elif "400" in msg or "401" in msg or "403" in msg or "invalid" in msg:
                print("❌ 키 유효하지 않음 (400/401/403)")
            else:
                print(f"❓ 기타 에러 발생 ({type(e).__name__})")


if __name__ == "__main__":
    main()