import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv()
client = Client()

dataset_name = "ESG_Master_Pipeline_Evaluation"

if client.has_dataset(dataset_name=dataset_name):
    client.delete_dataset(dataset_name=dataset_name)

# 1. 빈 데이터셋 생성
dataset = client.create_dataset(
    dataset_name=dataset_name,
    description="ESG 에이전트의 Scope 1, 2, 3 산출 정확도를 평가하기 위한 데이터셋"
)

# 2. 테스트 케이스 (문제와 정답지) 정의
examples = [
    {
        "inputs": {"question": "우리 회사 자체 공장 보일러를 가동하기 위해 이번 달에 LNG 5,000m3를 사용했어. 이에 대한 탄소 배출량을 계산해 줘."},
        "outputs": {
            "reference": "10,147.5 kg CO2e 이며, 이는 Scope 1 직접 배출에 해당합니다."
        }
    },
    {
        "inputs": {"question": "우리 본사 사옥에서 지난달 한국전력으로부터 전기 15,000kWh를 구매해서 사용했어. 이 전력 사용에 대한 탄소 배출량은 얼마야?"},
        "outputs": {
            "reference": "6,697.5 kg CO2e 이며, 이는 Scope 2 간접 배출에 해당합니다."
        }
    },
    {
        "inputs": {"question": "우리 회사 영업팀 직원 3명이 이번에 런던으로 비행기를 타고 왕복 출장(총 18,000km)을 다녀왔고, 현지에서 호텔에 4일간 숙박했어. 출장 탄소 배출량을 계산해 줘."},
        "outputs": {
            "reference": "항공편은 약 14,719 kg CO2e, 숙박은 약 124.8 kg CO2e 이며, 합산된 결과가 도출되어야 합니다. 또한 Scope 3 간접 배출로 분류해야 합니다."
        }
    }
]

# 3. 데이터셋에 업로드
for example in examples:
    client.create_example(
        inputs=example["inputs"],
        outputs=example["outputs"],
        dataset_id=dataset.id,
    )

print(f"{dataset_name} 데이터셋 업로드 완료")