import requests
import json

BASE_URL = "http://127.0.0.1:8000/api/v1"

def run_workflow():
    print("🚀 [Workflow 启动] 正在执行市场调研防坑管家...")
    
    domain = "极简收纳与空间整理服务"
    print(f"\n[Step 1] 正在为赛道【{domain}】生成防坑专家矩阵...")
    
    res_1 = requests.post(f"{BASE_URL}/personas", params={"product_domain": domain})
    personas_data = res_1.json()["personas"]
    
    print("✅ 找到以下高价值目标：")
    for i, p in enumerate(personas_data):
        print(f"  {i+1}. [{p['matrix_layer']}] {p['job_title']}")
        
    selected = [personas_data[0], personas_data[1]]
    print(f"\n[Step 2] 正在为 {selected[0]['job_title']} 生成极限施压提纲...")
    
    res_2 = requests.post(f"{BASE_URL}/scripts", json=selected)
    scripts_data = res_2.json()["scripts"]
    
    target_script = scripts_data[0]
    print(f"✅ 生成完毕！针对【{target_script['expert_title']}】的首个问题：")
    print(f"   ❓ {target_script['questions'][0]['question_text']}")
    print(f"   💡 防忽悠追问: {target_script['questions'][0]['counter_tactic']}")

    print("\n[Step 3] ⚔️ 进入红蓝对抗模式 (发送【复盘】可获取教练点评)")
    
    chat_history = []
    expert_title = target_script['expert_title']
    script_context = json.dumps(target_script['questions'], ensure_ascii=False)
    
    while True:
        user_input = input("\n访谈者 (你): ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        payload = {
            "expert_title": expert_title,
            "script_context": script_context,
            "chat_history": chat_history,
            "new_message": user_input
        }
        
        res_3 = requests.post(f"{BASE_URL}/roleplay", json=payload)
        response_data = res_3.json()
        
        if response_data["response_type"] == "review":
            print(f"\n🧑‍🏫 [教练复盘]:\n{response_data['content']}")
        else:
            print(f"\n🛡️ [{expert_title}]:\n{response_data['content']}")
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": response_data['content']})

if __name__ == "__main__":
    run_workflow()