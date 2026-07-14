import streamlit as st
from google import genai
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

# --- 제미나이 API 세팅 (클라우드 크레딧 연결) ---
api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
if api_key:
    try:
        # 💡 핵심: vertexai=True로 46만 원 크레딧 서버에 연결!
        client = genai.Client(api_key=api_key, vertexai=True)
    except Exception as e:
        st.error(f"🚨 제미나이 클라이언트 초기화 중 에러가 발생했어: {e}")
        st.stop()
else:
    st.error("앗, Secrets에 GEMINI_API_KEY가 없어. 확인해줘, 주인!")
    st.stop()

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
    "한국어 / 韓国語 (자막은 번역되지 않음)": "Korean", "힌디어 / ヒンディー語": "Hindi"
}

# 유튜브 업로드 시 사용되는 언어 코드
YT_LANG_CODES = {
    "Dutch": "nl", "Norwegian": "no", "Danish": "da", "German": "de",
    "Russian": "ru", "Malay": "ms", "Vietnamese": "vi", "Swedish": "sv",
    "Spanish": "es", "Arabic": "ar", "English": "en", "Uzbek": "uz",
    "Ukrainian": "uk", "Italian": "it", "Indonesian": "id", "Japanese": "ja",
    "Simplified Chinese": "zh-Hans", "Traditional Chinese (Taiwan)": "zh-TW",
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
if 'balloons_shown' not in st.session_state: st.session_state.balloons_shown = False 
if 'upload_success' not in st.session_state: st.session_state.upload_success = False
if 'error_logs' not in st.session_state: st.session_state.error_logs = [] # 🌟 에러 로그 저장용 배열 추가

def select_all():
    for lang in LANGUAGES.keys(): st.session_state[f"chk_{lang}"] = True
def deselect_all():
    for lang in LANGUAGES.keys(): st.session_state[f"chk_{lang}"] = False

def extract_video_id(url):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None

# --- 🌟 백그라운드 구글 인증 (OAuth 통행증) ---
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
        err_msg = f"인증 정보 로드 실패 (Secrets 확인 필요): {e}"
        st.error(f"🚨 {err_msg}")
        st.session_state.error_logs.append(err_msg)
        return None

# 유튜브 원본 메타데이터 가져오기 함수
def fetch_youtube_metadata(video_url):
    video_id = extract_video_id(video_url)
    if not video_id: return None, None
    creds = get_credentials()
    if not creds: return None, None
    try:
        youtube = build('youtube', 'v3', credentials=creds)
        res = youtube.videos().list(part="snippet", id=video_id).execute()
        if res.get('items'):
            snippet = res['items'][0]['snippet']
            return snippet.get('title', ''), snippet.get('description', '')
    except Exception as e:
        err_msg = f"메타데이터 불러오기 실패: {e}"
        st.error(f"🚨 {err_msg}")
        st.session_state.error_logs.append(err_msg)
    return None, None

# --- 번역 엔진 (선택된 모델 사용) ---
def translate_all_in_one(original_text, original_srt, orig_title, orig_desc, orig_license, target_lang, progress_bar, status_text, selected_model):
    is_korean = target_lang == "Korean"
    # 사용자가 선택한 모델을 그대로 반영
    model = genai.GenerativeModel(selected_model)
    
    # [1단계] 메타데이터 번역
    prompt_meta = f"""
    You are an expert YouTube SEO translator. Translate the following YouTube Title and Description to {target_lang}.
    CRITICAL RULES:
    1. Maintain the overall structure, tone, and formatting of the original.
    2. Keep ALL brackets, emojis, and special symbols exactly as they are.
    3. The translated Title MUST be strictly under 100 characters (including spaces).
    4. Translate the phrase "사용된 음원 라이선스 코드" into {target_lang}.
    5. Output strictly in the following format without markdown code blocks:
    [TITLE_START]
    (Translated Title in {target_lang})
    [TITLE_END]
    [DESC_START]
    (Translated Description in {target_lang})
    [DESC_END]
    [LICENSE_LABEL_START]
    (Translated phrase for "사용된 음원 라이선스 코드" in {target_lang})
    [LICENSE_LABEL_END]

    Original Title: {orig_title}
    Original Description: {orig_desc}
    """
    
    t_title, t_desc_raw, t_label = "", "", ""
    meta_attempt = 1
    meta_success = False
    
    while meta_attempt <= 3:
        if not st.session_state.is_processing: return None
        status_text.text(f"[{target_lang}] 1단계: 제목/설명 번역 중... ({meta_attempt}/3)")
        progress_bar.progress(int(meta_attempt * (50 / 3)))
        
        try:
            response = model.generate_content(prompt_meta)
            text = response.text.strip()
            
            if "[TITLE_START]" not in text or "[DESC_START]" not in text or "[LICENSE_LABEL_START]" not in text:
                raise ValueError("Missing Tags")
            
            t_title = text.split("[TITLE_START]")[1].split("[TITLE_END]")[0].strip()
            t_desc_raw = text.split("[DESC_START]")[1].split("[DESC_END]")[0].strip()
            t_label = text.split("[LICENSE_LABEL_START]")[1].split("[LICENSE_LABEL_END]")[0].strip()
            
            if len(t_title) > 100:
                status_text.text(f"⚠️ [{target_lang}] 제목 길이 초과({len(t_title)}자). AI에게 수정 요청 중...")
                prompt_meta += f"\n\nCorrection Request: Your previous translated title '{t_title}' is {len(t_title)} characters. It MUST be strictly under 100 characters. Please shorten it."
                time.sleep(2)
                meta_attempt += 1
                continue
                
            meta_success = True
            break
            
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                status_text.text("⚠️ API 한도 도달! 25초 대기...")
                time.sleep(25)
                continue
            status_text.text(f"⚠️ [{target_lang}] 텍스트 파싱 에러. 양식 수정 요청 중...")
            prompt_meta += f"\n\nCorrection Request: Your output format was incorrect. Please strictly follow the [TITLE_START], [DESC_START], and [LICENSE_LABEL_START] tag format."
            time.sleep(2)
            meta_attempt += 1

    if not meta_success:
        err_msg = f"[{target_lang}] 제목/설명 번역 3회 실패. 건너뜁니다."
        status_text.text(f"❌ {err_msg}")
        st.session_state.error_logs.append(err_msg) # 실패 로그 저장
        return None

    if orig_license and orig_license.strip():
        t_desc_final = f"{t_desc_raw}\n\n{t_label}\n{orig_license.strip()}"
    else:
        t_desc_final = t_desc_raw

    if is_korean:
        status_text.text(f"[{target_lang}] 완료! (한국어 메타데이터 완성)")
        progress_bar.progress(100)
        return {"title": t_title, "desc": t_desc_final, "srt": None}

    # [2단계] 자막(SRT) 번역
    prompt_srt = f"""
    You are an expert YouTube subtitle translator. 
    Translate the given SRT subtitles accurately into {target_lang}.
    
    CRITICAL RULES:
    1. Keep exactly {len(original_srt)} blocks. Do not merge or split subtitle lines.
    2. TONE & NUANCE (VERY IMPORTANT): Preserve the exact tone, formality, and sentence structure of the original text.
       - If the original text is a single word or a fragment (e.g., just a noun, exclamation), translate it as a single word or fragment. DO NOT force it into a grammatically complete sentence.
       - If the original text is informal/casual (e.g. 반말 in Japanese/Korean), translate it into the most natural informal/casual equivalent in {target_lang}.
       - If it is formal (존댓말/敬語), keep it formal.
       - Capture the raw emotion, spoken vibe, and briefness exactly as it is.
    3. Output strictly in raw SRT format inside the tags:
    [SRT_START]
    (Translated raw SRT text)
    [SRT_END]
    
    Original SRT:
    {original_text}
    """
    
    srt_attempt = 1
    final_srt_string = None
    
    while srt_attempt <= 3:
        if not st.session_state.is_processing: return None
        status_text.text(f"[{target_lang}] 2단계: 자막 번역 및 말투 살리는 중... ({srt_attempt}/3)")
        progress_bar.progress(50 + int(srt_attempt * (50 / 3)))
        
        try:
            response = model.generate_content(prompt_srt)
            text = response.text.strip()
            
            if "[SRT_START]" not in text or "[SRT_END]" not in text:
                raise ValueError("Missing SRT Tags")
                
            srt_part = text.split("[SRT_START]")[1].split("[SRT_END]")[0].strip()
            translated_srt = pysrt.from_string(srt_part)
            
            if len(original_srt) != len(translated_srt):
                status_text.text(f"⚠️ [{target_lang}] 자막 줄 수 불일치! (원문:{len(original_srt)}줄 / 번역:{len(translated_srt)}줄) AI에게 수정 요청 중...")
                prompt_srt += f"\n\nCorrection Request: The original SRT has exactly {len(original_srt)} lines, but your translation returned {len(translated_srt)} lines. You MUST keep exactly {len(original_srt)} lines without merging or splitting them."
                time.sleep(2)
                srt_attempt += 1
                continue
            
            final_srt_output = []
            for i in range(len(original_srt)):
                orig = original_srt[i]
                trans_text = translated_srt[i].text
                start_str = f"{orig.start.hours:02}:{orig.start.minutes:02}:{orig.start.seconds:02},{orig.start.milliseconds:03}"
                end_str = f"{orig.end.hours:02}:{orig.end.minutes:02}:{orig.end.seconds:02},{orig.end.milliseconds:03}"
                final_srt_output.append(f"{orig.index}\n{start_str} --> {end_str}\n{trans_text}")
            
            final_srt_string = "\n\n".join(final_srt_output)
            break
            
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                status_text.text("⚠️ API 한도 도달! 25초 대기...")
                time.sleep(25)
                continue
            status_text.text(f"⚠️ [{target_lang}] 자막 파싱 에러. 양식 수정 요청 중...")
            prompt_srt += f"\n\nCorrection Request: Your output format was incorrect. Please strictly provide the raw SRT text inside [SRT_START] and [SRT_END] tags."
            time.sleep(2)
            srt_attempt += 1

    if final_srt_string:
        status_text.text(f"[{target_lang}] 전 공정 완료! 🚀")
        progress_bar.progress(100)
        return {"title": t_title, "desc": t_desc_final, "srt": final_srt_string}
    else:
        err_msg = f"[{target_lang}] 자막 번역 최종 실패 (메타데이터만 저장됨)"
        status_text.text(f"⚠️ {err_msg}")
        st.session_state.error_logs.append(err_msg)
        progress_bar.progress(100)
        return {"title": t_title, "desc": t_desc_final, "srt": None}


# --- 🌟 유튜브 업데이트 로직 ---
def update_youtube_video(video_url, translated_data):
    video_id = extract_video_id(video_url)
    if not video_id: 
        st.session_state.error_logs.append("🚨 유효하지 않은 영상 링크입니다.")
        return False

    creds = get_credentials()
    if not creds: return False
    youtube = build('youtube', 'v3', credentials=creds)
    
    try:
        # [1] 기존 영상 메타데이터 불러오기 및 병합
        video_response = youtube.videos().list(part="snippet,localizations", id=video_id).execute()
        if not video_response.get('items'):
            st.session_state.error_logs.append("🚨 영상을 찾을 수 없습니다. (ID 확인 필요)")
            return False
            
        video_item = video_response['items'][0]
        snippet = video_item['snippet']
        localizations = video_item.get('localizations', {})
        
        if 'defaultLanguage' not in snippet: snippet['defaultLanguage'] = 'ja'
        if 'defaultAudioLanguage' not in snippet: snippet['defaultAudioLanguage'] = 'ja'

        for lang_name, data in translated_data.items():
            en_lang_name = next((val for key, val in LANGUAGES.items() if key.startswith(lang_name)), None)
            if not en_lang_name: continue
            
            yt_code = YT_LANG_CODES.get(en_lang_name)
            if yt_code:
                localizations[yt_code] = {
                    "title": data["title"],
                    "description": data["desc"]
                }
        
        # [2] 변경된 다국어 제목/설명 일괄 업데이트
        youtube.videos().update(
            part="snippet,localizations",
            body={
                "id": video_id,
                "snippet": snippet,
                "localizations": localizations
            }
        ).execute()
        time.sleep(1)

        # [3] 자막 업로드 루프
        captions_response = youtube.captions().list(part="snippet", videoId=video_id).execute()
        existing_captions = {item['snippet']['language']: item['id'] for item in captions_response.get('items', [])}

        for lang_name, data in translated_data.items():
            if not data.get('srt'): continue
            
            en_lang_name = next((val for key, val in LANGUAGES.items() if key.startswith(lang_name)), None)
            yt_code = YT_LANG_CODES.get(en_lang_name)
            
            if yt_code:
                media = MediaIoBaseUpload(io.BytesIO(data['srt'].encode('utf-8-sig')), mimetype='application/x-subrip')
                caption_body = {
                    "snippet": {
                        "videoId": video_id,
                        "language": yt_code,
                        "name": "", 
                        "isDraft": False
                    }
                }
                
                try:
                    if yt_code in existing_captions:
                        caption_body["id"] = existing_captions[yt_code]
                        youtube.captions().update(part="snippet", body=caption_body, media_body=media).execute()
                    else:
                        youtube.captions().insert(part="snippet", body=caption_body, media_body=media).execute()
                except Exception as cap_e:
                    err_msg = f"[{lang_name}] 자막 업로드 중 에러 발생: {cap_e}"
                    st.warning(f"⚠️ {err_msg}")
                    st.session_state.error_logs.append(err_msg)

        return True
    
    except Exception as e:
        err_msg = f"유튜브 API 통신 중 심각한 에러 발생: {e}"
        st.error(f"🚨 {err_msg}")
        st.session_state.error_logs.append(err_msg)
        return False


# --- UI 레이아웃 구성 ---
st.set_page_config(page_title="우타튜브 다국어 올인원 공장", page_icon="🚀", layout="wide")
st.title("우타튜브 다국어 올인원 공장🚀")
st.subheader("ウタチューブ・多言語オールインワン工場🚀")
st.markdown("---")

is_locked = st.session_state.is_processing

# 📂 [1단계] 영상 링크 및 정보 입력
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🔗 1단계: 대상 영상 및 자막 / 対象動画および字幕")
    st.info("유튜브 스튜디오에 미리 업로드한 영상의 링크와, 원본 일본어 자막을 넣어주세요.\n\nYouTubeスタジオに事前にアップロードした動画のリンクと、元の日本語字幕を入れてください。")
    
    video_url = st.text_input("🔗 유튜브 영상 링크 / YouTube動画リンク", placeholder="예: https://youtu.be/xxxxxxxxx", disabled=is_locked)
    
    uploaded_srt = st.file_uploader("📂 원본 일본어 자막 파일 (.srt) / 元の日本語字幕ファイル", type=["srt"], disabled=is_locked)
    
    custom_filename = st.text_input("💾 생성할 자막 파일 이름 (접두사) / 生成する字幕ファイル名 (接頭辞)", value="", placeholder="예: 영상 제목을 넣어주세요", disabled=is_locked)
    
    original_srt = None
    original_content = ""
    
    if uploaded_srt is not None:
        try:
            original_content = uploaded_srt.read().decode('utf-8-sig')
            original_srt = pysrt.from_string(original_content)
            
            if len(original_srt) == 0:
                st.error("🚨 자막 내용이 비어있습니다.")
            else:
                is_valid = True
                for i in range(len(original_srt)):
                    sub = original_srt[i]
                    if sub.end < sub.start:
                        st.error(f"🚨 무결성 에러: {sub.index}번 자막의 종료 시간이 시작 시간보다 빠릅니다! 타임라인을 확인해주세요.")
                        is_valid = False
                        break
                
                if is_valid:
                    st.success(f"✅ 자막 무결성 검증 완료! (총 {len(original_srt)}줄 문제없음)")
        except Exception as e:
            st.error(f"🚨 자막 파일을 읽는 중 오류가 발생했습니다: {e}")

with col2:
    st.subheader("📋 2단계: 기준 메타데이터 / 基準メタデータ")
    
    metadata_source = st.radio(
        "📝 메타데이터(제목/설명) 입력 방식 / メタデータ入力方式",
        options=["유튜브 스튜디오 원본 가져오기 (기본) / YouTubeスタジオから取得", "새로 직접 입력하기 / 直接入力"],
        index=0, disabled=is_locked
    )
    
    if "가져오기" in metadata_source:
        st.info("💡 공장 가동을 누르면 입력한 링크의 유튜브 영상에서 제목과 설명을 자동으로 끌어와 번역합니다.")
        video_title = ""
        video_desc = ""
    else:
        video_title = st.text_input("🔤 원본 일본어 제목 (최대 100자) / 動画のタイトル", max_chars=100, disabled=is_locked)
        video_desc = st.text_area("📋 원본 일본어 설명 (최대 5000자) / 動画の説明", max_chars=5000, height=120, disabled=is_locked)
        
    video_license = st.text_area("🎵 음원 라이선스 정보 (선택) / 音源ライセンス情報", height=85, disabled=is_locked)

st.markdown("---")

# 🌐 [2단계] 글로벌 번역 설정
st.subheader("🌐 3단계: 다국어 번역 타겟 선택 / 翻訳ターゲット選択")
btn_c1, btn_c2, _ = st.columns([1, 1, 6])
with btn_c1: st.button("전체 선택 / 全選択", on_click=select_all, use_container_width=True, disabled=is_locked)
with btn_c2: st.button("전체 해제 / 全解除", on_click=deselect_all, use_container_width=True, disabled=is_locked)

cols = st.columns(4)
for i, lang in enumerate(LANGUAGES.keys()):
    with cols[i % 4]: st.checkbox(lang, key=f"chk_{lang}", disabled=is_locked)

selected_langs = [lang for lang in LANGUAGES.keys() if st.session_state[f"chk_{lang}"]]
st.markdown("---")

# 🤖 [추가된 기능] 모델 선택 UI
st.subheader("🤖 4단계: AI 모델 선택 / AIモデル選択")
selected_model_name = st.radio(
    "번역에 사용할 제미나이 AI 모델을 선택해주세요:",
    options=["gemini-3.5-flash (권장 / 고품질)", "gemini-3.1-flash-lite (가벼운 작업 / 빠른 속도)"],
    index=0, 
    disabled=is_locked,
    horizontal=True
)
# 실제 모델 코드 추출 ('gemini-3.5-flash' 등)
target_model_code = selected_model_name.split(" ")[0]

st.markdown("---")

# ⚡ CSS 주입을 통해 Primary 버튼 글자 크기를 키우고 스타일을 강조
st.markdown("""
<style>
div.stButton > button[kind="primary"] {
    font-size: 26px !important;
    padding: 20px !important;
    font-weight: 900 !important;
}
div.stButton > button[kind="primary"] p {
    font-size: 26px !important;
    font-weight: 900 !important;
}
</style>
""", unsafe_allow_html=True)


# ⚡ 작업 제어단
if not st.session_state.is_processing:
    lang_count = len(selected_langs)
    # 버튼에 선택된 언어 개수 동적 반영
    btn_label = f"✨ 원클릭 공장 가동시작 (총 {lang_count}개 언어 / 번역 + 자동업로드)" if lang_count > 0 else "✨ 공장 가동시작 (선택된 언어 없음)"
    
    if st.button(btn_label, type="primary", use_container_width=True):
        if not video_url.strip(): 
            st.warning("유튜브 영상 링크를 입력해줘, 주인.")
        elif uploaded_srt is None or not original_srt: 
            st.warning("원본 SRT 자막 파일을 업로드해줘.")
        elif not selected_langs: 
            st.warning("번역해서 진출할 국가를 최소 하나 이상 선택해줘.")
        else:
            # 🌟 새 작업 시작 시 에러 로그 초기화
            st.session_state.error_logs = []
            
            if "가져오기" in metadata_source:
                with st.spinner("유튜브에서 원본 메타데이터를 불러오는 중..."):
                    fetched_title, fetched_desc = fetch_youtube_metadata(video_url)
                    if not fetched_title:
                        st.error("🚨 메타데이터를 불러오지 못했어. 영상 링크가 맞는지 확인하거나 에러 로그를 확인해줘!")
                        st.stop()
                    else:
                        st.session_state.run_title = fetched_title
                        st.session_state.run_desc = fetched_desc
            else:
                if not video_title.strip() or not video_desc.strip():
                    st.warning("직접 입력 모드입니다. 원본 제목과 설명을 채워줘.")
                    st.stop()
                st.session_state.run_title = video_title
                st.session_state.run_desc = video_desc
                
            st.session_state.is_processing = True
            st.session_state.results = {}
            st.session_state.balloons_shown = False 
            st.session_state.upload_success = False
            # 세션에 선택한 모델 코드 저장
            st.session_state.selected_model = target_model_code
            st.rerun()
else:
    if st.button("🛑 공장 비상 정지 (작업 중단)", type="primary", use_container_width=True):
        st.session_state.is_processing = False
        st.warning("작업을 중단했어.")
        time.sleep(1)
        st.rerun()

# --- 실제 번역 루프 및 ⚡ 원클릭 자동 업로드 엔진 ---
if st.session_state.is_processing:
    total_langs = len(selected_langs)
    st.subheader(f"📊 실시간 번역 공정 진행 중 ({st.session_state.selected_model} 가동중)")
    
    total_bar = st.progress(0)
    total_txt = st.empty()
    lang_bar = st.progress(0)
    lang_txt = st.empty()
    
    for idx, lang in enumerate(selected_langs):
        if not st.session_state.is_processing: break
        clean_name = lang.split(" / ")[0]
        total_txt.text(f"📊 전체 공정률: {idx+1}/{total_langs} 언어 처리 중... ({clean_name})")
        
        target_lang_en = LANGUAGES[lang]
        
        # 선택된 모델을 인자로 넘김
        output_data = translate_all_in_one(
            original_content, original_srt, 
            st.session_state.run_title, st.session_state.run_desc, video_license, 
            target_lang_en, lang_bar, lang_txt,
            st.session_state.selected_model
        )
        
        if output_data:
            st.session_state.results[clean_name] = output_data
        total_bar.progress((idx + 1) / total_langs)
        
    # ✨ 번역이 끝나면 유튜브로 자동 원클릭 전송 시작!
    if st.session_state.results and st.session_state.is_processing:
        st.subheader("🚀 2단계: 유튜브 스튜디오 자동 동기화 중 (API 일괄 전송)")
        total_txt.text("번역 완료! 유튜브 서버에 번역된 제목/설명/자막을 밀어넣고 있습니다...")
        lang_txt.empty()
        lang_bar.empty()
        
        with st.spinner("구글 권한 확인 및 유튜브 통신 중... (잠시만 기다려주세요)"):
            success = update_youtube_video(video_url, st.session_state.results)
            st.session_state.upload_success = success
            
    st.session_state.is_processing = False
    st.rerun()

# 🚀 [결과 대시보드] 원클릭 종료 후 화면
if st.session_state.results and not st.session_state.is_processing:
    st.markdown("---")
    st.subheader("🚀 모든 작업 완료 (대시보드)")
    
    if not st.session_state.balloons_shown:
        if st.session_state.upload_success:
            st.balloons()
        st.session_state.balloons_shown = True
        
    results = st.session_state.results
    success_count = len(results)
    failed_langs = [lang for lang in selected_langs if lang.split(" / ")[0] not in results]
    
    # --- 🚨 에러 로그 노출 UI 추가 ---
    if st.session_state.error_logs:
        st.error("🚨 작업 중 아래와 같은 문제(에러)들이 발생했습니다. 확인해주세요!")
        for error in st.session_state.error_logs:
            st.write(f"- {error}")
        st.markdown("---")

    # 종합 결과 메시지
    if st.session_state.upload_success and not st.session_state.error_logs:
        st.success(f"🎉 대성공! {success_count}개 국어 번역 및 유튜브 스튜디오 자동 업로드가 완벽하게 에러 없이 끝났습니다!")
    elif st.session_state.upload_success and st.session_state.error_logs:
        st.warning(f"⚠️ {success_count}개 언어 작업이 완료되었으나, 일부 과정에서 에러가 발생했습니다. (위의 에러 로그 참조)")
    else:
        st.error(f"❌ 번역은 일부 완료되었으나, 유튜브 자동 업로드 중 치명적인 문제가 발생했습니다.")
        
    if failed_langs:
        st.error(f"🚨 번역 자체를 실패한 언어 ({len(failed_langs)}개): {', '.join(failed_langs)}")
    
    # 압축 파일 생성
    zip_buffer = io.BytesIO()
    file_prefix = custom_filename.strip() if custom_filename.strip() else "자막백업"
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for lang_name, data in results.items():
            if data['srt']: 
                zip_file.writestr(f"{file_prefix}_{lang_name}.srt", data['srt'].encode("utf-8-sig"))
    zip_buffer.seek(0)
    
    st.markdown("### 💾 오프라인 자막 보관")
    st.info("💡 브라우저 보안 정책상 파일 자동 다운로드는 지원되지 않습니다. 아래 버튼을 눌러 번역된 자막 파일들을 보관하세요.")
    st.download_button(
        label=f"📦 오프라인 자막 백업본 ({file_prefix}_자막들.zip) 수동 다운로드",
        data=zip_buffer, file_name=f"{file_prefix}_자막들.zip", mime="application/zip", use_container_width=True
    )
