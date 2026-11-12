import streamlit as st
import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Literal
from openai import OpenAI
import os
import json
import re
from dotenv import load_dotenv
from tavily import TavilyClient

from financial_engine import FinancialAssumptions, FinancialSimulator

def safe_parse_json(content: str):
    """安全解析 JSON，无视大模型的废话"""
    content = content.strip()
    if "```" in content:
        match = re.search(r'```(?:json)?(.*?)```', content, re.DOTALL | re.IGNORECASE)
        if match: content = match.group(1).strip()
            
    start_dict = content.find('{')
    start_list = content.find('[')
    start_idx = min(start_dict, start_list) if start_dict != -1 and start_list != -1 else max(start_dict, start_list)
        
    if start_idx != -1:
        end_char = '}' if content[start_idx] == '{' else ']'
        end_idx = content.rfind(end_char)
        if end_idx != -1 and end_idx > start_idx:
            clean_json = content[start_idx:end_idx+1]
            try: return json.loads(clean_json)
            except: pass 
    return json.loads(content)

# ==========================================
# 0. 环境初始化
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com/v1")
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

search_tool = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "检索当地政策、竞品定价或市场规模。",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
    }
}]

# ==========================================
# 1. 结构化数据模型
# ==========================================
class AssumptionItem(BaseModel):
    assumption_id: str
    content: str = Field(description="假设内容，如'用户愿意每月付500元'")
    source_type: str = Field(default="模型推理初步假设")
    verification_status: str = Field(default="尚未核实")
    evidence_required: str = Field(description="用大白话写需要怎么去验证，比如'去街上问10个人'")

class EvidenceItem(BaseModel):
    key_metric: str; value: str; source_name: str; evidence_status: str

class FinanceExtraction(BaseModel):
    initial_capital: float = Field(ge=0)
    customer_acquisition_cost: float = Field(ge=0)
    avg_revenue_per_user: float = Field(ge=0)
    variable_cost_per_unit: float = Field(ge=0)
    fixed_cost_monthly: float = Field(ge=0)
    churn_rate_monthly: float = Field(ge=0, le=1) 
    days_inventory: int = Field(ge=0)
    days_sales_outstanding: int = Field(ge=0)
    days_payable: int = Field(ge=0)

class ValidationTask(BaseModel):
    timeframe: str; task: str; pass_condition: str

class ExecutiveVerdict(BaseModel):
    verdict: str = Field(description="必须指出 GO / CONDITIONAL GO / NO-GO，即使全凭假设也要给出一个方向！")
    feasibility_score: int = Field(description="0-100分，项目综合可行性打分")
    success_rate_score: int = Field(description="0-100分，预计存活成功率")
    justification: str = Field(description="用通俗的大白话解释为什么给这个结论和分数")

class FinalConsultingReport(BaseModel):
    executive_verdict: ExecutiveVerdict
    financial_interpretation: str = Field(description="用大白话解释财务底线，解释哪些指标会要了公司的命")
    expert_perspectives: dict
    competitive_game: dict
    failure_timeline: list
    validation_plan: List[ValidationTask]

# ==========================================
# 2. 页面架构
# ==========================================
st.set_page_config(page_title="AI 商业合伙人 (创业实战版)", layout="wide")
st.title("📊 AI 商业合伙人：项目推演与落地沙盘")

tab_simulate, tab_chat = st.tabs(["🚀 Phase 1: 项目可行性推演", "💬 Phase 2: 沙盘聊天室 (自由提问)"])

with st.sidebar:
    st.header("📝 基础项目参数")
    biz_idea = st.text_area("1. 商业灵感/产品", height=150)
    location = st.text_input("2. 目标地点/市场")
    target_audience = st.text_input("3. 核心客群")
    core_advantage = st.text_area("4. 核心护城河", height=100)
    sales_channels = st.text_input("5. 预期销售渠道")
    max_budget = st.number_input("6. 可用启动资金 (元)", value=500000, step=10000)
    st.markdown("---")
    competitor = st.text_input("7. 最强假想敌")
    generate_btn = st.button("🚀 启动沙盘推演", type="primary")

# ==========================================
# 3. Phase 1: 沙盘极限推演
# ==========================================
with tab_simulate:
    if generate_btn and biz_idea:
        secure_context = f"项目:{biz_idea}|市场:{location}|客群:{target_audience}|资金:{max_budget}|假想敌:{competitor}"
        
        try:
            with st.spinner("正在盘点你的点子并检索市场信息..."):
                first_response = client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=[{"role": "system", "content": f"检索行业大盘数据。调用 web_search。\n{secure_context}"}],
                    tools=search_tool, tool_choice="auto", temperature=0.3
                )
                
                search_result = ""
                if first_response.choices[0].message.tool_calls:
                    for tool_call in first_response.choices[0].message.tool_calls:
                        if tool_call.function.name == "web_search":
                            query = json.loads(tool_call.function.arguments)["query"]
                            st.toast(f"🔍 正在检索：{query}") 
                            search_result = tavily_client.search(query=query, search_depth="basic", max_results=5)
                            
                with st.spinner("正在把你的想法拆解为商业假设..."):
                    cleaner_prompt = f"""
                    极度重要：基于用户输入 {secure_context} 和 搜索结果 {search_result}。
                    你必须提取事实填入 evidence_ledger。
                    如果没有事实，**绝对不能留空**，必须把用户的产品、客群、护城河拆解成至少 4 条商业假设，填入 assumption_registry！
                    必须返回严格的 JSON：{{"evidence_ledger": {{"items": [...]}}, "assumption_registry": {{"items": [...]}}}}
                    """
                    ledger_response = client.chat.completions.create(
                        model="deepseek-flash",
                        messages=[{"role": "user", "content": cleaner_prompt}],
                        response_format={"type": "json_object"}, temperature=0.2
                    )
                    
                    dual_data = safe_parse_json(ledger_response.choices[0].message.content)
                    ev_raw = dual_data.get("evidence_ledger", {})
                    as_raw = dual_data.get("assumption_registry", {})
                    ev_list = ev_raw.get("items", []) if isinstance(ev_raw, dict) else (ev_raw if isinstance(ev_raw, list) else [])
                    as_list = as_raw.get("items", []) if isinstance(as_raw, dict) else (as_raw if isinstance(as_raw, list) else [])
                    evidence_ledger_json = json.dumps({"items": ev_list}, ensure_ascii=False)
                    assumption_registry_json = json.dumps({"items": as_list}, ensure_ascii=False)
                    
                    col_reg1, col_reg2 = st.columns(2)
                    with col_reg1:
                        st.markdown("### 📋 找得到的确凿事实 (硬数据)")
                        df_ev = pd.DataFrame(ev_list)
                        if not df_ev.empty:
                            cols_ev = [c for c in ["key_metric", "value", "source_name"] if c in df_ev.columns]
                            st.dataframe(df_ev[cols_ev] if cols_ev else df_ev, use_container_width=True)
                        else: st.info("暂无外部公开硬数据支撑。")
                            
                    with col_reg2:
                        st.markdown("### ⚠️ 必须去验证的核心假设 (你的猜想)")
                        df_as = pd.DataFrame(as_list)
                        if not df_as.empty:
                            cols_as = [c for c in ["content", "evidence_required"] if c in df_as.columns]
                            st.dataframe(df_as[cols_as] if cols_as else df_as, use_container_width=True)
                        else: st.info("提取假设失败。")

            with st.spinner("正在后台测算你能赚多少、亏多少 (Python 引擎)..."):
                param_prompt = f"""
                基于 {evidence_ledger_json} 和 {assumption_registry_json}，提取以下9个变量的纯数字（单位为新币或人民币均可，统一个单位即可）。
                缺失部分请按照行业经验**大胆推断，绝不允许报错**！必须输出纯数字 JSON 格式的 FinanceExtraction。
                {{
                    "initial_capital": 500000, "customer_acquisition_cost": 100, "avg_revenue_per_user": 200, 
                    "variable_cost_per_unit": 50, "fixed_cost_monthly": 15000, "churn_rate_monthly": 0.1, 
                    "days_inventory": 30, "days_sales_outstanding": 0, "days_payable": 15
                }}
                """
                param_completion = client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=[{"role": "user", "content": param_prompt}],
                    response_format={"type": "json_object"}, temperature=0.3
                )
                assumptions = FinancialAssumptions.model_validate(safe_parse_json(param_completion.choices[0].message.content))
                stress_test_results = FinancialSimulator(assumptions).generate_stress_scenarios()
                
            with st.spinner("主理人正在撰写最终项目评估与行动指南..."):
                final_prompt = f"""
                你是用户最信赖的创业合伙人。请基于 Python 结果：{json.dumps(stress_test_results)} 和前置假设撰写报告。
                
                指令：
                1. 不要像冷冰冰的机器，要说人话。给出 GO 或 CONDITIONAL GO 的结论，并打分。
                2. 告诉用户接下来 1-3 个月具体该干嘛（小规模试错验证）。
                
                必须平铺输出包含 6 个字段的 JSON：
                {{
                    "executive_verdict": {{"verdict": "(CONDITIONAL GO) 值得一试，但需控制初期投入", "feasibility_score": 75, "success_rate_score": 60, "justification": "大白话理由..."}},
                    "financial_interpretation": "大白话解释财务风险，别拽词...",
                    "expert_perspectives": {{"sales_resistance": "...", "churn_risk": "...", "sunk_cost": "...", "decision_maker": "...", "channel_lifeline": "..."}},
                    "competitive_game": {{"competitor_capability": "...", "strategic_motivation": "...", "competitor_action": "...", "our_response": "..."}},
                    "failure_timeline": [{{"timeframe": "第1-3个月", "potential_risk": "卖不出去", "trigger_condition": "引流太贵", "causal_link": "没钱了"}}],
                    "validation_plan": [{{"timeframe": "第1-2周", "task": "小红书发帖测品", "pass_condition": "拿到10个真实询单"}}]
                }}
                """
                final_completion = client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=[{"role": "user", "content": final_prompt}],
                    response_format={"type": "json_object"}, temperature=0.5
                )
                report = FinalConsultingReport.model_validate(safe_parse_json(final_completion.choices[0].message.content))

            # ================= ⑧ 终极报告渲染 =================
            st.markdown("---")
            col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
            with col_s1:
                st.header(f"🎯 终局结论：{report.executive_verdict.verdict}")
                st.info(f"💡 **合伙人大白话解析**：{report.executive_verdict.justification}")
            with col_s2:
                st.metric("综合可行性得分", f"{report.executive_verdict.feasibility_score} / 100")
            with col_s3:
                st.metric("预估商业成功率", f"{report.executive_verdict.success_rate_score} %")
            
            st.markdown("### 👣 接下来该干嘛？(最小成本试错计划)")
            plan_df = pd.DataFrame([t.model_dump() for t in report.validation_plan])
            if not plan_df.empty:
                plan_df.columns = ["时间阶段", "具体你要去做的任务", "达到什么标准才能花下一笔钱"]
                st.dataframe(plan_df, hide_index=True, use_container_width=True)

            st.markdown("---")
            st.markdown("### 🧮 能赚多少、亏多少？(财务算账大白话版)")
            bm, dm, sm = stress_test_results["base_scenario"], stress_test_results["downside_scenario"], stress_test_results["severe_stress_scenario"]
            metrics_df = pd.DataFrame({
                "财务指标 (大白话翻译)": ["每卖一单能净赚多少钱 (刨去成本)", "每个月要卖多少单才不亏本", "一个老客户这辈子能让你赚多少 (LTV)", "花1块钱营销能赚回几块钱", "拉一个新客需要几个月才能回本", "固定每个月要烧掉多少钱", "💰 现有的钱还能活几个月 (现金跑道)"],
                "正常情况 (Base)": [bm["contribution_margin"], bm["break_even_volume"], bm["ltv"], bm["ltv_cac_ratio"], bm["payback_months"], bm["monthly_burn_rate"], bm["runway_months"]],
                "生意不好时 (Downside)": [dm["contribution_margin"], dm["break_even_volume"], dm["ltv"], dm["ltv_cac_ratio"], dm["payback_months"], dm["monthly_burn_rate"], dm["runway_months"]],
                "极度恶劣时 (Severe)": [sm["contribution_margin"], sm["break_even_volume"], sm["ltv"], sm["ltv_cac_ratio"], sm["payback_months"], sm["monthly_burn_rate"], sm["runway_months"]]
            })
            st.dataframe(metrics_df, hide_index=True, use_container_width=True)
            st.error(f"**财务底线提醒**：\n{report.financial_interpretation}")
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("### ⚔️ 行业巨头会怎么搞你？")
                st.warning(f"**对手可能会**：\n{report.competitive_game.get('competitor_action', '')}")
                st.success(f"**我们的反击**：\n{report.competitive_game.get('our_response', '')}")
            with col_b:
                st.markdown("### ☠️ 如果失败，可能是怎么死掉的？")
                fail_df = pd.DataFrame(report.failure_timeline)
                if not fail_df.empty:
                    fail_df.columns = ["危险期", "最大隐患", "触发点(比如成本超标)", "恶性循环结果"]
                    st.dataframe(fail_df, hide_index=True, use_container_width=True)

            with st.expander("🧠 查看 5 大内行防坑视角", expanded=False):
                st.markdown(f"- **[客户为什么不买单]**: {report.expert_perspectives.get('sales_resistance', '')}")
                st.markdown(f"- **[老客为什么会跑路]**: {report.expert_perspectives.get('churn_risk', '')}")
                st.markdown(f"- **[供应链与渠道大坑]**: {report.expert_perspectives.get('channel_lifeline', '')}")
                
            st.session_state['report_context'] = secure_context
                
        except Exception as e:
            st.error(f"沙盘生成出错，请重试或检查代码格式: {str(e)}")
            st.exception(e)

# ==========================================
# 4. Phase 2: 沙盘聊天室 (自由对话)
# ==========================================
with tab_chat:
    st.markdown("### 💬 有什么顾虑或新想法？直接问我！")
    st.info("比如你可以问：'如果我把礼盒包装成本降一半，专做本地复购，你觉得可行吗？'")
    
    # === 补回丢失的这一段：1. 初始化抽屉，2. 把之前的聊天记录打印出来 ===
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("输入你的新商业假设或提问..."):
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant"):
            base_context = st.session_state.get('report_context', '暂无前置项目，请先在 Phase 1 运行沙盘。')
            qa_prompt = f"基于项目：{base_context}。用户提问：{prompt}。请用大白话，像一个精明且务实的生意合伙人一样直接回答，给出商业建议。"
            
            # 加上 try...except 捕获报错，防止死机
            try:
                with st.spinner("合伙人正在思考..."):
                    qa_response = client.chat.completions.create(
                        model="deepseek-chat", # 建议这里改成官方标准的 deepseek-chat 模型名
                        messages=[{"role": "user", "content": qa_prompt}],
                        temperature=0.6
                    ).choices[0].message.content
                st.markdown(qa_response)
                st.session_state.messages.append({"role": "assistant", "content": qa_response})
            except Exception as e:
                error_msg = f"哎呀，我的网络好像断了或者出错了，请再问一次！(详细报错: {str(e)})"
                st.error(error_msg)
                # 即使报错，也要把报错信息存进聊天记录，防止输入框错位
                st.session_state.messages.append({"role": "assistant", "content": error_msg})