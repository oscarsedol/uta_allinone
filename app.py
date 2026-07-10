import streamlit as st
import google.generativeai as genai
import os
import pysrt
import time
import zipfile
import io
import re
from dotenv import load_dotenv

# --- 🌟 구글 API 필수 라이브러리 ---
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- 환경변수 및 API 설정 / 環境変数およびAPI設定 ---
load_dotenv()

# 🔒 [보안 기능] Secrets에서 아이디/비밀번호 가져오기
VALID_USERNAME = st.secrets.get("APP_USERNAME", os.getenv("APP_USERNAME", "owner"))
VALID_PASSWORD = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", "password123"))

# --- 로그인 UI 처리 / ログインUI処理 ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.set_page_config(page_title="🔒 로그인 / ログイン", page_icon="🔐", layout="centered")
    st.title("🔐 시스템 접근 제한 / アクセス制限")
    st.subheader("이 앱은 허가된 사용자만 사용할 수 있습니다. / このアプリは許可されたユーザーのみ使用できます。")
    
    with st.form("login_form"):
        login_user = st.text_input("Username / ID")
        login_pass = st.text_input("Password / パスワード", type="password")
        submit_btn = st.form_submit_button("🔑 로그인 / ログイン", type="primary", use_container_width=True)
        
        if submit_btn:
            if login_user == VALID_USERNAME and login_pass == VALID_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 틀렸습니다. / IDまたはパスワードが間違っています。")
    st.stop()

# --- 제미나이 API 세팅 ---
api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("앗, Secrets에 GEMINI_API_KEY가 없어. 확인해줘!")

# 최신 경량/고속 모델로 적용
MODEL_NAME = 'gemini-3.1-flash-lite'

# --- 번역 가능 30개 언어 목록 & 유튜브 언어 코드 매핑 ---
LANGUAGES = {
    "네덜란드어 / オランダ語": "Dutch", "노르웨이어 / ノルウェー語": "Norwegian",
    "덴마크어 / デンマーク語": "Danish", "독일어 / ドイツ語": "German",
    "러시아어 / ロシア語": "Russian", "말레이어 / マレー語": "Malay",
    "베트남어 / ベトナム語": "Vietnamese", "스웨덴어 / スウェーデン語": "Swedish",
    "스페인어 / スペイン語": "Spanish", "아랍어 / アラビア語": "Arabic",
    "영어 / 英語": "English", "우즈베크어 / ウズベク語": "Uzbek",
    "우크라이나어 / ウクライナ語": "Ukrainian", "이탈리아어 / イタリア語": "Italian",
    "인도네시아어 / インドネシア語": "Indonesian", "일본어 / 日本語": "Japanese",
    "중국어(간체) / 中国語(簡体字)": "Simplified Chinese", "중국어(대만) / 中国語(台湾)": "Traditional Chinese (Taiwan)",
    "중국어(홍콩) / 中国語(香港)": "Traditional Chinese (Hong Kong)", "카자흐어 / カザフ語": "Kazakh",
    "태국어 / タイ語": "Thai", "튀르키예어 / トルコ語": "Turkish",
    "페르시아어 / ペルシア語": "Persian", "포르투갈어 / ポルトガル語": "Portuguese",
    "폴란드어 / ポーランド語": "Polish", "프랑스어 / フランス語": "French",
    "핀란드어 / フィンランド語": "Finnish", "필리핀어 / フィリピン語": "Filipino",
    "한국어 / 韓国語": "Korean", "힌디어 / ヒンディー語": "Hindi"
}

# 유튜브 업로드 시 사용되는 언어 코드
YT_LANG_CODES = {
    "Dutch": "nl", "Norwegian": "no", "Danish": "da", "German": "de",
    "Russian": "ru", "Malay": "ms", "Vietnamese": "vi", "Swedish": "sv",
    "Spanish": "es", "Arabic": "ar", "English": "en", "Uzbek": "uz",
    "Ukrainian": "uk", "Italian": "it", "Indonesian": "id", "Japanese": "ja",
    "Simplified Chinese": "zh-CN", "Traditional Chinese (Taiwan)": "zh-TW",
    "Traditional Chinese (Hong Kong)": "zh-HK", "Kazakh": "kk",
    "Thai": "th", "Turkish": "tr", "Persian": "fa", "Portuguese": "pt",
    "Polish": "pl", "French": "fr", "Finnish": "fi", "Filipino": "fil",
    "Korean": "ko", "Hindi": "hi"
}

# 세션 상태 초기화
for lang in LANGUAGES.keys():
    key = f"chk_{lang}"
    if key not in st.session_state:
        st.session_state[key] = ("일본어" not in lang)

if 'is_processing' not in st.session_state: st.session_state.is_processing = False
if 'results' not in st.session_state: st.session_state.results = {}
if 'video_title' not in st.session_state: st.session_state.video_title = ""
if 'balloons_shown' not in st.session_state: st.session_state.balloons_shown = False 

def select_all():
    for lang in LANGUAGES.keys(): st.session_state[f"chk_{lang}"] = True
def deselect_all():
    for lang in LANGUAGES.keys(): st.session_state[f"chk_{lang}"] = False

def extract_video_id(url):
    """유튜브 링크에서 Video ID만 안전하게 추출합니다."""
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None

# --- 🌟 1. 백그라운드 구글 인증 (OAuth 통행증) ---
def get_credentials():
    try:
        client_config = st.secrets["gcp_oauth"]
        refresh_token = st.secrets["refresh_token"]
        
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            token_uri=client_config["token_uri"]
        )
        return creds
    except Exception as e:
        st.error(f"🚨 인증 정보 로드 실패 (Secrets 확인 필요): {e}")
        return None

# --- 번역 엔진 ---
def translate_all_in_one(original_text, original_srt, orig_title, orig_desc, orig_license, target_lang, progress_bar, status_text):
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"""
    You are an expert YouTube SEO and subtitle translator.
    Translate the given SRT file, Video Title, and Description into {target_lang}.
    ALSO, translate the exact phrase "사용된 음원 라이선스 코드" into {target_lang}.

    CRITICAL RULES:
    1. ABSOLUTELY DO NOT output the original text. You MUST translate the content entirely into {target_lang}.
    2. For SRT: Keep exactly {len(original_srt)} blocks. Do not merge or split lines.
    3. Keep all brackets, symbols, and emojis exactly as they are.
    4. The Translated Title MUST be under 100 characters.

    Output strictly in this format:
    [TITLE_START]
    (Translated Title in {target_lang})
    [TITLE_END]
    [DESC_START]
    (Translated Description in {target_lang})
    [DESC_END]
    [LICENSE_LABEL_START]
    (Translated phrase for "사용된 음원 라이선스 코드" in {target_lang})
    [LICENSE_LABEL_END]
    [SRT_START]
    (Translated raw SRT text)
    [SRT_END]

    Original Title: {orig_title}
    Original Description: {orig_desc}
    Original SRT:
    {original_text}
    """
    attempt = 1
    while attempt <= 3:
        if not st.session_state.is_processing: return None
        status_text.text(f"[{target_lang}] 번역 및 검수 중... / 翻訳および検証中... ({attempt}/3)")
        progress_bar.progress(int(attempt * (100 / 3)))
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            t_title = text.split("[TITLE_START]")[1].split("[TITLE_END]")[0].strip()
            t_desc_raw = text.split("[DESC_START]")[1].split("[DESC_END]")[0].strip()
            t_label = text.split("[LICENSE_LABEL_START]")[1].split("[LICENSE_LABEL_END]")[0].strip()
            srt_part = text.split("[SRT_START]")[1].split("[SRT_END]")[0].strip()
            
            if orig_license and orig_license.strip():
                t_desc_final = f"{t_desc_raw}\n\n{t_label}\n{orig_license.strip()}"
            else:
                t_desc_final = t_desc_raw
            
            translated_srt = pysrt.from_string(srt_part)
            if len(original_srt) != len(translated_srt) or len(t_title) > 100:
                attempt += 1
                time.sleep(1)
                continue
            
            final_srt_output = []
            for i in range(len(original_srt)):
                orig = original_srt[i]
                trans_text = translated_srt[i].text
                start_str = f"{orig.start.hours:02}:{orig.start.minutes:02}:{orig.start.seconds:02},{orig.start.milliseconds:03}"
                end_str = f"{orig.end.hours:02}:{orig.end.minutes:02}:{orig.end.seconds:02},{orig.end.milliseconds:03}"
                final_srt_output.append(f"{orig.index}\n{start_str} --> {end_str}\n{trans_text}")
                
            status_text.text(f"[{target_lang}] 완료! ({attempt}회차 성공) / 完了!")
            progress_bar.progress(100)
            return {"title": t_title, "desc": t_desc_final, "srt": "\n\n".join(final_srt_output)}
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                status_text.text("⚠️ 한도 도달! 25초 대기... / API制限！25秒待機...")
                time.sleep(25)
                continue
            attempt += 1
            time.sleep(1)
    return None

# --- 🌟 3. 최종 유튜브 업데이트(메타데이터/자막 동기화) 로직 ---
def update_youtube_video(video_url, translated_data):
    video_id = extract_video_id(video_url)
    if not video_id:
        st.error("🚨 유효한 유튜브 영상 링크가 아닙니다.")
        return False

    creds = get_credentials()
    if not creds: return False
    youtube = build('youtube', 'v3', credentials=creds)
    
    st.info("🔄 유튜브 서버와 통신을 시작합니다... (기존 영상 정보를 불러오는 중)")
    
    try:
        # [1] 기존 영상 메타데이터 불러오기
        video_response = youtube.videos().list(part="snippet,localizations", id=video_id).execute()
        if not video_response.get('items'):
            st.error("🚨 영상을 찾을 수 없습니다. (비공개 영상이거나 계정이 다를 수 있습니다)")
            return False
            
        video_item = video_response['items'][0]
        snippet = video_item['snippet']
        localizations = video_item.get('localizations', {})
        
        # 언어 기본값 설정 보정 (일본어로 기본 설정)
        if 'defaultLanguage' not in snippet: snippet['defaultLanguage'] = 'ja'
        if 'defaultAudioLanguage' not in snippet: snippet['defaultAudioLanguage'] = 'ja'

        # 다국어 메타데이터 병합
        for lang_name, data in translated_data.items():
            en_lang_name = LANGUAGES[lang_name + " / " + lang_name.split(" / ")[1]] if " / " not in lang_name else LANGUAGES.get(lang_name)
            if not en_lang_name: continue
            
            yt_code = YT_LANG_CODES.get(en_lang_name)
            if yt_code:
                localizations[yt_code] = {
                    "title": data["title"],
                    "description": data["desc"]
                }
        
        # [2] 변경된 메타데이터(다국어 제목/설명) 유튜브에 업데이트 쏘기
        youtube.videos().update(
            part="snippet,localizations",
            body={
                "id": video_id,
                "snippet": snippet,
                "localizations": localizations
            }
        ).execute()
        st.success("✅ 메타데이터(다국어 제목/설명) 업데이트 완료!")
        time.sleep(1)

        # [3] 기존 자막 목록 불러오기 (덮어쓰기 판별을 위해)
        st.info("🔄 자막 업로드 준비 중...")
        captions_response = youtube.captions().list(part="snippet", videoId=video_id).execute()
        existing_captions = {item['snippet']['language']: item['id'] for item in captions_response.get('items', [])}

        # [4] 자막(SRT) 업로드 루프
        success_captions = 0
        for lang_name, data in translated_data.items():
            en_lang_name = LANGUAGES[lang_name + " / " + lang_name.split(" / ")[1]] if " / " not in lang_name else LANGUAGES.get(lang_name)
            yt_code = YT_LANG_CODES.get(en_lang_name)
            
            if yt_code:
                media = MediaIoBaseUpload(io.BytesIO(data['srt'].encode('utf-8-sig')), mimetype='application/x-subrip')
                caption_body = {
                    "snippet": {
                        "videoId": video_id,
                        "language": yt_code,
                        "name": lang_name.split(" / ")[0], # 예: "한국어"
                        "isDraft": False
                    }
                }
                
                try:
                    if yt_code in existing_captions:
                        # 이미 자막이 있다면 Update (덮어쓰기)
                        caption_body["id"] = existing_captions[yt_code]
                        youtube.captions().update(part="snippet", body=caption_body, media_body=media).execute()
                    else:
                        # 자막이 없다면 Insert (새로 추가)
                        youtube.captions().insert(part="snippet", body=caption_body, media_body=media).execute()
                    success_captions += 1
                except Exception as cap_e:
                    st.warning(f"⚠️ {lang_name} 자막 처리 중 에러 발생: {cap_e}")

        st.success(f"✅ 자막 업로드 완료! ({success_captions}개 언어 전송 성공)")
        return True
    
    except Exception as e:
        st.error(f"🚨 유튜브 API 통신 중 심각한 에러 발생: {e}")
        return False

# --- UI 레이아웃 구성 ---
st.set_page_config(page_title="우타튜브 올인원 시스템", page_icon="🚀", layout="wide")
st.title("우타튜브 다국어 동기화 공장🚀")
st.subheader("ウタチューブ・多言語同期工場🚀")
st.markdown("---")

is_locked = st.session_state.is_processing

# 📂 [1단계] 영상 링크 및 정보 입력
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🔗 1단계: 대상 영상 및 자막 / 対象動画および字幕")
    st.info("유튜브 스튜디오에 미리 업로드한 영상의 링크와, 원본 일본어 자막을 넣어주세요.")
    
    video_url = st.text_input("🔗 유튜브 영상 링크 / YouTube動画リンク", placeholder="예: https://youtu.be/xxxxxxxxx", disabled=is_locked)
    
    uploaded_srt = st.file_uploader("📂 원본 일본어 자막 파일 (.srt) / 元の日本語字幕ファイル", type=["srt"], disabled=is_locked)
    original_srt = None
    original_content = ""
    
    if uploaded_srt is not None:
        try:
            original_content = uploaded_srt.read().decode('utf-8-sig')
            original_srt = pysrt.from_string(original_content)
            if len(original_srt) == 0:
                st.error("🚨 자막 형식이 올바르지 않거나 비어있습니다.")
            else:
                st.success(f"✅ 자막 파일 인식 완료! (총 {len(original_srt)}줄)")
        except Exception as e:
            st.error(f"🚨 자막 파일을 읽는 중 오류가 발생했습니다: {e}")

with col2:
    st.subheader("📋 2단계: 기준 메타데이터 / 基準メタデータ")
    video_title = st.text_input("🔤 원본 일본어 제목 (최대 100자) / 動画のタイトル", max_chars=100, value=st.session_state.video_title, disabled=is_locked)
    st.session_state.video_title = video_title
    
    video_desc = st.text_area("📋 원본 일본어 설명 (최대 5000자) / 動画の説明", max_chars=5000, height=120, disabled=is_locked)
    video_license = st.text_area("🎵 음원 라이선스 정보 (선택) / 音源ライセンス情報", height=85, disabled=is_locked)

st.markdown("---")

# 🌐 [2단계] 글로벌 번역 설정
st.subheader("🌐 3단계: 30개 국어 번역 타겟 선택 / 30ヶ国語の翻訳ターゲット選択")
btn_c1, btn_c2, _ = st.columns([1, 1, 6])
with btn_c1: st.button("전체 선택 / 全選択", on_click=select_all, use_container_width=True, disabled=is_locked)
with btn_c2: st.button("전체 해제 / 全解除", on_click=deselect_all, use_container_width=True, disabled=is_locked)

cols = st.columns(4)
for i, lang in enumerate(LANGUAGES.keys()):
    with cols[i % 4]: st.checkbox(lang, key=f"chk_{lang}", disabled=is_locked)

selected_langs = [lang for lang in LANGUAGES.keys() if st.session_state[f"chk_{lang}"]]
st.markdown("---")

# ⚡ 작업 제어단
if not st.session_state.is_processing:
    btn_label = f"✨ 번역 공장 가동시작 ({len(selected_langs)}개 언어)" if selected_langs else "✨ 번역 공장 가동시작 (선택된 언어 없음)"
    
    if st.button(btn_label, type="primary", use_container_width=True):
        if not video_url.strip(): st.warning("유튜브 영상 링크를 입력해줘, 주인.")
        elif uploaded_srt is None or not original_srt: st.warning("원본 SRT 자막 파일을 업로드해줘.")
        elif not video_title.strip() or not video_desc.strip(): st.warning("원본 제목과 설명을 채워줘.")
        elif not selected_langs: st.warning("번역해서 진출할 국가를 최소 하나 이상 선택해줘.")
        else:
            st.session_state.is_processing = True
            st.session_state.results = {}
            st.session_state.balloons_shown = False 
            st.rerun()
else:
    if st.button("🛑 공장 비상 정지 (작업 중단)", type="primary", use_container_width=True):
        st.session_state.is_processing = False
        st.warning("작업을 중단했어.")
        time.sleep(1)
        st.rerun()

# --- 실제 번역 루프 실행 엔진 ---
if st.session_state.is_processing and video_url.strip() and original_srt and video_title.strip():
    total_langs = len(selected_langs)
    st.subheader("📊 실시간 변환 현황 / リアルタイム進行状況")
    
    total_bar = st.progress(0)
    total_txt = st.empty()
    lang_bar = st.progress(0)
    lang_txt = st.empty()
    
    for idx, lang in enumerate(selected_langs):
        if not st.session_state.is_processing: break
        clean_name = lang.split(" / ")[0]
        total_txt.text(f"📊 전체 공정률: {idx+1}/{total_langs} 언어 처리 중... ({clean_name})")
        
        target_lang_en = LANGUAGES[lang]
        output_data = translate_all_in_one(original_content, original_srt, video_title, video_desc, video_license, target_lang_en, lang_bar, lang_txt)
        
        if output_data:
            st.session_state.results[clean_name] = output_data
        total_bar.progress((idx + 1) / total_langs)
        
    st.session_state.is_processing = False
    st.rerun()

# 🚀 [3단계] 최종 원클릭 유튜브 업데이트 대시보드
if st.session_state.results and not st.session_state.is_processing:
    st.markdown("---")
    st.subheader("🚀 4단계: 유튜브 스튜디오 동기화 대시보드")
    
    if not st.session_state.balloons_shown:
        st.balloons()
        st.session_state.balloons_shown = True
        
    results = st.session_state.results
    title_clean = st.session_state.video_title.strip()
    
    success_count = len(results)
    failed_langs = [lang for lang in selected_langs if lang.split(" / ")[0] not in results]
    
    st.success(f"🎉 번역 완료: 총 {success_count}개 언어 성공")
    if failed_langs:
        st.error(f"🚨 번역 누락 및 실패 언어 ({len(failed_langs)}개): {', '.join(failed_langs)}")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for lang_name, data in results.items():
            zip_file.writestr(f"{title_clean}_{lang_name}.srt", data['srt'].encode("utf-8-sig"))
    zip_buffer.seek(0)
    
    st.download_button(
        label=f"📦 오프라인 자막 백업본 ({title_clean}_자막들.zip) 다운로드",
        data=zip_buffer, file_name=f"{title_clean}_자막들.zip", mime="application/zip", use_container_width=True
    )
    
    st.markdown("### 🛰️ 유튜브 스튜디오 일괄 자동 전송 (API 덮어쓰기)")
    st.info("아래 버튼을 누르면 입력한 유튜브 영상에 다국어 메타데이터와 30개국 자막이 자동으로 삽입됩니다.")
    
    if st.button("🚀 유튜브 서버에 데이터 동기화 시작 (Update)", type="primary", use_container_width=True):
        with st.spinner("구글 권한 확인 및 유튜브 통신 중..."):
            success = update_youtube_video(video_url, results)
            if success:
                st.success("🎉 대성공! 유카의 유튜브 영상에 30개 국어 정보가 완벽하게 주입되었습니다!")
