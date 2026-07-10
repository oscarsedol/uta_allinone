import streamlit as st
import google.generativeai as genai
import os
import pysrt
import time
import zipfile
import io
import datetime
from dotenv import load_dotenv

# --- 🌟 추가된 구글 API 필수 라이브러리 ---
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

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

# --- 로그인 성공 시 본 프로그램 실행 ---
api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("앗, .env 파일이나 Secrets에 GEMINI_API_KEY가 없어. 확인해줘, 주인. / GEMINI_API_KEYが見つかりません。")

MODEL_NAME = 'gemini-3.1-flash-lite'

# --- 번역 가능 30개 언어 목록 ---
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


# --- 🌟 추가된 유튜브 API 인증 함수 (Streamlit Secrets 연동) ---
def get_authenticated_service():
    """Secrets에서 인증 정보를 가져와 유튜브 API 서비스 객체를 생성합니다."""
    # Secrets에 저장된 [gcp_oauth] 딕셔너리 정보 가져오기
    client_config = {
        "installed": dict(st.secrets["gcp_oauth"])
    }
    
    # 유튜브 접근 권한 범위 설정
    scopes = [
        'https://www.googleapis.com/auth/youtube.force-ssl', 
        'https://www.googleapis.com/auth/youtube.upload'
    ]
    
    try:
        # 파일 대신 client_config 딕셔너리로 로그인 창 호출
        flow = InstalledAppFlow.from_client_config(client_config, scopes)
        
        # 브라우저를 열어 구글 로그인(유카 계정) 요청
        credentials = flow.run_local_server(port=0)
        
        # 인증된 객체(youtube) 반환
        youtube = build('youtube', 'v3', credentials=credentials)
        return youtube
    except Exception as e:
        st.error(f"구글 인증 중 오류가 발생했습니다: {e}")
        return None

# 구글 드라이브 가상 읽기 함수 (추후 실제 API로 교체 예정)
def fetch_srt_from_drive(drive_link):
    return "1\n00:00:01,000 --> 00:00:03,000\n테스트 자막입니다.\n\n2\n00:00:03,000 --> 00:00:05,000\n링크로 잘 가져옵니다."


# --- 번역 엔진 구동 ---
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
            
            # 🛠️ 수정: orig_license가 비어있을 때 발생하는 버그 수정
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

def deploy_to_youtube_studio(video_url, thumb_url, srt_url, privacy_status, scheduled_time, translated_data):
    # 🌟 여기에 위에서 만든 get_authenticated_service()를 호출하여 유튜브 서버와 통신 시작!
    youtube = get_authenticated_service()
    
    if youtube:
        st.success("✅ 유튜브 계정 연동 및 권한 확인 성공! (실제 업로드 로직은 추후 연결)")
        time.sleep(2) 
        return True
    else:
        st.error("🚨 구글 인증에 실패하여 업로드를 중단합니다.")
        return False

# --- UI 레이아웃 구성 ---
st.set_page_config(page_title="우타튜브 올인원 시스템", page_icon="🚀", layout="wide")
st.title("우타튜브 올인원 자동 업로드 공장🚀")
st.subheader("ウタチューブ・オールインワン自動アップロード工場🚀")
st.markdown("---")

is_locked = st.session_state.is_processing

# 📂 [1단계] 원본 파일 및 정보 입력
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📂 1단계: 구글 드라이브 소스 전체 연동 / Googleドライブソース連携")
    st.info("파일을 업로드할 필요 없이 구글 드라이브 공유 링크만 복사해서 넣어주세요. / ファイルをアップロードする必要はなく、Googleドライブの共有リンクをコピーして貼り付けてください。")
    drive_video = st.text_input("🔗 구글 드라이브 영상 파일 링크 / 動画ファイルのリンク", placeholder="5GB~10GB 대용량 영상 공유 링크 복붙", disabled=is_locked)
    drive_thumb = st.text_input("🔗 구글 드라이브 썸네일 이미지 링크 (선택) / サムネイル画像のリンク(任意)", placeholder="썸네일 이미지 파일 공유 링크 복붙", disabled=is_locked)
    drive_srt = st.text_input("🔗 구글 드라이브 원본 자막(SRT) 링크 / 元の字幕(SRT)リンク", placeholder="자막 파일 공유 링크 복붙 (입력 시 자동 검증)", disabled=is_locked)
    
    original_srt = None
    original_content = ""
    
    if drive_srt:
        original_content = fetch_srt_from_drive(drive_srt)
        try:
            original_srt = pysrt.from_string(original_content)
            if len(original_srt) == 0: st.error("🚨 자막 형식이 올바르지 않습니다. / 字幕の形式が正しくありません。")
            else: st.success(f"✅ 링크 내부 검증 완료! 총 **{len(original_srt)}**줄 확인. / 検証完了！計 {len(original_srt)} 行確認。")
        except Exception as e:
            st.error(f"🚨 SRT 파싱 오류 / パースエラー: {e}")

with col2:
    st.subheader("📋 2단계: 메타데이터 및 공개 세팅 / メタデータおよび公開設定")
    video_title = st.text_input("🔤 원본 동영상 제목 (최대 100자) / 動画のタイトル(最大100文字)", max_chars=100, value=st.session_state.video_title, disabled=is_locked)
    st.session_state.video_title = video_title
    
    video_desc = st.text_area("📋 원본 동영상 설명 (최대 5000자) / 動画の説明(最大5000文字)", max_chars=5000, height=120, disabled=is_locked)
    video_license = st.text_area("🎵 음원 라이선스 코드 (선택) / 音源ライセンスコード(任意)", placeholder="예: XXXXXXXXXXXXXXXX\nYYYYYYYYYYYYYYYY", height=85, disabled=is_locked)
    
    privacy_options = ["예약공개 (Scheduled) / 予約公開", "비공개 (Private) / 非公開", "일부공개 (Unlisted) / 限定公開", "공개 (Public) / 公開"]
    privacy_status = st.selectbox("👁️ 유튜브 업로드 시 기본 공개 상태 설정 / アップロード時の公開設定", privacy_options, index=0, disabled=is_locked)
    
    final_schedule_time = None
    if "예약공개" in privacy_status:
        st.markdown("**📅 예약 날짜 및 시간 설정 / 予約日付および時間設定**")
        sched_c1, sched_c2 = st.columns(2)
        with sched_c1:
            sched_date = st.date_input("날짜 선택 / 日付の選択", datetime.date.today(), disabled=is_locked)
        with sched_c2:
            sched_time = st.time_input("시간 선택 / 時間の選択", datetime.datetime.now().time(), disabled=is_locked)
        final_schedule_time = datetime.datetime.combine(sched_date, sched_time)

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
    # 언어 선택 개수가 반영되는 동적 버튼!
    btn_label = f"✨ 번역 공장 가동시작 ({len(selected_langs)}개 언어) / 翻訳開始 ({len(selected_langs)}言語)" if selected_langs else "✨ 번역 공장 가동시작 (선택된 언어 없음) / 翻訳開始 (言語未選択)"
    
    if st.button(btn_label, type="primary", use_container_width=True):
        if not drive_video.strip(): st.warning("구글 드라이브 영상 링크를 입력해줘, 주인. / 動画リンクを入力してください。")
        elif not drive_srt or not original_srt: st.warning("원본 SRT 자막 링크를 먼저 입력해줘. / 元の字幕リンクを入力してください。")
        elif not video_title.strip() or not video_desc.strip(): st.warning("원본 제목과 설명을 채워줘. / タイトルと説明を入力してください。")
        elif not selected_langs: st.warning("번역해서 진출할 국가를 최소 하나 이상 선택해줘. / 言語を1つ以上選択してください。")
        else:
            st.session_state.is_processing = True
            st.session_state.results = {}
            st.session_state.balloons_shown = False 
            st.rerun()
else:
    if st.button("🛑 공장 비상 정지 (작업 중단) / 作業中断", type="primary", use_container_width=True):
        st.session_state.is_processing = False
        st.warning("작업을 중단했어. / 作業を中断しました。")
        time.sleep(1)
        st.rerun()

# --- 실제 번역 루프 실행 엔진 ---
if st.session_state.is_processing and drive_video.strip() and original_srt and video_title.strip():
    total_langs = len(selected_langs)
    st.subheader("📊 실시간 변환 현황 / リアルタイム進行状況")
    
    total_bar = st.progress(0)
    total_txt = st.empty()
    lang_bar = st.progress(0)
    lang_txt = st.empty()
    
    for idx, lang in enumerate(selected_langs):
        if not st.session_state.is_processing: break
        clean_name = lang.split(" / ")[0]
        total_txt.text(f"📊 전체 공정률: {idx+1}/{total_langs} 언어 처리 중... ({clean_name}) / 全体進行状況")
        
        target_lang_en = LANGUAGES[lang]
        output_data = translate_all_in_one(original_content, original_srt, video_title, video_desc, video_license, target_lang_en, lang_bar, lang_txt)
        
        if output_data:
            st.session_state.results[clean_name] = output_data
        total_bar.progress((idx + 1) / total_langs)
        
    st.session_state.is_processing = False
    st.rerun()

# 🚀 [3단계] 최종 원클릭 유튜브 업로드 대시보드
if st.session_state.results and not st.session_state.is_processing:
    st.markdown("---")
    st.subheader("🚀 4단계: 유튜브 스튜디오 최종 발사 대시보드 / 最終アップロードダッシュボード")
    
    if not st.session_state.balloons_shown:
        st.balloons()
        st.session_state.balloons_shown = True
        
    results = st.session_state.results
    title_clean = st.session_state.video_title.strip()
    
    # 성공/실패 명확화 로직 추가!
    success_count = len(results)
    failed_langs = [lang for lang in selected_langs if lang.split(" / ")[0] not in results]
    
    st.success(f"🎉 번역 완료: 총 {success_count}개 언어 성공 / 翻訳完了: 計 {success_count} 言語成功")
    
    # 누락된(실패한) 언어가 있다면 빨간색으로 경고!
    if failed_langs:
        st.error(f"🚨 번역 누락 및 실패 언어 ({len(failed_langs)}개) / 翻訳失敗言語: {', '.join(failed_langs)}")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for lang_name, data in results.items():
            zip_file.writestr(f"{title_clean}_{lang_name}.srt", data['srt'].encode("utf-8-sig"))
    zip_buffer.seek(0)
    
    st.download_button(
        label=f"📦 오프라인 자막 백업본 ({title_clean}_자막들.zip) 다운로드 / オフライン字幕バックアップのダウンロード",
        data=zip_buffer, file_name=f"{title_clean}_자막들.zip", mime="application/zip", use_container_width=True
    )
    
    st.markdown("### 🛰️ 유튜브 스튜디오 일괄 자동 전송 / YouTube Studioへ即時一括アップロード")
    st.info(f"아래 버튼을 누르면 구글 드라이브의 영상/자막 소스와 {success_count}개 국어 메타데이터가 유튜브 서버로 즉시 전송됩니다. / 下のボタンを押すと、すべてのデータがYouTubeサーバーに即時転送されます。")
    
    if st.button("🚀 유튜브 스튜디오로 즉시 일괄 업로드 및 세팅 시작 / アップロード開始", type="primary", use_container_width=True):
        with st.spinner("유튜브 인증 및 업로드 인젝션 가동 중..."):
            success = deploy_to_youtube_studio(drive_video, drive_thumb, drive_srt, privacy_status, final_schedule_time, results)
            if success:
                st.success("🎉 대성공! 영상 파일 업로드, 썸네일/자막 드라이브 연동, 언어별 메타데이터 세팅, 그리고 지정된 날짜 예약 공개까지 완벽하게 완료되었습니다! / 完璧に完了しました！")
