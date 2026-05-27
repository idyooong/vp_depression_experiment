import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import datetime

# [설정] 구글 시트 클라이언트
def get_gspread_client():
    creds_dict = json.loads(st.secrets["gcp_service_account"])
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

GROUPS = {
    "group_A": ["M0", "M1", "M2", "M3", "F0", "F1", "F2", "F3"],
    "group_B": ["M1", "M2", "M3", "F0", "F1", "F2", "F3", "M0"],
    "group_C": ["M2", "M3", "F0", "F1", "F2", "F3", "M0", "M1"],
    "group_D": ["M3", "F0", "F1", "F2", "F3", "M0", "M1", "M2"],
    "group_E": ["F0", "F1", "F2", "F3", "M0", "M1", "M2", "M3"],
    "group_F": ["F1", "F2", "F3", "M0", "M1", "M2", "M3", "F0"],
    "group_G": ["F2", "F3", "M0", "M1", "M2", "M3", "F0", "F1"],
    "group_H": ["F3", "M0", "M1", "M2", "M3", "F0", "F1", "F2"],
}

def main():
    st.set_page_config(page_title="HCI 실험", layout="centered")
    
    if st.query_params.get("admin") == st.secrets["ADMIN_PASS"]:
        admin_dashboard()
        return

    if 'stage' not in st.session_state:
        st.session_state.stage = 0
        st.session_state.data = {}
        st.session_state.video_order = None

    participant_view()

def participant_view():
    # 1. 상태에 따라 최상단 제목 분리 (마지막 페이지 번호가 11로 밀림)
    if st.session_state.stage < 11:
        st.title("실험 참여 페이지")
    else:
        st.title("VP-tts 실험 종료 및 제출 완료")

    # [Stage 0] 인구통계 및 참여 코드 확인
    if st.session_state.stage == 0:
        with st.form("demography"):
            st.session_state.data['name'] = st.text_input("참여자 이름/ID")
            st.session_state.data['age'] = st.number_input("나이", 18, 100)
            # access_code = st.text_input("실험 참여 코드", type="password") 
            
            if st.form_submit_button("다음 단계로"):
                # 코드 검증
                # if access_code != "HCI2026": 
                #     st.error("올바른 참여 코드가 아닙니다. 연구자에게 문의하십시오.")
                #     st.stop()
                
                # 통과 시 안내사항 페이지로 이동
                st.session_state.stage = 1
                st.rerun()

    # [Stage 1] 실험 안내사항 (새로 추가된 페이지)
    elif st.session_state.stage == 1:
        st.subheader("📢 실험 진행 안내사항")
        st.markdown(":blue[본 실험은 영상의 음성과 아바타의 모션(Influence Cues)을 평가하므로, 반드시 **이어폰을 착용하거나 스피커 볼륨을 켠 상태**로 진행해 주십시오.]")
        st.markdown(":blue[원활한 구동을 위해 가급적 **PC 환경의 Chrome 브라우저** 사용을 권장합니다.]")        
        st.write("위 안내사항을 모두 확인하셨다면 아래 버튼을 눌러 본 실험을 시작해 주십시오.")
        
        # 여기서 '실험 시작'을 눌러야만 비로소 구글 시트 통신 및 그룹 할당 진행
        if st.button("안내사항 확인 및 실험 시작"):
            with st.spinner("실험 환경을 설정 중입니다..."):
                client = get_gspread_client()
                sheet = client.open("ExperimentDB").worksheet("groups")
                data = pd.DataFrame(sheet.get_all_records())
                
                min_group = data.loc[data['count'].idxmin()]
                st.session_state.video_order = GROUPS[min_group['group_id']]
                st.session_state.data['group_id'] = min_group['group_id']
                
                # 그룹 카운트 자동 증가
                row_index = data.index[data['group_id'] == min_group['group_id']][0] + 2
                sheet.update_cell(row_index, 2, int(min_group['count']) + 1)
                
                # 첫 번째 영상 페이지(Stage 2)로 이동
                st.session_state.stage = 2
                st.rerun()

    # [Stage 2~9] 영상 및 설문 (기존 1~8에서 밀림)
    elif 2 <= st.session_state.stage <= 9:
        idx = st.session_state.stage - 2
        video_id = st.session_state.video_order[idx]
        
        # 진행도 표시 (1/8 ~ 8/8)
        st.write(f"### {idx + 1} / 8")
        st.video(f"videos/{video_id}.mp4")

        with st.form(f"survey_{idx}"):
            st.session_state.data[f"{video_id}_severity"] = st.radio("Severity", ["None", "Mild", "Moderate", "Severe"])
            st.session_state.data[f"{video_id}_influence"] = st.multiselect("Influence Cues", ["Text", "Eye&Head", "Face", "Motion"])
            st.session_state.data[f"{video_id}_feedback"] = st.text_area("피드백")
            st.session_state.data[f"{video_id}_realism"] = st.slider("Realism (1~5)", 1, 5)
            
            if st.form_submit_button("다음 영상으로"):
                st.session_state.stage += 1
                st.rerun()

    # [Stage 10] 최종 저장 프로세스 (기존 9에서 밀림)
    elif st.session_state.stage == 10:
        with st.spinner("데이터를 서버에 기록 중입니다. 잠시만 기다려주세요..."):
            client = get_gspread_client()
            sheet = client.open("ExperimentDB").worksheet("logs")
            
            # 1. 타임스탬프 추가
            st.session_state.data['timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 2. 헤더 순서 정의 (시트의 A열부터 순서대로)
            ordered_keys = ['timestamp', 'name', 'age', 'group_id']
            videos = ["M0", "M1", "M2", "M3", "F0", "F1", "F2", "F3"]
            for v in videos:
                ordered_keys.extend([f"{v}_severity", f"{v}_influence", f"{v}_feedback", f"{v}_realism"])
            
            # 3. 데이터 추출 및 전처리 (리스트형 방지)
            ordered_data = []
            for k in ordered_keys:
                val = st.session_state.data.get(k, "N/A")
                if isinstance(val, list):
                    val = ", ".join(map(str, val))
                ordered_data.append(val)

            # 시트에 전송
            sheet.append_row(ordered_data)
            
            # 4. 상태 변경 및 화면 새로고침
            st.session_state.stage = 11
            st.rerun() 

    # [Stage 11] 실험 완료 화면 (기존 10에서 밀림)
    elif st.session_state.stage == 11:
        st.balloons()
        st.success("실험이 모두 완료되었습니다. 데이터가 정상적으로 저장되었습니다.")
        st.write("참여해 주셔서 감사합니다. 창을 닫아주셔도 좋습니다.")

def admin_dashboard():
    st.write("### 관리자 페이지")
    # ... 대시보드 로직 ...

if __name__ == "__main__":
    main()