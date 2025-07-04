import requests
# import pandas as pd # Pandas는 이제 직접적으로 사용되지 않으므로 제거합니다.
from bs4 import BeautifulSoup
import time # API 요청 간 지연 시간을 위해
import datetime
import random # 로또 번호 추첨을 위해
import json # JSON 파일 저장 및 로드를 위해
import os # 파일 존재 여부 확인을 위해

# 로또 이력 데이터를 저장할 파일 경로
HISTORY_FILE = "lotto_combinations.json"


def get_max_draw_number():
    """
    동행복권 웹사이트에서 현재 가장 최신 로또 회차 번호를 가져옵니다.
    최신 회차를 가져오는 데 실패하면 기본값(예: 현재 시점의 대략적인 최신 회차)을 반환합니다.
    """
    url = "https://www.dhlottery.co.kr/common.do?method=main"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status() # HTTP 오류가 발생하면 예외 발생
        soup = BeautifulSoup(response.text, "lxml")
        max_numb_tag = soup.find(name="strong", attrs={"id": "lottoDrwNo"})
        if max_numb_tag:
            return int(max_numb_tag.text)
        else:
            print("웹사이트에서 최신 회차 번호를 찾을 수 없습니다. 임시 기본값 사용 (현재: 1124회차).")
            return 1124 # 찾지 못했을 경우 임의의 최신 회차로 설정
    except requests.exceptions.RequestException as e:
        print(f"최신 회차를 가져오는 중 오류 발생: {e}")
        return 1124 # 오류 발생 시 임의의 최신 회차로 설정

def get_lotto_numbers_data(draw_no):
    """
    특정 로또 회차의 당첨 번호 데이터를 동행복권 API를 통해 가져와 딕셔너리로 반환합니다.
    주요 당첨 번호 6개는 정렬된 튜플 형태로도 포함됩니다.
    """
    api_url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={draw_no}"
    try:
        res = requests.get(api_url, timeout=5)
        res.raise_for_status()
        data = res.json()

        if data.get('returnValue') == 'success':
            main_numbers = sorted([
                data.get('drwtNo1'), data.get('drwtNo2'),
                data.get('drwtNo3'), data.get('drwtNo4'),
                data.get('drwtNo5'), data.get('drwtNo6')
            ])
            # None 값을 필터링하여 유효한 숫자만 포함 (간혹 API 응답에 null이 있을 경우 대비)
            main_numbers = tuple(num for num in main_numbers if num is not None)

            # 모든 숫자가 유효하게 추출되었는지 확인 (6개)
            if len(main_numbers) != 6:
                print(f"경고: {draw_no}회차에서 6개의 유효한 당첨 번호를 추출할 수 없습니다. 데이터 건너뛰기.")
                return None

            return {
                'draw_no': draw_no,
                'draw_date': data.get('drwNoDate'),
                'lotto_num1': data.get('drwtNo1'),
                'lotto_num2': data.get('drwtNo2'),
                'lotto_num3': data.get('drwtNo3'),
                'lotto_num4': data.get('drwtNo4'),
                'lotto_num5': data.get('drwtNo5'),
                'lotto_num6': data.get('drwtNo6'),
                'bonus_num': data.get('bnusNo'),
                'winning_combination': main_numbers # 6개 당첨 번호 조합 (정렬된 튜플)
            }
        else:
            return None # API 호출은 성공했으나 데이터가 없거나 실패한 경우
    except requests.exceptions.RequestException as e:
        return None # API 요청 자체에서 오류가 발생한 경우

def load_and_update_past_combinations(num_years=2):
    """
    로또 이력 파일에서 과거 당첨 조합을 로드하고, 최신 데이터로 업데이트한 후 파일에 저장합니다.
    """
    past_winning_combinations_set = set()
    last_fetched_draw_no_from_file = 0

    # 1. 기존 이력 파일 로드
    if os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
                last_fetched_draw_no_from_file = history_data.get('last_fetched_draw_no', 0)
                
                # 저장된 조합 (list of lists)을 set of tuples로 변환
                for combo_list in history_data.get('combinations', []):
                    # 모든 요소가 숫자인지, 6개인지 확인하여 유효한 조합만 추가
                    if len(combo_list) == 6 and all(isinstance(x, int) for x in combo_list):
                        past_winning_combinations_set.add(tuple(combo_list))
                
            print(f"'{HISTORY_FILE}' 파일에서 {len(past_winning_combinations_set)}개의 이전 조합 로드 완료. 마지막 업데이트 회차: {last_fetched_draw_no_from_file}회차")
        except json.JSONDecodeError as e:
            print(f"경고: '{HISTORY_FILE}' 파일 로드 중 오류 발생 ({e}). 파일을 다시 생성합니다.")
            last_fetched_draw_no_from_file = 0 # 오류 발생 시 처음부터 다시 가져오도록 설정
            past_winning_combinations_set = set()
    else:
        print(f"'{HISTORY_FILE}' 파일이 없거나 비어있습니다. 새로운 파일을 생성합니다.")

    # 2. 최신 로또 회차 번호 가져오기
    current_max_draw = get_max_draw_number()
    if current_max_draw == 1124: # 기본값이 반환된 경우 (오류)
        print("최신 회차 정보를 가져오는 데 실패하여 데이터 업데이트가 불안정할 수 있습니다.")

    # 3. 데이터 가져올 시작 회차 결정
    start_fetch_from = last_fetched_draw_no_from_file + 1
    
    # 만약 파일이 비었거나 초기 로드 시 오류가 있었다면, 지난 N년간의 데이터를 다시 가져옵니다.
    if last_fetched_draw_no_from_file == 0:
        # 대략적인 num_years치 회차 수 계산 (1년 52주 * num_years)에 여유분을 더합니다.
        num_draws_to_fetch_initial = num_years * 52 * 1.1
        start_fetch_from = max(1, current_max_draw - int(num_draws_to_fetch_initial))
        print(f"이력 파일이 없거나 오류로 인해 지난 {num_years}년간의 전체 이력을 ({start_fetch_from}회차부터 {current_max_draw}회차까지) 가져옵니다.")
    else:
        print(f"최신 회차({current_max_draw})까지 새로운 데이터만 가져옵니다 (시작 회차: {start_fetch_from}).")

    newly_fetched_count = 0
    # 4. 새로운(또는 초기) 데이터 가져오기 및 Set 업데이트
    # 현재 최신 회차부터 start_fetch_from까지 역순으로 가져오는 것이 효율적입니다.
    # 그래야 최신 데이터부터 빠르게 확인하고 필요시 중단할 수 있습니다.
    fetch_range = range(current_max_draw, start_fetch_from - 1, -1) if start_fetch_from <= current_max_draw else []

    if not fetch_range and last_fetched_draw_no_from_file > 0:
        print("가져올 새로운 회차가 없습니다. 최신 상태입니다.")
    elif fetch_range:
        print(f"새로운/업데이트할 회차 수: {len(fetch_range)}개")
        for draw_no in fetch_range:
            if draw_no <= last_fetched_draw_no_from_file:
                # 이미 파일에 있는 회차는 건너뜁니다.
                # (역순으로 가져오기 때문에 이 조건은 일반적으로 시작점에 도달하면 만족합니다.)
                break 

            lotto_data = get_lotto_numbers_data(draw_no)
            if lotto_data and lotto_data['winning_combination']:
                # winning_combination은 이미 정렬된 튜플
                if lotto_data['winning_combination'] not in past_winning_combinations_set:
                    past_winning_combinations_set.add(lotto_data['winning_combination'])
                    newly_fetched_count += 1
            
            time.sleep(0.05) # 서버 부하 방지

            if newly_fetched_count > 0 and newly_fetched_count % 20 == 0:
                print(f"  {newly_fetched_count}개 새로운 조합 수집 중...")

    print(f"총 {newly_fetched_count}개의 새로운 로또 조합을 추가했습니다.")
    print(f"현재까지 총 {len(past_winning_combinations_set)}개의 고유 당첨 조합 수집 완료.")

    # 5. 업데이트된 데이터를 파일에 저장
    data_to_save = {
        'last_fetched_draw_no': current_max_draw,
        'combinations': [list(combo) for combo in past_winning_combinations_set] # Set의 튜플을 리스트로 변환하여 JSON 저장
    }
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    print(f"업데이트된 로또 이력 ({len(past_winning_combinations_set)}개 조합, 마지막 회차: {current_max_draw}회차)을 '{HISTORY_FILE}' 파일에 저장 완료.")

    return past_winning_combinations_set

def generate_unique_lotto_combination(past_combinations_set):
    """
    과거 당첨 조합과 겹치지 않는 새로운 6개 로또 번호 조합을 생성합니다.
    """
    all_possible_numbers = list(range(1, 46)) # 1부터 45까지의 숫자 리스트
    max_attempts = 500000 # 무한 루프 방지를 위한 최대 시도 횟수 (조합이 많을수록 늘려야 함)
    # 로또 전체 경우의 수는 8,145,060 이므로, 10만번은 금방 소진될 수 있습니다.

    for attempt in range(max_attempts):
        # 1부터 45까지의 숫자 중 6개를 무작위로 선택하여 조합 생성
        new_combination = tuple(sorted(random.sample(all_possible_numbers, 6)))

        # 생성된 조합이 과거 당첨 조합 Set에 없는지 확인
        if new_combination not in past_combinations_set:
            return list(new_combination) # 리스트로 반환하여 사용 편의성 제공

        if (attempt + 1) % 50000 == 0:
            print(f"  {attempt + 1}번째 시도: 고유 조합 생성 중...")

    # 최대 시도 횟수 내에 고유한 조합을 찾지 못한 경우
    print(f"경고: {max_attempts}번의 시도 내에 고유한 로또 조합을 찾지 못했습니다. 이미 모든 조합이 당첨되었거나, 시도 횟수가 부족할 수 있습니다.")
    return None # 고유 조합을 찾지 못했음을 알림

if __name__ == "__main__":
    print("로또 당첨 번호 이력을 파일에서 관리하고, 새로운 (겹치지 않는) 조합을 추첨합니다...\n")

    # ====================================================================
    # 로또 조합 데이터 로드 및 업데이트 로직 시작
    # ====================================================================
    print("--- 로또 당첨 이력 데이터 로드 및 업데이트 시작 ---")
    # 지난 2년간의 당첨 조합 또는 업데이트된 데이터 로드 (파일 관리 포함)
    past_combinations = load_and_update_past_combinations(num_years=2)

    if not past_combinations:
        print("과거 당첨 조합을 가져오는 데 실패했습니다. 새로운 조합 추첨을 진행할 수 없습니다.")
    else:
        print("\n--- 새로운 로또 조합 추첨 시작 (이력 파일 데이터 기반) ---")
        print("과거 당첨 조합과 겹치지 않는 새로운 로또 조합 5개를 추첨 중...")
        generated_combinations = []
        num_sets_to_generate = 5 # 5가지 세트 생성

        for i in range(num_sets_to_generate):
            print(f"\n[{i+1}/{num_sets_to_generate}] 번째 조합 생성 중...")
            new_lotto_combination = generate_unique_lotto_combination(past_combinations)
            
            if new_lotto_combination:
                generated_combinations.append(new_lotto_combination)
                # (선택 사항) 생성된 조합이 이후 생성될 조합과도 겹치지 않도록 할 경우 아래 주석 해제
                # past_combinations.add(tuple(new_lotto_combination)) 
                print(f"  생성된 조합: {new_lotto_combination}")
            else:
                print(f"  [{i+1}/{num_sets_to_generate}] 번째 조합 생성을 실패했습니다. (자세한 내용은 위 경고 참고)")
                break # 조합 생성 실패 시 중단

        if generated_combinations:
            print("\n\n✨ 당신의 행운의 로또 조합들 (지난 2년간 당첨 조합과 겹치지 않음):")
            for idx, combo in enumerate(generated_combinations):
                print(f"  조합 {idx+1}: {combo}")
        else:
            print("\n로또 조합 추첨에 실패했습니다.")

    print("\n모든 작업 완료.")
